# Data Enrichment Plan

Tracks ongoing enrichment tasks for the Israeli film industry pipeline.
Each section covers a gap, its method, status, and how to run it.

---

## E8 — Rabinovich Cinema Project lectors (2013–2025) ✅ DONE 2026-05-20

**Source:** `cinemaproject.org.il` — downloaded 5 PDF files covering years 2013–2025:
lectors2015 (2013-15), lectors2017 (2016-17), lectors2023 (2020-23), lectors-2024, lectors-2025

**Script:** `import_rabinovich_lectors.py`

**Status:** 56 synthetic entries written to `out/rabinovich_cinema/mentions.jsonl` (1226 total).
Covers feature film, documentary, student, regional tracks. Years 2013–2025.

Additional Rabinovich PDFs — OCR done 2026-05-20:
- `rabinovich__projects2015.pdf` — funded projects 2015 (21 pages) ✅ OCR done
- `rabinovich__films2023.pdf` — funded films 2023 (19 pages) ✅ OCR done
- `rabinovich__budget-2020-2025.pdf` — budget data (21 pages) ✅ OCR done
- OCR output: `sources/rabinovich_cinema/files/rabinovich__films_ocr.json` (427KB)
- Import script: `import_rabinovich_films.py` — 55 new records, 1197 persons extracted
- Total `out/rabinovich_cinema/mentions.jsonl`: 1281 records

---

## E9 — fdoc.org.il documentary film catalog ✅ SCRAPED 2026-05-20

**Source:** `https://www.fdoc.org.il/movie-sitemap.xml` — 361 URLs
**Script:** `scrape_from_sitemap.py` + `llm_extract.py`

**Status:** 360 pages scraped to `sources/fdoc/pages/`. LLM extraction running (→ `out/fdoc/mentions.jsonl`).

Each page contains: film title, year, director (בימוי), producer (הפקה), supporting funds (גופים תומכים).
The supporting funds field cross-references Makor, Gesher, Rabinovich, NFCT etc.

**Run when needed:**
```bash
python3 scrape_from_sitemap.py fdoc "הפורום הדוקומנטרי" https://www.fdoc.org.il/movie-sitemap.xml
export OPENROUTER_API_KEY=...
python3 llm_extract.py sources/fdoc/pages out --source-name fdoc --workers 8
```

---

## E10 — Guild position papers — igudim 2025 PDF

**Source:** `https://github.com/levialon/doc-funding` → `files/2026-igudim-papers.pdf`
**File:** `sources/guilds/files/guilds__2026-igudim-position-papers.pdf` (18 pages, Dec 2025)

**Content:** Position paper on Communications Law from Israeli creators' guilds.
**Problem:** Custom font encoding — 0 readable Hebrew chars via pdftotext/PyMuPDF.
**Solution:** Vision LLM OCR (Gemini 2.5 Flash) → `sources/guilds/files/guilds__2026-igudim-ocr.json`

**Status:** OCR running as of 2026-05-20.

---

## E11 — Fund budget and grant amounts

