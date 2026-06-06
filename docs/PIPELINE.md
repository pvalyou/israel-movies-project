# Israeli Film Industry — Data Pipeline

## Overview

The pipeline collects data from public websites of Israeli film funds, festivals, and institutions, extracts structured entities via LLM, resolves duplicates across sources, and generates an investigative HTML report of conflicts of interest.

```
Web sources
    │
    ▼
scrape.py ──────────────────────► sources/<src>/pages/
                                     *.md  (page content)
                                     *.meta.json  (URL, fetch date, hash)
    │
    ▼
pdf_to_pages.py  (PDFs/DOCX only)
    │
    ▼
llm_extract.py ─────────────────► out/<src>/mentions.jsonl
                                     one JSON line per scraped page
    │
    ▼
enrich_mentions.py  (in-place)
    │
    ▼
resolve_entities.py ────────────► connections_report.html
                                  connections_report.xlsx
                                  entity_registry.json  (intermediate)
```

---

## Step 1 — Scraping (`scrape.py`)

Sends URLs to the `crawl4ai-wrapper` cloud service, which fetches pages and returns Markdown. Results are saved as file pairs:

| File | Contents |
|---|---|
| `sources/<src>/pages/<src>__<slug>__<hash>.md` | Page content as Markdown |
| `sources/<src>/pages/<src>__<slug>__<hash>.meta.json` | URL, fetch timestamp, status, MD5 hash |

**Key options:**
```bash
python3 scrape.py <source_id> "<name_he>" <url> [url2 ...]
python3 scrape.py <source_id> "<name_he>" --file urls.txt

SCRAPER_MAX_DEPTH=0        # 0 = single page only, 2 = follow links 2 levels deep
SCRAPER_FOLLOW_LINKS=false # don't crawl linked pages
SCRAPER_CONCURRENCY=5      # parallel requests
```

**Current sources scraped:**

| Source ID | Organization |
|---|---|
| `nfct` | הקרן החדשה לקולנוע וטלוויזיה |
| `filmfund` | הקרן הישראלית לקולנוע |
| `gesher` | קרן גשר לקולנוע רב-תרבותי |
| `makor` | קרן מקור |
| `rabinovich_cinema` | קרן רבינוביץ' (קולנוע) |
| `rabinovich_foundation` | קרן רבינוביץ' (קרן) |
| `jerusalem_film_fund` | קרן ירושלים לקולנוע |
| `arava_film_fund` | קרן ערבה |
| `galilee_film_fund` | קרן הגליל |
| `ministry_of_culture` | משרד התרבות והספורט |
| `lectors_database` | מאגר לקטורים — המועצה לקולנוע |
| `guidestar` | גיידסטאר (רשם העמותות) |

---

## Step 2 — PDF/DOCX conversion (`pdf_to_pages.py`)

Some sources publish lector lists and protocols as PDF or DOCX files. This script converts them into the same `.md` + `.meta.json` format so `llm_extract.py` can process them uniformly.

```bash
python3 pdf_to_pages.py --source gesher
python3 pdf_to_pages.py   # all sources
```

Source documents go in `sources/<src>/files/`. Output lands in `sources/<src>/pages/` like any scraped page.

---

## Step 3 — Manual imports (`import_*_lectors.py`)

For sources where the lector list was obtained as a structured file (JSON/CSV) rather than scraped HTML, dedicated import scripts write directly to `mentions.jsonl` as a single synthetic record with a `manual://` URL.

| Script | Source |
|---|---|
| `import_filmfund_lectors.py` | הקרן הישראלית לקולנוע |
| `import_gesher_lectors.py` | קרן גשר |

These produce the most reliable lector data because years and roles are explicitly structured.

---

## Step 4 — LLM Extraction (`llm_extract.py`)

Reads every `.md` file in a source's pages directory. Applies a pre-filter (Hebrew film vocabulary + named entities) to skip irrelevant pages. Sends relevant pages to an LLM (via OpenRouter) and extracts:

- **People** — `name_he`, `name_en`, `primary_roles`, `gender`, `context_sentence`
- **Organizations** — `name_he`, `name_en`, `type`
- **Films** — `title_he`, `title_en`, `year`, `sources`
- **Roles** — links a person to an org with `role_type`, `start_year`, `end_year`

Output: one JSON line per page appended to `out/<src>/mentions.jsonl`.

