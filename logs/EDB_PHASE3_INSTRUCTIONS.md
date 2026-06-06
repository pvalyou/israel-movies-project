# EDB Phase 3 — Person Pages + Collaborator Expansion

**Date written:** 2026-05-29  
**Context:** EDB phases 1+2 are done. `edb_films.json` has 285 films with crew (production staff only, no actors). Phase 3 expands person coverage by scraping individual person pages and their collaboration network.

---

## What already exists

| File | Contents |
|------|----------|
| `edb_films.json` | 285 films, each with `crew: [{edb_id, name_he, role_he, role}]` |
| `edb_film_ids.json` | `{films:[...], shorts:[...], all:[...]}` — 286 film IDs |
| `scripts/edb/scrape_edb.py` | Already fetches `/title/<id>/cast/` for crew data |
| `scripts/edb/export_edb_mentions.py` | Exports edb_films.json → out/edb/mentions.jsonl |

The current `scrape_film()` in `scrape_edb.py` fetches `/title/<id>/cast/` and extracts crew rows via:
```python
for row in re.findall(r'<tr[^>]*>(.*?)</tr>', cast_html, re.DOTALL):
    name_m = re.search(r'href="/name/(n\d+)/"[^>]*>([^<]+)</a>', row)
    role_m = re.findall(r'<td[^>]*>\s*([^\n<]{2,40}?)\s*</td>', row)
```

---

## Phase 3 Goal

Build `edb_persons.json` — a dict keyed by EDB person ID, containing:
- Full filmography (all films they've worked on, from their `/name/<id>/` page)
- The "מרבה לעבוד עם..." (frequent collaborators) section — list of other person IDs
- Basic identity: name_he, name_en, roles seen across all films

Then expand one hop: for every **collaborator** found on a person page, also fetch their person page. This gives us second-degree connections.

---

## URL Structure

| URL | Content |
|-----|---------|
| `https://www.edb.co.il/name/<id>/` | Person's main page — bio + filmography |
| `https://www.edb.co.il/title/<id>/cast/` | Film's cast page — already scraped in Phase 1 |

**Known person IDs:** Extract all unique `edb_id` values from `edb_films.json`:
```python
import json
films = json.load(open("edb_films.json"))
seed_ids = {c["edb_id"] for f in films for c in f.get("crew", []) if c.get("edb_id")}
# Expect ~500-800 unique person IDs
```

**Example person page:** `https://www.edb.co.il/name/n0035480/`
- Section "מרבה לעבוד עם..." contains `<a href="/name/<id>/">` links to frequent collaborators
- Filmography section contains `<a href="/title/<id>/">` links with role

---

## Scraping Approach

### Step 1 — Scrape all seed persons (from edb_films.json crew)

For each person ID in `seed_ids`, fetch `https://www.edb.co.il/name/<id>/` and extract:

1. **Name:**
   ```python
   # og:title or h1 or meta name="title"
   name_m = re.search(r'og:title.*?content="([^"(]+)', html)
   ```

2. **Filmography** (title+role for each film they appear in):
   ```python
   # Each row in the filmography table has:
   # <a href="/title/(t\d+)/">title text</a>  and a role column
   films_on_page = re.findall(r'href="/title/(t\d+)/"[^>]*>([^<]+)</a>', html)
   # Role is in an adjacent <td> — parse with row-by-row logic similar to scrape_film()
   ```

3. **Collaborators** (from the "מרבה לעבוד עם..." section):
   ```python
   # Find the section heading מרבה לעבוד עם
   collab_section_m = re.search(
       r'מרבה לעבוד עם.*?(?=<section|<h[23]|$)', html, re.DOTALL
   )
   if collab_section_m:
       collab_ids = re.findall(r'href="/name/(n\d+)/"', collab_section_m.group())
   ```

### Step 2 — Expand to collaborators (1 hop only)

After scraping all seed persons, collect all `collab_ids` found. For any collaborator ID not already scraped, scrape their page too. **Do NOT recurse** — only 1 hop beyond the seed set.

Total expected: seed ~600 + collaborators ~1,000 = ~1,500–2,000 unique persons.

---

## Output Format

Save to `edb_persons.json` — a **list** (not dict, for JSON serialization consistency with `edb_films.json`):

```json
[
  {
    "edb_id": "n0035480",
    "name_he": "שירה מרגלית",
    "name_en": "Shira Margalit",
    "films": [
      {
        "film_id": "t0017863",
        "title": "לשדך את אמא",
        "year": 2022,
        "role_he": "שחקנית",
        "role": "actor"
      }
    ],
    "collaborators": ["n0012345", "n0067890"],
    "is_seed": true
  }
]
```

`is_seed: true` = found directly in `edb_films.json` crew  
`is_seed: false` = found via collaborator expansion  

Use `edb_persons.json` as a **checkpoint** — write it every 100 persons. Skip already-scraped IDs on resume.

---

## Rate Limiting

Use `time.sleep(0.4)` between requests. EDB is a small Israeli site — don't hammer it.

---

## Script Location and Name

Create: `scripts/edb/scrape_edb_persons.py`

Run from project root:
```bash
python3 scripts/edb/scrape_edb_persons.py            # Full run
python3 scripts/edb/scrape_edb_persons.py --seed-only # Only scrape seed persons, skip expansion
```

---

## Pipeline Integration (after scraping)

After `edb_persons.json` is built, update `scripts/edb/export_edb_mentions.py` to also emit person-level data. Specifically:

1. **Actors**: persons with `role = "actor"` in their `films` list — add them to `out/edb/mentions.jsonl` with `primary_roles: ["actor"]`  
2. **Collaborator edges**: for the network graph, `co_collaborated` edges between persons who appear in "מרבה לעבוד עם" lists (directed: A→B means A's page lists B as frequent collaborator)

The export should extend — not replace — the existing `out/edb/mentions.jsonl` which currently only has production crew data.

---

## HTML Parsing Tips

Inspect `https://www.edb.co.il/name/n0035480/` before writing the parser. The site uses similar table structure to the `/cast/` pages. Key patterns to verify:

- Is the filmography in a `<table>` or in `<div>` cards?  
- Does "מרבה לעבוד עם" have its own `<section id="...">` or is it a `<div class="...">` block?
- Are year and role in separate `<td>` columns or in the same cell?

**Do a test fetch first**, print the relevant HTML section, confirm the regex patterns match before writing the full loop.

---

## Verification

After `edb_persons.json` is built, run:
```python
import json
persons = json.load(open("edb_persons.json"))
seed   = [p for p in persons if p.get("is_seed")]
collab = [p for p in persons if not p.get("is_seed")]
total_films = sum(len(p.get("films",[])) for p in persons)
total_collabs = sum(len(p.get("collaborators",[])) for p in persons)
print(f"Seed: {len(seed)}, Expanded: {len(collab)}, Total: {len(persons)}")
print(f"Total film credits: {total_films}")
print(f"Total collaborator links: {total_collabs}")
# Sanity checks
assert len(persons) > 500, "too few persons"
assert total_films > 2000, "too few film credits"
print("OK")
```

Write verification results to `logs/EDB_PHASE3_COMPLETE.md`.
