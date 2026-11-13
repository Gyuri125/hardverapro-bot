from dealradar.specs import brand, extract, norm

LEGION_DETAIL = """
Kihasználatlanság miatt eladó prémium gamer laptopom.
Processzor: Intel Core i7-14700HX (20 mag, max. 5.5 GHz)
Videókártya: NVIDIA GeForce RTX 5050 (8GB GDDR7)
Memória: 32 GB DDR5 RAM (5600 MHz)
Háttértár: 1 TB NVMe SSD
Kijelző: 15.1" WQXGA (2560x1600), 165 Hz
Garancia: 2028.11.13 ig
"""


def test_extract_full_listing():
    specs = extract(LEGION_DETAIL, "Eladó Csúcskategóriás Gamer Laptop – Lenovo Legion 5")
    assert specs.gpus == ["rtx 5050"]
    assert specs.cpu == "i7-14700HX"
    assert specs.ram_gb == 32
    assert specs.storage_gb == 1024
    assert specs.refresh_hz == 165
    assert specs.screen_inch == 15.1
    assert specs.warranty is True


def test_extract_slash_title():
    title = "Lenovo Legion 5 15ACH6H / Ryzen 7 5800H / 16GB / 512GB / RTX 3060"
    specs = extract(title)
    assert specs.cpu == "ryzen 7 5800H"
    assert specs.ram_gb == 16
    assert specs.storage_gb == 512
    assert specs.gpus == ["rtx 3060"]
    assert specs.gpu_tier == 2


def test_extract_title_without_slashes():
    title = "ASUS ROG Strix G15 i7-10750H 16GB 512GB SSD RTX 2070 144Hz"
    specs = extract(title)
    assert specs.cpu == "i7-10750H"
    assert specs.ram_gb == 16
    assert specs.storage_gb == 512
    assert specs.refresh_hz == 144


def test_gpu_variants():
    assert extract("RTX4060 laptop").gpus == ["rtx 4060"]
    assert extract("Geforce RTX 4070 8GB").gpus == ["rtx 4070"]
    assert extract("Radeon RX 7800 XT").gpus == ["rx 7800"]
    assert extract("Intel Arc A770").gpus == ["arc a770"]


def test_new_detection():
    assert extract("Lenovo Legion 5, ÚJ, bontatlan").is_new is True
    assert extract("Lenovo Legion 5 újszerű állapot").is_new is False
    assert extract("Legion 5, ÚJ ÁRA 500.000 felett volt").is_new is False


def test_warranty_detection():
    assert extract("1 év garancia, számla").warranty is True
    assert extract("garancia nélkül, ahogy van").warranty is False
    assert extract("gari nélkül").warranty is False
    assert extract("Lenovo Legion 5").warranty is False


def test_ram_and_storage_not_confused():
    specs = extract("Legion 5 Pro 16GB RAM 1TB SSD")
    assert specs.ram_gb == 16
    assert specs.storage_gb == 1024

    specs = extract("Dell XPS 32GB DDR5 2TB NVMe")
    assert specs.ram_gb == 32
    assert specs.storage_gb == 2048


def test_brand_detection():
    assert brand("Lenovo Legion 5 15ACH6H") == "lenovo"
    assert brand("ASUS ROG Strix G15") == "asus"
    assert brand("Valami ismeretlen gép") is None


def test_norm_is_accent_insensitive():
    assert norm("Hibás TÖRÖTT") == "hibas torott"
    assert norm("  sok   szóköz  ") == "sok szokoz"
