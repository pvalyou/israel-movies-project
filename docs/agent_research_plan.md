# Research Agent Plan — Missing Data Gaps
*Generated 2026-06-01*

## What the agent needs to do

For each item below, the agent should:
1. Fetch the URL
2. Extract all people (name_he, role, year, org)
3. Add a new JSONL record to the correct `out/<source>/mentions.jsonl`
4. Format must match the existing records (see `out/jff/mentions.jsonl` for the template)

After all items are done, run: `python3 resolve_entities.py`

---

## Priority 1 — Festival staff pages (lector-equivalent roles, direct conflict risk)

These are selectors/programmers who also make films — the same conflict pattern as fund lectors.

### JFF — All staff pages via site search (scrape loop)

**Search URL** (returns all "צוות" articles on jff.org.il / jer-cin.org.il):
```
https://www.google.com/search?q=site:+jff.org.il+%D7%A6%D7%95%D7%95%D7%AA
```

**Agent task**:
1. Fetch the Google search results page above
2. Extract all `jff.org.il` or `jer-cin.org.il` result URLs that look like staff/team pages (contain "צוות" or year in URL/title)
3. For each result URL, fetch the page and extract all people (name_he, role, year)
4. Add each year as a separate JSONL record to `out/jff/mentions.jsonl`
5. We already have **2022** (article 68273) and **2025** (article 86793) — skip those, add the rest

**Known missing years**: 2021, 2023, 2024 (and earlier if found)
**Target**: source_name = "jff", roles = festival_programmer / artistic_director / festival_director, year = the festival year
**URL pattern on jer-cin.org.il**: `/he/מאמר/<id>` — the article ID encodes the year indirectly

### DocAviv — Selection committee
- **DocAviv 2024/2025 selectors**: `https://www.docaviv.co.il/` — find the team/staff page
- Target: `out/festival_data/mentions.jsonl`, source_name = "festival_data"

### Haifa Film Festival — Selection committee
- Already have `out/haifa_film_festival/` but check if selectors are there or only management
- URL: `https://www.haifaff.co.il/` → staff/team page
- Target: `out/haifa_film_festival/mentions.jsonl`

---

## Priority 2 — TISFF (Student Film Festival) past years

Site: `https://srita.net/`
We added 2021. Still missing:
- **TISFF 2022**: search `srita.net` for the 2022 final results article
- **TISFF 2023**: search `srita.net` for the 2023 final results article
- **TISFF 2024**: search `srita.net` for the 2024 final results article
- Format: add to `out/festival_data/mentions.jsonl` (same as TISFF 2021 entry we added today)
- Only extract **Israeli competition** and **short film competition** winners (international names not relevant)

---

## Priority 3 — Talent agency rosters (filmmaker profiles)

These give us film lists + fund connections for known filmmakers.

### Niv Eshet Cohen agency — full client list
- URL: `https://niveshetcohen.com/` → browse all client profiles
- We already did כליל כובש. The agency likely has 15–30 other filmmakers.
- For each client: extract name, films, funds, festivals
- Films to add: if a film is funded by a fund in our data (gesher/rabinovich/makor/nfct/filmfund/galilee), add the film+person to `out/<fund>/mentions.jsonl`
- **Especially valuable**: any client who is ALSO a lector in our data → immediate conflict

### Other Israeli talent agencies to check:
- Dafna Ella Agency (`https://www.dafna-ella.com/`)
- Cast & Characters (`https://castcharacters.co.il/`)

---

## Priority 4 — כליל כובש — complete filmography (immediate)

From `https://niveshetcohen.com/rep/כליל-כובש/` we have her full filmography but haven't added all films to the data yet:

Films to add to `out/makor/mentions.jsonl` and other relevant fund sources:
| Film | Year | Fund | Status |
|------|------|------|--------|
| שכבות (Layers) | 2024 | Negev Film Fund + Makor | completed |
| נחל עמוד (Nahal Amud) | 2025 | Galilee Film Fund + Lehat Family | post-production |
| ילדי בר (Bar Children) | TBD | Rabinowitz + Galilee | post-production |
| אורות (Lights) | TBD | Rabinowitz (development) | development |
| אחו (Achu) | 2020 | student | completed |
| מסיבת פרידה (Farewell Party) | 2017 | student | completed |
| קראנו לו בית (We Called It Home) | 2016 | student | completed |
| נינו (Nino) | 2015 | student | completed |

Note: "שכבות" is already in makor data. Add the others especially fund-supported ones.

---

## Priority 5 — 94 gatekeepers with no film data

There are 94 people who hold lector/board/jury roles but have NO film data. For each:
1. Search EDB (`edb.co.il/name/`) for their name
2. If found, add their EDB profile to `out/edb/mentions.jsonl`

High-value targets (lectors with common Israeli filmmaker names):
- לימור אהרונוביץ'
- ענת אגמון
- גיל סמסונוב
- טלי אוברמן
- נמרוד לב
- דנה גובי
- חלי סממה פדידה

---

## Priority 6 — Wikipedia enrichment

For each person in the entity_registry who has NO wiki_url in `enriched/wiki_persons.json`:
- Search Hebrew Wikipedia for their name
- If found: extract birth year, intro snippet, career description
- Update `enriched/wiki_persons.json`

This helps with:
- Gender inference (context sentences from Wikipedia)
- Birth year → career timeline analysis
- Verifying role information

---

## What NOT to do
- Don't fetch generic search pages (Google, etc.) — fetch known structured pages only
- Don't add people who are purely operational staff (box office, ushers, drivers)
- Don't add people from international competition (non-Israeli names)
- Skip people who already have 3+ sources in `entity_registry.json`

---

## Output format reminder

Every new JSONL record must follow this structure:
```json
{
  "file": "<source>__<slug>__manual.md",
  "url": "<actual_page_url_or_manual://>",
  "source_name": "<source_key>",
  "status": "ok",
  "content_hash": "manual",
  "content_length": 0,
  "filter_info": {"reason": "manual_import"},
  "truncated": false,
  "elapsed_sec": 0,
  "data": {
    "metadata": {"source_url": "...", "source_name": "...", "extraction_date": "2026-06-01", "language": "he"},
    "entities": {
      "people": { "person_001": {"name_he": "...", "name_en": null, "aliases": [], "primary_roles": [...], "context_sentence": "...", "sources": ["..."]} },
      "organizations": { "org_001": {"name_he": "...", "name_en": "...", "type": "...", "sources": ["..."]} },
      "films": {},
      "events": {}
    },
    "roles": [
      {"id": "role_001", "person_id": "person_001", "organization_id": "org_001", "role_type": "festival_programmer", "start_year": 2022, "end_year": 2022, "notes": "...", "sources": ["..."]}
    ],
    "relationships": [],
    "films": []
  }
}
```

### Valid role types for festival context:
- `festival_programmer` — film selector / curator (= "אוצר")
- `festival_director` — festival director
- `artistic_director` — artistic director
- `jury_member` — jury member
- `prize_winner` — award recipient
- `ceo` — CEO/director general
- `lector` — only if they specifically screen scripts (fund context)

### Valid source keys:
- `jff` → Jerusalem Film Festival (jff.org.il / jer-cin.org.il)
- `festival_data` → all other festivals (docaviv, haifa, TISFF, etc.)
- `haifa_film_festival` → Haifa specifically (already has source)
- `makor` / `gesher` / `rabinovich_cinema` / etc. → fund-specific
