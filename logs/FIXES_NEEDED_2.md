# EDB Graph — Fixes Needed (Round 2)
**Reviewed:** 2026-05-29  
**Reviewer:** Claude Code (verified against actual network_graph.json)  
**Previous fixes:** See FIXES_NEEDED.md — all verified complete except issues below.

---

## Summary

Node/edge totals match the report exactly. Zero dangling edges confirmed. Three issues found:

| Issue | Severity | Impact |
|-------|----------|--------|
| 33 duplicate person nodes (hyphen/apostrophe variants) | 🔴 Critical | Conflict persons split — their conflict flags won't show in visualization |
| Reviewed edges doubled (~7,847 vs ~4,005 expected) | 🔴 Critical | Each critic review appears twice in the graph |
| Fix 4 overstated — roles still 58% "other" (claimed 45%) | 🟡 Medium | Co-credited edges have less useful role metadata than claimed |

---

## Bug A — 33 duplicate person nodes 🔴

**Problem:**  
Fix 1 created stub nodes using edb name spellings. The existing pipeline nodes use slightly different spellings for the same people. The stub creation didn't normalize before checking for duplicates, so 33 people now have two separate nodes. Some are **conflict persons** — their conflict flags are on the pipeline node, but co_credited edges from edb point to the stub node (no conflict flag). The visualization will treat them as different people.

**Verified:** 33 duplicate label pairs found. Examples:

| Pipeline node (with conflict) | EDB stub (no conflict) | Difference |
|-------------------------------|------------------------|------------|
| `person::דורון גרסי` | `person::דורון ג'רסי` | apostrophe |
| `person::דינה צבי ריקליס` | `person::דינה צבי-ריקליס` | hyphen |
| `person::קובי פרג` | `person::קובי פרג'` | apostrophe |
| `person::דנאל אל פלג` | `person::דנאל אל-פלג` | hyphen |
| `person::אמיר בן דוד` | `person::אמיר בן-דוד` | hyphen |
| `person::אופיר ליבוביץ` | `person::אופיר ליבוביץ'` | apostrophe |

**Root cause:**  
The stub creation checked `if node_id not in nodes_dict` using the raw edb name. But `person::דורון ג'רסי` ≠ `person::דורון גרסי` as string keys, so both were inserted.

**Fix:**  
Before inserting a stub, normalize the candidate name and check against a normalized index of existing nodes. If a match is found, use the existing node's ID for all edges — do not create a stub.

```python
import re, unicodedata

def normalize_for_dedup(name: str) -> str:
    """Strip punctuation variants that differ between sources."""
    name = unicodedata.normalize("NFKC", name)        # normalize unicode (curly → straight apostrophe)
    name = re.sub(r"['’׳']", "", name) # strip all apostrophe forms
    name = re.sub(r"[-־]", " ", name)             # hyphen/maqaf → space
    name = re.sub(r"\s+", " ", name).strip()
    return name

# Build at graph-build time, before any stub creation:
norm_to_existing_id: dict[str, str] = {
    normalize_for_dedup(n["label"]): n["id"]
    for n in existing_nodes
    if n["type"] == "person"
}

def ensure_person_node(nodes_dict, name_he, edb_id=None):
    norm = normalize_for_dedup(name_he)
    if norm in norm_to_existing_id:
        return norm_to_existing_id[norm]   # reuse existing node, don't create stub
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
        norm_to_existing_id[norm] = node_id  # register new stub too
    return node_id
```

**Expected result:** 33 fewer nodes; co_credited edges for conflict persons route through the correct node (with conflict flags). Conflict persons visible in both the co-credit network and the conflict filter simultaneously.

---

## Bug B — Reviewed edges doubled 🔴

**Problem:**  
Critics were added to the graph as nodes twice:
1. From Phase 2 data: keyed by edb numeric ID → e.g. `person::n0013128` with label `"אלי שגב"`
2. From Fix 1 (stub creation): keyed by name → e.g. `person::אלי שגב`

Both nodes exist in the graph with different IDs but identical labels. Both got the full set of `reviewed` edges attached, doubling the count.

**Verified:**
```
אלי שגב:      2,289 × 2 nodes = 4,578 edges  (should be ~1,471)
יונתן דורון:  1,224 × 2 nodes = 2,448 edges  (should be ~291)
גל סדלינסקי:    192 × 2 nodes =   384 edges  (should be ~97)
...
Total: 7,847  (should be ~4,005)
```

**Root cause:**  
Phase 2 built critic nodes using `f"person::{edb_id}"` as the node ID (e.g. `person::n0013128`). Fix 1's `ensure_person_node()` then created a second node `person::אלי שגב` because the key `n0013128 ≠ אלי שגב`. The normalize-for-dedup fix from Bug A won't catch this since `n0013128` doesn't look like a name.

**Fix:**  
Change Phase 2's critic node creation to key by **name**, not edb ID — consistent with how all other person nodes are keyed:

