"""Kijelzőadatok (nit, színhűség) és a bolt-hirdetések szennyezésének tesztjei."""

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
