---
name: t26-movies-db-film-dedup-bug
description: movies_db filmography shows duplicate film entries because same film has different film_id keys across sources (edb:tXXX vs makor:YYY vs nfct:ZZZ); 231 affected cards, 400 duplicate pairs
metadata:
  type: project
---

**Bug found 2026-06-05** — introduced by the movies_db filmography refactor.

`_build_movies_index()` deduplicates films by `film_id`. Each data source assigns its own `film_id` namespace prefix (`edb:`, `makor:`, `nfct:`, `fdoc:`, etc.), so the same film appears under multiple keys. `person_films()` returns all matches without cross-namespace title deduplication, and the render loop (line 2914–2944 in `resolve_entities.py`) emits one `<div class="resume-film-entry">` per bucket entry.

**Scale:**
- 231 profile cards have at least one duplicate film title
- 400 total duplicate pairs (307 both linked, 93 one linked + one unlinked)
- 3 triple duplicates (מועדון בית הקברות, צלקת, דרייבר)
- Top example: משה אדרי shows "רוק בקסבה" twice — edb (2011) and cinemaofisrael (2012)

**Fix:** Add a post-merge title-based dedup step in `person_films()` or in the render loop. After collecting all credits, group by `normalize_film_title(title)` and keep the entry with the best URL (prefer `edb.co.il` URLs; merge roles from all entries in the group).

**Why:** No cross-source film_id mapping exists in movies_db; each importer writes its own `film_id` prefix and the merge only dedupes within the same prefix.

**How to apply:** Report as FAIL in every QA run. This is the top-priority bug from the movies_db filmography change.

See also [[t22-rabinovich-no-film-url]] for the related "no URL" pattern.
