# Data Pipeline — Israeli Film Conflict Graph

The pipeline scrapes Israeli film industry data, resolves entities, builds graphs, and renders **three HTML deliverables**.

---

## End Goal: 3 HTML Outputs

| HTML | Purpose | Data File | Built By |
|------|---------|-----------|----------|
| **graph.html** | Interactive conflict-of-interest network (Cytoscape) | `conflict_graph.json` | `scripts/build_conflict_graph.py` |
| **films.html** | Searchable films database (2,067 films) | `data/movies_db.json` | `scripts/build_films_html.py` |
| **connections_report.html** | Entity resolution QA report (dedup + fuzzy matches) | `entity_registry.json` + mentions | `resolve_entities.py` |

---

## Pipeline Flow (top → bottom)

```
╔═══════════════════════════════════════════════════════════════════════════╗
║  STAGE 1 — SCRAPE                       (raw data from web)               ║
╠═══════════════════════════════════════════════════════════════════════════╣

   edb.co.il      cinemaofisrael    jfc.org.il    nfct.org.il   filmfund.org.il
       │                │                │              │                │
   scrape_edb.py   scrape_ci.py    scrape_jfc.py  scrape_nfct.py  scrape_filmfund.py
       │                │                │              │                │
       ▼                ▼                ▼              ▼                ▼
   data/edb/        data/ci/         data/jfc/     data/funds/      data/funds/
   raw_films.json   raw_films.json   raw_films.json  nfct_films.json  filmfund_films.json

   ┌─────────────────────────────────────────────────────────────────────┐
   │ Manual sources:                                                     │
   │   - film_faculty_data/faculty_members.json (5 schools, ~400 names)  │
   │   - film_faculty_data/israeli_film_people.csv (critics list)        │
   └─────────────────────────────────────────────────────────────────────┘

╔═══════════════════════════════════════════════════════════════════════════╗
║  STAGE 2 — EXTRACT MENTIONS             (NER + LLM extraction)            ║
╠═══════════════════════════════════════════════════════════════════════════╣

   all scraped pages + manual imports
                  │
        llm_extract.py + scripts/importers/*
                  │
                  ▼
        out/<source>/mentions.jsonl    (one per source)

╔═══════════════════════════════════════════════════════════════════════════╗
║  STAGE 3 — RESOLVE                      (canonical entity IDs)            ║
╠═══════════════════════════════════════════════════════════════════════════╣

   out/*/mentions.jsonl  +  faculty_members.json
                  │
            resolve_entities.py
                  │
       ┌──────────┼───────────┐
       ▼          ▼           ▼
   entity_    ambiguous_   ┌──────────────────────────┐
   registry   pairs.json   │ ★ connections_report.html │ ◄─ HTML #1 (QA report)
   .json                   └──────────────────────────┘

╔═══════════════════════════════════════════════════════════════════════════╗
║  STAGE 4 — CONSOLIDATE FILMS            (merge 3 raw sources)             ║
╠═══════════════════════════════════════════════════════════════════════════╣

   data/edb/raw_films.json   ─┐
   data/ci/raw_films.json    ─┼──►  build_movies_db.py
   data/jfc/raw_films.json   ─┤              │
   entity_registry.json      ─┘              ▼
                                     data/movies_db.json  (2,067 films)
                                              │
   data/funds/*_films.json  ──►  match_fund_films.py
                                              │
                                              ▼
                                     data/movies_db.json  (+ funds field on 580 films)
                                              │
                                              ▼
                                  ┌─────────────────────┐
                                  │   ★ films.html      │ ◄─ HTML #2 (films DB)
                                  │  build_films_html.py│
                                  └─────────────────────┘

╔═══════════════════════════════════════════════════════════════════════════╗
║  STAGE 5 — BUILD GRAPHS                 (network → conflict)              ║
╠═══════════════════════════════════════════════════════════════════════════╣

   data/edb/raw_films.json + entity_registry.json
                  │
        build_network_graph.py
                  │
                  ▼
        network_graph.json  (persons + institutions)
                  │
                  ├──◄── data/movies_db.json       (films + crew + funds)
                  ├──◄── faculty_members.json      (school staff)
                  │
        build_conflict_graph.py
                  │
                  ▼
        conflict_graph.json  (834 nodes, 1,613 edges)
                  │
                  ▼
        ┌──────────────────────┐
        │    ★ graph.html      │ ◄─ HTML #3 (interactive viz)
        │   (Cytoscape+fcose)  │
        └──────────────────────┘
```

