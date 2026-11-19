"""Processzor- és videokártya-benchmark adatok a PassMark oldalairól.

Egy-egy konkrét modellre kérdezünk rá (nem töltjük le a teljes listát),
mert így pontos, laptop-specifikus értéket kapunk, kevés kéréssel.

Ha a PassMark nem elérhető (Cloudflare, hálózat), a program egyszerűen
kihagyja a pontszámot – a találat ettől még kimegy.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import quote_plus

from .fetch import FetchError, Fetcher
from .specs import norm

log = logging.getLogger(__name__)

CPU_PAGE = "https://www.cpubenchmark.net/cpu.php?cpu={}"
GPU_PAGE = "https://www.videocardbenchmark.net/gpu.php?gpu={}"

_CPU_SCORE_RE = re.compile(r"Average CPU Mark:\s*([\d,]+)")
_GPU_SCORE_RE = re.compile(r"Average G3D Mark:\s*([\d,]+)")
_H1_RE = re.compile(r"<h1>([^<]*)</h1>")
_TITLE_RE = re.compile(r"<title>([^<]*)</title>", re.S)


@dataclass(frozen=True)
class BenchResult:
    """Egy benchmark találat."""

    name: str
    score: int
    url: str
    kind: str  # "cpu" | "gpu"


def cpu_queries(cpu: str) -> list[str]:
    """A hirdetésből kinyert rövid CPU-névből PassMark-keresőnevek."""
    n = norm(cpu)
    if n.startswith(("i3", "i5", "i7", "i9")):
        return [f"Intel Core {cpu}"]
    if n.startswith("ultra"):
        rest = cpu.split(" ", 1)[1] if " " in cpu else cpu
        return [f"Intel Core Ultra {rest}"]
    if n.startswith("ryzen"):
        rest = cpu.split(" ", 1)[1] if " " in cpu else cpu
        rest = re.sub(r"\bai\b", "AI", rest, flags=re.I)
        rest = re.sub(r"\bhx\b", "HX", rest, flags=re.I)
        return [f"AMD Ryzen {rest}", f"AMD {cpu}"]
    if n.startswith(("xeon", "pentium", "celeron")):
        return [f"Intel {cpu}"]
    return [cpu]


def gpu_queries(gpu: str) -> list[str]:
    """'rtx 4060' -> ['GeForce RTX 4060 Laptop GPU', 'GeForce RTX 4060']."""
    up = gpu.upper()
    if up.startswith(("RTX", "GTX")):
        return [f"GeForce {up} Laptop GPU", f"GeForce {up}"]
    if up.startswith("RX"):
        return [f"Radeon {up}", f"Radeon {up} Laptop GPU"]
    if up.startswith("ARC"):
        rest = up[4:] if up.startswith("ARC ") else up[3:]
        return [f"Arc {rest} Laptop GPU", f"Arc {rest}"]
    if up.startswith("IRIS"):
        return ["Intel Iris Xe Graphics"]
    if up.startswith("UHD"):
        return ["Intel UHD Graphics"]
    if up.startswith("RADEON"):
        return [f"Radeon {up[7:]}" if up.startswith("RADEON ") else up]
    if up.startswith("QUADRO") or up.startswith("RTX A"):
        return [f"NVIDIA {up} Laptop GPU", up]
    return [up]


class Benchmarks:
    """PassMark lekérdezések, futáson belüli cache-el."""

    def __init__(self, fetcher: Fetcher, max_lookups: int = 24) -> None:
        self.fetcher = fetcher
        self.max_lookups = max_lookups
        self._cache: dict[str, BenchResult | None] = {}
        self._requests = 0

    # ------------------------------------------------------------------
    def _get(self, url: str) -> str | None:
        if self._requests >= self.max_lookups:
            return None
        self._requests += 1
        try:
            return self.fetcher.get(url, use_cache=True)
        except FetchError as exc:
            log.debug("PassMark kihagyva (%s): %s", url, exc)
            return None

    def _lookup(self, url: str, score_re: re.Pattern[str], kind: str) -> BenchResult | None:
        if url in self._cache:
            return self._cache[url]

        html = self._get(url)
        result: BenchResult | None = None
        if html:
            match = score_re.search(html)
            if match:
                name_match = _H1_RE.search(html) or _TITLE_RE.search(html)
                name = unescape(name_match.group(1)).strip() if name_match else ""
                result = BenchResult(
                    name=name,
                    score=int(match.group(1).replace(",", "")),
                    url=url,
                    kind=kind,
                )
        self._cache[url] = result
        return result

    # ------------------------------------------------------------------
    def cpu(self, cpu: str | None) -> BenchResult | None:
        if not cpu:
            return None
        for query in cpu_queries(cpu):
            result = self._lookup(CPU_PAGE.format(quote_plus(query)), _CPU_SCORE_RE, "cpu")
            if result:
                return result
        return None

    def gpu(self, gpu: str | None) -> BenchResult | None:
        if not gpu:
            return None
        for query in gpu_queries(gpu):
            result = self._lookup(GPU_PAGE.format(quote_plus(query)), _GPU_SCORE_RE, "gpu")
            if result:
                return result
        return None
