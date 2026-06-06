# Israeli Film Industry — Intelligence Pipeline

## Purpose

Map the Israeli film industry to surface **conflicts of interest** — cases where the same person sits on both sides of a funding or awarding decision.

Examples of the conflicts this project hunts for:

- A **lector** (reader/evaluator) at a fund whose own film receives money from that same fund
- A **festival staffer or juror** whose film wins at that same festival
- A **committee member** voting on a film by a close collaborator or family member
- A **critic** who reviews films made by people they have institutional ties to
- A **faculty member** at a school whose students or colleagues get funded under their watch

## Approach

Two halves: **collect everything first, then derive conflicts from the graph.**

1. **Collect.** Scrape ~16 sources (EDB, cinemaofisrael, fund sites, festival sites, school faculty pages, critic lists, council protocols, …) and build two canonical databases:
   - a **movies DB** (`data/movies_db.json`) — who made each film, who funded it, who awarded it
   - a **persons DB** (`entity_registry.json`) — every person plus all their roles (lector, director, juror, faculty, critic, council member, …)
2. **Derive conflicts.** Once people and films are linked, conflicts fall out as graph patterns — the same person appearing on both the "decider" side and the "recipient" side of the same fund, festival, or committee.

---

## Quick start

```bash
# Run the full pipeline (scrape → extract → resolve → report)
python3 resolve_entities.py

# Outputs:
#   entity_registry.json      — all people, funds, films, conflicts
#   ambiguous_pairs.json      — unresolved name-match candidates
#   connections_report.html   — human-readable conflict report
#   network_graph.json        — D3/Sigma-ready node+edge graph
```

---

## Repository layout

```
.
├── CLAUDE.md                   ← Claude Code instructions (do not move)
├── QA_TESTS.md                 ← QA test suite for connections_report.html
├── EDB_SCRAPE_PLAN.md          ← Plan for scraping edb.co.il film credits
│
├── resolve_entities.py         ← Main pipeline: entity resolution + report
│
├── scripts/
│   ├── llm_extract.py          ← LLM-based entity extraction utility
│   ├── scrapers/               ← Web scrapers (scrape.py, scrape_from_sitemap.py, ...)
│   ├── importers/              ← Per-source manual importers (import_*.py)
│   ├── enrichers/              ← Enrichment helpers (enrich_*.py, nfct_fix_film_urls.py)
│   ├── edb/                    ← edb.co.il scrape & graph build scripts
│   │   ├── scrape_edb.py           ← Collect film IDs + crew
│   │   ├── scrape_edb_critics.py   ← Collect blog reviews
│   │   ├── export_edb_mentions.py  ← edb_films.json → out/edb/mentions.jsonl
│   │   ├── extract_funding.py      ← Funding amounts → out/funding_amounts/
│   │   ├── fix_films_data.py       ← Fix role mapping + is_short in edb_films.json
│   │   └── build_network_graph.py  ← Build network_graph.json from all sources
│   └── archive/                ← Older scripts kept for reference
│
├── out/                        ← Structured extractions (pipeline input)
│   └── <source>/mentions.jsonl
│
├── sources/                    ← Raw scraped HTML/markdown pages
├── enriched/                   ← Lookup tables used during resolution
│   ├── wiki_persons.json       ← 679 persons enriched from Wikipedia
│   ├── funding_amounts.json    ← Fund budgets reference
│   └── films_missing_year.json ← Films TMDB couldn't date
│
├── film_faculty_data/          ← Film school faculty JSON (feeds import_film_faculty.py)
├── data/urls/                  ← URL lists for scrapers
├── arava_film_fund/            ← Legacy scrape (first source, kept for reference)
├── bak/                        ← Archived legacy files (not used by pipeline)
│
├── edb_film_ids.json           ← 286 film IDs (199 features + 98 shorts)
├── edb_films.json              ← 285 films with crew (source for out/edb/)
├── edb_blog_reviews.json       ← 11,190 review articles (source for out/edb_critics/)
│
└── docs/                       ← Project documentation
```

---

## Data flow

```
sources/          out/*/mentions.jsonl          entity_registry.json
  └─ scrape ──►  └─ import_*.py / llm_extract  └─ resolve_entities.py ──► HTML report
                                                                        └─► network_graph.json
```

## Network graph

`network_graph.json` — D3/Sigma-compatible, 7,167 nodes · 20,814 edges:

| Nodes | Count |
|-------|-------|
| `person` | 3,880 (200 with conflict flags) |
| `film` | 3,279 (285 Israeli + 2,994 reviewed stubs) |
| `fund` | 8 |

| Edges | Count |
|-------|-------|
| `co_credited` | 16,373 (production crew pairs per film) |
| `reviewed` | 4,005 (critic → film) |
| `institutional` | 218 (person → fund gatekeeping role) |
| `film_funded` | 218 (person's film ← fund) |

See `EDB_SCRAPE_PLAN.md` for full schema. `scripts/edb/build_network_graph.py` builds the graph.
