"""Discord webhook értesítés."""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone

import requests

from .links import cpu_manufacturer_url, specs_url
from .models import Hit

log = logging.getLogger(__name__)

MAX_EMBEDS_PER_MESSAGE = 10
# A Discord egy üzenetben összesen 6000 karaktert enged az embedekben.
# Biztonsági ráhagyással 5200-nál vágunk, és új üzenetbe kezdünk.
MAX_MESSAGE_CHARS = 5200

COLOR_GREAT = 0x2ECC71  # zöld
COLOR_GOOD = 0xF1C40F  # sárga
COLOR_OK = 0xE67E22  # narancs
COLOR_OVER_BUDGET = 0x9B59B6  # lila – keret feletti találat
COLOR_SUSPICIOUS = 0xE74C3C  # piros – gyanúsan olcsó


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


def _label(text: str) -> str:
    """Link-felirat biztonságosítása (Discord markdown)."""
    cleaned = re.sub(r"[\[\]()*_~`|]", "", text or "")
    return re.sub(r"\s+", " ", cleaned).strip() or "?"


def _markdown_number(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def _cpu_field(hit: Hit) -> str:
    cpu = hit.listing.specs.cpu
    if not cpu:
        return "–"
    url = cpu_manufacturer_url(cpu)
    name = _label(cpu)
    value = f"[{name}]({url})" if url else name
    if hit.cpu_bench:
        score = _markdown_number(hit.cpu_bench.score)
        value += f"\nCPU Mark: **[{score}]({hit.cpu_bench.url})**"
    if hit.cpu_delta_pct is not None and hit.reference_cpu:
        sign = "+" if hit.cpu_delta_pct >= 0 else ""
        value += (
            f"\n**{sign}{hit.cpu_delta_pct:.0f}%** a te "
            f"{_label(hit.reference_cpu)}-hez képest"
        )
    return value


GPU_CLASSES = [
    (26000, "4K/1440p, AAA játékok magas beállításon"),
    (19000, "1440p magas / 1080p ultra"),
    (14000, "1080p magas, AAA játékok közepes–magas"),
    (10000, "1080p közepes–magas"),
    (7000, "1080p közepes, e-sport magas FPS"),
    (4500, "1080p alacsony–közepes"),
    (0, "alap felhasználás, régebbi játékok"),
]


def gpu_capability(score: int) -> str:
    """PassMark G3D Mark -> rövid, emberi kategória."""
    for limit, label in GPU_CLASSES:
        if score >= limit:
            return label
    return ""


def _gpu_field(hit: Hit) -> str:
    if not hit.listing.specs.gpus:
        return "–"
    name = _label(hit.listing.specs.gpus[0].upper())
    if hit.gpu_bench:
        value = f"[{name}]({hit.gpu_bench.url})\nG3D Mark: **{_markdown_number(hit.gpu_bench.score)}**"
        capability = gpu_capability(hit.gpu_bench.score)
        if capability:
            value += f"\n{capability}"
        return value
    return name


def _keyboard_field(hit: Hit) -> str:
    specs = hit.listing.specs
    if specs.keyboard == "hu":
        if specs.keyboard_source == "photo":
            return "magyar (fotó alapján)"
        if specs.keyboard_note == "matricás":
            return "magyar matrica (nem gyári)"
        return "magyar (a hirdetés szerint)"
    if specs.keyboard == "foreign":
        if specs.keyboard_source == "photo":
            return "külföldi (fotó alapján)"
        return "külföldi"
    if specs.keyboard_note:
        return f"**nem derül ki**\n{specs.keyboard_note} – kérdezz rá az eladónál"
    return "**nem derül ki**\nkérdezz rá az eladónál"


def _screen_field(hit: Hit) -> str | None:
    specs = hit.listing.specs
    line = specs.screen_line()
    if not line:
        return None

    missing: list[str] = []
    if not specs.nits:
        missing.append("fényerő: nincs adat")
    if not specs.gamut:
        missing.append("színhűség: nincs adat")

    value = line
    if missing:
        value += "\n" + " · ".join(missing)
    if hit.screen_delta_pct is not None and hit.reference_nits:
        sign = "+" if hit.screen_delta_pct >= 0 else ""
        value += (
            f"\n**{sign}{hit.screen_delta_pct:.0f}%** fényerő a te "
            f"{hit.reference_nits} nitedhez képest"
        )
    if hit.gamut_delta_pct is not None and hit.reference_srgb:
        sign = "+" if hit.gamut_delta_pct >= 0 else ""
        value += (
            f"\n**{sign}{hit.gamut_delta_pct:.0f}%** színtartomány a te "
            f"{hit.reference_srgb}% sRGB-det képest"
        )
    return value


def build_embed(hit: Hit) -> dict:
    listing = hit.listing
    specs = listing.specs

    seller = listing.seller or "ismeretlen"
    if listing.seller_rating:
        seller += f" ({listing.seller_rating:+d})"
    if listing.is_business:
        seller += " · üzlet"

    details = [part for part in (specs.details(), listing.condition) if part]
    if listing.shipping:
        details.append("csomagküldés")

    fields = [
        {"name": "Ár", "value": format_huf(listing.price), "inline": True},
        {"name": "Célár", "value": format_huf(hit.target_price), "inline": True},
        {"name": "Pontszám", "value": f"{hit.score}/100", "inline": True},
        {"name": "Processzor", "value": _truncate(_cpu_field(hit), 1024), "inline": True},
        {"name": "Videokártya", "value": _truncate(_gpu_field(hit), 1024), "inline": True},
        {"name": "Billentyűzet", "value": _keyboard_field(hit), "inline": True},
        {"name": "Hely", "value": _truncate(listing.location or "–", 100), "inline": True},
        {"name": "Eladó", "value": _truncate(seller, 100), "inline": True},
        {
            "name": "Specifikáció",
            "value": f"[Megnézem]({specs_url(listing.title)})",
            "inline": True,
        },
    ]
    screen_value = _screen_field(hit)
    if screen_value:
        fields.insert(
            5, {"name": "Kijelző", "value": _truncate(screen_value, 1024), "inline": True}
        )

    if hit.suspiciously_cheap and listing.price and hit.market_median:
        ratio = listing.price / hit.market_median * 100
        fields.insert(
            0,
            {
                "name": "GYANÚSAN OLCSÓ",
                "value": (
                    f"Piaci medián: **{format_huf(hit.market_median)}** – ez az ár annak "
                    f"{ratio:.0f}%-a. Nézd meg figyelmesen: lehet hibás, hiányos vagy csalás."
                ),
                "inline": False,
            },
        )

    if hit.previous_price and listing.price:
        drop = f" (-{hit.price_drop_pct:.0f}%)" if hit.price_drop_pct else ""
        fields.insert(
            0,
            {
                "name": "ÁRCÖKKENÉS",
                "value": f"{format_huf(hit.previous_price)} → **{format_huf(listing.price)}**{drop}",
                "inline": False,
            },
        )

    if hit.over_budget and listing.price and hit.budget:
        over = listing.price - hit.budget
        fields.insert(
            0,
            {
                "name": "KERET FELETT",
                "value": (
                    f"**{format_huf(listing.price)}** – {format_huf(over)}-tal a "
                    f"{format_huf(hit.budget)}-os keret felett. "
                    "Csak kiemelkedő deal esetén érdemes elgondolkodni rajta."
                ),
                "inline": False,
            },
        )
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
        "description": _truncate(" · ".join(details), 400),
        "color": (
            COLOR_SUSPICIOUS
            if hit.suspiciously_cheap
            else COLOR_OVER_BUDGET
            if hit.over_budget
            else _color(hit.score)
        ),
        "fields": fields,
        "footer": {"text": _truncate(f"Hardverapró · {listing.posted or 'ismeretlen időpont'}", 200)},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def send_summary(webhook: str, day: str, items: list[dict], *, dry_run: bool = False) -> int:
    """Napi összefoglaló: hány új találat volt, és a legjobb három."""
    if not items:
        return 0

    top = sorted(items, key=lambda item: item.get("score") or 0, reverse=True)[:3]
    lines: list[str] = []
    for index, item in enumerate(top, 1):
        title = _label(item.get("title") or "?")
        url = item.get("url")
        link = f"[{title}]({url})" if url else title
        lines.append(
            f"{index}. {link} – **{item.get('score')} pont** – {format_huf(item.get('price'))}"
        )

    embed = {
        "title": f"Napi összefoglaló – {day}",
        "description": f"**{len(items)} új találat** a Hardveraprón.\n\n" + "\n".join(lines),
        "color": COLOR_GREAT,
    }
    payload = {"embeds": [embed]}

    if dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    _post(requests.Session(), webhook, payload)
    return len(items)


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
        "content": "**apro-deal-radar** – a webhook működik. Innentől jönnek a találatok.",
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


def _embed_size(embed: dict) -> int:
    """Hozzávetőleges karakterhossz, ahogy a Discord számolja."""
    size = len(embed.get("title") or "") + len(embed.get("description") or "")
    size += len(embed.get("footer", {}).get("text") or "")
    for field in embed.get("fields", []):
        size += len(field.get("name") or "") + len(field.get("value") or "")
    return size


def _chunk_embeds(items: list[tuple[Hit, dict]]) -> list[list[tuple[Hit, dict]]]:
    """Darabolás a Discord 6000 karakteres üzenetlimije alatt."""
    chunks: list[list[tuple[Hit, dict]]] = []
    current: list[tuple[Hit, dict]] = []
    current_size = 0

    for hit, embed in items:
        size = _embed_size(embed)
        if current and (
            len(current) >= MAX_EMBEDS_PER_MESSAGE or current_size + size > MAX_MESSAGE_CHARS
        ):
            chunks.append(current)
            current = []
            current_size = 0
        current.append((hit, embed))
        current_size += size

    if current:
        chunks.append(current)
    return chunks


def send(webhook: str, hits: list[Hit], *, dry_run: bool = False) -> set[str]:
    """Elküldi a találatokat. Visszaadja az elküldött hirdetések azonosítóit."""
    if not hits:
        log.info("Nincs új találat, nem küldünk semmit.")
        return set()

    if dry_run:
        for hit in hits:
            print(
                f"[DRY] {hit.score:3d}/100  {format_huf(hit.listing.price):>12}  "
                f"{hit.profile:<32}  {hit.listing.title[:70]}"
            )
            print(f"      {hit.listing.url_abs}")
        return set()

    session = requests.Session()
    sent: set[str] = set()
    items = [(hit, build_embed(hit)) for hit in hits]
    chunks = _chunk_embeds(items)
    log.info("%d találat, %d Discord üzenetben", len(hits), len(chunks))

    for index, chunk in enumerate(chunks):
        embeds = [embed for _, embed in chunk]
        payload: dict = {"embeds": embeds}
        if index == 0:
            payload["content"] = f"**{len(hits)} új találat** a Hardveraprón"
        try:
            _post(session, webhook, payload)
        except RuntimeError as exc:
            # Egy rossz üzenet ne vigye magával a többit.
            log.error("Discord üzenet kihagyva: %s", exc)
            continue

        sent.update(hit.listing.uadid for hit, _ in chunk)
        log.info("Discord: %d/%d találat elküldve", len(sent), len(hits))
        if index < len(chunks) - 1:
            time.sleep(1.0)

    return sent
