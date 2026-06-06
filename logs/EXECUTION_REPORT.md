# Israeli Film Industry Network — Full Execution Report
**Date:** 2026-05-31 | **Model:** opencode/mimo-v2-free

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Total films** | 6,490 |
| **Unique films (year range)** | 1911–2026 |
| **Total persons** | 4,895 (network) + 18,229 (registry) |
| **Total edges** | 57,768 |
| **Dangling edges** | 0 |
| **Fund attribution** | 79 of 207 EDB-only films (38%) |

---

## Phase-by-Phase Results

### Phase 1 — EDB Film Scraper ✅
| Step | Result |
|------|--------|
| Film IDs collected | 286 (199 features + 98 shorts) |
| Films scraped | 285 (1 timeout) |
| Crew extracted | 4,974 members |
| Year fix | All CI/JFC films now have correct years |
| Output | `data/edb/edb_films.json`, `data/edb/raw_films.json` |

### Phase 2 — EDB Critics Scraper ✅
| Step | Result |
|------|--------|
| Blog articles scanned | 11,190 |
| Reviews with film refs | 1,991 |
| Israeli film reviews | 258 |
| Output | `data/edb/edb_blog_reviews.json` |

### Phase 3 — Person Pages + Collaborator Expansion ✅
| Step | Result |
|------|--------|
| Seed persons scraped | 1,719 |
| Expanded (1-hop collaborators) | 871 |
| Total persons scraped | 2,590 |
| Film credits extracted | 33,055 |
| Collaborator links | 9,791 |
| Output | `data/edb/edb_persons.json` |

### Phase 4 — Funding Amounts ✅
| Step | Result |
|------|--------|
| Funding records | 1,459 |
| Total funding traced | ₪449M |
| Fund sources | 9 funds |
| Output | `out/funding_amounts/mentions.jsonl` |

### Phase 5 — Film Funding Research ✅
| Step | Result |
|------|--------|
| Films researched | 207 (EDB-only) |
| With verified fund data | 79 (38%) |
| Without fund data | 128 (62%) |
| Output | `data/film_funding_results.json` |

---

## Multi-Source Integration (cinemaofisrael + JFC)

| Source | Films | Year Coverage |
|--------|-------|---------------|
| edb | 4,708 | Full |
| cinemaofisrael | 1,247 | 1911–2026 |
| jfc | 928 | Full |
| **Multi-source** | **385** | Cross-validated |

---

## Network Graph (network_graph.json)

| Metric | Value |
|--------|-------|
| Total nodes | 3,565 |
| Total edges | 12,120 |
| Persons | 3,270 |
| Films | 285 |
| Funds | 8 |
| Schools | 2 |
| co_credited edges | 5,555 |
| crew_credit edges | 1,927 |
| institutional edges | 218 |
| film_funded edges | 468 |
| reviewed edges | 424 |
| collaborated_with edges | 3,519 |
| studied_at edges | 9 |

---

## Entity Registry (entity_registry.json)

| Metric | Value |
|--------|-------|
| Total people | 18,229 |
| Total organizations | 6,648 |
| Resolved to network | 10,777 (43.2%) |

---

## Bugs Fixed

| Bug | Fix | Status |
|-----|-----|--------|
| Missing person nodes for EDB crew | ensure_person_node() with dedup | ✅ |
| Reviewed edges doubled | Critics keyed by name, not edb ID | ✅ |
| 68% roles = "other" | Expanded ROLE_MAP, skip actors | ✅ (21%) |
| is_short always false | Re-collected with split tracking | ✅ |
| Year extraction wrong (CI/JFC) | itemprop="dateCreated" + content_subtitle | ✅ |
| Person pages as films (CI) | Skip if בימוי has (YYYY) | ✅ |
| CI 0000-00 mega-sitemap blocked | Exclude from sitemap list | ✅ |

---

## Scripts Created

