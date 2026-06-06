# Plan: EDB Film Fund Enrichment
**Task:** For each film in `edb_films.json`, discover which Israeli fund(s) (קרן) supported it by scraping the EDB film main page.

**Context:** `edb_films.json` has 285 films with `film_id, url, title, year, is_short, crew`. Missing: `funds` (list of fund names/keys that funded the film). This is needed so the network graph can have direct `fund_recipient` edges: film → fund.

---

## Where fund data lives on EDB

Each EDB film has a main page at `https://www.edb.co.il/title/{film_id}/`. The existing scraper already fetches this page but only extracts title and year. The page contains a **"תמיכה" (support) section** listing funding bodies.

**Before writing any code:** Inspect 2–3 sample film pages to confirm the HTML structure of the fund section. Recommended samples:
- `https://www.edb.co.il/title/t0001223/` (אחוזת דג'אני, 2025)
- `https://www.edb.co.il/title/t0016283/` (עוד ניפגש, 2020)
- `https://www.edb.co.il/title/t0013689/` (any conflict-list film)

Look for: a section with class/id containing "support", "fund", "תמיכה", "קרן", or a `<ul>` / `<table>` listing fund names.

---

## Output schema

Add a `funds` field to each film in `edb_films.json`:

```json
{
  "film_id": "t0001223",
  "url": "https://www.edb.co.il/title/t0001223/",
  "title": "אחוזת דג'אני",
  "year": 2025,
  "is_short": false,
  "crew": [...],
  "funds": ["nfct", "makor"],
  "production_companies": ["שם חברה הפקות"],
  "genre": "documentary",
  "description_he": "..."
}
```

**Fund name → key mapping** (normalize scraped names to these keys):
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
For fund names not in the map, store the raw Hebrew string. The pipeline will handle unknown funds gracefully.

---

## Script to write: `scripts/edb/enrich_edb_funds.py`

```python
#!/usr/bin/env python3
"""
Enrich edb_films.json with fund (קרן) data scraped from each film's main page.
Reads edb_films.json, fetches /title/{id}/ for any film missing 'funds' field,
parses the support/fund section, and writes back to edb_films.json.

Run: python3 scripts/edb/enrich_edb_funds.py [--limit N]
     --limit N  : only process N films (for testing)
     --force    : re-scrape even films that already have 'funds' field
"""

import json, re, sys, time
import requests

UA   = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
BASE = "https://www.edb.co.il"
INPUT_FILE = "data/edb/edb_films.json"

FUND_NAME_MAP = {
    "הקרן החדשה לקולנוע וטלוויזיה": "nfct",
    "קרן מקור":     "makor",
    "קרן רבינוביץ": "rabinovich_cinema",
    "קרן ירושלים":  "jerusalem_film_fund",
    "קרן גשר":      "gesher",
    "קרן קולנוע ישראל": "filmfund",
    "קרן הסרט הישראלי": "filmfund",
}

def parse_funds(html: str) -> list[str]:
    """
    Extract fund names from EDB film page HTML.
    FIRST: inspect a live page and fill in the correct regex/selector here.
    Placeholder patterns — update after inspection:
    """
    funds_raw = []

    # Pattern A: look for a "תמיכה" section with fund links or text
    # <section ...>תמיכה...<a href="...">קרן מקור</a>...
    section_m = re.search(
        r'(?:תמיכה|support|funds?)[^<]{0,200}?(<[^>]+>[^<]*(?:קרן|fund)[^<]*<)',
        html, re.IGNORECASE | re.DOTALL
    )
    if section_m:
        # Extract text from any <a> or <li> tags in the section
        funds_raw += re.findall(r'>([^<]+(?:קרן|fund)[^<]+)<', section_m.group(0))

    # Pattern B: JSON-LD or meta tags listing funders
    ld = re.findall(r'"funder"[^}]*?"name"\s*:\s*"([^"]+)"', html)
    funds_raw += ld

    # Normalize
    seen = set()
    result = []
    for raw in funds_raw:
        raw = raw.strip()
        key = FUND_NAME_MAP.get(raw, raw)
        if key and key not in seen:
            seen.add(key)
            result.append(key)
    return result


def parse_production_companies(html: str) -> list[str]:
    """Extract production company names. Fill in after page inspection."""
    # Placeholder: look for company links in הפקה section
    companies = re.findall(r'class="company[^"]*"[^>]*>([^<]+)</a>', html)
    return [c.strip() for c in companies if c.strip()]


def parse_genre(html: str) -> str:
    """Extract genre/category. Fill in after page inspection."""
    m = re.search(r'"genre"[^:]*:\s*"([^"]+)"', html)
    return m.group(1) if m else ""


def main():
    force   = "--force"  in sys.argv
    limit_n = None
    for i, a in enumerate(sys.argv):
        if a == "--limit" and i + 1 < len(sys.argv):
            limit_n = int(sys.argv[i + 1])

    films = json.loads(open(INPUT_FILE, encoding="utf-8").read())
    sess  = requests.Session()
    sess.headers.update({"User-Agent": UA})

    updated = 0
    for i, film in enumerate(films):
        if limit_n and updated >= limit_n:
            break
        if not force and "funds" in film:
            continue  # already enriched

        fid = film["film_id"]
        try:
            resp = sess.get(f"{BASE}/title/{fid}/", timeout=15)
            html = resp.text
        except Exception as e:
            print(f"  SKIP {fid}: {e}")
            continue

        film["funds"]               = parse_funds(html)
        film["production_companies"] = parse_production_companies(html)
        film["genre"]               = parse_genre(html)
        updated += 1

        if updated % 25 == 0:
            open(INPUT_FILE, "w", encoding="utf-8").write(
                json.dumps(films, ensure_ascii=False, indent=2))
            print(f"  checkpoint: {updated} films enriched")
        time.sleep(0.5)

    open(INPUT_FILE, "w", encoding="utf-8").write(
        json.dumps(films, ensure_ascii=False, indent=2))
    print(f"Done: {updated} films updated → {INPUT_FILE}")


if __name__ == "__main__":
    main()
```

---

## After enrichment: wire into the graph

Once `edb_films.json` has `funds` populated, add this to `build_network_graph()` in `resolve_entities.py` inside the film-node creation loop (around line 4060):

```python
# fund_recipient edges: film → fund
for fund_key in (film.get("funds") or []):
    fnid = f"fund::{fund_key}"
    if fnid in nodes:  # only known funds
        edges.append({
            "id":     f"e{len(edges)}",
            "source": film_nid,
            "target": fnid,
            "type":   "fund_recipient",
            "weight": 1,
        })
```

---

## Steps summary

1. Inspect 2–3 EDB film pages manually to identify the fund HTML section
2. Fill in `parse_funds()` with the correct regex/selector
3. Run `python3 scripts/edb/enrich_edb_funds.py --limit 10` to test
4. Verify output looks correct in `edb_films.json`
5. Run without `--limit` for all 285 films
6. Add `fund_recipient` edges to `build_network_graph()` as shown above
7. Run `python3 resolve_entities.py` to rebuild graph
8. Run QA agent to verify no regressions
