# EDB Phase 3 — Person Pages + Collaborator Expansion — Complete

**Date:** 2026-05-29
**Runtime:** ~35 minutes total

## Scraping Results

| Metric | Value |
|--------|-------|
| Seed persons (from edb_films.json crew) | 1,719 |
| Expanded persons (collaborator 1-hop) | 871 |
| **Total persons scraped** | **2,590** |
| Total film credits | 33,055 |
| Total collaborator links | 9,791 |
| Persons with actor roles | 914 |
| Output file | `edb_persons.json` (6.0MB) |

## Film Role Distribution

| Role | Count | % |
|------|-------|---|
| other | 15,032 | 45.5% |
| actor | 4,775 | 14.4% |
| producer | 3,765 | 11.4% |
| director | 2,377 | 7.2% |
| screenwriter | 2,158 | 6.5% |
| cinematographer | 1,659 | 5.0% |
| editor | 1,318 | 4.0% |
| creator | 711 | 2.2% |
| line_producer | 653 | 2.0% |

## Graph Integration

| Metric | Before | After |
|--------|--------|-------|
| Persons | 3,880 | **4,532** |
| Actor nodes | 0 | **383** |
| collaborator_with edges | 0 | **7,172** |
| Dangling edges | 0 | **0** ✅ |
| Duplicate person labels | 0 | **0** ✅ |

## New Edge Types

- `collaborated_with`: 7,172 person↔person edges (from "מרבה לעבוד עם" sections)
- `actor` role added to 383 person nodes (enabled by person page scraping)

## Files Created

| File | Size | Contents |
|------|------|----------|
| `edb_persons.json` | 6.0MB | 2,590 person profiles with filmography + collaborators |
| `scripts/edb/scrape_edb_persons.py` | — | The Phase 3 scraper |
| `network_graph.json` | ~12MB | Updated with Phase 3 data |
