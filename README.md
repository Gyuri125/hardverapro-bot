# apro-deal-radar 🎯

Hardverapró figyelő, ami **naponta 3x** végignézi a hirdetéseket, kiszűri a
számodra érdekes, **jó árú laptopokat**, és **Discordra** küldi őket.

Nem kell szervert futtatni: a **GitHub Actions** végzi a munkát ingyen, a
beállítás pedig egyetlen `config.yaml` fájl.

```
GitHub Actions (cron 3x/nap)
        │
        ├─ Hardverapró kategóriaoldalak letöltése (udvarias, 1.5s szünet)
        ├─ hirdetések szűrése (ár, tiltott szavak, eladó, hely)
        ├─ részoldalak letöltése a jelöltekhez (leírás, állapot, gari)
        ├─ hardver kinyerése: CPU / GPU / RAM / SSD / Hz
        ├─ pontozás: profil-egyezés + ár-előny + felszereltség
        ├─ duplikátum-szűrés (state/seen.json)
        └─ Discord webhook
```

---

## Mit tud

- **Profilok**: megmondod, mi érdekel (pl. „Legion 5, RTX 4060/4070, max 430 eFt”),
  a program csak azokat küldi.
- **Ékezet-független** keresés: a „hibás” szűrő a „HIBAS”-t is elkapja.
- **Piaci medián**: a futás során látott hirdetésekből számol árszintet
  GPU-osztályonként, és jelzi, ha valami feltűnően olcsó.
- **Részoldal-elemzés**: a leírásból is kiszedi a RAM/SSD/GPU/garancia adatokat,
  és a leírásban szereplő „hibás / törött / javított” szavakra is szűr.
- **Nincs spam**: amit már elküldött, azt nem küldi újra (kivéve, ha az ára
  jelentősen lecsökkent).
- **Pontszám 0–100**: látod, mennyire jó az adott ajánlat.
- **Tesztelt**: 62 unit teszt, valódi Hardverapró HTML-lel.

---

## Telepítés GitHubra (5 perc)

### 1. Repo létrehozása

Hozz létre egy **private** repót GitHubon (a webhook secret miatt a private a
biztonságosabb, de a kód maga nyilvános is lehet), majd:

```bash
cd apro-deal-radar
git init -b main
git add .
git commit -m "apro-deal-radar: első verzió"
git remote add origin https://github.com/<FELHASZNÁLÓ>/apro-deal-radar.git
git push -u origin main
```

### 2. Discord webhook

1. Discord → a csatorna → **Beállítások → Integrációk → Webhookok → Új webhook**
2. Másold ki a webhook URL-t.
3. **Fontos:** a korábban chatben elküldött webhookot generáld újra
   (ugyanott: *Webhook szerkesztése → Új token*), mert aki látta, az is tud rá írni.

### 3. Secret beállítása

GitHubon: **Settings → Secrets and variables → Actions → New repository secret**

- Name: `DISCORD_WEBHOOK_URL`
- Secret: a webhook URL

> A webhook URL **soha** ne kerüljön a kódba vagy a `config.yaml`-ba. A program
> kizárólag a `DISCORD_WEBHOOK_URL` környezeti változóból olvassa.

### 4. Első próba

**Actions → Hardverapró deal radar → Run workflow**

- először kapcsold be a `test_webhook`-öt → meg kell érkeznie a tesztüzenetnek
- utána `dry_run = true` → csak a logban látod a találatokat
- végül üresen futtasd → mennek a valódi értesítések

### 5. Kész

A cron ütemezés a `main` branch-en automatikusan él:
`10 5,11,17 * * *` (UTC) ≈ 06:10, 12:10, 18:10 budapesti idő.

---

## Helyi futtatás

```bash
python -m pip install -r requirements.txt

# csak kiírja, nem küldi el
python -m dealradar --dry-run

# egy oldal, gyors próba
python -m dealradar --dry-run --max-pages 1

# minden találat pontszámmal (hangoláshoz)
python -m dealradar --dry-run --show-all --max-pages 2

# tesztüzenet a webhookra
$env:DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/..."
python -m dealradar --test-webhook

# tesztek
python -m pytest -q
```

Hasznos kapcsolók:

| Kapcsoló | Mit csinál |
|---|---|
| `--dry-run` | nem küld Discordra, csak listáz |
| `--max-pages N` | felülírja a `max_pages` értéket |
| `--watch "notebook"` | csak az egyik figyelőt futtatja |
| `--show-all` | a küszöb alatti találatokat is kiírja |
| `--cache` | a letöltött HTML-t a `.cache/`-ba menti |
| `-v` | részletes napló |

---

## Konfiguráció (`config.yaml`)

### `settings`

| Kulcs | Alap | Jelentés |
|---|---|---|
| `request_delay` | `1.5` | másodperc kérések között (a robots.txt `crawl-delay: 1`) |
| `min_score` | `50` | ez alatt nem küld értesítést |
| `max_notifications` | `20` | egy futásban max. ennyi üzenet |
| `deep_scan` | `true` | töltsön-e részoldalakat a jelöltekhez |
| `deep_scan_limit` | `40` | max. ennyi részoldal / futás |
| `state_retention_days` | `60` | ennyi után felejti el a látott hirdetéseket |
| `renotify_price_drop_percent` | `10` | ennyi árcsökkenésnél újra szól (0 = soha) |
| `webhook_env` | `DISCORD_WEBHOOK_URL` | a webhookot tartalmazó env változó neve |