---

## Per-Stage Reference

### Stage 1 — Scrape (raw data)
| Script | Source | Output File | Records |
|--------|--------|-------------|---------|
| `scripts/edb/scrape_edb.py` | edb.co.il | `data/edb/raw_films.json` | 285 films |
| `scripts/cinemaofisrael/scrape_cinemaofisrael.py` | cinemaofisrael.org | `data/cinemaofisrael/raw_films.json` | 2,100+ films |
| `scripts/jfc/scrape_jfc.py` | jfc.org.il | `data/jfc/raw_films.json` | 400+ films |
| `scripts/funds/scrape_nfct.py` | nfct.org.il (sitemaps) | `data/funds/nfct_films.json` | 1,359 films |
| `scripts/funds/scrape_filmfund.py` | filmfund.org.il (enumerated) | `data/funds/filmfund_films.json` | 511 films |
| `scripts/importers/import_*_faculty.py` | manual + 5 school sites | `film_faculty_data/faculty_members.json` | ~400 names |

### Stage 2 — Extract Mentions
| Script | Inputs | Output |
|--------|--------|--------|
| `scripts/llm_extract.py` | scraped pages | `out/<source>/mentions.jsonl` |
| `scripts/importers/*.py` | manual + web sources | `out/<source>/mentions.jsonl` |

### Stage 3 — Resolve Entities → produces HTML #1
| Script | Inputs | Outputs |
|--------|--------|---------|
| `resolve_entities.py` | `out/*/mentions.jsonl`, `faculty_members.json` | `entity_registry.json`, `ambiguous_pairs.json`, **`connections_report.html`** |

### Stage 4 — Consolidate Films → produces HTML #2
| Script | Inputs | Outputs |
|--------|--------|---------|
| `scripts/build_movies_db.py` | 3 raw_films.json files + `entity_registry.json` | `data/movies_db.json` (~6,500 films) |
| `scripts/funds/enrich_movies_db_from_funds.py` | `out/*/mentions.jsonl` + `data/funds/*.json` | `data/movies_db.json` (~8,800 films, fund data added) |
| `scripts/build_films_html.py` | `data/movies_db.json` | **`films.html`** |

### Stage 5 — Build Graphs → produces HTML #3
| Script | Inputs | Outputs |
|--------|--------|---------|
| `scripts/edb/build_network_graph.py` | `raw_films.json` + `entity_registry.json` | `network_graph.json` |
| `scripts/build_conflict_graph.py` | `network_graph.json` + `movies_db.json` + `faculty_members.json` | `conflict_graph.json` (834 nodes, 1,613 edges) |
| `graph.html` (static) | reads `conflict_graph.json` at runtime | **`graph.html`** (the file itself is hand-written) |

---

## Data Files at a Glance

**Raw (Stage 1):**
- `data/edb/raw_films.json` — EDB films + crew
- `data/cinemaofisrael/raw_films.json` — Cinema of Israel films + cast
- `data/jfc/raw_films.json` — JFC films + descriptions
- `data/funds/nfct_films.json` — NFCT-funded films
- `data/funds/filmfund_films.json` — Israeli Film Fund films

**Intermediate (Stages 2–5):**
- `out/*/mentions.jsonl` — extracted person/org mentions per source
- `entity_registry.json` — canonical person/org IDs (with aliases)
- `ambiguous_pairs.json` — fuzzy matches for human review
- `data/movies_db.json` — **canonical film database (~8,800 films); source of truth for all reports**
- `network_graph.json` — person × institution network
- `conflict_graph.json` — graph viz data (filtered subgraph)

**Outputs (HTMLs):**
- `connections_report.html` — Stage 3 QA report
- `films.html` — Stage 4 films browser
- `graph.html` — Stage 5 conflict network

