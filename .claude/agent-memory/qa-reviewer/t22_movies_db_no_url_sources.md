---
name: t22-movies-db-no-url-sources
description: Updated T22 analysis for movies_db era — 664 unlinked film entries from 786 movies_db records that have no usable URL; breakdown by source
metadata:
  type: project
---

**Updated 2026-06-05** — after movies_db filmography refactor replaced manual:// path.

The old T22 pattern (309 rabinovich_cinema manual:// entries) is now replaced by a new structural breakdown. T22 warns on 664 unlinked entries. Breakdown by `movies_db.json` source:

| Source | No-URL films | Notes |
|--------|-------------|-------|
| makor | 325 | Fund-page films; no per-film canonical URL |
| edb_persons | 291 | EDB person-page imports; `urls={}` because film page was not scraped |
| jerusalem_film_fund | 74 | Fund-page films |
| arava_film_fund | 40 | Fund-page films |
| galilee_film_fund | 31 | Fund-page films |
| gesher | 25 | Fund-page films |

416 of the 664 unlinked entries also have no funder badge (edb_persons films have `funds=[]`).

The remaining 248 have a funder badge but no URL link — these are fund-page films where the fund URL is the source but there's no per-film page.

**Not a code bug** — these films genuinely don't have scrapable per-film URLs in the current data. T22 result "~664 unlinked entries" is WARN, not FAIL.

**Note:** 72 of the 664 could theoretically be linked via a `urls['edb']` fallback in other movies_db records with the same title. The render function already reads `urls.get("edb")` via `_build_movies_index()`, but those films happen to be indexed under a different entry (cross-source dedup issue — see [[t26-movies-db-film-dedup-bug]]).

**How to apply:** When T22 warns, check if the unlinked titles are fund-page sourced. If count is ~600–700, treat as expected structural gap. If count grows unexpectedly, investigate new source imports.
