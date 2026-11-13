"""HTTP letöltés udvarias időzítéssel és újrapróbálkozással."""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class FetchError(Exception):
    """Nem sikerült letölteni az oldalt."""


class Fetcher:
    """Egyszerű, soros letöltő.

    - kérések között `delay` másodpercet vár (a robots.txt crawl-delay miatt),
    - 429/5xx esetén exponenciálisan növekvő várakozással újrapróbál,
    - opcionálisan lemezre cache-el (fejlesztéshez, `--cache`).
    """

    def __init__(
        self,
        user_agent: str,
        delay: float = 1.5,
        timeout: int = 20,
        retries: int = 3,
        cache_dir: Path | None = None,
    ) -> None:
        self.delay = max(0.0, delay)
        self.timeout = timeout
        self.retries = max(1, retries)
        self.cache_dir = cache_dir
        self._last_request = 0.0
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "hu-HU,hu;q=0.9,en;q=0.6",
                "Accept-Encoding": "gzip, deflate",
            }
        )
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]
        return Path(self.cache_dir) / f"{digest}.html"  # type: ignore[arg-type]

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request = time.monotonic()

    # ------------------------------------------------------------------
    def get(self, url: str, *, use_cache: bool = False) -> str:
        if self.cache_dir and use_cache:
            path = self._cache_path(url)
            if path.exists():
                log.debug("cache találat: %s", url)
                return path.read_text(encoding="utf-8", errors="replace")

        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            self._throttle()
            try:
                response = self.session.get(url, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = exc
                log.warning("hálózati hiba (%s/%s): %s – %s", attempt, self.retries, url, exc)
            else:
                if response.status_code == 200:
                    response.encoding = response.encoding or "utf-8"
                    text = response.text
                    if self.cache_dir:
                        self._cache_path(url).write_text(text, encoding="utf-8")
                    return text
                if response.status_code in RETRYABLE_STATUS:
                    retry_after = response.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                    log.warning(
                        "HTTP %s (%s/%s): %s – várakozás %.0fs",
                        response.status_code,
                        attempt,
                        self.retries,
                        url,
                        wait,
                    )
                    time.sleep(wait)
                    last_error = FetchError(f"HTTP {response.status_code}")
                    continue
                raise FetchError(f"HTTP {response.status_code}: {url}")

            time.sleep(2**attempt)

        raise FetchError(f"Nem sikerült letölteni: {url} ({last_error})")
