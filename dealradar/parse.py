"""Hardverapró HTML feldolgozás."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .models import Listing

BASE_URL = "https://hardverapro.hu"

_PRICE_LOCAL = re.compile(r"(\d+(?:[.,]\d+)?)\s*m\b", re.I)


def parse_price(text: str | None) -> int | None:
    """'400 000 Ft' -> 400000, '3,00M Ft' -> 3000000, 'Keresem' -> None."""
    if not text:
        return None
    t = text.replace("\u00a0", " ").replace("\u202f", " ").replace("\u2009", " ").strip().lower()
    if not t:
        return None
    if any(marker in t for marker in ("keresem", "ár nélkül", "ar nelkul", "csere", "megegyezés")):
        return None
    if "ingyenes" in t or t.strip() == "0 ft":
        return 0

    match = _PRICE_LOCAL.search(t)
    if match:
        try:
            return int(round(float(match.group(1).replace(",", ".")) * 1_000_000))
        except ValueError:  # pragma: no cover - elméleti
            return None

    digits = re.sub(r"[^\d]", "", t)
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:  # pragma: no cover
        return None


def parse_rating(text: str | None) -> int:
    """'+879' -> 879, '-3' -> -3, '–' -> 0."""
    if not text:
        return 0
    match = re.search(r"([+-]?\d+)", text.replace("\u00a0", " "))
    return int(match.group(1)) if match else 0


def page_url(base: str, page_index: int) -> str:
    """0 -> az alap URL, 1 -> ?offset=100, 2 -> ?offset=200 ..."""
    if page_index <= 0:
        return base
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}offset={page_index * 100}"


# --------------------------------------------------------------------------
#  listaoldal
# --------------------------------------------------------------------------


def parse_list_page(html: str, page_url_: str = "") -> list[Listing]:
    """Egy kategóriaoldal hirdetései."""
    soup = BeautifulSoup(html, "html.parser")
    listings: list[Listing] = []

    for item in soup.select("li.media[data-uadid]"):
        uadid = item.get("data-uadid", "").strip()
        title_link = item.select_one(".uad-col-title h1 a")
        if not uadid or title_link is None:
            continue

        title = title_link.get_text(" ", strip=True)
        href = title_link.get("href", "")
        url = urljoin(BASE_URL, href) if href else ""
        if not title or not url:
            continue

        # A cím-oszlopban a pontos ár van ("2 999 999 Ft"),
        # az ár-oszlopban néha kerekített ("3,00M Ft") – ezért az elsőt vesszük.
        price_el = item.select_one(".uad-col-title .uad-price") or item.select_one(
            ".uad-col-price .uad-price"
        )
        price = parse_price(price_el.get_text(" ", strip=True) if price_el else None)

        seller_el = item.select_one(".uad-user-text a")
        seller = seller_el.get_text(" ", strip=True) if seller_el else ""

        rating_el = item.select_one(".uad-rating")
        rating = parse_rating(rating_el.get_text(" ", strip=True) if rating_el else None)

        location_el = item.select_one(".uad-cities")
        location = location_el.get_text(" ", strip=True) if location_el else ""

        time_el = item.select_one(".uad-time time")
        posted = time_el.get_text(" ", strip=True) if time_el else ""

        ribbons = [
            el.get_text(" ", strip=True)
            for el in item.select(".uad-corner-ribbon span")
            if el.get_text(strip=True)
        ]

        item_text = item.get_text(" ", strip=True)
        promoted = "Előresorolva" in item_text
        is_business = "uad-business-user" in (item.get("class") or []) or bool(
            item.select_one(".user-business-icon")
        )

        listings.append(
            Listing(
                uadid=uadid,
                title=title,
                url=url,
                price=price,
                seller=seller,
                seller_rating=rating,
                is_business=is_business,
                location=location,
                posted=posted,
                ribbons=ribbons,
                promoted=promoted,
            )
        )

    return listings


# --------------------------------------------------------------------------
#  részoldal
# --------------------------------------------------------------------------


def parse_detail_page(html: str) -> dict:
    """Egy hirdetés részoldalának kiegészítő adatai."""
    soup = BeautifulSoup(html, "html.parser")
    data: dict = {}

    price_el = soup.select_one(".uad-details h2")
    if price_el:
        data["price"] = parse_price(price_el.get_text(" ", strip=True))

    attributes: dict[str, str] = {}
    for row in soup.select(".uad-details table tr"):
        th = row.find("th")
        td = row.find("td")
        if th and td:
            key = th.get_text(" ", strip=True).rstrip(":").strip().lower()
            attributes[key] = td.get_text(" ", strip=True)
    if "állapot" in attributes:
        data["condition"] = attributes["állapot"]
    if "szándék" in attributes:
        data["intent"] = attributes["szándék"]

    content_el = soup.select_one(".uad-content")
    if content_el:
        paragraphs = [p.get_text("\n", strip=True) for p in content_el.select("p")]
        text = "\n".join(paragraphs) or content_el.get_text("\n", strip=True)
        data["description"] = re.sub(r"\n{3,}", "\n\n", text).strip()

    # A részoldalon két .uad-time-location blokk van: az első az eladó
    # értékelése, a második a helyszín. A térkép-ikon alapján találjuk meg.
    marker = soup.select_one(".uad-time-location .fa-map-marker")
    if marker is not None and marker.parent is not None:
        location = marker.parent.get_text(" ", strip=True)
        if location and "pozit" not in location.lower() and "negat" not in location.lower():
            data["location"] = location

    data["shipping"] = bool(soup.select_one(".fa-truck")) or "csomagküldéssel" in soup.get_text(
        " ", strip=True
    ).lower()

    # Eladó: "Hksz03 (újonc) – 2 órája regisztrált" / "18 pozitív értékelés"
    seller_meta = ""
    seller_new = False
    first_block = soup.select_one(".uad-time-location")
    if first_block is not None:
        seller_meta = first_block.get_text(" ", strip=True)
        low = seller_meta.lower()
        seller_new = any(
            marker in low
            for marker in (
                "friss újonc",
                "órája regisztrált",
                "napja regisztrált",
                "hete regisztrált",
                "hónapja regisztrált",
            )
        )
    data["seller_meta"] = seller_meta
    data["seller_new"] = seller_new

    images: list[str] = []
    for anchor in soup.select(".carousel-item a[href]"):
        href = (anchor.get("href") or "").strip()
        if href.startswith("//"):
            href = "https:" + href
        if href.startswith("http") and href not in images:
            images.append(href)
    if not images:
        for img in soup.select(".carousel-inner img[src]"):
            src = (img.get("src") or "").strip()
            if src.startswith("//"):
                src = "https:" + src
            if src.startswith("http") and src not in images:
                images.append(src)
    data["images"] = images

    return data


def enrich(listing: Listing, detail: dict) -> Listing:
    """Részoldal adatainak beolvasztása a hirdetésbe."""
    if detail.get("price") is not None:
        listing.price = detail["price"]
    listing.condition = detail.get("condition") or listing.condition
    listing.intent = detail.get("intent") or listing.intent
    listing.description = detail.get("description") or listing.description
    listing.location = detail.get("location") or listing.location
    listing.shipping = bool(detail.get("shipping")) or listing.shipping
    listing.seller_new = bool(detail.get("seller_new")) or listing.seller_new
    listing.seller_meta = detail.get("seller_meta") or listing.seller_meta
    images = detail.get("images") or []
    if images:
        listing.images = list(images)
    return listing
