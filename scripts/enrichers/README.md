# scripts/enrichers/

Fill gaps in existing `out/*/mentions.jsonl` records — add missing years, genders, Wikipedia links, and crew data without re-running the full LLM extraction.

All enrichers are **idempotent**: already-set fields are never overwritten.

---

## enrich_film_pages.py

Finds films with fewer than `--min-people` crew members extracted, fetches their individual film pages, and appends enriched crew records to `out/<source>/mentions.jsonl`.

```bash
python3 scripts/enrichers/enrich_film_pages.py                    # all sources
python3 scripts/enrichers/enrich_film_pages.py --source nfct --limit 50
python3 scripts/enrichers/enrich_film_pages.py --source fdoc --dry-run
python3 scripts/enrichers/enrich_film_pages.py --min-people 2     # re-enrich thin pages
```

---

## enrich_film_years.py

Finds films missing a `year` field and looks them up via the TMDB API. Writes results to `enriched/film_years.json` (consumed by `resolve_entities.py`).

Requires: `TMDB_API_KEY` env var (free key from themoviedb.org).

```bash
export TMDB_API_KEY=your_key

python3 scripts/enrichers/enrich_film_years.py             # dry run, prints matches
python3 scripts/enrichers/enrich_film_years.py --write     # patch mentions.jsonl in-place
python3 scripts/enrichers/enrich_film_years.py --source jerusalem_film_fund
```

Output: `enriched/film_years.json`, `enriched/film_years_log.json`

---

## enrich_from_wiki.py

Looks up each person on Hebrew Wikipedia and extracts `wiki_url`, `birth_year`, key roles, and affiliations. Results are consumed by `resolve_entities.py` to populate person cards.

```bash
python3 scripts/enrichers/enrich_from_wiki.py              # lector-priority persons
python3 scripts/enrichers/enrich_from_wiki.py --all        # all Hebrew persons
python3 scripts/enrichers/enrich_from_wiki.py --limit 200
python3 scripts/enrichers/enrich_from_wiki.py --name "אביגיל שפרבר"
python3 scripts/enrichers/enrich_from_wiki.py --dry-run
```

Output: `enriched/wiki_persons.json`

---

## enrich_mentions.py

Two-pass in-place enrichment of all `mentions.jsonl` files:

1. **Year on roles** — infers `start_year` from the film year on the same page, or from the URL path, or from the extraction date.
2. **Gender** — adds `gender: f|m|unknown` using a Hebrew name lookup table + morphological heuristics.

```bash
python3 scripts/enrichers/enrich_mentions.py                             # all sources
python3 scripts/enrichers/enrich_mentions.py --source nfct
python3 scripts/enrichers/enrich_mentions.py --dry-run
```

---

## nfct_fix_film_urls.py

One-off fix for NFCT film entities whose `sources[]` pointed to search-result pages (`/movies-archive?keywords=...`) instead of actual film pages. Builds a slug index from already-scraped NFCT pages and rewrites bad URLs in `out/nfct/mentions.jsonl`.

```bash
python3 scripts/enrichers/nfct_fix_film_urls.py [--dry-run]
python3 scripts/enrichers/nfct_fix_film_urls.py --scrape-list out/nfct/missing_film_urls.json
```
