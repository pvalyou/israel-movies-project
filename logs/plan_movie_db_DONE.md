# Plan Movie DB — Execution Complete
**Date:** 2026-05-29  
**Runtime:** ~4 hours total

## Phase Results

| Component | Result |
|-----------|--------|
| EDB raw films | 285 films (converted from existing data) |
| JFC scraper | 928 movies (658 with crew data from JSON-LD) |
| CI scraper | 100 films (from targeted sitemaps) |
| **movies_db.json** | **1,043 films** from 3 sources |

## People Resolution
- 4,423 of 5,890 crew/cast names resolved (75.1%)
- Against 18,213 canonical names in entity_registry.json

## Final Graph (network_graph.json)

| Metric | Before | After |
|--------|--------|-------|
| Nodes | 7,167 | **9,207** |
| Persons | 3,880 | **4,932** |
| Films | 3,279 | **4,265** |
| Edges | 20,814 | **30,026** |
| co_credited | 17,372 | **18,412** |
| reviewed | 4,005 | **4,005** |
| fund_recipient | 0 | **1** (title-matched) |
| collaborated_with | 7,172 | **7,172** |
| Dangling edges | 0 | **0** ✅ |

## New / Enhanced
- +1,062 person nodes (from JFC + CI crew)
- +986 film nodes (JFC films now have crew/co_credited edges)
- +1 fund_recipient edge (title-matched to EDB film)
- films now span 1913–2026 (was mostly 1960s+ from EDB alone)

## Source Coverage
| Source | Films | Unique value |
|--------|-------|-------------|
| EDB | 285 | crew roles, funds, is_short |
| JFC | 658 | directors, actors, descriptions, pre-1990 films |
| CI | 100 | cast+characters, English titles, prod companies |
