"""Hardver-adatok kinyerése a hirdetés szövegéből.

Szándékosan megengedő: ami nem ismerhető fel, az None marad, és a
szűrők ilyenkor nem utasítják el a hirdetést.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .models import Specs

GPU_RE = re.compile(
    r"\b(?:nvidia\s+)?(?:geforce\s+)?(rtx|gtx|rx|arc)\s?-?\s?([a-z]?\d{3,4})\b",
    re.I,
)
CPU_ULTRA_RE = re.compile(r"\bcore\s+ultra\s+([579])\s+(\d{3}[a-z]{0,2})\b", re.I)
# "Intel 7 240H" / "Ultra 7 240H" (a "Core" szó elhagyva)
CPU_ULTRA_SHORT_RE = re.compile(r"\b(?:intel\s+|core\s+)?ultra\s+([579])\s+(\d{3}[a-z]{0,2})\b", re.I)
CPU_INTEL_NUM_RE = re.compile(r"\bintel\s+([579])\s+(\d{3}[a-z]{0,2})\b", re.I)
CPU_INTEL_RE = re.compile(r"\b(?:intel\s+)?core\s+([iI][3579])[-\s]?(\d{4,5}[a-z]{0,3}\d{0,2})\b", re.I)
CPU_INTEL_BARE_RE = re.compile(r"\b([iI][3579])[-\s]?(\d{4,5}[a-zA-Z]{0,3}\d{0,2})\b")
CPU_RYZEN_RE = re.compile(r"\bryzen\s?([3579])\s+(\d{3,4}[a-z]{0,3})\b", re.I)
CPU_RYZEN_AI_RE = re.compile(r"\bryzen\s+ai\s+([3579])\s+(\d{3}[a-z]{0,2})\b", re.I)

RAM_CTX_RE = re.compile(r"(\d{1,3})\s*GB\s*(?:DDR\d?|RAM)\b", re.I)
RAM_LABEL_RE = re.compile(r"\bRAM\b[^0-9]{0,12}(\d{1,3})\s*GB", re.I)

STORAGE_CTX_RE = re.compile(r"(\d{1,4})\s*(GB|TB)\b[^0-9]{0,10}(?:NVMe|SSD|M\.2|PCIe)", re.I)
STORAGE_LABEL_RE = re.compile(r"(?:NVMe|SSD|M\.2|PCIe)[^0-9]{0,10}(\d{1,4})\s*(GB|TB)\b", re.I)
TB_RE = re.compile(r"\b(\d{1,2})\s*TB\b", re.I)
GB_TOKEN_RE = re.compile(r"\b(\d{1,4})\s*(GB|TB)\b", re.I)

HZ_RE = re.compile(r"\b(\d{2,3})\s*Hz\b", re.I)
MEMORY_RE = re.compile(r"\b(?:lp)?ddr\s?([345])(?:x)?\b", re.I)
# Rövidített írásmód: "16G D5", "32G D4"
MEMORY_SHORT_RE = re.compile(r"\b\d{1,3}\s?g\s?d([45])\b", re.I)
NITS_RE = re.compile(r"\b(\d{3,4})\s*(?:nit|nits|cd/m2|cd/m²)\b", re.I)
GAMUT_RE = re.compile(r"\b(\d{2,3})\s*%\s*(srgb|dci-?p3|adobe\s*rgb|ntsc)\b", re.I)
RAM_D5_RE = re.compile(r"\b(\d{1,3})\s?g\s?d[45]\b", re.I)

_INTEL_YEAR = {6: 2016, 7: 2017, 8: 2018, 9: 2019, 10: 2020, 11: 2021, 12: 2022, 13: 2023, 14: 2024}
_AMD_SERIES_YEAR = {3000: 2020, 4000: 2020, 5000: 2021, 6000: 2022, 7000: 2023, 8000: 2024}
_AMD_SHORT_YEAR = {4: 2020, 5: 2021, 7: 2023, 2: 2024, 3: 2025}

# A hirdetésekben gyakori ® ™ © jelek széttörik a mintákat ("Core™ i5-1240P")
_TRADEMARK_RE = re.compile(r"[®™©]")

# Integrált grafikák
IRIS_RE = re.compile(r"\biris\s*xe\b", re.I)
UHD_RE = re.compile(r"\b(?:intel\s+)?uhd\s+graphics\b", re.I)
RADEON_IGPU_RE = re.compile(r"\bradeon\s+(\d{3}m)\b", re.I)
SCREEN_RE = re.compile(
    r"(\d{1,2}(?:[.,]\d)?)\s*(?:\"|”|''|inch\b|hüvelyk\b|col\b|-os\b)", re.I
)

# Modellszámból kiolvasható méret: 15ACH6H, 16IRH8, 15ARH7 (Lenovo-jelölés).
# A kódban kell lennie számjegynek, különben a "16GB" is méretnek látszana.
MODEL_CODE_SIZE_RE = re.compile(r"\b(1[2-7])[A-Z]{2,}\d[A-Z]{0,2}\b", re.I)
# ASUS/ROG jelölés: F15, G15, A15, K15 (a betű és a szám egybe, vagy kötőjellel)
MODEL_LETTER_SIZE_RE = re.compile(r"\b[AFGKM]-?(1[2-7])\b", re.I)
# Családnév + méret: "Zenbook 14", "IdeaPad 5 15", "MacBook Air 13"
_FAMILIES = (
    r"zenbook|vivobook|swift|aspire|ideapad|thinkbook|thinkpad|yoga|pavilion|victus|"
    r"macbook air|macbook pro|legion|loq|katana|cyborg|modern|prestige|stealth|raider|"
    r"zephyrus|strix|tuf|nitro|omen|envy|spectre|surface laptop|gram|expertbook|"
    r"probook|elitebook|precision|latitude|vostro|inspiron|xps"
)
FAMILY_SIZE_RE = re.compile(
    rf"\b(?:{_FAMILIES})\b(?:\s+(?:[a-z]{{1,8}}|\d{{1,2}})){{0,2}}\s+(1[2-7])\b", re.I
)

OLED_RE = re.compile(r"\boled\b", re.I)

# "külföldi / német / US billentyűzet" – ezt ki kell szűrni, ha magyar kell
FOREIGN_KB_RE = re.compile(
    r"(kulfoldi billentyu|nem magyar billentyu|nemet billentyu|us billentyu|"
    r"uk billentyu|angol billentyu|"
    r"\b(?:angol|nemet|francia|olasz|spanyol|orosz|ukran|uk|us|de)\s+kiosztas|"
    r"billentyuzet\s*[:\-]\s*(?:angol|nemet|us|uk|francia|olasz|spanyol|orosz)\b|"
    r"kiosztas\s*:\s*(?:us|uk|de|nemet|angol|kulfoldi))"
)
HU_KB_RE = re.compile(
    r"(magyar billentyu|magyar kiosztas|magyar bill\.|magyar keyboard|"
    r"hun billentyu|hu billentyu|magyarra lezerezve|magyarra lezerezett|"
    r"\bhungarian keyboard\b|\bhungarian layout\b|\bHUN\b)"
)
# Önmagában álló "MAGYAR" csak a hirdetés végén jellemző (pl. "... - MAGYAR"),
# és csak a címben: a leírásban a "Windows 11 Pro - Magyar" az operációs rendszerre utal.
HU_BARE_RE = re.compile(r"\bmagyar\b\s*[.!]?\s*$")

# Csak a már felragasztott matrica számít. A "matricázható" / "matrica szett
# hozzá" NEM: az azt jelenti, hogy a billentyűzet idegen, a matrica külön jár.
HU_STICKER_RE = re.compile(r"\b(?:fel)?matricazott\b|\bmatricazva\b")


@dataclass
class KeyboardInfo:
    layout: str | None = None  # "hu" | "foreign" | None
    source: str | None = None  # "text" | "photo"
    note: str | None = None

STORAGE_VALUES = {120, 128, 240, 256, 320, 480, 500, 512, 640, 750, 1000, 1024, 2048, 4096}
RAM_VALUES = {4, 8, 12, 16, 20, 24, 32, 48, 64, 96, 128}


def norm(text: str) -> str:
    """Kisbetűs, ékezet nélküli, egységes szóközű alak."""
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d")
    return re.sub(r"\s+", " ", text).strip()


def _find_gpus(text: str, limit: int = 3) -> list[str]:
    found: list[str] = []
    for brand, number in GPU_RE.findall(text):
        gpu = f"{brand.lower()} {number.lower()}"
        if gpu not in found:
            found.append(gpu)
    found = found[:limit]

    # Integrált grafikák (Iris Xe, UHD, Radeon 780M)
    if not found:
        if IRIS_RE.search(text):
            found.append("iris xe")
        elif UHD_RE.search(text):
            found.append("uhd graphics")
        else:
            match = RADEON_IGPU_RE.search(text)
            if match:
                found.append(f"radeon {match.group(1).lower()}")

    return found


def _find_cpu(text: str) -> str | None:
    """A legkorábban előforduló CPU-jelöltet adja vissza.

    Sorrend helyett pozíció számít: egy bolt-hirdetés leírásában sok gép
    szerepel, és az első említés a hirdetett gép.
    """
    candidates: list[tuple[int, str]] = []

    match = (
        CPU_ULTRA_RE.search(text)
        or CPU_ULTRA_SHORT_RE.search(text)
        or CPU_INTEL_NUM_RE.search(text)
    )
    if match:
        candidates.append((match.start(), f"ultra {match.group(1)} {match.group(2).upper()}"))

    match = CPU_RYZEN_AI_RE.search(text)
    if match:
        candidates.append((match.start(), f"ryzen ai {match.group(1)} {match.group(2).upper()}"))

    match = CPU_INTEL_RE.search(text)
    if match:
        candidates.append((match.start(), f"{match.group(1).lower()}-{match.group(2).upper()}"))

    match = CPU_INTEL_BARE_RE.search(text)
    if match:
        candidates.append((match.start(), f"{match.group(1).lower()}-{match.group(2).upper()}"))

    match = CPU_RYZEN_RE.search(text)
    if match:
        candidates.append((match.start(), f"ryzen {match.group(1)} {match.group(2).upper()}"))

    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]


def _context_ok(text: str, start: int, end: int) -> bool:
    """Kiszűri a 'max 32 GB-ig bővíthető' típusú csapdákat."""
    before = norm(text[max(0, start - 25) : start])
    after = norm(text[end : end + 14])
    if re.search(r"(bovithet|tamogat|max|maximum)[^0-9]{0,12}$", before):
        return False
    if re.search(r"^\s*-?\s*ig\b", after):
        return False
    return True


def _find_ram(text: str, title: str) -> int | None:
    # "16G D5" / "32G D4" – a memória típusa egyértelműsíti
    match = RAM_D5_RE.search(text)
    if match:
        value = int(match.group(1))
        if 4 <= value <= 256:
            return value
    for regex in (RAM_CTX_RE, RAM_LABEL_RE):
        for match in regex.finditer(text):
            if not _context_ok(text, match.start(), match.end()):
                continue
            value = int(match.group(1))
            if 1 <= value <= 256:
                return value
    # tartalék: "16GB / 512GB" típusú címek
    tokens = [
        (int(m.group(1)), m.group(2).upper(), m.start(), m.end())
        for m in GB_TOKEN_RE.finditer(title)
    ]
    tokens = [t for t in tokens if _context_ok(title, t[2], t[3])]
    for value, unit, _, _ in tokens:
        if unit == "GB" and value in RAM_VALUES:
            # ha van mellette nagyobb tároló token, ez a RAM
            if any(u == "TB" or (u == "GB" and v >= 240) for v, u, _, _ in tokens):
                return value
    return None


def _find_storage(text: str, title: str) -> int | None:
    for regex in (STORAGE_CTX_RE, STORAGE_LABEL_RE, TB_RE):
        for match in regex.finditer(text):
            if not _context_ok(text, match.start(), match.end()):
                continue
            value = int(match.group(1))
            unit = match.group(2).upper() if match.lastindex and match.lastindex >= 2 else "TB"
            return value * 1024 if unit == "TB" else value
    # tartalék: címben "32GB 1TB" vagy "16GB/512GB"
    tokens = [
        (int(m.group(1)), m.group(2).upper(), m.start(), m.end())
        for m in GB_TOKEN_RE.finditer(title)
    ]
    tokens = [t for t in tokens if _context_ok(title, t[2], t[3])]
    for value, unit, _, _ in tokens:
        if unit == "TB":
            return value * 1024
    for value, unit, _, _ in tokens:
        if unit == "GB" and value in STORAGE_VALUES and value >= 240:
            return value
    # rövidítés: "512G", "1T" (csak tárolásra jellemző méretnél)
    for match in re.finditer(r"\b(\d{2,4})\s?g\b", title, re.I):
        value = int(match.group(1))
        if value in STORAGE_VALUES and value >= 240:
            return value
    return None


def _find_screen(text: str, allow_model_heuristics: bool = True) -> float | None:
    # 1) kifejezett hüvelyk: 15,6", 14 col, 16 hüvelyk, 14"-os
    for match in SCREEN_RE.finditer(text):
        raw = match.group(1).replace(",", ".")
        try:
            value = float(raw)
        except ValueError:  # pragma: no cover
            continue
        if 10.0 <= value <= 20.0:
            return value

    # A modell-alapú tippek (15ACH6H, F15, "MacBook Pro 15") csak a címre
    # érvényesek: egy bolt leírásában más gyártók gépei is szerepelnek.
    if not allow_model_heuristics:
        return None

    # 2) Lenovo-szerű modellszám: 15ACH6H, 16IRH8
    match = MODEL_CODE_SIZE_RE.search(text)
    if match:
        return float(match.group(1))

    # 3) ASUS/ROG betű+szám: F15, G15, A15
    match = MODEL_LETTER_SIZE_RE.search(text)
    if match:
        return float(match.group(1))

    # 4) családnév + méret: "Zenbook 14", "IdeaPad 5 15", "MacBook Air 13"
    match = FAMILY_SIZE_RE.search(text)
    if match:
        return float(match.group(1))

    return None


def _find_refresh(text: str) -> int | None:
    values = [int(m) for m in HZ_RE.findall(text)]
    values = [v for v in values if 30 <= v <= 540]
    return max(values) if values else None


def _has_warranty(text: str) -> bool:
    n = norm(text)
    if not re.search(r"garanci|(?:^|\W)gari\b", n):
        return False
    return not re.search(r"(garanci\w*|gari)\s*nelkul", n)


def _is_new(text: str) -> bool:
    n = norm(text)
    if "bontatlan" in n or "vadonatuj" in n or "uj, bontatlan" in n:
        return True
    if "uj ara" in n or "ujkori ar" in n:
        return False
    return bool(re.search(r"\buj\b", n))


def _find_keyboard(text: str, title: str | None = None) -> KeyboardInfo:
    n = norm(text)
    # 1) Kifejezetten magyar billentyűzet
    if HU_KB_RE.search(n):
        return KeyboardInfo("hu", "text")
    # 2) Felragasztott magyar matrica (a "matricázható" nem számít)
    if HU_STICKER_RE.search(n):
        return KeyboardInfo("hu", "text", "matricás")
    # 3) Kifejezetten külföldi – erősebb, mint a leírásban szereplő "magyar"
    #    (pl. "Windows 11 Pro - Magyar" mellett "Billentyűzet: UK")
    if FOREIGN_KB_RE.search(n):
        return KeyboardInfo("foreign", "text")
    # 4) Önmagában "MAGYAR" csak a cím végén számít
    if title and HU_BARE_RE.search(norm(title)):
        return KeyboardInfo("hu", "text")
    return KeyboardInfo()


def _memory_gen(text: str) -> int | None:
    gens = [int(value) for value in MEMORY_RE.findall(text)]
    gens += [int(value) for value in MEMORY_SHORT_RE.findall(text)]
    return max(gens) if gens else None


def _cpu_year(cpu: str | None) -> int | None:
    """A processzor platformjának hozzávetőleges éve (DDR5 korszak >= 2022)."""
    if not cpu:
        return None
    n = norm(cpu)

    if n.startswith("ultra"):
        match = re.search(r"\b(\d{3})", n)
        if match:
            return {1: 2024, 2: 2025, 3: 2026}.get(int(match.group(1)[0]))
        return None

    if n.startswith(("i3", "i5", "i7", "i9")):
        match = re.search(r"i[3579][-\s]?(\d{4,5}[a-z]{0,3}\d{0,2})", n)
        if not match:
            return None
        lead = re.match(r"\d+", match.group(1))
        if not lead:
            return None
        digits = lead.group(0)
        if len(digits) >= 5 or digits.startswith("1"):
            generation = int(digits[:2])
        else:
            generation = int(digits[0])
        return _INTEL_YEAR.get(generation)

    if n.startswith("ryzen"):
        if "ai" in n:
            return 2025
        numbers = re.findall(r"\d{3,4}", n)
        if not numbers:
            return None
        number = int(numbers[0])
        if number >= 1000:
            return _AMD_SERIES_YEAR.get((number // 1000) * 1000)
        return _AMD_SHORT_YEAR.get(int(str(number)[0]))

    return None


def extract(text: str, title: str | None = None) -> Specs:
    """Specifikációk kinyerése a címből + leírásból."""
    text = _TRADEMARK_RE.sub("", text)
    title = _TRADEMARK_RE.sub("", title if title is not None else text)
    keyboard = _find_keyboard(text, title)
    # A cím a legmegbízhatóbb: bolt-hirdetések leírásában sok más gép szerepel.
    cpu = _find_cpu(title) or _find_cpu(text)
    gpus = _find_gpus(title) or _find_gpus(text)
    screen = _find_screen(title) or _find_screen(text, allow_model_heuristics=False)
    storage = _find_storage(title, title) or _find_storage(text, title)
    ram = _find_ram(title, title) or _find_ram(text, title)

    nits_match = NITS_RE.search(text)
    gamut_match = GAMUT_RE.search(text)
    nits = int(nits_match.group(1)) if nits_match else None
    gamut: str | None = None
    if gamut_match:
        gamut_name = gamut_match.group(2)
        gamut_name = "sRGB" if gamut_name.lower() == "srgb" else gamut_name.upper()
        gamut = f"{gamut_match.group(1)}% {gamut_name}"

    return Specs(
        gpus=gpus,
        cpu=cpu,
        cpu_year=_cpu_year(cpu),
        memory_gen=_memory_gen(text),
        nits=nits,
        gamut=gamut,
        ram_gb=ram,
        storage_gb=storage,
        refresh_hz=_find_refresh(text),
        screen_inch=screen,
        oled=bool(OLED_RE.search(text)),
        keyboard=keyboard.layout,
        keyboard_source=keyboard.source,
        keyboard_note=keyboard.note,
        is_new=_is_new(text),
        warranty=_has_warranty(text),
    )


def brand(text: str) -> str | None:
    """Márka a címből (a medián-csoportosításhoz)."""
    n = norm(text)
    known = [
        "lenovo", "asus", "acer", "hp", "dell", "msi", "apple", "macbook",
        "razer", "gigabyte", "samsung", "huawei", "xiaomi", "microsoft",
        "surface", "toshiba", "fujitsu", "clevo", "xmg", "framework",
    ]
    for name in known:
        if re.search(rf"\b{name}\b", n):
            return name
    return None
