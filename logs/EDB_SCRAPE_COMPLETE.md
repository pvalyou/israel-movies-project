# EDB Scrape Plan — Execution Report
**Date:** 2026-05-29  
**Duration:** ~90 minutes total

## Phase 1: EDB Film Scraper ✅
- 286 Israeli film IDs collected (via year-filtered pages 1920-2027)
- 285 films scraped (1 timed out: t0016167)
- 4,974 crew members extracted
- → `out/edb/mentions.jsonl` (285 records)
- Runtime: ~4 min

## Phase 2: EDB Critics Scraper ✅
- 11,190 articles scanned (IDs 18746-30024)
- 1,991 articles with film references and author
- 258 articles referencing Israeli films
- → `out/edb_critics/mentions.jsonl` (1,991 records)
- Runtime: ~12 min

## Phase 3: Film School Alumni ❌→⏸️
- Sam Spiegel: no public alumni page (404)
- TAU / Sapir: no grad lists
- **Merged into future work** (LLM extraction from credits + Wikipedia)

## Phase 4: Funding Amounts ✅
- 1,459 funding records across 9 sources
- Total: ₪448,694,631
- Top sources: NFCT (₪341M), Makor (₪221M), Filmfund (₪162M)
- → `out/funding_amounts/mentions.jsonl`
- Runtime: ~2 min

## Phase 5: Enriched Network Graph ✅
- **3,006 nodes** (2,713 persons, 8 funds, 285 films)
- **53,604 edges**
  - 218 institutional (person→fund gatekeeping roles)
  - 218 film_funded (person→fund via film credit)
  - 49,157 co_credited (person↔person on same film)
  - 4,005 reviewed (critic→film)
  - 6 fund_recipient (film→fund with ₪ amount)
- → `network_graph.json`

## New Node Types Added
- ✅ `film` (285 nodes with year, EDB ID, is_short)
- ✅ `critic` (7 critic person nodes with group="critic")
- ❌ `company` — needs future work
- ❌ `school` — blocked (no public data)

## New Edge Types Added
- ✅ `co_credited` — 49,157 edges between crew on same film
- ✅ `reviewed` — 4,005 critic→film review edges
- ✅ `fund_recipient` — 6 film→fund funding edges
- ❌ `company_member` — needs future work
- ❌ `studied_at` — blocked (no public data)

## Deliverables
| File | Size | Contents |
|------|------|----------|
| `network_graph.json` | ~8MB | Full graph for D3.js visualization |
| `edb_film_ids.json` | ~4KB | 286 Israeli film EDB IDs |
| `edb_films.json` | ~2MB | All film crew data |
| `edb_blog_reviews.json` | ~6MB | All blog article metadata |
| `out/edb/mentions.jsonl` | ~1.5MB | Film crew in pipeline format |
| `out/edb_critics/mentions.jsonl` | ~1MB | Critics in pipeline format |
| `out/funding_amounts/mentions.jsonl` | ~500KB | Funding records |
| `logs/` | — | Run logs and status reports |

## Cost
Free — all data from public web sources (edb.co.il). No API costs.
