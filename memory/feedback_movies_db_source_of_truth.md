---
name: feedback-movies-db-source-of-truth
description: movies_db.json must be the single source of truth for all film data in reports and graphs — never patch films in elsewhere
metadata:
  type: feedback
---

**Rule:** `data/movies_db.json` is the authoritative source for all film data. All film credits, fund associations, and crew must be added there first — never directly into `resolve_entities.py`, `mentions.jsonl`, or the conflict graph.

**Why:** Adding films via `filmmaker_profiles` importer or by patching mentions.jsonl is a workaround that creates inconsistency. The reports and graphs should all derive from the same dataset. Patching in multiple places makes it impossible to query "what films did person X participate in" reliably.

**How to apply:**
- When a film is missing from a person's card: add it to `movies_db.json` with correct crew + fund data, then rebuild.
- When a fund association is missing: run `enrich_movies_db_from_funds.py` or add the fund key directly to the film's `funds` array in movies_db.
- The pipeline order is: `build_movies_db.py` → `enrich_movies_db_from_funds.py` → `resolve_entities.py` → `build_network_graph.py` → `build_conflict_graph.py`.
- `scripts/query_films.py` is the canonical way to check a person's films: `python3 scripts/query_films.py person "שם הבמאי"`.
- The `filmmaker_profiles` importer and manual film patches (like `add_klil_kovesh_films.py`) are deprecated in favor of direct movies_db entries.
