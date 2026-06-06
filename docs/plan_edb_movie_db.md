> **Superseded** by `docs/plan_movie_db.md` (multi-source plan). Kept for reference.

# Plan: EDB Comprehensive Movie Database (EDB only — archived)

**Task:** Build a comprehensive Israeli film entity database by enriching `edb_films.json` with full metadata (description, genre, awards, production companies, festivals, box office) and expanding coverage beyond the current 286 films.

**Context:** Current `edb_films.json` has 285 films scraped from a conflict-relevant browse list. EDB likely contains thousands of Israeli films. We want a `movies_db.json` that is the authoritative film entity store — linked to person entities via `edb_id` — so the network graph can do tripartite analysis (person↔film↔fund) and the HTML report can display rich film cards.

---

## Phase 0 — Expand film ID collection

Current coverage: 199 feature films + 98 shorts = 297 total from browse page.

EDB browse URL structure (verified):
```
https://www.edb.co.il/browse/b/c/israel/t/movies/?p={page}
https://www.edb.co.il/browse/b/c/israel/t/shorts/?p={page}
```

**Additional categories to check** (inspect URLs before scraping):
- Documentary films: likely `/t/documentary/` or `/t/docs/`
- TV films: likely `/t/tv/` or a separate browse path
- Animation: likely `/t/animation/`

**Task for scraping agent:**
1. Fetch each browse category page by page until pagination stops (detect: same IDs as previous page, or empty results)
2. Extract all film IDs from `<a href="/title/(t[0-9]+)/">` links
3. Merge with existing `edb_film_ids.json` (no duplicates)
4. Output: updated `edb_film_ids.json` with all categories tracked

---

## Phase 1 — Scrape full film metadata

For each film ID in `edb_film_ids.json`, fetch `https://www.edb.co.il/title/{film_id}/` and extract:

### Fields to extract

| Field | EDB location | Notes |
|-------|-------------|-------|
| `title_he` | `<h1>` or `og:title` | Hebrew title |
| `title_en` | Subtitle or `og:title` | English title if shown |
| `year` | Already have | |
| `is_short` | Already have | |
| `description_he` | Synopsis section | Hebrew paragraph(s) |
| `genre` | JSON-LD `"genre"` or category breadcrumb | e.g. "documentary", "drama" |
| `duration_min` | Runtime field | Integer minutes |
| `funds` | "תמיכה" section | List of fund keys (see FUND_NAME_MAP) |
| `production_companies` | "הפקה" section | List of company name strings |
| `festivals` | "פסטיבלים" section | List of `{"name": ..., "year": ..., "award": ...}` |
| `awards` | Award section | List of `{"award": ..., "year": ..., "category": ...}` |
| `country` | Country field | Usually "ישראל" |
| `language` | Language field | e.g. "עברית", "ערבית" |
| `edb_id` | Already have (`film_id`) | |

### Output schema per film

```json
{
  "film_id":              "t0016283",
  "url":                  "https://www.edb.co.il/title/t0016283/",
  "title_he":             "עוד ניפגש",
  "title_en":             "We Will Meet Again",
  "year":                 2020,
  "is_short":             false,
  "duration_min":         82,
  "genre":                "documentary",
  "description_he":       "...",
  "country":              "ישראל",
  "language":             "עברית",
  "funds":                ["nfct", "makor"],
  "production_companies": ["קמה פילמס"],
  "festivals": [
    {"name": "פסטיבל דוקאביב", "year": 2020, "award": "פרס הקהל"},
    {"name": "Hot Docs", "year": 2020, "award": null}
  ],
  "awards": [
    {"award": "אופיר", "year": 2020, "category": "סרט תיעודי מצטיין"}
  ],
  "crew": [ ... ]
}
```

### FUND_NAME_MAP (normalize to these keys)

```python
FUND_NAME_MAP = {
    "הקרן החדשה לקולנוע וטלוויזיה": "nfct",
    "קרן מקור":                      "makor",
    "קרן רבינוביץ":                  "rabinovich_cinema",
    "קרן ירושלים":                   "jerusalem_film_fund",
    "קרן גשר":                       "gesher",
    "קרן קולנוע ישראל":              "filmfund",
    "קרן הסרט הישראלי":              "filmfund",
    "מסלול הפקות":                   "nfct",
    "הרשות לשידורי כבלים":           "cable_authority",
    "yes דוקו":                      "yes_doco",
    "hot8":                          "hot8",
}
```

