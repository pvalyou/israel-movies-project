# Israeli Film Industry Investigation — Completion Plan

**Goal:** A PDF investigative report exposing conflicts of interest, power concentration, and funding patterns in the Israeli film industry.

**Current state:** Core fund lector/conflict layer works. ~15% of required sources scraped. Gender, network graph, repeat winners, companies, schools, and festivals all missing.

---

## Phase 1 — Quick wins on existing data (no new scraping needed)

These use data we already have. Do these first — they immediately improve the report.

### 1.1 Gender detection
Add a `gender` field to every resolved person. Approach:
- Build a Hebrew first-name → gender lookup table (500–800 common names)
- Names ending in `ה/ית/ת` (unambiguous feminine endings) → female
- Fallback: mark as `unknown`
- Add gender breakdown stats to the HTML report and to Excel export

**Files to touch:** `resolve_entities.py` — add `infer_gender(name_he)` function, store in person entry, add summary table.

### 1.2 Repeat winners detection
For each director/producer in the data: count how many films they received funding for, from which funds, in which years. Flag anyone with 3+ funded films.

**Files to touch:** `resolve_entities.py` — add `repeat_winners` section to output; add a new HTML table sorted by funding count.

### 1.3 Production company tracking
Currently we track people; we need to also track production companies (חברות הפקה). The LLM already extracts organizations — we just need to surface them.

- Add a "companies" section to the HTML report
- For each company: which films funded, which funds, which years, who the listed producers are
- Flag companies whose producers/directors also sat on lector panels

**Files to touch:** `resolve_entities.py` — use `orgs_raw` data (already loaded, not yet rendered).

### 1.4 Excel export
Add `--export-excel` flag to `resolve_entities.py` that writes:
- Sheet 1: All persons (name_he, name_en, gender, roles, sources, years, conflict_flag)
- Sheet 2: All conflicts (person, role_a, src_a, years_a, role_b, src_b, years_b, strength)
- Sheet 3: Repeat winners (person, film_count, funds, years)
- Sheet 4: Companies (company, films, funds, years, linked_persons)

**Library:** `openpyxl` or `pandas` — already likely available.

### 1.5 Funding round year fix
Currently conflict strength uses film release year as proxy for funding year (off by 2-4 years). Fix:
- Lector list years (`start_year`/`end_year` in roles) = when they served = the evaluation year
- Use lector year directly — don't subtract anything
- Update `conflict_strength` logic: if lector year overlaps with any film page year → "חפיפה"; within 2 years → "סמוך"

---

## Phase 2 — New sources to scrape (high priority)

Use the existing scraper service. Run `scrape.py` or equivalent for each source, then `llm_extract.py`, then `resolve_entities.py`.

### Priority order:

#### 2A — Festival juries & prize committees (highest signal)
These pages name the actual decision-makers per year.

| Source | URL | What to extract |
|---|---|---|
| דוקאביב | https://www.docaviv.co.il/ | jury members, competition selections, industry panels |
| פסטיבל ירושלים | https://jff.org.il/ | jury, programmers, industry days participants |
| פסטיבל חיפה | https://www.haifaff.co.il/ | jury, award winners, selections |
| פרסי אופיר | https://www.israelfilmacademy.co.il/ | judges, nominees, winners by year |
| פסטיבל קולנוע דרום | https://www.sapir.ac.il/cinema/csf | jury, Sapir Prize, lab participants |
| TLVFest | https://tlvfest.com/ | jury, selections |
| פסטיבל אנימיקס | https://www.animixfest.co.il/ | jury |

**LLM prompt additions needed:** add `judge`, `jury_member`, `festival_programmer`, `award_winner` to role extraction schema.

#### 2B — Film schools / faculty lists (high signal for network mapping)
Faculty pages are compact and yield clean data.

| Source | URL | What to extract |
|---|---|---|
| סם שפיגל | https://www.jsfs.co.il/ | faculty, lab mentors, alumni in industry |
| TAU סטיב טיש | https://arts.tau.ac.il/filmTV | faculty, adjuncts |
| ספיר | https://www.sapir.ac.il/staff/dep/17 | faculty list (direct page) |
| בצלאל | https://www.bezalel.ac.il/academics/bachelor_degree/screen | faculty |
| מנשר | https://www.minshar.org.il/film-studies/ | faculty |
| מעלה | https://www.maale.co.il/ | faculty |

**LLM prompt additions needed:** add `lecturer` (academic, not fund lector), `department_head`, `alumni` roles.

#### 2C — Guilds and unions (board members, prize committees)
| Source | URL | What to extract |
|---|---|---|
| איגוד הבמאיות והבמאים | https://directorsguild.org.il/ | board, prize committee |
| איגוד המפיקים | https://producers.org.il/ | board |
| הפורום הדוקומנטרי | https://www.fdoc.org.il/ | board, competition jury |
| האקדמיה הישראלית לקולנוע | https://www.israelfilmacademy.co.il/ | board, Ophir judges |
| איגוד התסריטאים | https://www.writersguild.org.il/ | board |

