"""Képernyőméret-felismerés és a minimum méret szűrő tesztjei."""

from dealradar.config import WatchedFilters
from dealradar.models import Listing
from dealradar.rules import passes_filters
from dealradar.specs import extract


def test_explicit_inches():
    assert extract('Lenovo Legion 5 15,6" FHD 165Hz').screen_inch == 15.6
    assert extract('ASUS Zenbook 14" OLED').screen_inch == 14.0
    assert extract("Acer Nitro 5 17.3 inch").screen_inch == 17.3
    assert extract("Dell XPS 16 col").screen_inch == 16.0


def test_lenovo_model_code():
    assert extract("Lenovo Legion 5 15ACH6H RTX 3060").screen_inch == 15.0
    assert extract("Lenovo Legion 5 Pro 16IRH8").screen_inch == 16.0
    assert extract("Lenovo IdeaPad 15ARH7").screen_inch == 15.0


def test_asus_letter_size():
    assert extract("ASUS TUF Gaming F15 FX507VI").screen_inch == 15.0
    assert extract("ASUS ROG Strix G15 G513QM").screen_inch == 15.0


def test_family_name_size():
    assert extract("ASUS Zenbook 14 OLED UX3402").screen_inch == 14.0
    assert extract("IdeaPad 5 15ITL6").screen_inch == 15.0
    assert extract("MacBook Air 13 M2").screen_inch == 13.0
    assert extract("HP Pavilion 15").screen_inch == 15.0


def test_no_false_positive_on_model_numbers():
    # "Legion 5" nem 15 colos mérés, a "5" nem méret
    assert extract("Lenovo Legion 5 Pro").screen_inch is None
    # "A 16 GB RAM" nem 16 colos kijelző
    assert extract("stabil marad. A 16 GB RAM és a 256 GB SSD").screen_inch is None
    # "16GB" nem méret
    assert extract("Lenovo ThinkPad 16GB RAM 512GB SSD").screen_inch is None


def test_trademark_symbols_do_not_break_cpu():
    specs = extract("CPU: Intel® Core™ i5-1240P (12M Cache, up to 4.40 GHz)")
    assert specs.cpu == "i5-1240P"


def test_ryzen_without_space():
    assert extract("Acer Nitro V 17 - Ryzen7 260, 16GB").cpu == "ryzen 7 260"
    assert extract("ASUS ROG Ryzen 7 5800H").cpu == "ryzen 7 5800H"


def test_integrated_gpu_detection():
    assert extract("Intel® Iris® Xe Graphics eligible").gpus == ["iris xe"]
    assert extract("Intel UHD Graphics").gpus == ["uhd graphics"]
    assert extract("Radeon 780M integrated").gpus == ["radeon 780m"]


def test_intel_ultra_variants():
    assert extract("Core Ultra 7 155H").cpu == "ultra 7 155H"
    assert extract("Ultra 7 240H RTX 5050").cpu == "ultra 7 240H"
    assert extract("Intel 7 240H RTX 5050 8GB").cpu == "core 7 240H"


def test_core_7_240h_year():
    assert extract("Intel 7 240H").cpu_year == 2025
    assert extract("Intel Core 7 240H").cpu_year == 2025


def test_compact_ultra_writing():
    specs = extract("CoreUltra7-155H 8/16mag 22szál")
    assert specs.cpu == "ultra 7 155H"
    assert specs.cpu_year == 2024


def test_rtx_studio_writing():
    specs = extract("Intel ARC + Geforce RTX Studio 4050 6GB Videokártya")
    assert specs.gpus == ["rtx 4050"]


def test_hdr_brightness():
    specs = extract("16' 2.5K OLED 240Hz G-sync HDR500 Kijelző")
    assert specs.nits == 500
    assert specs.oled is True


def test_american_keyboard():
    assert extract("2025-ös amerika import modell. Amerikai billentyűzettel.").keyboard == "foreign"
    assert extract("US layout keyboard").keyboard == "foreign"


def make_listing(text: str) -> Listing:
    listing = Listing(uadid="1", title=text, url="https://x", price=300_000)
    listing.specs = extract(text)
    return listing


def test_screen_filter_rejects_small():
    filters = WatchedFilters(min_screen_inch=15.0, screen_unknown="reject")
    assert not passes_filters(make_listing('ASUS Zenbook 14" OLED'), filters)
    assert passes_filters(make_listing('Lenovo Legion 5 15,6" RTX 4060'), filters)
    assert passes_filters(make_listing('Dell XPS 16 RTX 4060'), filters)


def test_screen_filter_unknown_policy():
    reject = WatchedFilters(min_screen_inch=15.0, screen_unknown="reject")
    allow = WatchedFilters(min_screen_inch=15.0, screen_unknown="allow")
    listing = make_listing("Lenovo Legion 5 RTX 4060 16GB")
    assert listing.specs.screen_inch is None

    # a cím alapján még nem zárjuk ki (a leírásban lehet a méret)
    assert passes_filters(listing, reject)
    # a részoldal beolvasása után viszont igen
    assert not passes_filters(listing, reject, final=True)
    assert passes_filters(listing, allow, final=True)


def test_known_small_screen_is_rejected_even_before_deep_scan():
    filters = WatchedFilters(min_screen_inch=15.0, screen_unknown="reject")
    assert not passes_filters(make_listing('ASUS Zenbook 14" OLED'), filters)


def test_screen_filter_disabled_by_default():
    filters = WatchedFilters()
    assert passes_filters(make_listing('ASUS Zenbook 14" OLED'), filters)