---

## Script to write: `scripts/edb/scrape_edb_movie_db.py`

```python
#!/usr/bin/env python3
"""
Scrape full metadata for all EDB films → movies_db.json.

Reads film IDs from edb_film_ids.json (or edb_films.json as fallback).
Fetches /title/{id}/ for each film and extracts full metadata.
Writes to movies_db.json (checkpoint every 50 films).

Run: python3 scripts/edb/scrape_edb_movie_db.py [--limit N] [--force]
     --limit N  : only process N films (for testing)
     --force    : re-scrape even films already in movies_db.json
"""

import json, re, sys, time
import requests
from bs4 import BeautifulSoup   # pip install beautifulsoup4

UA      = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
BASE    = "https://www.edb.co.il"
ID_FILE = "data/edb/edb_film_ids.json"
OUT_FILE = "data/edb/movies_db.json"
CHECKPOINT = 50

FUND_NAME_MAP = {
    "הקרן החדשה לקולנוע וטלוויזיה": "nfct",
    "קרן מקור":     "makor",
    "קרן רבינוביץ": "rabinovich_cinema",
    "קרן ירושלים":  "jerusalem_film_fund",
    "קרן גשר":      "gesher",
    "קרן קולנוע ישראל": "filmfund",
    "קרן הסרט הישראלי": "filmfund",
    "מסלול הפקות":   "nfct",
    "הרשות לשידורי כבלים": "cable_authority",
    "yes דוקו":      "yes_doco",
    "hot8":          "hot8",
}

def parse_film_page(html: str, film_id: str) -> dict:
    """
    Parse a film main page and return structured metadata.
    IMPORTANT: inspect 2-3 live pages before finalizing selectors.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Title
    title_he = ""
    title_en = ""
    h1 = soup.find("h1")
    if h1:
        title_he = h1.get_text(strip=True)

    # Year
    year = None
    m = re.search(r'"dateCreated"\s*:\s*"?(\d{4})', html)
    if m:
        year = int(m.group(1))

    # Genre (from JSON-LD or meta)
    genre = ""
    m = re.search(r'"genre"\s*:\s*"([^"]+)"', html)
    if m:
        genre = m.group(1)

    # Duration
    duration_min = None
    m = re.search(r'"duration"\s*:\s*"PT(\d+)M"', html)
    if m:
        duration_min = int(m.group(1))

    # Description
    description_he = ""
    # Look for synopsis/description div — UPDATE SELECTOR after page inspection
    desc_div = soup.find("div", class_=re.compile(r'synopsis|description|about', re.I))
    if desc_div:
        description_he = desc_div.get_text(separator=" ", strip=True)

    # Funds — from "תמיכה" section — UPDATE after page inspection
    funds_raw = []
    # Pattern: find section labeled תמיכה, collect links/text within it
    # Placeholder — inspect page HTML to find correct selector
    for tag in soup.find_all(string=re.compile(r'תמיכה')):
        parent = tag.parent
        if parent:
            for a in parent.find_next_siblings():
                text = a.get_text(strip=True)
                if text:
                    funds_raw.append(text)

    funds = []
    seen = set()
    for raw in funds_raw:
        key = FUND_NAME_MAP.get(raw, raw)
        if key and key not in seen:
            seen.add(key)
            funds.append(key)

    # Production companies — UPDATE after page inspection
    companies = []
    # Placeholder

    # Festivals — UPDATE after page inspection
    festivals = []
    # Placeholder

    # Awards — UPDATE after page inspection
    awards = []

    return {
        "film_id":              film_id,
        "url":                  f"{BASE}/title/{film_id}/",
        "title_he":             title_he,
        "title_en":             title_en,
        "year":                 year,
        "is_short":             False,   # set from id list
        "duration_min":         duration_min,
        "genre":                genre,
        "description_he":       description_he,
        "country":              "ישראל",
        "language":             "",
        "funds":                funds,
        "production_companies": companies,
        "festivals":            festivals,
        "awards":               awards,
        "crew":                 [],      # filled from cast page
    }


def main():
    force   = "--force" in sys.argv
    limit_n = None
    for i, a in enumerate(sys.argv):
        if a == "--limit" and i + 1 < len(sys.argv):
            limit_n = int(sys.argv[i + 1])

    id_data = json.load(open(ID_FILE, encoding="utf-8"))
    all_ids = id_data.get("all", [])
    short_ids = set(id_data.get("shorts", []))

    # Load existing db
    try:
        db = {f["film_id"]: f for f in json.load(open(OUT_FILE, encoding="utf-8"))}
    except FileNotFoundError:
        db = {}

    sess = requests.Session()
    sess.headers.update({"User-Agent": UA})

    updated = 0
    for fid in all_ids:
        if limit_n and updated >= limit_n:
            break
        if not force and fid in db:
            continue

        try:
            resp = sess.get(f"{BASE}/title/{fid}/", timeout=15)
            if resp.status_code == 429:
                time.sleep(5)
                resp = sess.get(f"{BASE}/title/{fid}/", timeout=15)
            html = resp.text
        except Exception as e:
            print(f"  SKIP {fid}: {e}")
            continue

        film = parse_film_page(html, fid)
        film["is_short"] = fid in short_ids
        db[fid] = film
        updated += 1
        print(f"  [{updated}] {fid} — {film['title_he']} ({film['year']})")

        if updated % CHECKPOINT == 0:
            _save(db)
            print(f"  checkpoint: {updated} films")

        time.sleep(0.5)

    _save(db)
    print(f"Done: {updated} new/updated films → {OUT_FILE} ({len(db)} total)")


def _save(db: dict):
    films_list = sorted(db.values(), key=lambda f: f["film_id"])
    open(OUT_FILE, "w", encoding="utf-8").write(
        json.dumps(films_list, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

---

## Phase 2 — Crew scraping (cast page)

Each film's crew/cast lives at:
```
https://www.edb.co.il/title/{film_id}/cast/
```

This is already how `edb_films.json` was built. The movie DB script should also populate `crew` by fetching the cast page.

**Crew record schema** (matches existing `edb_films.json`):
```json
{
  "name_he": "שירה מרגלית",
  "role":    "director",
  "role_he": "במאית",
  "edb_id":  "n0001234"
}
```

Reuse the existing `scrape_edb.py` cast-page parser rather than reimplementing it.

---

## Phase 3 — Link to person entities

After `movies_db.json` is populated, the pipeline links films to persons:

- `crew[].edb_id` → matches `edb_persons.json[].edb_id` and `connections[].edb_id`
- This enables `crew_credit` edges: person → film (already in `build_network_graph()`)
- Extended: any film in `movies_db.json` with a crew member whose `edb_id` is known → `crew_credit` edge

**In `resolve_entities.py`:** update `build_network_graph()` to read `movies_db.json` instead of (or in addition to) `edb_films.json` for film nodes and crew_credit edges, once the new file is ready.

---

## Execution order for scraping agent

1. **Inspect** 2-3 film pages manually before writing any selectors:
   - `https://www.edb.co.il/title/t0001223/` (אחוזת דג'אני, 2025)
   - `https://www.edb.co.il/title/t0016283/` (עוד ניפגש, 2020)
   - `https://www.edb.co.il/title/t0013689/` (any conflict-list film)
   
   Find: description `<div>`, fund list selector, genre/duration in JSON-LD, festivals/awards sections.

2. **Optionally expand** `edb_film_ids.json` to include documentary/TV/animation browse categories.

3. **Run with `--limit 5`** to test selectors → verify `movies_db.json` output.

4. **Run without `--limit`** for all films (expect ~2-4 hours at 0.5s/request for 2000+ films).

5. **Report back:** `movies_db.json` total count, % with description, % with funds, sample records.

---

## Integration into resolve_entities.py (after scraping is done)

Replace `edb_films.json` read with `movies_db.json` in `build_network_graph()`:

```python
# In build_network_graph(), replace:
edb_path = Path("data/edb/edb_films.json")
# With:
edb_path = Path("data/edb/movies_db.json") if Path("data/edb/movies_db.json").exists() else Path("data/edb/edb_films.json")
```

Also add `fund_recipient` edges as described in `docs/plan_edb_fund_enrichment.md`.
