"""Billentyűzet- és OLED-felismerés, valamint a magyar-szűrő tesztjei."""

from dealradar.config import WatchedFilters
from dealradar.models import Listing
from dealradar.rules import passes_filters
from dealradar.specs import extract


def test_hungarian_keyboard_detected():
    assert extract("Lenovo Legion 5, magyar billentyűzet").keyboard == "hu"
    assert extract("MAGYAR BILLENTYŰZET, HU kiosztás").keyboard == "hu"
    assert extract("Dell XPS 15 HUN billentyűzet").keyboard == "hu"
    assert extract("külföldi billentyűzet magyarra lezerezve").keyboard == "hu"


def test_foreign_keyboard_detected():
    assert extract("Lenovo Legion 5, külföldi billentyűzet").keyboard == "foreign"
    assert extract("US billentyűzet, lezerezés nélkül").keyboard == "foreign"
    assert extract("német billentyűzet").keyboard == "foreign"
    assert extract("kiosztás: DE").keyboard == "foreign"
    assert extract("- Billentyűzet: Angol kiosztású").keyboard == "foreign"
    assert extract("Billentyűzet: angol").keyboard == "foreign"
    assert extract("francia kiosztás").keyboard == "foreign"


def test_unknown_keyboard():
    assert extract("Lenovo Legion 5 RTX 4060 32GB").keyboard is None


def test_bare_magyar_means_hungarian_keyboard():
    assert extract("Lenovo Legion 5 - 15.6\" FHD 165Hz - Ryzen 5 5600H - MAGYAR").keyboard == "hu"
    assert extract("ASUS ROG Strix G15, magyar").keyboard == "hu"


def test_magyar_with_other_nouns_is_not_keyboard():
    assert extract("Lenovo Legion 5, magyar garancia, számla").keyboard is None
    assert extract("Magyarország legjobb árai").keyboard is None
    assert extract("Magyar nyelvű Windows").keyboard is None


def test_foreign_keyboard_wins_over_hungarian_windows():
    """A leírásban a Windows lehet magyar, attól a billentyűzet még UK."""
    text = (
        "Dell Precision 7670, 16\" FHD+, 32 GB RAM. "
        "Billentyűzet: UK, világítós. Windows 11 Pro - Magyar, frissen telepítve."
    )
    assert extract(text, "Dell Precision 7670 4K OLED IR UK").keyboard == "foreign"


def test_hungarian_windows_alone_is_not_a_keyboard():
    text = "Windows 11 Pro - Magyar, frissen újratelepítve. Szép állapot."
    assert extract(text, "Dell Precision 7670").keyboard is None


def make_listing(text: str) -> Listing:
    listing = Listing(uadid="1", title=text, url="https://x", price=300_000)
    listing.specs = extract(text)
    return listing


def test_keyboard_filter_hu_rejects_foreign():
    filters = WatchedFilters(keyboard="hu")
    assert not passes_filters(make_listing("Legion 5 külföldi billentyűzet"), filters)
    assert passes_filters(make_listing("Legion 5 magyar billentyűzet"), filters)
    # ha nem derül ki, nem utasítjuk el
    assert passes_filters(make_listing("Legion 5 RTX 4060"), filters)


def test_keyboard_filter_any_allows_everything():
    filters = WatchedFilters(keyboard="any")
    assert passes_filters(make_listing("Legion 5 külföldi billentyűzet"), filters)


def test_oled_detection():
    assert extract("Lenovo Yoga OLED 14\" panel").oled is True
    assert extract("OLED kijelző, 2.8K").oled is True
    assert extract("Lenovo Legion 5 IPS 165Hz").oled is False
