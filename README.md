# hardverapro-bot

[![CI](https://github.com/Gyuri125/hardverapro-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/Gyuri125/hardverapro-bot/actions/workflows/ci.yml)
[![Deal radar](https://github.com/Gyuri125/hardverapro-bot/actions/workflows/radar.yml/badge.svg)](https://github.com/Gyuri125/hardverapro-bot/actions/workflows/radar.yml)
![Python](https://img.shields.io/badge/python-3.12-3776AB)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Serverless deal scanner for [Hardverapró](https://hardverapro.hu), the largest
Hungarian classifieds marketplace.

The bot runs on GitHub Actions three times a day, scores new laptop listings
against configurable buyer profiles, enriches the shortlisted ads with hardware
specifications and PassMark benchmarks, and delivers the matches to Discord.

No server, no database, no paid infrastructure. The only credential is a Discord
webhook, stored as a GitHub Actions secret.

---

## Table of contents

- [How it works](#how-it-works)
- [Example notification](#example-notification)
- [Features](#features)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [Local development](#local-development)
- [Testing](#testing)
- [Data sources and rate limits](#data-sources-and-rate-limits)
- [Design notes](#design-notes)
- [Limitations](#limitations)
- [License](#license)
- [Magyar összefoglaló](#magyar-összefoglaló)

---

## How it works

```
GitHub Actions (cron: 3 times a day)
   |
   +-- fetch public category pages ......... dealradar/fetch.py
   +-- parse listing cards ................. dealradar/parse.py
   +-- hard filters (price, keywords,
   |   seller, keyboard layout) ............ dealradar/rules.py
   +-- deep scan shortlisted ads
   |   (description, condition, shipping) .. dealradar/parse.py
   +-- extract hardware specs .............. dealradar/specs.py
   +-- match buyer profiles, score 0-100 ... dealradar/rules.py
   +-- de-duplicate against committed state . dealradar/state.py
   +-- enrich with PassMark scores ......... dealradar/benchmarks.py
   +-- post embeds to Discord .............. dealradar/notify.py
```

| Stage | Module | Responsibility |
| --- | --- | --- |
| Collection | `fetch.py` | Polite HTTP client: 1.5 s delay between requests, retries with exponential backoff, optional disk cache |
| Parsing | `parse.py` | Listing cards and detail pages to `Listing` objects |
| Specification extraction | `specs.py` | CPU, GPU, RAM, storage, refresh rate, screen size, OLED, keyboard layout, warranty, condition |
| Evaluation | `rules.py` | Hard filters, profile matching, market median, 0-100 score |
| State | `state.py` | JSON of already-notified ads, committed back to the repository |
| Enrichment | `benchmarks.py` | PassMark CPU Mark and G3D Mark lookups, best effort |
| Delivery | `notify.py` | Discord embeds with clickable links, rate-limit handling |

The pipeline is deliberately linear: every stage is a pure function over data,
which keeps the whole thing testable without network access.

## Example notification

```
Lenovo Legion 5 15ACH6H / RTX 4060 / i7-14700HX / 32 GB / 1 TB

32 GB RAM · 1 TB SSD · 165 Hz · garanciás · használt · csomagküldés

Ár: 349 000 Ft      Célár: 390 000 Ft      Pontszám: 78/100

Processzor                 Videokártya                Billentyűzet
i7-14700HX [1]             RTX 4060 [2]               nem derül ki
CPU Mark: 36 314 [3]       G3D Mark: 17 306           kérdezz rá az eladónál

Hely: Budapest, XI. ker.   Eladó: +22                 Specifikáció [4]
Miért jó: ár 10%-kal a célár alatt · 32 GB RAM · 165 Hz

[1] Intel / AMD product search
[2] PassMark GPU page (laptop variant)
[3] PassMark CPU page
[4] Model specification search
```

Keyboard layout is reported in three states:

| Value | Meaning |
| --- | --- |
| `magyar` | The ad states a Hungarian keyboard |
| `nem derül ki` | Not mentioned; the buyer has to ask |
| `külföldi` | Explicitly foreign; filtered out before scoring |

## Features

- **Profile-based matching.** Keywords, GPU/CPU allow-lists, minimum RAM and
  storage, price bands, per-profile target price.
- **Accent-insensitive Hungarian matching.** `hibas`, `hibás` and `HIBÁS` are
  the same token.
- **Description-level scan.** Shortlisted ads are opened to read the description,
  so defects ("törött", "javított", "vízkár") and specifications that only appear
  in the body text are caught.
- **Market-relative pricing.** Besides the manual target price, the bot computes a
  median price per GPU class from the current snapshot and rewards listings that
  sit well below it.
- **Benchmark enrichment.** PassMark CPU Mark for the processor and G3D Mark for
  the laptop GPU variant, with a graceful fallback when the source is unavailable.
- **Hardware-aware filtering.** Screen size (four detection methods), keyboard
  layout (HU / foreign / unknown), OLED, warranty and condition.
- **Duplicate suppression.** A JSON state file records what has already been
  sent; a significant price drop re-notifies.
- **No server.** Scheduling, execution and persistence are all handled by GitHub
  Actions and the repository itself.
- **Self-check.** `--self-check` validates the configuration, the Discord webhook
  and access to Hardverapró in a few seconds. On GitHub Actions it emits
  annotations, so a failing run explains itself on the summary page instead of
  hiding the reason in the log.

## Configuration

Everything lives in [`config.yaml`](config.yaml). The file is annotated in
Hungarian, since it describes Hungarian marketplace categories and filters.

### `settings`

| Key | Default | Description |
| --- | --- | --- |
| `request_delay` | `1.5` | Seconds between HTTP requests (robots.txt asks for 1) |
| `timeout` / `retries` | `20` / `3` | HTTP behaviour |
| `min_score` | `50` | Minimum score to notify |
| `max_notifications` | `15` | Per-run message cap |
| `deep_scan` | `true` | Open candidate ads for description parsing |
| `deep_scan_limit` | `40` | Maximum detail pages per run |
| `state_file` | `state/seen.json` | Persistence path |
| `state_retention_days` | `60` | How long to remember seen ads |
| `renotify_price_drop_percent` | `10` | Re-notify on a price drop of this size |
| `webhook_env` | `DISCORD_WEBHOOK_URL` | Environment variable holding the webhook |

### `watches`

A watch is a category URL plus hard filters.

```yaml
watches:
  - name: "Notebook"
    url: "https://hardverapro.hu/aprok/notebook/index.html"
    max_pages: 3
    filters:
      min_price: 80000
      max_price: 500000
      exclude_keywords: [alkatrész, hibás, törött, javított]
      keyboard: hu
      exclude_promoted: true
      allow_business: true
      min_seller_rating: 0
      locations: []
```

Filter reference:

| Key | Description |
| --- | --- |
| `min_price` / `max_price` | Absolute price band |
| `include_keywords` | At least one must appear |
| `exclude_keywords` | None may appear (title and description) |
| `keyboard` | `hu` rejects explicitly foreign layouts; unknown values pass |
| `min_screen_inch` | Minimum screen size in inches (0 = no limit) |
| `screen_unknown` | `reject` drops ads where the size cannot be determined |
| `exclude_promoted` | Skip paid "Előresorolva" placements |
| `allow_business` | Whether shop sellers are allowed |
| `min_seller_rating` | Minimum seller reputation |
| `locations` | Optional county/city allow-list |

### `profiles`

A profile defines what counts as a good deal. A listing is evaluated against
every profile and the highest score wins.

```yaml
profiles:
  - name: "Sweet spot - RTX 4070 / 5050 / 5060 / 5070, under 450k"
    any_keywords: []
    all_keywords: []
    none_keywords: [alkatrész, hibás, törött]
    min_price: 150000
    max_price: 450000
    deal_price: 390000
    specs:
      gpu_any: ["4070", "5050", "5060", "5070"]
      min_ram_gb: 16
      min_storage_gb: 512
      strict: false
```

`strict: true` means that a required specification must be recognised; the
default (`false`) treats unknown values as "not disqualifying".

### Scoring

| Points | Source |
| --- | --- |
| 0-40 | Profile match (base) |
| 0-45 | Price advantage versus the target price or market median; 20% below target is full marks, and a price at the target still scores |
| 0-20 | Hardware: 32 GB RAM, 1 TB SSD, 165 Hz, GPU tier, OLED, warranty, Hungarian keyboard |

Anything at or above `min_score` is delivered. The score is a prioritisation
heuristic, not an appraisal.

## Deployment

### 1. Discord webhook

Create a webhook for the target channel (Channel settings, Integrations,
Webhooks) and copy the URL.

### 2. Repository secret

Settings, Secrets and variables, Actions, New repository secret:

- Name: `DISCORD_WEBHOOK_URL`
- Value: the webhook URL

The webhook is read from the environment only. It is never written to the
repository, and `.env` is excluded by `.gitignore`.

### 3. First run

Actions, "Hardverapró deal radar", Run workflow:

1. `test_webhook = true` sends a single test message.
2. `dry_run = true` prints the matches without sending anything.
3. An empty run is the real thing.

### 4. Schedule

`.github/workflows/radar.yml` runs at `15 4,9,14,19 * * *` UTC, which is roughly
05:15, 10:15, 15:15 and 20:15 in Budapest. A second schedule at `45` past the same
hours acts as a fallback: GitHub's scheduler is best-effort and occasionally skips
a slot, and the de-duplication state makes a redundant run harmless.

The run commits the updated `state/seen.json` back to the repository. If that
step fails, enable Settings, Actions, General, Workflow permissions, "Read and
write permissions".

## Local development

```bash
python -m pip install -r requirements.txt

cp .env.example .env          # then paste the webhook URL
python -m dealradar --dry-run --max-pages 1
python -m dealradar --dry-run --show-all --max-pages 2
python -m dealradar --test-webhook
```

Useful flags:

| Flag | Effect |
| --- | --- |
| `--dry-run` | Print matches, send nothing |
| `--show-all` | Print every scored match, including below the threshold |
| `--max-pages N` | Override pages per watch |
| `--watch NAME` | Run a single watch |
| `--cache` | Cache downloaded HTML in `.cache/` |
| `--self-check` | Validate the config, the Discord webhook and access to Hardverapró without scanning |
| `-v` | Debug logging |

`--show-all` is the main tuning tool: it shows whether nearby candidates land at
45-49 points (lower `min_score`) or whether the profile is simply wrong.

## Testing

```bash
python -m pytest -q
```

The suite covers parsing, specification extraction, profile matching, scoring,
market medians, state handling and embed construction. HTML fixtures are real
snapshots of Hardverapró pages, so a markup change breaks the tests before it
breaks the bot. No network access is required.

## Data sources and rate limits

- **Hardverapró.** Public category pages only. The client respects
  `crawl-delay: 1` and never uses the paginated search endpoint, which
  `robots.txt` disallows. A run touches 3 category pages and up to 40 ad pages.
- **PassMark.** One request per distinct CPU or GPU among the notified ads,
  normally a handful per run. If the site is unavailable, scores are omitted and
  the notification still goes out.
- **Specification link.** A Google search for the model, because manufacturer
  URLs differ per brand and per generation.

## Design notes

**Why GitHub Actions.** The workload is a few dozen HTTP requests three times a
day. A cron job on a server would cost money and attention; Actions provides
both for free on public repositories.

**Why no database.** The only state is "which ads have been seen". A JSON file
committed by the workflow is sufficient, survives runner recycling, and makes
the state inspectable and diffable in the repository history. Actions cache is
evicted and would re-notify.

**Why fixtures instead of live tests.** Scrapers break silently. Committing real
HTML snapshots means the parser is tested against the actual markup, and a test
failure points directly at the broken selector.

**Why "unknown" is not "no".** Most ads omit half of the specifications. Treating
missing RAM as disqualifying would remove most of the market, so optional specs
only add points. Profiles that depend entirely on specifications (for example
"32 GB + 1 TB") use `strict: true` to require them.

**Why the score is relative.** Absolute prices age badly. The bot combines a
hand-set target price with a median computed from the current snapshot, so it
adapts to the market without retraining or a price database.

## Limitations

- The parser is tied to Hardverapró's markup. Selectors live in `parse.py` and
  are covered by fixtures.
- Hungarian market only; the text normalisation and filters assume Hungarian.
- No authentication is used. Only publicly visible pages are read.
- The score is a heuristic. It narrows the list; it does not replace checking the
  ad, the seller's history and the machine itself.
- Not affiliated with Hardverapró or PROHARDVER Informatikai Kft.

## License

[MIT](LICENSE)

---

## Magyar összefoglaló

A `hardverapro-bot` egy Hardverapró-figyelő, ami GitHub Actionsön fut naponta
háromszor, és Discordra küldi a beállított szempontok szerint jó árúnak számító
laptopokat. A hirdetésekből kinyeri a processzort, videokártyát, memóriát,
tárolót, kijelzőt és a billentyűzet kiosztását, PassMark-pontszámot rendel a
CPU-hoz és a GPU-hoz, majd 0-100 közötti pontszámmal rangsorolja őket.

A beállítás a `config.yaml` fájlban van: milyen kategóriát figyeljen, milyen
szavakat zárjon ki, mekkora az árplafon, és mely hardver-kombinációk számítanak
jó dealnek. A már elküldött hirdetéseket a `state/seen.json` tartja nyilván,
amit a workflow minden futás után visszakommitol.

Helyi futtatás: `.env` fájlba másolt webhook URL, majd
`python -m dealradar --dry-run`.
