"""Kijelzőadatok (nit, színhűség) és a bolt-hirdetések szennyezésének tesztjei."""

from pathlib import Path

from dealradar.models import Hit, Listing
from dealradar.notify import build_embed
from dealradar.specs import extract

SHOP_TEXT = """
Intel 12. generációs i5-ös, 12 magos mobil vpro HX-es CPU-val.
Intel Core i5-12600HX (18 MB cache, 16 threads, 12 cores, up to 4.60 GHz, vpro)
(pl. 17%-al erősebb mint az előző i9-11950H, 19%-al, mint az Ultra 9 288V)
Dell Precision 7770 4K 120Hz / i9-12950HX 16C / RTX A4500 16G / 1T
Dell Precision 5680 FHD+ i7-13800H 32G 1T Rtx 3500 12G Ada
"""


def test_earliest_cpu_wins_in_shop_description():
    specs = extract(SHOP_TEXT, "Dell Precision 7670 FHD+ / 12600HX / 16G D5")
    assert specs.cpu == "i5-12600HX"


def test_title_cpu_beats_description():
    specs = extract(
        "Valami más: Ultra 9 288V és i9-14900HX is szerepel a leírásban",
        "Lenovo Legion 5 i7-12700H RTX 4060",
    )
    assert specs.cpu == "i7-12700H"


def test_gpu_list_is_limited():
    specs = extract(SHOP_TEXT, "Dell Precision 7670 / A2000")
    assert len(specs.gpus) <= 3


def test_nits_and_gamut():
    specs = extract('16" FHD+ 500 nits, 100% sRGB, 165Hz')
    assert specs.nits == 500
    assert specs.gamut == "100% sRGB"

    specs = extract('14" OLED, 400 nit, 100% DCI-P3')
    assert specs.nits == 400
    assert specs.gamut == "100% DCI-P3"

    assert extract("16 GB RAM").nits is None
    assert extract("16 GB RAM").gamut is None


def test_screen_field_shows_brightness_comparison():
    listing = Listing(
        uadid="1",
        title='Lenovo Legion 5 16" 500 nits 100% sRGB',
        url="https://x",
        price=300_000,
    )
    listing.specs = extract(listing.title)
    listing.specs.nits = 500
    listing.specs.gamut = "100% sRGB"

    hit = Hit(listing=listing, profile="p", score=80)
    hit.screen_delta_pct = 66.7
    hit.reference_nits = 300

    fields = {f["name"]: f["value"] for f in build_embed(hit)["fields"]}
    assert "500 nit" in fields["Kijelző"]
    assert "100% sRGB" in fields["Kijelző"]
    assert "+67%" in fields["Kijelző"]


def test_storage_shorthand_in_title():
    specs = extract("Dell Precision 7670 / 512G G4 / 16G D5", "Dell Precision 7670 / 512G G4")
    assert specs.storage_gb == 512
    # a 16G RAM nem lesz tárolás
    assert specs.storage_gb != 16


def test_ryzen_ai_hx_cpu():
    specs = extract("AMD Ryzen AI 9 HX 370, Radeon 890M, 32 GB LPDDR5X")
    assert specs.cpu == "ryzen ai 9 HX 370"
    assert specs.cpu_year == 2025


def test_cpu_in_parentheses():
    assert extract("processzor: Amd ryzen 5 (7535HS)").cpu == "ryzen 5 7535HS"
    assert extract("Intel Core i5 (1240P)").cpu == "i5-1240P"


def test_hungarian_keyboard_with_comma():
    specs = extract("• Magyar, háttérvilágításos billentyűzet")
    assert specs.keyboard == "hu"


def test_macbook_is_excluded():
    from dealradar.config import load_config
    from dealradar.rules import passes_filters

    config = load_config(
        Path(__file__).resolve().parent.parent / "config.yaml"
    )
    listing = Listing(
        uadid="1",
        title="MacBook Pro 16 (2019) i9 / 32 GB RAM / 1 TB SSD",
        url="https://x",
        price=179_000,
    )
    listing.specs = extract(listing.title)
    assert not passes_filters(listing, config.watches[0].filters)


def test_screen_field_without_nits_is_explicit():
    listing = Listing(
        uadid="1",
        title='ASUS Zenbook S 16 OLED 120 Hz',
        url="https://x",
        price=449_000,
    )
    listing.specs = extract(listing.title)
    listing.specs.screen_inch = 16
    listing.specs.refresh_hz = 120
    listing.specs.oled = True

    hit = Hit(listing=listing, profile="p", score=60)
    fields = {f["name"]: f["value"] for f in build_embed(hit)["fields"]}
    assert "16" in fields["Kijelző"]
    assert "fényerő: nincs adat" in fields["Kijelző"]