```python
# Phase 2 critic node — use name as key, store edb_id as attribute
critic_node_id = f"person::{critic_name_he}"   # was: f"person::{critic_edb_id}"
nodes_dict[critic_node_id] = {
    "id":    critic_node_id,
    "label": critic_name_he,
    "type":  "person",
    "group": "critic",
    "edb_id": critic_edb_id,    # keep edb_id as attribute for cross-referencing
    ...
}
```

And update all `reviewed` edge sources to use `f"person::{critic_name_he}"` instead of `f"person::{critic_edb_id}"`.

Then Fix 1's `ensure_person_node()` will find the critic in `norm_to_existing_id` and skip creating a duplicate stub.

**Expected result:** ~3,842 duplicate reviewed edges removed; 7 critics each appear as a single node; reviewed count returns to ~4,005.

---

## Fix 4 — Role mapping still 58% "other" (claimed 45%) 🟡

**Problem:**  
After the expanded ROLE_MAP (33 new strings), roles are still 58.3% "other" — not the claimed 45%. The largest unmapped category is **empty string** (`role_he = ""`), which accounts for 829 crew entries and can't be mapped to anything meaningful.

**Verified role_a distribution on co_credited edges:**
```
other:           33,012  (58%)
director:         4,431
producer:         3,034
screenwriter:     2,661
composer:           920
cinematographer:    918
line_producer:      734
co_producer:        729
editor:             496
creator:            351
...
```

**Fix:**  
Two steps:

1. **Skip empty-role crew entries entirely** — a crew member with no role string is almost certainly an actor listed by character name (edb lists actors with their character name as the "role"). These inflate `other` and aren't useful for conflict detection or the network graph.

```python
# In scrape_film(), when building crew list:
for row in re.findall(r'<tr[^>]*>(.*?)</tr>', cast_html, re.DOTALL):
    name_m = re.search(r'href="/name/(n\d+)/"[^>]*>([^<]+)</a>', row)
    role_m = re.findall(r'<td[^>]*>\s*([^\n<]{2,40}?)\s*</td>', row)
    if not name_m:
        continue
    role_he_raw = role_m[-1].strip() if role_m else ""
    role = ROLE_MAP.get(role_he_raw, "other")
    
    # Skip actors (empty role_he = character name in a separate cell) and unmapped roles
    # that are clearly not production crew
    if not role_he_raw:
        continue   # ← ADD THIS — skips ~829 blank-role entries
    
    crew.append({...})
```

2. **Add a few more high-frequency unmapped strings** found after Fix 4:

```python
# Add to ROLE_MAP:
"עיצוב סאונד":        "sound_designer",
"(צוות אחר)":         None,   # skip — catch-all category
"מבצע/ת":             "performer",
"קול":                "voice_actor",
"עצמו":               None,   # skip — documentary subject appearing as themselves
"עצמה":               None,   # skip
"...":                None,   # skip — placeholder entries
```

For `None`-mapped entries: skip the crew member entirely (don't add to crew list).

**Expected result after both steps:** "other" drops from 58% to ~30-35%, dominated by legitimate but rare technical roles. Re-export `out/edb/mentions.jsonl` from existing `edb_films.json` — no re-scraping needed.

---

## Execution order

```
1. Apply Bug A fix (normalize_for_dedup in ensure_person_node)
2. Apply Bug B fix (critic nodes keyed by name, not edb ID)
3. Apply Fix 4 improvement (skip empty roles, add None-mapped entries)
4. Re-export out/edb/mentions.jsonl from existing edb_films.json (no scrape)
5. Run resolve_entities.py → regenerates network_graph.json
6. Verify with checks below
```

---

## Verification checks

```python
import json
from collections import Counter

g = json.load(open("network_graph.json"))
node_ids = {n["id"] for n in g["nodes"]}

# Zero dangling
dangling = [e for e in g["edges"] if e["source"] not in node_ids or e["target"] not in node_ids]
assert len(dangling) == 0, f"{len(dangling)} dangling edges"

# No duplicate person labels
label_counts = Counter(n["label"] for n in g["nodes"] if n["type"] == "person")
dupes = [(l, c) for l, c in label_counts.items() if c > 1]
assert len(dupes) == 0, f"Duplicate person labels: {dupes[:5]}"

# No edb-ID-as-label person nodes
id_nodes = [n for n in g["nodes"] if n["type"] == "person" and n["label"].startswith("n0")]
assert len(id_nodes) == 0, f"{len(id_nodes)} persons have edb ID as label"

# Reviewed edges not doubled — each critic should appear once
critic_nodes = [n for n in g["nodes"] if n.get("group") == "critic"]
critic_ids = {n["id"] for n in critic_nodes}
assert len(critic_ids) == len({n["label"] for n in critic_nodes}), "Duplicate critic nodes"

# Role 'other' under 40%
cc = [e for e in g["edges"] if e["type"] == "co_credited"]
all_roles = [e.get("role_a") for e in cc] + [e.get("role_b") for e in cc]
other_pct = 100 * all_roles.count("other") / len(all_roles)
assert other_pct < 40, f"'other' roles at {other_pct:.1f}% — expected <40%"

print(f"All checks passed. Graph: {len(g['nodes'])} nodes, {len(g['edges'])} edges, {other_pct:.1f}% other roles")
```
