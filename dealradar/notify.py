"""Discord webhook értesítés."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import requests

from .models import Hit

log = logging.getLogger(__name__)

MAX_EMBEDS_PER_MESSAGE = 10

COLOR_GREAT = 0x2ECC71  # zöld
COLOR_GOOD = 0xF1C40F  # sárga
COLOR_OK = 0xE67E22  # narancs


def format_huf(value: int | None) -> str:
    if value is None:
        return "–"
    return f"{value:,}".replace(",", " ") + " Ft"


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _color(score: int) -> int:
    if score >= 75:
        return COLOR_GREAT
    if score >= 60:
        return COLOR_GOOD
    return COLOR_OK


def build_embed(hit: Hit) -> dict:
    listing = hit.listing
    specs = listing.specs.summary()

    seller = listing.seller or "ismeretlen"
    if listing.seller_rating:
        seller += f" ({listing.seller_rating:+d})"
    if listing.is_business:
        seller += " · üzlet"

    details = [specs] if specs else []
    if listing.condition:
        details.append(listing.condition)
    if listing.shipping:
        details.append("csomagküldés")

    description = "\n".join(details)

    fields = [
        {"name": "Ár", "value": format_huf(listing.price), "inline": True},
        {"name": "Célár", "value": format_huf(hit.target_price), "inline": True},
        {"name": "Pontszám", "value": f"{hit.score}/100", "inline": True},
        {"name": "Hely", "value": _truncate(listing.location or "–", 100), "inline": True},
        {"name": "Eladó", "value": _truncate(seller, 100), "inline": True},
        {"name": "Profil", "value": _truncate(hit.profile, 100), "inline": True},
    ]
    if hit.reasons:
        fields.append(
            {
                "name": "Miért jó",
                "value": _truncate(" · ".join(hit.reasons), 1000),
                "inline": False,
            }
        )

    return {
        "title": _truncate(listing.title, 250),
        "url": listing.url_abs,
        "description": _truncate(description, 400),
        "color": _color(hit.score),
        "fields": fields,
        "footer": {"text": _truncate(f"Hardverapró · {listing.posted or 'ismeretlen időpont'}", 200)},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _post(session: requests.Session, webhook: str, payload: dict) -> None:
    for attempt in range(1, 4):
        response = session.post(webhook, json=payload, timeout=20)
        if response.status_code in (200, 204):
            return
        if response.status_code == 429:
            try:
                wait = float(response.json().get("retry_after", 2))
            except ValueError:
                wait = 2.0
            log.warning("Discord rate limit, várakozás %.1fs", wait)
            time.sleep(min(wait, 30))
            continue
        # Egyéb hiba: ne próbáljuk végtelenül
        raise RuntimeError(f"Discord hiba {response.status_code}: {response.text[:300]}")
    raise RuntimeError("Discord: túl sok próbálkozás (rate limit)")


def send_test(webhook: str, *, dry_run: bool = False) -> int:
    """Egyetlen tesztüzenet a webhook működésének ellenőrzésére."""
    payload = {
        "content": "✅ **apro-deal-radar** – a webhook működik. Innentől jönnek a találatok.",
        "embeds": [
            {
                "title": "Teszt értesítés",
                "description": "Ez egy próbaüzenet a GitHub Actions beállítás ellenőrzéséhez.",
                "color": 0x2ECC71,
                "footer": {"text": "apro-deal-radar"},
            }
        ],
    }
    if dry_run:
        print("[DRY] teszt webhook üzenet:")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    _post(requests.Session(), webhook, payload)
    return 1


def send(webhook: str, hits: list[Hit], *, dry_run: bool = False) -> int:
    """Elküldi a találatokat. Visszaadja az elküldött elemek számát."""
    if not hits:
        log.info("Nincs új találat, nem küldünk semmit.")
        return 0

    if dry_run:
        for hit in hits:
            print(
                f"[DRY] {hit.score:3d}/100  {format_huf(hit.listing.price):>12}  "
                f"{hit.profile:<32}  {hit.listing.title[:70]}"
            )
            print(f"      {hit.listing.url_abs}")
        return 0

    session = requests.Session()
    sent = 0
    chunks = [hits[i : i + MAX_EMBEDS_PER_MESSAGE] for i in range(0, len(hits), MAX_EMBEDS_PER_MESSAGE)]

    for index, chunk in enumerate(chunks):
        embeds = [build_embed(hit) for hit in chunk]
        content = None
        if index == 0:
            content = f"🎯 **{len(hits)} új jó deal** a Hardveraprón" + (
                f" – összesen {len(chunks)} üzenet" if len(chunks) > 1 else ""
            )
        payload: dict = {"embeds": embeds}
        if content:
            payload["content"] = content

        _post(session, webhook, payload)
        sent += len(chunk)
        log.info("Discord: %d/%d találat elküldve", sent, len(hits))
        if index < len(chunks) - 1:
            time.sleep(1.0)

    return sent
