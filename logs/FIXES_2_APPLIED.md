# Fixes Round 2 — Applied & Verified

## Bug A: Duplicate person nodes ✅
**Before:** 33 duplicate person labels (apostrophe/hyphen variants)
**After:** `ensure_person_node()` normalizes names via `norm_for_dedup()` and reuses existing nodes via `_norm_to_id` index
→ **0 duplicate labels** — 33 duplicates merged

## Bug B: Reviewed edges doubled ✅
**Before:** 7,847 reviewed edges (doubled — each critic appeared as both `person::n...` and `person::name`)
**After:** Critics keyed by name only; old edb-ID-keyed nodes stripped at load
→ **4,005 reviewed edges** (correct, not doubled). 7 critics, each one node.

## Fix 4: Roles at 58% "other" (claimed 45%) ✅
**Before:** 58.3% "other" role labels
**After:** Skip actors (empty role_he / first-name only), skip junk entries, expanded ROLE_MAP
→ **32.8% "other"** (target was <40%). 3,034 crew members kept (1,940 actors/junk skipped)

## Final Verification — all passed
| Check | Result |
|-------|--------|
| Zero dangling edges | ✅ |
| No duplicate person labels | ✅ |
| No person nodes with edb ID as label | ✅ |
| No duplicate critic nodes | ✅ |
| Reviewed edges = 4,005 (not 7,847) | ✅ |
| Roles: "other" = 32.8% (<40%) | ✅ |

## Final Graph
7,167 nodes (3,880 persons, 3,279 films, 8 funds), 20,814 edges
