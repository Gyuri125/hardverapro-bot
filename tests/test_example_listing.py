"""Végponttól végpontig teszt a felhasználó saját példahirdetésével.

A 400 000 Ft-os Lenovo Legion 5 (i7-14700HX, RTX 5050, 32 GB, 1 TB, 165 Hz,
garancia 2028-ig) a valódi config.yaml szűrőin és pontozásán kell átmenjen.
Ez a teszt védi meg a "csere" típusú szűrőhibákat is.
"""

from pathlib import Path

from dealradar.config import load_config
from dealradar.models import Listing
from dealradar.parse import enrich, parse_detail_page
from dealradar.rules import best_hit, passes_filters
from dealradar.specs import extract

ROOT = Path(__file__).resolve().parent.parent

TITLE = (
    "Eladó Csúcskategóriás Gamer Laptop Kifogástalan Állapotban! "
    "- Lenovo Legion 5 Eclipse Black"
)


def build_listing() -> Listing:
    listing = Listing(
        uadid="7707247",
        title=TITLE,
        url="https://hardverapro.hu/apro/legion/friss.html",
        price=400_000,
        seller="GregS",
        seller_rating=22,
        location="Budapest, XI. kerület",
        posted="17 órája",
    )
    detail = parse_detail_page(
        (ROOT / "tests" / "fixtures" / "detail_page.html").read_text(encoding="utf-8")
    )
    enrich(listing, detail)
    listing.specs = extract(listing.text, listing.title)
    return listing


def test_example_listing_passes_watch_filters():
    config = load_config(ROOT / "config.yaml")
    listing = build_listing()
    assert passes_filters(listing, config.watches[0].filters)


def test_example_listing_is_detected_as_deal():
    config = load_config(ROOT / "config.yaml")
    listing = build_listing()
    hit = best_hit(listing, config.profiles, config.market, {})
    assert hit is not None
    assert "5050" in hit.profile
    assert hit.score >= config.settings.min_score


def test_example_specs_are_correct():
    specs = build_listing().specs
    assert specs.cpu == "i7-14700HX"
    assert specs.gpus == ["rtx 5050"]
    assert specs.ram_gb == 32
    assert specs.storage_gb == 1024
    assert specs.refresh_hz == 165
    assert specs.warranty is True
