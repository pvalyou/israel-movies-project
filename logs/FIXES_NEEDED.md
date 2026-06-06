# EDB Graph — Fixes Needed
**Reviewed:** 2026-05-29  
**Reviewer:** Claude Code (analysis of actual files, not the report)

---

## Summary

Raw data collection is good. The graph-building step has 3 bugs that make 89% of the new edges unusable. Fix these before the visualization project starts.

| Issue | Edges affected | Severity |
|-------|---------------|----------|
| Missing person nodes for edb crew | 43,915 co_credited dangling | 🔴 Critical |
| Reviewed edges point to films not in graph | 3,869 reviewed dangling | 🔴 Critical |
| fund_recipient has no film source | 6/6 broken | 🟡 Medium |
| 68% of roles mapped to "other" | affects all co_credited | 🟡 Medium |
| Report totals wrong (₪341M vs actual ₪119M for NFCT) | documentation only | 🟠 Minor |

---

## Fix 1 — Missing person nodes for edb crew 🔴

**Problem:**  
`build_network_graph()` creates co_credited edges between crew members using `person::{name_he}` IDs, but only creates *nodes* for people already known to the existing pipeline (fund lectors, guild members, etc.). The ~2,800 Israeli filmmakers who appear only in edb credits have edges but no corresponding nodes. D3/Sigma drops dangling edges silently — **89% of co_credited edges are invisible in the visualization.**

**Verified:** 43,915 / 49,157 co_credited edges dangling.

**Fix:**  
When iterating edb crew to generate co_credited edges, check if a person node already exists. If not, create a stub node:

```python
def ensure_person_node(nodes_dict, name_he, edb_id=None):
    node_id = f"person::{name_he}"
    if node_id not in nodes_dict:
        nodes_dict[node_id] = {
            "id": node_id,
            "label": name_he,
            "type": "person",
            "group": "person",
            "edb_id": edb_id or "",
            "has_strict_conflict": False,
            "has_soft_conflict": False,
            "source_count": 0,
            "roles": [],
        }
    return node_id
```

Call this for both crew members before appending each co_credited edge. Add all resulting stub nodes to the graph's node list before writing `network_graph.json`.

**Expected result after fix:** ~2,800 new person nodes added; all 49,157 co_credited edges become valid.

---

## Fix 2 — Reviewed edges point to films not in graph 🔴

**Problem:**  
The 7 edb critics reviewed 3,116 unique films total, but the graph only contains 285 film nodes (the Israeli films from Phase 1). The reviewed edges use correct edb film IDs (`film::t0002695` etc.) but those films are not nodes — **96% of reviewed edges are dangling.**

**Verified:** 3,869 / 4,005 reviewed edges dangling (target side only — critic person nodes are fine).

**Two options — pick one:**

**Option A (recommended): Add reviewed films as stub nodes**  
When building reviewed edges, for any target film ID not already in the node set, create a stub film node:

```python
def ensure_film_node(nodes_dict, edb_film_id, title="", year=None):
    node_id = f"film::{edb_film_id}"
    if node_id not in nodes_dict:
        nodes_dict[node_id] = {
            "id": node_id,
            "label": title or edb_film_id,
            "type": "film",
            "group": "film",
            "year": year,
            "edb_id": edb_film_id,
            "edb_url": f"https://www.edb.co.il/title/{edb_film_id}/",
            "is_short": False,
        }
    return node_id
```

The `edb_blog_reviews.json` file already contains the film title and year for each reviewed film — use those to populate `label` and `year`.

**Option B (simpler): Filter reviewed edges to in-graph films only**  
Skip any reviewed edge whose target film is not already in the 285-film node set. This drops 96% of reviews but keeps the graph clean. Do this if you don't want to bloat the graph with non-Israeli films.

**Expected result after Fix A:** ~3,100 additional film nodes; all 4,005 reviewed edges become valid.  
**Expected result after Fix B:** ~136 reviewed edges remain, all valid.

---

## Fix 3 — fund_recipient edges have no film source 🟡

**Problem:**  
All 6 fund_recipient edges have an empty string as their source node (`"" → fund::filmfund`). The funding records in `out/funding_amounts/mentions.jsonl` contain grant amounts but no edb film IDs — so there's no way to link them to specific film nodes.

**Verified:** 6/6 fund_recipient edges dangling on source side.

**Fix (partial — best effort):**  
Match funding records to film nodes by normalizing Hebrew titles. For each funding record that has a film title, find the closest-matching film node by title. Only create the edge if the match is unambiguous (exact normalized title match or near-exact).

```python
from unicodedata import normalize as uni_norm
import re

def norm_title(t):
    t = uni_norm("NFKC", t or "")
    t = re.sub(r'["\'״׳.,!?]', '', t)
    return re.sub(r'\s+', ' ', t).strip()

# Build lookup: norm_title → film_node_id
title_to_film = {norm_title(n["label"]): n["id"] 
                 for n in graph_nodes if n["type"] == "film"}

# When building fund_recipient edge:
film_id = title_to_film.get(norm_title(record_film_title))
if film_id:
    # create edge: film_id → fund_node_id
```

If no title match, **skip the edge** — a dangling edge is worse than no edge.

**Note:** Most funding records don't have a film title at all (they aggregate totals per fund, not per film). Only wire the ones that do. This will result in fewer than 6 edges — that's fine.