```bash
python3 llm_extract.py sources/nfct/pages ./out --source-name nfct --workers 12
python3 llm_extract.py sources/gesher/pages ./out --source-name gesher --reprocess-truncated
```

**Resumable:** already-processed pages are skipped. Safe to re-run.

---

## Step 5 — Enrichment (`enrich_mentions.py`)

Runs in-place on `mentions.jsonl` files. Fills gaps the LLM left:

- **Years** — infers `start_year`/`end_year` on roles from:
  1. Film release year (most accurate, on `/blog/movies/` pages)
  2. Year in URL path `/(20XX)/`
  3. *(Metadata date skipped — too unreliable)*
- **Gender** — adds `gender: f|m|unknown` via Hebrew name lookup + morphological rules (`ית` → female, trailing `ה` → female)

```bash
python3 enrich_mentions.py --source nfct
python3 enrich_mentions.py   # all sources
```

Idempotent — re-running doesn't overwrite already-set fields.

---

## Step 6 — Entity Resolution & Report (`resolve_entities.py`)

Reads all `out/*/mentions.jsonl` files. Performs:

1. **Deduplication** — groups people by normalized Hebrew name; fuzzy matching flags near-duplicates for manual review
2. **Org aliases** — merges known variants (e.g. `משרד התרבות` → `משרד התרבות והספורט`)
3. **Cross-source connection analysis** — finds people appearing in 2+ sources; flags role conflicts with temporal overlap check
4. **Film-level conflict detection** — person held institutional role (lector, CEO, board) at fund X AND appears in credits of a film funded by fund X
5. **Gender aggregation, repeat winners, production companies**

```bash
python3 resolve_entities.py
python3 resolve_entities.py --export-excel
```

**Outputs:**

| File | Description |
|---|---|
| `connections_report.html` | Full investigative report — conflicts, cross-source people, orgs, repeat winners |
| `connections_report.xlsx` | Excel export — 4 sheets: people, conflicts, repeat winners, companies |
| `entity_registry.json` | Intermediate — canonical resolved entities (do not edit) |

---

## Where data lives

### Source of truth — `mentions.jsonl`

```
out/
├── nfct/mentions.jsonl         ← ~66,000 records
├── filmfund/mentions.jsonl
├── gesher/mentions.jsonl
└── ...
```

Each line is one JSON record per scraped page:
```json
{
  "url": "https://nfct.org.il/about/management/",
  "source_name": "nfct",
  "status": "ok",
  "data": {
    "entities": {
      "people":  { "p1": { "name_he": "דוד פישר", "primary_roles": ["ceo"], ... } },
      "films":   { "f1": { "title_he": "שם הסרט", "year": 2005, ... } },
      "organizations": { ... }
    },
    "roles": [
      { "person_id": "p1", "role_type": "ceo", "start_year": 1999, "end_year": 2008 }
    ]
  }
}
```

**To manually correct data** (e.g. add missing years): patch `mentions.jsonl` directly with a Python script, then re-run `resolve_entities.py`. Never edit `entity_registry.json` — it is fully regenerated on every run.

### Scraped pages — `sources/`

```
sources/
├── nfct/
│   ├── pages/    ← ~68,000 .md + .meta.json pairs
│   └── files/    ← source PDFs/DOCX (if any)
├── gesher/
│   └── pages/
└── ...
```

---

## Adding a new source

```bash
# 1. Scrape
python3 scrape.py <source_id> "<name_he>" https://example.org/

# 2. Convert PDFs if needed
python3 pdf_to_pages.py --source <source_id>

# 3. Extract
python3 llm_extract.py sources/<source_id>/pages ./out --source-name <source_id>

# 4. Enrich
python3 enrich_mentions.py --source <source_id>

# 5. Regenerate report
python3 resolve_entities.py
```

---

## Key design decisions

| Decision | Reason |
|---|---|
| One `mentions.jsonl` per source | Isolates failures; easy to re-run one source without touching others |
| LLM extracts — rule engine resolves | LLM handles Hebrew morphology and context; deterministic rules handle deduplication and conflict logic |
| `manual://` URLs for canonical lector lists | Prioritized over scraped evidence in the UI; links to the actual official document |
| Year overlap required for role conflicts | Prevents false positives where someone was a producer years before/after their institutional role |
| `mentions.jsonl` is source of truth | `entity_registry.json` is fully derived — all corrections go into the JSONL files |