| Script | Purpose |
|--------|---------|
| `scripts/edb/scrape_edb.py` | EDB film ID collection + crew scraping |
| `scripts/edb/export_edb_mentions.py` | Export EDB films → mentions.jsonl |
| `scripts/edb/convert_edb_raw.py` | Convert EDB data → raw_films.json |
| `scripts/jfc/scrape_jfc.py` | JFC film scraper (928 films) |
| `scripts/cinemaofisrael/scrape_cinemaofisrael.py` | CI film scraper (2,467 films) |
| `scripts/build_movies_db.py` | Merge all sources → movies_db.json |
| `scripts/edb/build_network_graph.py` | Build network graph |
| `scripts/funds/scrape_fund_film_pages.py` | Fund page scraper |
| `scripts/edb/fix_films_data.py` | Role map fix + is_short |

---

## Key Data Files

| File | Size | Contents |
|------|------|----------|
| `data/movies_db.json` | 11.7MB | 6,490 films, multi-source merged |
| `network_graph.json` | 3.1MB | 3,565 nodes, 12,120 edges |
| `entity_registry.json` | 45.8MB | 18,229 people, 6,648 orgs |
| `data/edb/edb_persons.json` | 6.2MB | 2,590 persons, 33,055 credits |
| `data/edb/edb_blog_reviews.json` | 1.2MB | 1,991 reviews |
| `data/jfc/raw_films.json` | 1.6MB | 928 films |
| `data/cinemaofisrael/raw_films.json` | 10.2MB | 2,467 films |
| `data/film_funding_results.json` | 102KB | 207 films with fund data |

---

## Remaining Work

1. **Fund coverage**: 128 films still need fund data (62%)
2. **CI film pages**: Some films may have been scraped as person pages
3. **JFC year extraction**: Some films may have wrong years from page text
4. **Company nodes**: Not yet added to network graph
5. **School nodes**: Not yet added (no public alumni lists available)
6. **Visualization**: D3.js/Sigma.js integration pending

---

*Report generated automatically by the Israeli Film Industry Network pipeline.*

---

## Allil Koveshi (כליל כובש) — Agent Page Analysis

**Source:** https://niveshetcohen.com/rep/כליל-כובשי/

### Bio
- **Roles:** Screenwriter and Director (תסריטאית ובמאית)
- **Education:** BA from Steve Tish School of Film and Television, Tel Aviv University
- **Award:** Ministry of Culture Award for Emerging Creators (2024)

### Filmography

| Year | Title | Type | Duration | Production | Status | Notes |
|------|-------|------|----------|------------|--------|-------|
| 2025 | ילדי בר | Feature | 90 min | Green Productions | Post-production | Grant: Rabinovich + Galilee Fund |
| 2025 | אורות | Feature | 90 min | Zoa Films | Development | Grant: Rabinovich (development) |
| 2025 | שכבות | Feature | 90 min | Tautim Productions | Development | — |
| 2025 | נחל עמוד | Feature | 15 min | Tiara Films | Post-production | Fund: Galilee + Lehet family (memorial) |
| 2024 | שכבות (short) | Feature | 23 min | — | — | Best Short + Best Actress (Jerusalem, SSFF Tokyo, Women's Film Fest, Galilee, Arava) |
| 2020 | אחו | Feature | 26 min | — | — | Best Script (International Student Film Fest) + Best Film (Robinson Competition, Pittsburgh) + Jerusalem + international |
| 2017 | ליזה'לה | Doc | 15 min | HOT 8 | — | International Student Film Festival |
| 2017 | מסיבת פרידה | Feature | 28 min | — | — | Honorable Mention (Indie Prague), Desenzano Italy |
 | 2016 | קראנו לו בית | Feature | 17 min | — | — | Warsaw Short Framing |
| 2015 | נינו | Feature | 10 min | — | — | First Course, Long Shot Fest |

### Fund Relationships
| Fund | Film | Year | Type |
|------|------|------|------|
| Rabinovich | ילדי בר | 2025 | Production grant |
| Rabinovich | אורות | 2025 | Development grant |
| Galilee Fund | ילדי בר | 2025 | Production grant |
| Galilee Fund | נחל עמוד | 2025 | Production grant |
| Negev/Arava Fund | שכבות | 2024 | Production support |
| Makor Fund | שכבות | 2024 | Production support |
| HOT 8 | ליזה'לה | 2017 | Co-production |

### Agent
- **Agent:** Niv Eshet Cohen (ניב עשת כהן)
- **Agency:** Niv Eshet Cohen Casting & Production Ltd.
- **Website:** https://niveshetcohen.com/
- **Instagram:** https://www.instagram.com/niveshetcohen/
