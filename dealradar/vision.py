"""Billentyűzet-kiosztás felismerése a hirdetés fotóiból.

Opcionális réteg: csak akkor fut, ha van API-kulcs. A válaszokat a
`state/vision_cache.json` tárolja, így ugyanazt a fotót nem elemezzük újra.

Támogatott providerek:
  - openai    (OpenAI és minden OpenAI-kompatibilis végpont, pl. OpenRouter)
  - anthropic (Claude)

A prompt szándékosan szigorú: ha a fotón nem látszik a billentyűzet,
"unclear" a válasz, és a hirdetés megtartja a "nem derül ki" jelzést.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from .config import VisionConfig

log = logging.getLogger(__name__)

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_IMAGE_BYTES = 6_000_000

PROMPT = (
    "You are inspecting photos of a used laptop to determine its keyboard layout.\n"
    "A Hungarian (HU) keyboard has these letters printed on the keycaps: "
    "á é í ó ö ő ú ü ű. The most reliable marker is a dedicated key with 'í' "
    "(long i), plus keys with 'ő' and 'ű'. A US or UK keyboard has none of these.\n"
    "Some laptops have Hungarian sticker overlays applied over a foreign keyboard; "
    "if you see a sticker overlay, say so in the evidence.\n"
    "Judge only the keyboard legends. Ignore the Windows language and the seller text.\n"
    "If the keyboard is not visible, or the photo is too blurry to read the legends, "
    'answer "unclear".\n'
    "Answer with JSON only, no markdown, no code fences:\n"
    '{"layout":"hu|foreign|unclear","confidence":0.0,"evidence":"one short sentence"}'
)


@dataclass(frozen=True)
class VisionResult:
    layout: str  # "hu" | "foreign" | "unclear"
    confidence: float
    evidence: str = ""

    def to_dict(self) -> dict:
        return {"layout": self.layout, "confidence": self.confidence, "evidence": self.evidence}

    @classmethod
    def from_dict(cls, data: dict) -> "VisionResult":
        try:
            confidence = float(data.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        return cls(
            layout=str(data.get("layout") or "unclear").strip().lower(),
            confidence=max(0.0, min(1.0, confidence)),
            evidence=str(data.get("evidence") or "").strip()[:300],
        )


def parse_response(text: str) -> VisionResult | None:
    """A modell válaszából kinyeri a JSON-t, toleránsan."""
    if not text:
        return None
    match = re.search(r"\{.*?\}", text, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    result = VisionResult.from_dict(data)
    if result.layout not in {"hu", "foreign", "unclear"}:
        return None
    return result


# --------------------------------------------------------------------------
#  API kliens
# --------------------------------------------------------------------------


class VisionClient:
    """Egy vékony kliens az OpenAI / Anthropic vision végpontokhoz."""

    def __init__(self, config: VisionConfig, session: requests.Session | None = None) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.api_key = os.environ.get(config.api_key_env) or None

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def check_model(self) -> tuple[bool, str]:
        """Ellenőrzi, hogy a beállított modell elérhető-e ezzel a kulccsal."""
        if not self.api_key:
            return False, "nincs API-kulcs"

        if self.config.provider == "gemini":
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self.config.model}?key={self.api_key}"
            )
            headers: dict = {}
        elif self.config.provider == "anthropic":
            url = f"https://api.anthropic.com/v1/models/{self.config.model}"
            headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        else:
            url = f"{self.config.base_url.rstrip('/')}/models/{self.config.model}"
            headers = {"Authorization": f"Bearer {self.api_key}"}

        try:
            response = self.session.get(url, headers=headers, timeout=20)
        except requests.RequestException as exc:
            return False, f"hálózati hiba: {exc}"

        if response.status_code == 200:
            return True, f"{self.config.model} elérhető"
        if response.status_code in (401, 403):
            return False, f"a kulcsot elutasította a szolgáltató (HTTP {response.status_code})"
        if response.status_code == 404:
            return False, f"a(z) {self.config.model} modell nem található (HTTP 404)"
        return False, f"HTTP {response.status_code}: {response.text[:120]}"

    def analyze(self, image_urls: list[str]) -> VisionResult | None:
        urls = [u for u in image_urls if u][: self.config.max_images]
        if not urls or not self.api_key:
            return None
        if self.config.provider == "anthropic":
            return self._anthropic(urls)
        if self.config.provider == "gemini":
            return self._gemini(urls)
        return self._openai(urls)

    # ------------------------------------------------------------------
    def _openai(self, urls: list[str]) -> VisionResult | None:
        content: list[dict] = [{"type": "text", "text": PROMPT}]
        content += [{"type": "image_url", "image_url": {"url": url}} for url in urls]
        payload = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 300,
            "temperature": 0,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        endpoint = self.config.base_url.rstrip("/") + "/chat/completions"
        return self._post(
            endpoint,
            payload,
            headers,
            lambda data: data["choices"][0]["message"]["content"],
        )

    def _anthropic(self, urls: list[str]) -> VisionResult | None:
        content: list[dict] = [
            {"type": "image", "source": {"type": "url", "url": url}} for url in urls
        ]
        content.append({"type": "text", "text": PROMPT})
        payload = {
            "model": self.config.model,
            "max_tokens": 300,
            "messages": [{"role": "user", "content": content}],
        }
        headers = {"x-api-key": self.api_key or "", "anthropic-version": "2023-06-01"}
        return self._post(
            "https://api.anthropic.com/v1/messages",
            payload,
            headers,
            lambda data: data["content"][0]["text"],
        )

    def _gemini(self, urls: list[str]) -> VisionResult | None:
        """Gemini natív API: a képeket base64-ként küldjük (inline_data)."""
        parts: list[dict] = [{"text": PROMPT}]
        for url in urls:
            content, mime = self._download(url)
            if not content:
                continue
            parts.append(
                {
                    "inline_data": {
                        "mime_type": mime,
                        "data": base64.b64encode(content).decode("ascii"),
                    }
                }
            )
        if len(parts) == 1:
            log.warning("Gemini: egyik kép sem tölthető le")
            return None

        endpoint = GEMINI_ENDPOINT.format(model=self.config.model) + f"?key={self.api_key}"
        payload = {"contents": [{"parts": parts}]}
        return self._post(
            endpoint,
            payload,
            {},
            lambda data: data["candidates"][0]["content"]["parts"][0]["text"],
        )

    def _download(self, url: str) -> tuple[bytes | None, str]:
        try:
            response = self.session.get(
                url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (apro-deal-radar)"}
            )
        except requests.RequestException as exc:
            log.debug("Kép letöltési hiba (%s): %s", url, exc)
            return None, ""
        if response.status_code != 200 or not response.content:
            return None, ""
        if len(response.content) > MAX_IMAGE_BYTES:
            log.debug("Kép túl nagy, kihagyva: %s", url)
            return None, ""
        mime = (response.headers.get("Content-Type") or "").split(";")[0].strip()
        if not mime.startswith("image/"):
            mime = "image/jpeg"
        return response.content, mime

    def _post(self, url: str, payload: dict, headers: dict, extractor) -> VisionResult | None:
        for attempt in range(1, 3):
            try:
                response = self.session.post(url, json=payload, headers=headers, timeout=60)
            except requests.RequestException as exc:
                log.warning("Vision hálózati hiba: %s", exc)
                return None

            if response.status_code == 200:
                try:
                    text = extractor(response.json())
                except (KeyError, IndexError, TypeError, ValueError):
                    log.warning("Vision: váratlan válaszszerkezet")
                    return None
                result = parse_response(text)
                if result is None:
                    log.warning("Vision: nem értelmezhető válasz: %s", str(text)[:150])
                return result

            if response.status_code == 429 and attempt == 1:
                log.warning("Vision rate limit, várakozás")
                time.sleep(5)
                continue

            log.warning("Vision HTTP %s: %s", response.status_code, response.text[:200])
            return None
        return None


def build_client(config: VisionConfig) -> VisionClient | None:
    """Visszaad egy klienst, ha be van kapcsolva és van kulcs; különben None."""
    if config.enabled in {"off", "false", "no", "0"}:
        return None
    client = VisionClient(config)
    if not client.available:
        if config.enabled in {"on", "true", "yes", "1"}:
            log.warning(
                "Vision bekapcsolva, de hiányzik a(z) %s környezeti változó – kihagyva.",
                config.api_key_env,
            )
        return None
    return client


# --------------------------------------------------------------------------
#  Cache
# --------------------------------------------------------------------------


def image_key(urls: list[str]) -> str:
    joined = "|".join(sorted(urls))
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:20]


class VisionCache:
    """Fotó-URL-ek hash-éhez kötött eredménytár."""

    def __init__(self, path: str | Path, retention_days: int = 60) -> None:
        self.path = Path(path)
        self.retention_days = retention_days
        self.items: dict[str, dict] = {}
        self.dirty = False

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        items = data.get("items") if isinstance(data, dict) else None
        self.items = items if isinstance(items, dict) else {}

    def save(self) -> None:
        if not self.dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "items": self.items,
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.dirty = False

    def prune(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        for key, entry in list(self.items.items()):
            try:
                seen = datetime.fromisoformat(entry.get("at", ""))
            except ValueError:
                del self.items[key]
                self.dirty = True
                continue
            if seen < cutoff:
                del self.items[key]
                self.dirty = True

    def get(self, key: str) -> VisionResult | None:
        entry = self.items.get(key)
        if not entry:
            return None
        return VisionResult.from_dict(entry)

    def put(self, key: str, result: VisionResult) -> None:
        self.items[key] = {
            **result.to_dict(),
            "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        self.dirty = True