#### 2D — Government records (public money trail)
| Source | URL | What to extract |
|---|---|---|
| מאגר לקטורים — מועצה לקולנוע | https://www.gov.il/he/departments/publications/Call_for_bids/lectors | official lector registry |
| פרוטוקולים — מועצה לקולנוע | https://www.gov.il/he/pages/pr8 | meeting minutes, decisions |
| מבחני תמיכה קולנוע | https://www.gov.il/he/departments/units/cinema | support criteria, eligible amounts |
| ועדות הכנסת | https://main.knesset.gov.il/ | culture committee minutes |

#### 2E — Film databases (credits cross-reference)
| Source | URL | What to extract |
|---|---|---|
| ארכיון הסרטים הישראלי | https://jfc.org.il/lobby/israeli-cinema/ | canonical credits, years |
| EDB | https://www.edb.co.il/browse/israeli/ | Israeli films credits |
| Israel Film Center | https://israelfilmcenter.org/ | credits, fund attributions |

---

## Phase 3 — New analysis features

### 3.1 Network graph export
Build `export_graph.py` that reads `resolve_entities.py` output and writes:
- `graph.gexf` — for Gephi
- `graph.json` — for D3 / browser visualization

**Nodes:** people, films, funds/organizations, festivals, schools
**Edges:**
- person → fund: `served_as_lector` (year)
- person → fund: `board_member` (years)
- person → film: `produced`, `directed`, `wrote`
- person → school: `teaches_at`
- person → festival: `jury_member` (year)
- film → fund: `received_funding` (year, amount if available)

**Gephi layout:** ForceAtlas2, node size = degree centrality. Color by institution type.

### 3.2 "Revolving door" pattern detection
Flag people who:
- Were a lector at fund X in year Y → received funding from fund X in years Y±2
- Were a board member at fund X → produced a film funded by fund X
- Sat on a festival jury → their film was selected that year or the next

Add a `revolving_door` section to the HTML report with these cases ranked by severity.

### 3.3 Institutional network map (per person)
Extend person cards to show all institutional affiliations in one view:
- Fund: lector / board
- Festival: jury / programmer
- School: faculty
- Guild: board
- Lab/market: mentor / curator

This turns individual conflict cards into a full power-map per person.

---

## Phase 4 — Deliverables

| Deliverable | How | When |
|---|---|---|
| **HTML report** (current) | `resolve_entities.py` | After each scraping phase |
| **Excel raw data** | `--export-excel` flag | After Phase 1.4 |
| **Network graph** | `export_graph.py` → Gephi | After Phase 3.1 |
| **Gender analysis tables** | Section in HTML + Excel sheet | After Phase 1.1 |
| **Repeat winners table** | Section in HTML + Excel sheet | After Phase 1.2 |
| **Suspicious cases list** | Already in HTML conflict cards | Improve after Phase 3.2 |
| **PDF conclusions document** | Manual write, based on data | Last step |

---

## Suggested execution order

```
Week 1 (no new scraping):
  → 1.1 Gender field
  → 1.2 Repeat winners
  → 1.4 Excel export
  → 1.5 Funding round year fix

Week 2 (new scraping — festivals + schools):
  → Scrape 2A (festivals: DocAviv, Jerusalem FF, Haifa, Ophir)
  → Run llm_extract.py on each
  → Scrape 2B (schools: Sam Spiegel, TAU, Sapir faculty page)
  → Re-run resolve_entities.py

Week 3 (new scraping — guilds + government):
  → Scrape 2C (guilds)
  → Scrape 2D (gov.il protocols + lector registry)
  → Scrape 2E (EDB, JFC archive)
  → Re-run resolve_entities.py

Week 4 (analysis):
  → 3.1 Network graph (Gephi export)
  → 3.2 Revolving door detection
  → 3.3 Full person institutional profiles

Week 5 (deliverables):
  → Final resolve_entities.py run on all sources
  → Export Excel
  → Export Gephi graph
  → Write PDF conclusions
```

---

## Notes on scraping approach

- Use existing scraper service (`crawl4ai-wrapper`) — already configured
- For gov.il pages: depth=1 is enough (flat listing pages)
- For festival sites: depth=2 (index → individual pages for jury/programme)
- For school faculty pages: depth=1 (single staff page usually lists everyone)
- For EDB/JFC: depth=2, filter to Israeli films only
- Add new source names to `llm_extract.py` source list as they come in
- Run `--reprocess-truncated` after each new source to catch missed pages

## Open questions for client

1. **Amount data**: Do you have access to the actual grant amounts per film/round? (gov.il XLS files sometimes have this — would enable "repeat winners by money" not just count)
2. **Time scope**: What years does the report cover? (Affects how deep to scrape festival archives)
3. **Companies Registrar**: Should we cross-reference production companies via `ica.justice.gov.il`? (Requires manual lookup or API — not easily scrapeable)
4. **Conclusions framing**: Is the goal to expose specific individuals, or to characterize systemic patterns? (Affects how we weight individual vs. aggregate findings)