### `watches` – hol keress

```yaml
watches:
  - name: "Notebook"
    url: "https://hardverapro.hu/aprok/notebook/index.html"
    max_pages: 3
    filters:
      min_price: 80000
      max_price: 600000
      exclude_keywords: [alkatrész, hibás, törött, javított]
      exclude_promoted: true     # fizetett "Előresorolva" hirdetések kihagyása
      allow_business: true       # bolti eladók engedélyezése
      min_seller_rating: 0       # csak nem-negatív értékelésű eladóktól
      locations: []              # pl. [budapest, debrecen] – üresen országos
```

Bármilyen Hardverapró kategória-URL működik, pl.
`https://hardverapro.hu/aprok/hardver/videokartya/index.html`.
A lapozás automatikus (`?offset=100`, `?offset=200`, …).

### `profiles` – mi számít jó dealnek

```yaml
profiles:
  - name: "Legion 5 – jó ár"
    any_keywords: ["legion 5", "legion5"]   # legalább egy kell
    all_keywords: []                         # mindegyik kell
    none_keywords: ["hibás", "törött"]       # egyik sem lehet
    min_price: 120000
    max_price: 430000                        # ennél drágábbat nem küld
    deal_price: 340000                       # ez alatt "igazi vétel"
    specs:
      gpu_any: ["3060", "4060", "4070"]
      cpu_any: ["i7-14700", "ryzen 7 5800"]
      min_ram_gb: 16
      min_storage_gb: 512
      min_refresh_hz: 0
```

Ha egy adat (pl. RAM) nem derül ki a szövegből, az **nem** utasítja el a
hirdetést – csak nem ad plusz pontot. A `gpu_any` viszont szigorú: ha nincs
felismerhető GPU, a profil nem illeszkedik.

### `market_compare` – piaci medián

```yaml
market_compare:
  enabled: true
  group_by: gpu            # gpu | cpu | brand
  min_samples: 10          # ennyi hirdetés alatt nem számol
  good_deal_discount: 0.20 # 20% medián alatt = jó deal
```

Így nem kell minden árat kézzel belőni: a program a frissen látott
hirdetésekből számol szintet, és ahhoz viszonyít.

---

## Hogyan jön ki a pontszám?

| Pont | Miért |
|---|---|
| 35 | illeszkedik a profilra |
| 0–40 | mennyivel van a célár (`deal_price`) alatt; 25%-os kedvezmény = max |
| 0–25 | felszereltség: 32 GB RAM, 1 TB SSD, 165 Hz, erős GPU, garancia, „új” |

`min_score: 50` azt jelenti: profil-egyezés + valami érdemi előny.
Ha túl kevés jön, vidd lejjebb 40-re; ha túl sok a szemét, emeld 60-ra.

---

## Etikett és korlátok

- A program **nem lép be** a Hardverapróra, csak a nyilvános oldalakat olvassa.
- A robots.txt `crawl-delay: 1` előírását betartja (alapból 1,5 s szünet).
  Ne vidd 1 alá a `request_delay`-t.
- A `keres.php?offset=` lapozást a robots.txt tiltja – a program ezért
  kategóriaoldalakon lapoz (`index.html?offset=`), ami engedélyezett.
- Napi 3 futás, futásonként néhány oldal: ez bőven a tisztességes használat.
- Ha a Hardverapró átalakítja a HTML-t, a `tests/fixtures/` alapján gyorsan
  javítható a parser (a tesztek azonnal jelzik).

---

## Projektstruktúra

```
apro-deal-radar/
├─ config.yaml                 # minden beállítás
├─ dealradar/
│  ├─ cli.py                   # futtatás, összefoglaló
│  ├─ config.py                # YAML betöltés + validálás
│  ├─ fetch.py                 # udvarias HTTP, retry, cache
│  ├─ parse.py                 # Hardverapró HTML -> Listing
│  ├─ specs.py                 # CPU/GPU/RAM/SSD/Hz kinyerése
│  ├─ rules.py                 # szűrés, profil, medián, pontozás
│  ├─ state.py                 # látott hirdetések (dedupe)
│  └─ notify.py                # Discord embed + küldés
├─ tests/                      # 62 teszt, valódi HTML fixture-ökkel
├─ .github/workflows/radar.yml # a cron + futtatás
└─ state/seen.json             # automatikusan commitolva futás után
```

---

## Gyakori kérdések

**Miért nem küld semmit?**
Nézd meg a logot: lehet, hogy minden találat `min_score` alatt van, vagy már
minden ismert (`state/seen.json`). Próbáld `--show-all`-lal.

**Elveszett a state / mindent újra akarok kapni?**
Töröld a `state/seen.json`-t és commitold.

**Szeretnék több kategóriát?**
Vegyél fel még egy elemet a `watches` alá ugyanazzal a `filters`-szal.

**Működik más ország oldalaival?**
A parser Hardverapró-specifikus, de a `parse.py` egy helyen van, így egy másik
oldalhoz csak azt kell újraírni.
