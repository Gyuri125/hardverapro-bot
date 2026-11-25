"""A 'Megjegyzés' mező (gari, akku, hibák, tartozékok) tesztjei."""

from dealradar.models import Hit, Listing
from dealradar.notify import build_embed
from dealradar.specs import extract

ZEPHYRUS = """
Asus ROG Zephyrus G16 GU605MU
CoreUltra7-155H 8/16mag 22szál 1.4-4.8Ghz
16GB DDR5
1TB Nvme 100/100% Kb. 117óra üzemidő és kb. 8TB írás/olvasás
Intel ARC + Geforce RTX Studio 4050 6GB Videokártya
16' 2.5K ROG Nebula OLED 240Hz G-sync HDR500 Kijelző
Asus Aurasync Magyar Billentyűzet
90Wh Akku 92.5% / 7.5% Használt. Szuper gyors töltés
DolbyAtmos 6 hangszorós hangzás
Dobozok,Papírok,Tápegység.
Garancia 2028.05 Alza Magyar
"""


def test_notes_from_business_listing():
    specs = extract(ZEPHYRUS)
    assert "garancia 2028.05-ig" in specs.notes
    assert any("akku 92.5%" in note for note in specs.notes)
    assert any("doboz" in note for note in specs.notes)


def test_negated_defect_is_not_reported():
    specs = extract("Szép állapot, nem koszos, nem zsíros, nem foltos.")
    assert not any("folt" in note for note in specs.notes)


def test_real_defect_is_reported():
    specs = extract("Van egy kis horpadás a bal sarokban, egyébként hibátlan.")
    assert any("horpad" in note for note in specs.notes)


def test_notes_appear_in_embed():
    listing = Listing(uadid="1", title="Teszt gép", url="https://x", price=300_000)
    listing.specs = extract(ZEPHYRUS)
    hit = Hit(listing=listing, profile="p", score=70)

    embed = build_embed(hit)
    fields = {field["name"]: field["value"] for field in embed["fields"]}
    assert "Megjegyzés" in fields
    assert "garancia 2028.05" in fields["Megjegyzés"]
    assert "akku 92.5%" in fields["Megjegyzés"]
