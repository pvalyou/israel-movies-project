# Intelligence Plan: Israeli Film Industry Network

## End goal

An interactive network graph (D3.js / Sigma.js) of the Israeli film industry —
nodes are people, funds, films, companies, schools; edges are all relationships.
**This document covers data collection only.** Visualization is the next project.

## What we already have

`network_graph.json` is already in the right schema for D3/Sigma:

```json
{
  "nodes": [ {"id": "...", "label": "...", "type": "...", "group": "...", ...} ],
  "edges": [ {"id": "...", "source": "...", "target": "...", "type": "...", "weight": 1} ]
}
```

**Current node types:** `person`, `fund`
**Current edge types:** `institutional` (person→fund role), `film_funded` (person's film←fund)

**What's missing:**

| Node type | Represents |
|-----------|-----------|
| `film` | Individual film title |
| `company` | Production company |
| `school` | Film school |
| `festival` | Film festival (separate from funds) |

| Edge type | Represents |
|-----------|-----------|
| `co_credited` | Two people worked on the same film |
| `reviewed` | Critic reviewed a film |
| `studied_at` | Person studied at a school (with year) |
| `company_member` | Person is part of a production company |
| `fund_recipient` | Film received money from fund (with ₪ amount) |

---

## Node schema — complete spec

All nodes share the base fields `id`, `label`, `type`, `group`.
Additional fields per type:

### person
```json
{
  "id":                   "person::שמוליק דובדבני",
  "label":                "שמוליק דובדבני",
  "type":                 "person",
  "group":                "conflict | soft | person | critic",
  "gender":               "m | f | unknown",
  "birth_year":           1968,
  "wiki_url":             "https://he.wikipedia.org/wiki/...",
  "edb_id":               "n0012345",
  "has_strict_conflict":  true,
  "has_soft_conflict":    false,
  "source_count":         4,
  "roles":                ["director", "lector", "board_member"]
}
```

### fund
```json
{
  "id":     "fund::makor",
  "label":  "קרן מקור",
  "type":   "fund",
  "group":  "fund",
  "url":    "https://kerenmakor.org.il"
}
```

### film
```json
{
  "id":        "film::t0014365",
  "label":     "זוג יונים",
  "type":      "film",
  "group":     "film",
  "year":      2017,
  "edb_id":    "t0014365",
  "edb_url":   "https://www.edb.co.il/title/t0014365/",
  "is_short":  false,
  "funds":     ["makor", "nfct"]
}
```

### company
```json
{
  "id":     "company::וורדור הפקות",
  "label":  "וורדור הפקות",
  "type":   "company",
  "group":  "company"
}
```

### school
```json
{
  "id":     "school::sam_spiegel",
  "label":  "בית הספר סם שפיגל",
  "type":   "school",
  "group":  "school",
  "url":    "https://www.jsfs.co.il"
}
```

---

## Edge schema — complete spec

All edges: `id`, `source` (node id), `target` (node id), `type`, `weight`.

### co_credited — person ↔ person
```json
{
  "id":      "e_cc_001",
  "source":  "person::דובר קוסאשווילי",
  "target":  "person::מרק רוזנבאום",
  "type":    "co_credited",
  "film_id": "film::t0014365",
  "film_title": "זוג יונים",
  "year":    2017,
  "role_a":  "director",
  "role_b":  "producer",
  "weight":  1
}
```
Weight = number of films worked on together (accumulate if pair appears multiple times).

### reviewed — person → film
```json
{
  "id":      "e_rv_001",
  "source":  "person::אורי קליין",
  "target":  "film::t0014365",
  "type":    "reviewed",
  "outlet":  "הארץ",
  "year":    2017,
  "score":   4,
  "weight":  1
}
```

### studied_at — person → school
```json
{
  "id":            "e_sa_001",
  "source":        "person::...",
  "target":        "school::sam_spiegel",
  "type":          "studied_at",
  "grad_year":     2015,
  "degree":        "BFA",
  "weight":        1
}
```

### company_member — person → company
```json
{
  "id":     "e_cm_001",
  "source": "person::...",
  "target": "company::וורדור הפקות",
  "type":   "company_member",
  "role":   "founder | producer | employee",
  "weight": 1
}
```

### fund_recipient — film → fund
```json
{
  "id":         "e_fr_001",
  "source":     "film::t0014365",
  "target":     "fund::makor",
  "type":       "fund_recipient",
  "year":       2017,
  "amount_ils": 450000,
  "weight":     1
}
```

### institutional — person → fund (already exists)
```json
{
  "id":       "e0",
  "source":   "person::קובי מזרחי",
  "target":   "fund::makor",
  "type":     "institutional",
  "roles":    ["lector"],
  "years":    [2024, 2025, 2026],
  "weight":   3
}
```

---

## Data sources → graph elements

| Source | Scrape output | Adds to graph |
|--------|--------------|---------------|
| edb.co.il/films | `out/edb/mentions.jsonl` | `film` nodes, `co_credited` edges, `company_member` edges |
| edb.co.il/critics | `out/edb_critics/mentions.jsonl` | `reviewed` edges, critic `person` nodes |
| Film school alumni | `out/schools/mentions.jsonl` | `school` nodes, `studied_at` edges |
| Fund PDFs (existing) | already in `out/*/mentions.jsonl` | `institutional` edges (already working) |
| Fund film pages (existing) | already scraped | `fund_recipient` edges (₪ amounts to add) |

---

## Phase 1 — edb film scraper (highest priority)

### Step 1a — Collect all Israeli film IDs

```python
import re, requests, time, json

UA   = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
BASE = "https://www.edb.co.il"

def get_page_ids(url_template: str) -> set[str]:
    all_ids, prev = set(), set()
    for page in range(1, 10000):
        html = requests.get(url_template.format(page),
                            headers={"User-Agent": UA}).text
        ids = set(re.findall(r'/title/(t\d+)/', html))
        if not ids or ids == prev:
            print(f"  done at page {page}, {len(all_ids)} films")
            break
        all_ids |= ids
        prev = ids
        time.sleep(0.3)
    return all_ids

film_ids  = get_page_ids(BASE + "/browse/b/c/israel/t/movies/?p={}")
short_ids = get_page_ids(BASE + "/browse/b/c/israel/t/shorts/?p={}")
all_ids   = film_ids | short_ids

json.dump(sorted(all_ids), open("edb_film_ids.json", "w"), ensure_ascii=False)
print(f"Total: {len(all_ids)} films+shorts")
```

### Step 1b — Scrape each film's crew

```python
def scrape_film(film_id: str) -> dict | None:
    try:
        cast_html = requests.get(f"{BASE}/title/{film_id}/cast/",
                                 headers={"User-Agent": UA}, timeout=10).text
        main_html = requests.get(f"{BASE}/title/{film_id}/",
                                 headers={"User-Agent": UA}, timeout=10).text
    except Exception:
        return None

    title_m = re.search(r'og:title.*?content="([^"]+)"', main_html)
    year_m  = re.search(r'\((\d{4})\)', main_html)

    crew = []
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>', cast_html, re.DOTALL):
        name_m = re.search(r'href="/name/(n\d+)/"[^>]*>([^<]+)</a>', row)
        role_m = re.findall(r'<td[^>]*>\s*([^\n<]{2,40}?)\s*</td>', row)
        if name_m:
            crew.append({
                "edb_id":  name_m.group(1),
                "name_he": name_m.group(2).strip(),
                "role_he": role_m[-1].strip() if role_m else "",
                "role":    ROLE_MAP.get(role_m[-1].strip() if role_m else "", "other"),
            })
    return {
        "film_id":  film_id,
        "url":      f"{BASE}/title/{film_id}/",
        "title":    title_m.group(1).split("(")[0].strip() if title_m else "",
        "year":     int(year_m.group(1)) if year_m else None,
        "is_short": film_id in short_ids,
        "crew":     crew,
    }

ROLE_MAP = {
    "בימוי": "director", "הפקה": "producer", "תסריט": "screenwriter",
    "עריכה": "editor",   "צילום": "cinematographer",
    "מוסיקה מקורית": "composer", "עיצוב פסקול": "sound_designer",
    "שחקן": "actor",     "שחקנית": "actor",
}

# Resume-safe: load existing checkpoint
import os
checkpoint = "edb_films.json"
done = {}
if os.path.exists(checkpoint):
    done = {f["film_id"]: f for f in json.load(open(checkpoint))}

ids_todo = [i for i in sorted(all_ids) if i not in done]
print(f"{len(ids_todo)} films to scrape, {len(done)} already done")

for film_id in ids_todo:
    result = scrape_film(film_id)
    if result:
        done[film_id] = result
    if len(done) % 100 == 0:
        json.dump(list(done.values()), open(checkpoint, "w"), ensure_ascii=False)
        print(f"  checkpoint: {len(done)} films")
    time.sleep(0.5)

json.dump(list(done.values()), open(checkpoint, "w"), ensure_ascii=False)
```

### Step 1c — Export to mentions.jsonl

```python
import jsonlines  # pip install jsonlines
from datetime import date

with jsonlines.open("out/edb/mentions.jsonl", mode="w") as writer:
    for film in json.load(open("edb_films.json")):
        if not film.get("crew"):
            continue

        people = {}
        for i, c in enumerate(film["crew"]):
            pid = f"person_{i+1:03d}"
            people[pid] = {
                "name_he":      c["name_he"],
                "name_en":      None,
                "aliases":      [],
                "primary_roles": [c["role"]],
                "sources":      [film["url"]],
                "gender":       "unknown",
                "edb_id":       c["edb_id"],      # ← extra field for graph builder
            }

        writer.write({
            "url":         film["url"],
            "source_name": "edb",
            "status":      "ok",
            "data": {
                "metadata": {
                    "source_url":       film["url"],
                    "source_name":      "edb",
                    "extraction_date":  str(date.today()),
                    "language":         "he",
                },
                "entities": {
                    "people": people,
                    "films": {
                        "film_001": {
                            "title":    film["title"],
                            "year":     film["year"],
                            "url":      film["url"],
                            "edb_id":   film["film_id"],   # ← extra field
                            "is_short": film["is_short"],  # ← extra field
                            "crew":     [{"name_he": c["name_he"],
                                          "role":    c["role"],
                                          "edb_id":  c["edb_id"]}
                                         for c in film["crew"]],
                        }
                    }
                }
            }
        })
```

---

## Phase 2 — edb critics scraper

```
https://www.edb.co.il/critics/           ← list all critics
https://www.edb.co.il/critics/{id}/      ← each critic's review list
```

Output to `out/edb_critics/mentions.jsonl` — same schema, with `reviewed` relationships.

---

## Phase 3 — Film school alumni

**Sam Spiegel** publishes alumni:
```
https://www.jsfs.co.il/alumni
```

**TAU / Sapir** — check if public lists exist; fallback is to extract names from
edb film credits and cross-reference graduation years via Wikipedia.

Output to `out/schools/mentions.jsonl`.

---

## Phase 4 — Funding amounts

Fund websites list supported films with grant amounts. Some are in PDFs, some on
HTML pages. Adding `amount_ils` to `fund_recipient` edges makes the visualization
show concentration of money (like the ₪104M stat on the prototype site).

This enriches existing data — no new scraper needed, just parse amounts from
pages we've already scraped.

---

## What resolve_entities.py needs to do with this (Phase 5 — future work)

`build_network_graph()` currently only knows about `person` and `fund` nodes.
When the edb data is in `out/edb/mentions.jsonl`, the pipeline needs to:

1. Add `film` nodes from edb film records
2. Add `co_credited` edges between every pair of crew members on the same film
3. Add `studied_at` edges from school alumni data
4. Add `reviewed` edges from critics data
5. Export the enriched `network_graph.json`

**This is the only code change needed in the pipeline** — everything else is
already wired up to read `out/*/mentions.jsonl` automatically.

---

## Execution order

```
1. python3 scrape_edb.py              → edb_film_ids.json + edb_films.json
2. python3 export_edb_mentions.py     → out/edb/mentions.jsonl
3. python3 scrape_edb_critics.py      → out/edb_critics/mentions.jsonl
4. python3 scrape_schools.py          → out/schools/mentions.jsonl
5. python3 resolve_entities.py        → network_graph.json (extended)
```

## Rate limiting

- 0.5s between requests minimum — edb.co.il is a small Israeli site
- Save checkpoint every 100 films (scraper is resume-safe by design)
- If HTTP 429: back off to 5s and retry