**Source:** `https://github.com/levialon/doc-funding` (levialon's dashboard)
**File:** `enriched/funding_amounts.json`

**Content:**
- Budget per fund per year (2023–2025): Rabinovich, NFCT, Makor, Gesher + 4 regional funds
- Approval rates: Makor 3%, Rabinovich 6%, Gesher 10%, NFCT 12%
- Top funded projects with amounts (13 entries with film names, fund, year, NIS amount)
- Two named filmmakers: גלעד טוקטלי (Rabinovich 748K), דורון צברי (Rabinovich 400K)
- Total documentary investment 2025: 62.4M NIS

**Status:** ✅ DONE 2026-05-20. Data ready in `enriched/funding_amounts.json`.

---

## E12 — Wikipedia person enrichment

**Script:** `enrich_from_wiki.py`
**Output:** `enriched/wiki_persons.json`

**Priority queue:** 3,738 persons (lectors + multi-source), sorted by conflict relevance.
Searches Hebrew Wikipedia API, extracts: birth_year, wiki_url, key_roles, affiliations.

**Run:**
```bash
python3 enrich_from_wiki.py --limit 500   # first 500 priority persons
python3 enrich_from_wiki.py --all         # all 15,929 Hebrew persons
python3 enrich_from_wiki.py --name "שם"  # single lookup
```

**Status:** Running 2026-05-20 (PID varies). 101 cached, 41 with hits, 24 with birth years.
Match quality improved: requires both first AND last name to appear in article title.
False positive rate reduced (e.g. "קובי מזרחי" no longer matches "קובי פרג'").

**Results so far (partial, 101/~4078):**
Birth years found: אביגיל שפרבר (1973), עידו הר (1974), ארז לאופר (1962), עמית גורן (1957),
דליה מבורך (1955), רון גולדמן (1970), חגי ארד (1975), שירה גפן (1971), גלעד ענבר (1973), etc.

---

## E1 — Film year lookup via TMDB

**Gap:** 15 films from `/film/`-style fund pages are missing release year.
Year is used by the conflict-strength calculation (strong ≤ 2yr, medium ≤ 4yr, weak > 4yr).
All currently active conflict entries already have years; this closes the gap for borderline cases.

**Source:** [The Movie Database (TMDB)](https://www.themoviedb.org/) — free API, good Israeli coverage.

**Script:** `enrich_film_years.py`

```bash
export TMDB_API_KEY=<your_key>   # register at themoviedb.org/settings/api

# Dry run — prints matches, no writes
python3 enrich_film_years.py

# Also patch years back into mentions.jsonl files
python3 enrich_film_years.py --write

# Limit to one source
python3 enrich_film_years.py --source jerusalem_film_fund
```

**Outputs:**
- `enriched/film_years.json` — `{normalized_title: year}` lookup consumed by resolve_entities.py
- `enriched/film_years_log.json` — full TMDB response log

**Status:** Script written, awaiting TMDB_API_KEY.
**Films to enrich (15):** All from `jerusalem_film_fund`; e.g. "החתונה של מאיה", "טירת החול", "The Cakemaker".

---

## E1b — filmfund historical lectors — May 2023 PDF

**Source:** Official Israel Film Fund approved lectors list as of May 2023.
**PDF URL:** `https://d18hmyzxupgbf8.cloudfront.net/wp-content/uploads/2023/06/%D7%A8%D7%A9%D7%99%D7%9E%D7%AA-%D7%94%D7%9C%D7%A7%D7%98%D7%95%D7%A8%D7%99%D7%9D-%D7%94%D7%9E%D7%90%D7%95%D7%A9%D7%A8%D7%99%D7%9D-%D7%A0%D7%9B%D7%95%D7%9F_%D7%9C%D7%9E%D7%90%D7%99_2023.pdf`
**Record:** `manual://filmfund/lectors-list-2026-05/supplemental-2023` (228 names)

**Why keep:** Historical panel; 207/228 names are not on the current live page but were
official gatekeepers in 2023. Relevant for conflict detection against films funded that year.

**Note:** Cards in the report show "לקטור (מאי 2023)" to distinguish from the current 2026 list.
`import_filmfund_lectors.py` is safe to re-run — the supplemental-2023 record is preserved.

---

## E2 — Gesher Film Fund lectors (web scrape refresh)

**Gap:** Our manual import covers 2015-2025 (512 lectors). The Gesher page is live and may have updates.

**Source:** `https://gesherfilmfund.org.il/Page/45/`
**Fetched:** 2026-05-19 — full current list retrieved (≈230 names, see below for sample).

**Status:** Live list retrieved successfully. Cross-check with `out/gesher/mentions.jsonl` to identify new names.

**New names to verify (spot-check from live page):**
תמר גן צבי, יאיר רוה, גיא עפרן, נועה אהרוני, ערן ברק, אסף לפיד, רנא אבו פריחה, ענת אייזנברג, קובי פרג', רות ולק, מורן נקר, חלי רוזנברג, דנאל אל-פלג, בר כהן, עומר פרלמן, פיני טבגר, עמיר מנור, סמדר זמיר, אסתי מקלברג, אודיה רוזנק, זוהר שחר

To import as manual records:
```bash
# Edit import_gesher_lectors.py → add new names → re-run
python3 import_gesher_lectors.py
```

---

## E3 — NFCT lector PDFs (2021-2025)

**Gap:** The NFCT lectors page (`nfct.org.il/lectors/`) links to yearly PDFs but displays no names inline.
We have the 2026-05 manual import; older years may have additional lectors not yet in the database.

**Sources (PDFs to parse):**
- Lectors and Artistic Directors 2025
- Lectors and Artistic Directors 2024
- Lectors and Artistic Directors 2023
- Lectors and Artistic Directors 2022
- Lectors and Artistic Directors 2021

**Method:** `pdf_to_pages.py` → LLM extraction → `import_nfct_lectors.py`

**Status:** 2026 list already imported. Earlier years pending.

---

## E4 — Jerusalem Film Fund lectors (deeper scrape)

**Gap:** JFF lector list is from 2021 only (`manual://jerusalem_film_fund/lectors-list-2021/`).
The fund likely updated its panel since then.

**Source:** `https://www.jda.gov.il/en/wp-content/uploads/` — look for updated lector PDF.

**Status:** Pending. Check JDA website for 2022-2025 lector lists.

---

## E5 — Guilds board members

**Gap:** `guilds` source has only 8 pages scraped — mostly home/about pages with no structured lists.
Board members of major guilds are publicly listed but not yet in the database.

**Guilds to scrape:**
| Guild | URL | Board page |
|---|---|---|
| Directors Guild | directorsguild.org.il | Look for `/ועד` or `/board` |
| Producers Guild | producers.org.il | Board page |
| Screenwriters Guild | act.org.il | Board/committee |
| Documentary Guild | fdoc.org.il | Board |

**Method:** Scrape with `scrape.py` targeting board/committee pages specifically.

**Status:** Pending. Roles to extract: `guild_board_member`, `guild_chair`.

---

## E6 — Film Council full membership

**Gap:** Only 4 Film Council pages scraped; the council has ~20 members who are key gatekeepers.

**Source:** `https://www.gov.il/he/departments/units/film_council`
(Returns 403 when fetched programmatically — may need direct browser download.)

**Status:** Pending. Try fetching the council member list from a cached/archived version.

---

## E7 — DocAviv & festival jury lists

**Gap:** `docaviv_festivals` source has 8 pages. Festival jury members are a key power-role category
(they decide which documentaries win prizes and gain visibility).

**Sources:**
- DocAviv: `docaviv.co.il/about/` + annual jury pages (2021-2025)
- Jerusalem Film Festival: `jff.org.il` + jury pages
- TLV International Student Film Festival: `tlvfest.com`
- Animix: `animixfest.co.il`

**Status:** Pending deeper scrape. Target `role: jury_member`, `role: prize_committee_member`.

---

## Bug Fix — Missing relationship records (2026-05-19)

**Bug:** The LLM sometimes records a person with a creative role (e.g., `producer`) on a film's dedicated page but omits the explicit `produced` relationship linking them to the film. The conflict detector only matched crew via relationships and `director_ids`, silently missing these people.

**Impact:** Caused at least two missed conflicts:
- **יוני כהן** — lector at Jerusalem Film Fund AND producer of "בייבי מאפט" (2019, funded by JFF)
- **בני פרדמן** — lector at filmfund, filmmaker on filmfund-adjacent pages

**Fix (resolve_entities.py):** Added fallback in `extract_film_conflicts()`: on dedicated `/film/` pages, any person with a `CREATIVE_ROLES` role is treated as implicit crew of all films on that page, even if no explicit relationship record exists.

**QA test:** T12 in `QA_TESTS.md` — detects lectors who appear as crew on film pages but may be missing from the conflict report.

---

## Running enrichment end-to-end

```bash
# 1. Enrich film years (requires TMDB key)
export TMDB_API_KEY=xxx
python3 enrich_film_years.py --write

# 2. Re-run lector imports after adding new names
python3 import_gesher_lectors.py
python3 import_filmfund_lectors.py

# 3. Regenerate report
python3 resolve_entities.py
```