---

## Fix 4 — Role mapping: 68% mapped to "other" 🟡

**Problem:**  
The original `ROLE_MAP` only handled 6 Hebrew role strings. EDB uses parenthetical format for technical roles (`(עריכה)`, `(עיצוב פסקול)`) and gender-neutral slashes (`מפיק/ה שותפ/ה`). 3,384 of 4,974 crew entries (68%) are `role: "other"`, making `role_a`/`role_b` fields on co_credited edges mostly useless for filtering.

**Fix:**  
Replace the ROLE_MAP in `scrape_edb.py` with the expanded version below, then re-export `out/edb/mentions.jsonl` from the existing `edb_films.json` (no re-scraping needed):

```python
ROLE_MAP = {
    # Major roles — plain Hebrew
    "בימוי":              "director",
    "הפקה":               "producer",
    "תסריט":              "screenwriter",
    "עריכה":              "editor",
    "צילום":              "cinematographer",
    "מוסיקה מקורית":      "composer",
    "עיצוב פסקול":        "sound_designer",
    "שחקן":               "actor",
    "שחקנית":             "actor",

    # Parenthetical technical roles
    "(עריכה)":            "editor",
    "(צילום)":            "cinematographer",
    "(עיצוב פסקול)":      "sound_designer",
    "(עיצוב פסקול ועירבול)": "sound_designer",
    "(עיצוב אמנותי)":     "production_designer",
    "(עיצוב תלבושות)":    "costume_designer",
    "(ליהוק)":            "casting_director",
    "(איפור)":            "makeup_artist",
    "(עריכת תסריט)":      "script_editor",
    "(הקלטה)":            "sound_recordist",
    "(מקליט/ת ראשי/ת)":   "sound_recordist",
    "(עוזר/ת בימוי)":     "assistant_director",
    "(עוזר/ת בימוי ראשונ/ה)": "first_ad",
    "(עיצוב תמונה)":      "production_designer",
    "(הפקת פוסט)":        "post_producer",
    "(תחקיר)":            "researcher",
    "(צילום סטילס)":      "still_photographer",

    # Gender-neutral slash notation
    "מפיק/ה שותפ/ה":      "co_producer",
    "מפיק/ה ראשי/ת":      "executive_producer",
    "מפיק/ה אחראי/ת":     "line_producer",
    "צלמ/ת ראשי/ת":       "cinematographer",

    # Other production roles
    "הפקה בפועל":         "line_producer",
    "מפיק שותף":          "co_producer",
    "עיצוב אמנותי":       "production_designer",
    "יצירה":              "creator",
}
```

After updating the map, re-run Phase 1c (the export script only — `edb_films.json` is already complete, no re-scraping):

```bash
python3 export_edb_mentions.py   # regenerates out/edb/mentions.jsonl
```

Then re-run Phase 5 (graph rebuild) to get the updated role labels on co_credited edges.

---

## Fix 5 — is_short flag always False 🟠

**Problem:**  
The `short_ids` set was collected in Phase 1a but not persisted. By the time Phase 1b ran, `is_short` was always `False` because `film_id in short_ids` had no set to check against.

**Fix:**  
`edb_film_ids.json` currently stores a flat list of all IDs. Change it to store short vs. feature IDs separately:

```json
{
  "feature_ids": ["t0001223", ...],
  "short_ids": ["t0005001", ...],
  "all_ids": ["t0001223", ..., "t0005001", ...]
}
```

Then in `scrape_film()`, pass in the short_ids set and set `"is_short": film_id in short_ids`.

Since `edb_films.json` is already scraped, just update the `is_short` field in-place:

```python
import json

# Load the ID lists (re-run Phase 1a with the fix, or manually identify shorts)
short_ids = set(...)   # the 98 short IDs from Phase 1a

films = json.load(open("edb_films.json"))
for f in films:
    f["is_short"] = f["film_id"] in short_ids
json.dump(films, open("edb_films.json", "w"), ensure_ascii=False)
```

---

## Execution order for fixes

```
1. Fix ROLE_MAP in scrape_edb.py
2. Re-run Phase 1c → regenerates out/edb/mentions.jsonl with correct roles
3. Fix build_network_graph() in resolve_entities.py:
     a. ensure_person_node() for all edb crew
     b. ensure_film_node() for all reviewed films (or filter)
     c. Fix fund_recipient source wiring
4. Run resolve_entities.py → regenerates network_graph.json
5. Verify: zero dangling edges in output
```

---

## Verification checks (run after fixes)

```python
import json
g = json.load(open("network_graph.json"))
node_ids = {n["id"] for n in g["nodes"]}
dangling = [e for e in g["edges"] if e["source"] not in node_ids or e["target"] not in node_ids]
assert len(dangling) == 0, f"{len(dangling)} dangling edges remain"

# Expected counts after fixes
persons = [n for n in g["nodes"] if n["type"] == "person"]
films   = [n for n in g["nodes"] if n["type"] == "film"]
cc      = [e for e in g["edges"] if e["type"] == "co_credited"]
assert len(persons) > 4000, f"Expected 4000+ persons, got {len(persons)}"
assert len(cc) == 49157, f"All co_credited edges should be valid"
print("All checks passed")
```
