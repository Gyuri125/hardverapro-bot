from pathlib import Path

import pytest

from dealradar.parse import enrich, page_url, parse_detail_page, parse_list_page, parse_price, parse_rating

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("400 000 Ft", 400000),
        ("400\u00a0000 Ft", 400000),
        ("400\u202f000 Ft", 400000),
        ("3,00M Ft", 3_000_000),
        ("88,89M Ft", 88_890_000),
        ("1,2M Ft", 1_200_000),
        ("9 389 Ft", 9389),
        ("Ingyenes", 0),
        ("Keresem", None),
        ("Ár nélkül", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_price(raw, expected):
    assert parse_price(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [("+879", 879), ("-3", -3), ("+22", 22), ("–", 0), (None, 0)],
)
def test_parse_rating(raw, expected):
    assert parse_rating(raw) == expected


def test_page_url():
    assert page_url("https://hardverapro.hu/aprok/notebook/index.html", 0).endswith("index.html")
    assert page_url("https://hardverapro.hu/aprok/notebook/index.html", 2).endswith("index.html?offset=200")
    assert page_url("https://hardverapro.hu/x?stext=a", 1).endswith("?stext=a&offset=100")


def test_parse_list_page():
    html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    listings = parse_list_page(html)
    assert len(listings) == 4

    by_title = {listing.title[:20]: listing for listing in listings}
    assert any("Ki az az ÁRON" in t for t in by_title)

    malak = next(l for l in listings if "Ki az az ÁRON" in l.title)
    assert malak.price == 2_999_999
    assert malak.seller_rating == 879
    assert malak.uadid.isdigit()
    assert malak.url_abs.startswith("https://hardverapro.hu/apro/")

    promoted = [l for l in listings if l.promoted]
    assert len(promoted) == 1
    assert promoted[0].title.startswith("Ki az az ÁRON")

    business = [l for l in listings if l.is_business]
    assert len(business) >= 2


def test_parse_detail_page():
    html = (FIXTURES / "detail_page.html").read_text(encoding="utf-8")
    detail = parse_detail_page(html)
    assert detail["price"] == 400_000
    assert detail["condition"] == "használt"
    assert detail["intent"] == "kínál"
    assert detail["shipping"] is True
    assert "Budapest" in detail["location"]
    assert "RTX 5050" in detail["description"]
    assert "2560x1600" in detail["description"]


def test_enrich_merges_detail_into_listing():
    html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    listing = parse_list_page(html)[0]
    detail = parse_detail_page((FIXTURES / "detail_page.html").read_text(encoding="utf-8"))
    enrich(listing, detail)
    assert listing.price == 400_000
    assert listing.condition == "használt"
    assert listing.shipping is True
    assert "RTX 5050" in listing.description


def test_location_is_not_the_seller_rating():
    """A részoldalon két uad-time-location blokk van; a helyszín a térkép-ikonos."""
    html = """
    <div class="uad-time-location">
      <span><span class="uad-rating uad-rating-positive">18 pozitív</span> értékelés</span>
      <span>2026-11-11 21:36</span>
    </div>
    <div class="uad-time-location">
      <span><span class="fas fa-map-marker"></span> Százhalombatta</span>
      <span><span class="fas fa-truck"></span> csomagküldéssel is</span>
    </div>
    """
    detail = parse_detail_page(html)
    assert detail["location"] == "Százhalombatta"
    assert detail["shipping"] is True


def test_detail_images_are_extracted():
    html = """
    <div class="carousel-item">
      <a href="//cdn.rios.hu/dl/uad/1/a.jpg"><img src="//cdn.rios.hu/dl/uad/1/a.jpg/100"></a>
    </div>
    <div class="carousel-item">
      <a href="https://cdn.rios.hu/dl/uad/1/b.jpg">kép</a>
    </div>
    <div class="carousel-item">
      <a href="//cdn.rios.hu/dl/uad/1/a.jpg">duplikált</a>
    </div>
    """
    images = parse_detail_page(html)["images"]
    assert images == [
        "https://cdn.rios.hu/dl/uad/1/a.jpg",
        "https://cdn.rios.hu/dl/uad/1/b.jpg",
    ]


def test_enrich_copies_images():
    html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    listing = parse_list_page(html)[0]
    enrich(listing, {"images": ["https://cdn.rios.hu/x.jpg"]})
    assert listing.images == ["https://cdn.rios.hu/x.jpg"]