---

## Rebuild Commands

**Use the Makefile — it encodes the full acyclic DAG and rebuilds only what changed:**
```bash
make            # build all 3 deliverables, in correct order (incremental)
make validate   # schema-check mentions / registry / movies_db
make clean      # remove generated outputs
make serve      # http.server on :8000
make help       # list targets
```
`./build.sh` is a thin wrapper that calls `make`.

**Acyclic order the Makefile runs** (breaks the old resolve↔movies_db cycle via `--phase`):
```bash
resolve_entities.py --phase resolve                  # → entity_registry.json (no movies_db read)
scripts/build_movies_db.py                           # merge EDB + CI + JFC  → data/movies_db.json
scripts/funds/enrich_movies_db_from_funds.py         # + fund data
scripts/enrich_movies_db_crew.py                     # + full crew from edb_persons.json & fund film pages
resolve_entities.py --phase render                   # → connections_report.html + network_graph.json (reads FRESH movies_db)
scripts/compute_derived_conflicts.py                 # → data/derived_conflicts.json
scripts/build_conflict_graph.py && node scripts/precompute_layout.js   # → conflict_graph.json
scripts/build_films_html.py                          # → films.html
# graph.html is hand-written; reads conflict_graph.json at runtime
```

Reproducibility: the Makefile pins `PYTHONHASHSEED=0` so report output is byte-stable
run-to-run (otherwise set-ordering varies and `make` sees spurious changes).

**Serve locally:**
```bash
python3 -m http.server 8000
# → http://localhost:8000/graph.html
# → http://localhost:8000/films.html
# → http://localhost:8000/connections_report.html
```

---

## movies_db.json — Source of Truth

`data/movies_db.json` is the **single authoritative source for all film data** in this project. Every report, graph, and card derives film credits and fund associations from this file.

### Rule
> If a film is missing from a person's profile card, or a fund badge is wrong, **fix it in `movies_db.json`** — not in `mentions.jsonl`, not in the conflict graph scripts, not via manual importer patches.

### Adding a missing film
1. Add the film record directly to `data/movies_db.json` with the correct `crew`, `funds`, and `year`.
2. Or re-run `scripts/funds/enrich_movies_db_from_funds.py` after scraping the fund source.
3. Then rebuild: `python3 resolve_entities.py && python3 scripts/build_conflict_graph.py`.

### Adding a missing fund association
Edit the film's `funds` array in `movies_db.json`, or re-run `enrich_movies_db_from_funds.py`.

### Querying films
```bash
# All films a person participated in (any crew role)
python3 scripts/query_films.py person "כליל כובש"
python3 scripts/query_films.py person "אסף לפיד"

# All films funded by a specific fund
python3 scripts/query_films.py fund makor
python3 scripts/query_films.py fund galilee_film_fund

# Find a specific film and its metadata
python3 scripts/query_films.py film "שכבות"
```

### movies_db.json schema (key fields)
| Field | Type | Notes |
|-------|------|-------|
| `film_id` | string | `edb:tXXXXX` for EDB films, `<source>:<hash>` for others |
| `sources` | string[] | Which scrapers provided data: `edb`, `cinemaofisrael`, `jfc`, `makor`, etc. |
| `title_he` | string | Hebrew title (canonical) |
| `title_en` | string | English title |
| `year` | int | Release year |
| `is_short` | bool | True for short films |
| `funds` | string[] | Fund source keys: `filmfund`, `nfct`, `makor`, `rabinovich_cinema`, `galilee_film_fund`, `arava_film_fund`, `gesher`, `jerusalem_film_fund`, `fdoc` |
| `crew` | object[] | `{name_he, role, role_he, edb_id, registry_id}` |
| `cast` | object[] | `{name_he, role, character}` |
| `urls` | object | `{source_key: url}` — canonical URL per source |

### What's deprecated
- `scripts/importers/import_filmmaker_profiles.py` — was a workaround to add individual filmmaker filmographies. **Use `movies_db.json` directly.**
- `scripts/add_*.py` scripts (`add_klil_kovesh_films.py`, etc.) — one-off patches. **Add to `movies_db.json` instead.**
