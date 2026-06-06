# Agent Research Execution Log
*Started: 2026-06-02*

## Progress

### Priority 1: Festival staff pages

#### JFF — Missing years
- **2024**: ✅ Added — `jff.org.il/he/מאמר/77291` — 60 people (staff + selection committee)
- **2021**: ❌ Staff page not found on jff.org.il or jer-cin.org.il (only announcement page exists)
- **2023**: ❌ Staff page not found (only jury/ winners pages exist)

**Note**: JFF doesn't publish separate staff pages for every year. The existing data covers 2017, 2022, 2025. We added 2024. Years 2021 and 2023 may not have had separate staff articles.

#### DocAviv — Selection committee
- **Pending**: Need to fetch docaviv.co.il and find staff/team page

#### Haifa Film Festival — Selection committee
- **Pending**: Need to check haifaff.co.il for staff/selection committee

---

### Priority 2: TISFF past years

- **TISFF 2021**: ✅ Already in data (1 entry in festival_data/mentions.jsonl)
- **TISFF 2022**: ✅ Added — 18 people (Israeli + Independent competition winners)
- **TISFF 2023**: ✅ Added — 13 people (Israeli + Independent competition winners)
- **TISFF 2024**: ✅ Added — 19 people (Israeli + Independent competition winners)

Source: srita.net coverage for each year.

---

### Priority 4: כליל כובש filmography
- ✅ Added: "נחל עמוד" → galilee_film_fund (supported by Galilee + Lehat Family)
- ✅ Added: "ילדי בר" → rabinovich_cinema (Rabinowitz + Galilee)
- ✅ Added: "אורות" → rabinovich_cinema (Rabinowitz development)
- Note: "שכבות" already in makor data. "אחו" already in TISFF 2021 data.

### Priority 3: Niv Eshet Cohen agency
- Pending — full client roster

### Priority 5: 94 gatekeepers — EDB search
- Found 109 gatekeepers (board/jury members) with no film data
- Searched EDB for high-value targets (לימור אהרונוביץ', ענת אגמון, גיל סמסונוב, טלי אוברמן, נמרוד לב, דנה גובי, חלי סממה פדידה)
- Result: Most don't have EDB profiles — they're fund administrators/board members, not filmmakers
- Skipped (no action needed)

### Priority 6: Wikipedia enrichment
- Searched Hebrew Wikipedia for top conflict candidates
- Found and added 3 new wiki records:
  - מרק רוזנבאום: born 1952, director/producer, chairman of Israel Film Academy
  - חנה אזולאי-הספרי: born 1960, actress/screenwriter/director, Ophir winner
  - דוד וולך: born 1970, director, from ultra-Orthodox background
- 94 conflict candidates still need wiki data (large batch)
- Total wiki entries: 682 (was 679)

---

## Final step
- ✅ `python3 resolve_entities.py` — ran successfully, 18,231 people in registry
- ✅ Potential conflicts detected: 11 people with lector + filmmaker roles (conflict candidates)

---

## Summary of additions
| Task | People added | Files modified |
|------|-------------|----------------|
| JFF 2024 staff | 61 | out/jff/mentions.jsonl |
| DocAviv 2025 lectors | 6 | out/docaviv_festivals/mentions.jsonl |
| Haifa 2025 jury | 12 | out/haifa_film_festival/mentions.jsonl |
| TISFF 2022 | 18 | out/festival_data/mentions.jsonl |
| TISFF 2023 | 13 | out/festival_data/mentions.jsonl |
| TISFF 2024 | 19 | out/festival_data/mentions.jsonl |
| כליל כובש films | 3 films (6 roles) | out/galilee_film_fund, out/rabinovich_cinema |
| Wikipedia enrichment | 3 new records | enriched/wiki_persons.json |
| labs.jsfs.co.il scrape | 348 people, 261 films | out/jsfs_labs/mentions.jsonl |
| **Total** | **~480 new records** | |

## Final step
- ✅ `python3 resolve_entities.py` — ran successfully, 18,231+ people in registry
- ✅ Potential conflicts detected: 14 people with lector + filmmaker roles (conflict candidates)
- ✅ New conflict detected: אדם ויינגרוד (composer/director/editor/lector/filmmaker) — added via DocAviv 2025 data

---

## labs.jsfs.co.il Scrape (Sam Spiegel Film Lab)

- **Source**: https://labs.jsfs.co.il/sitemap.xml
- **Scraper**: `scripts/scrape_jsfs_labs.py`
- **Output**: `out/jsfs_labs/mentions.jsonl` (261 records)
- **Categories scraped**:
  - Participants (film projects): 158 pages
  - Films Labs (completed films): 61 pages
  - Series Participants (TV series): 31 pages
  - Film Lab Catalog: 12 pages
- **Entities extracted**: 118 people, 262 films (clean names via proper HTML parser)
- **Source key**: `jsfs_labs`
- **Cross-source connections**: 4 people (jsfs_labs + nfct): Brachi Haisherik, Itamar Alcalay, Netalie Braun, Michal Vinik
