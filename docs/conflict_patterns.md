# Conflict Patterns — Israeli Film Industry Network

A catalogue of all conflict-of-interest patterns we detect (and could detect in the future).
Each pattern has a type name, detection method, data required, and known examples.

---

## Currently Detected Patterns

### Pattern 0 — `institutional` (original)
**What it is:** Person holds a formal gatekeeper role (lector, board member, CEO, fund manager) at Fund X, AND their film was funded by Fund X.
**Signal type:** Strict (strongest)
**Data needed:** Fund source JSONL (role mentions) + film crew credits (EDB)
**Detection:** `extract_film_conflicts()` in `resolve_entities.py`
**Examples:** קובי מזרחי (makor lector + פרפרים funded by makor), ערן ריקליס (JFF lector + ערבים רוקדים funded by JFF)
**Count:** 218 conflicts

---

### Pattern 1 — `critic_committee`
**What it is:** A film critic / journalist who also serves on a fund committee (as lector or board member). They shape public opinion on films AND control who gets funded.
**Signal type:** Derived — strong
**Data needed:** `entity_registry.json` → `all_roles` contains both `critic` and one of `{lector, board_member, ...}`
**Detection:** `compute_derived_conflicts.py` → `compute_critic_committee()`
**Examples:**
- שמוליק דובדבני — critic + board_member/lector at makor, filmfund, nfct, rabinovich + Sam Spiegel faculty
- דן שדור — critic + director/producer + lector at 5 funds (fdoc, gesher, makor, nfct, rabinovich)
- מרלין וניג — critic + director + film council board + filmfund/rabinovich lector
- רון פוגל — critic + board_member at filmfund, makor, rabinovich (+ Israeli Film Academy)
**Count:** 16 people

---

### Pattern 2 — `family_conflict`
**What it is:** Two people with the same surname who both hold institutional positions in the film funding ecosystem. Probable couples, parent-child, or siblings.
**Signal type:** Derived — medium (requires verification of actual family relationship)
**Data needed:** `network_graph.json` institutional edges → group by surname
**Detection:** `compute_derived_conflicts.py` → `compute_family_pairs()`
**Examples:**
- ערן ריקליס + דינה צבי-ריקליס — likely married couple; both lectors at 5+ funds each (filmfund, jff, makor, nfct, rabinovich)
- נדב לפיד + חיים לפיד — likely father-son; both lectors at filmfund, nfct, rabinovich
- אסף לפיד + נדב לפיד — both lectors (possible relation)
- טלי הלטר שנקר + גלעד אמיליו שנקר — both on makor committee
**Count:** 6 pairs

---

### Pattern 3 — `collab_committee`
**What it is:** Two filmmakers who co-worked on a film together, AND both currently sit on the same fund committee. They vote on each other's colleagues' funding applications, and their former collaborators may reciprocally apply.
**Signal type:** Derived — medium
**Data needed:** `network_graph.json` co_credited edges + institutional edges
**Detection:** `compute_derived_conflicts.py` → `compute_collab_committee()`
**Examples:**
- קובי מזרחי + שירה הוכמן — both on makor; shared films: עין לבנה, שממה
- ערן ריקליס + סייד קשוע — both on JFF; shared film: ערבים רוקדים
- חיים מקלברג + ניר ברגמן — both on filmfund; shared film: פינק ליידי
- אורי ברבש + חיים שריר — both on JFF; shared films: קאפו בירושלים, מילואים
**Count:** 50 pairs

---

### Pattern 4 — `multi_fund`
**What it is:** A single person serves on 2+ different fund committees simultaneously, giving them disproportionate influence across the industry.
**Signal type:** Derived — informational (not a conflict alone, but amplifies other conflicts)
**Data needed:** `network_graph.json` institutional edges → count unique fund targets per person
**Detection:** `compute_derived_conflicts.py` → `compute_multi_fund()`
**Examples:**
- נטעלי בראון — 3 funds: gesher, rabinovich, festival_data
- קובי מזרחי — 2 funds: makor + rabinovich (AND film credits at both)
- ניר ברגמן — 2 funds: jerusalem_film_fund + filmfund (AND received money from both)
- ערן קולירין — 2 funds: filmfund + jerusalem_film_fund
**Count:** 17 people (2+ funds)

---

### Pattern 5 — `faculty_committee`
**What it is:** A film school faculty member who also sits on fund committees. Their students graduate and apply to those funds; the teacher votes on those applications.
**Signal type:** Derived — medium
**Data needed:** `entity_registry.json` → `all_roles` contains `faculty` AND fund roles; `sources` contains school keys
**Detection:** `compute_derived_conflicts.py` → `compute_faculty_committee()`
**Examples:**
- אפרת כורם — teaches at school + lector at 6 funds: filmfund, gesher, jff, makor, nfct, rabinovich
- שלומי אלקבץ — faculty + lector at 6 funds
- עמיר מנור — faculty + lector at 5 funds: filmfund, gesher, jff, nfct, rabinovich
- שמוליק דובדבני — Sam Spiegel faculty + lector/board at 4 funds
**Count:** 38 people

---

### Pattern 6 — `festival_committee`
**What it is:** A festival director or programmer who also serves on a fund committee. They control which films get festival exposure AND which films get funded — two major industry levers in one person.
**Signal type:** Derived — strong
**Data needed:** `entity_registry.json` → `all_roles` contains festival roles AND fund roles
**Detection:** `compute_derived_conflicts.py` → `compute_festival_committee()`
**Examples:**
- גליה בדור — DocAviv director + CEO at makor, nfct
- עמית גורן — artistic director + CEO at gesher, makor, nfct
- אסף לפיד — festival programmer at multiple festivals + board_member/lector at fdoc, gesher, jff, makor, nfct
- דינה צבי-ריקליס — JFF programmer + lector at 6 funds
- אור סיגולי — artistic director at Jerusalem Cinematheque + lector at gesher, jff, rabinovich
**Count:** 23 people

---

### Pattern 7 — `exec_filmmaker`
**What it is:** A fund CEO, executive director, or fund manager who is also an active filmmaker (director, producer, screenwriter). They run the fund AND make films that need funding from similar sources.
**Signal type:** Derived — medium-strong
**Data needed:** `entity_registry.json` → `all_roles` contains exec roles AND filmmaker roles
**Detection:** `compute_derived_conflicts.py` → `compute_exec_filmmaker()`
**Examples:**
- עמית גורן — CEO at gesher, makor, nfct + director + screenwriter + producer
- רות דיסקין — CEO at gesher, nfct + distributor + producer
- דוד פישר — CEO at nfct + director + producer (AND received nfct funding for ששה מיליון ואחד)
- אורנה בן דור — CEO at nfct + director + screenwriter (also received nfct funding)
**Count:** 24 people

---

## Patterns to Add in the Future

These require additional data sources not yet collected.

### Future Pattern A — `peer_review_loop`
**What it is:** Person A reviewed/praised a film by Person B in the press, and Person B sits on the fund committee that funds Person A's films (or vice versa). Mutual back-scratching loop.
**Signal type:** Derived — medium
**Data needed:** Film review database (critic → film mentions) cross-referenced with committee membership and film credits
**How to detect:** `reviewed` edges (already partially in network_graph.json for 7 critics) cross-referenced with institutional edges of the film's director/producer

### Future Pattern B — `shared_production_company`
**What it is:** Committee members A and B share a production company (as co-owners or co-listed), and both vote on each other's funding applications.
**Signal type:** Derived — strong
**Data needed:** Company registry (guidestar.org.il) → fetch ownership records for production companies
**How to detect:** Cross-reference org_groups (production companies) with institutional edges

### Future Pattern C — `teacher_student`
**What it is:** A faculty member taught a specific student who now applies for funding. The teacher sits on the committee reviewing that application.
**Signal type:** Derived — strong
**Data needed:** School alumni lists (graduation records or school websites) → specific person-to-person teacher-student edges
**How to detect:** Would need `taught_by` edges; currently only have `studied_at` edges (person → school)

### Future Pattern D — `juror_applicant`
**What it is:** A person served on a festival jury that selected a film, AND they have a financial relationship with that film (co-producer, distributor).
**Signal type:** Derived — strong
**Data needed:** Festival jury membership lists (most festivals publish this) + film financial relationships
**How to detect:** New jury_member edges from festival sources + cross-ref with film credits

### Future Pattern E — `revolving_door_government`
**What it is:** A person who moved from a government role (Ministry of Culture, Film Council) to a fund leadership position (or vice versa), with potential to steer policy in their former institution's favor.
**Signal type:** Derived — strong
**Data needed:** Government/ministry personnel data, LinkedIn-style career timelines
**How to detect:** Temporal analysis of institutional roles across `ministry_of_culture` and `film_council` sources vs fund sources

### Future Pattern F — `funding_concentration`
**What it is:** A single producer/director has received funding from 3+ different funds for the same film, meaning multiple gatekeepers approved the same project — possibly indicating a connected figure.
**Signal type:** Statistical anomaly
**Data needed:** Per-film multi-fund records (requires EDB fund enrichment from TODO.md)
**How to detect:** After `enrich_edb_funds.py` runs, aggregate `funds` field per film

### Future Pattern G — `publication_funder`
**What it is:** A critic/journalist works for a publication that received advertising or sponsorship from a film fund, while also reviewing films funded by that fund.
**Signal type:** Institutional
**Data needed:** Media outlet funding records (requires new scraping from fund annual reports)
**How to detect:** New `sponsors` edges from fund → media outlet + `employed_at` edges for critics

### Future Pattern H — `alumni_committee`
**What it is:** A school graduate (alumni) later becomes a lector/committee member at a fund — and votes on applications from students at their alma mater.
**Signal type:** Derived — soft
**Data needed:** Alumni lists from schools (currently not available in detail) + `studied_at` edges
**How to detect:** `studied_at` edges + institutional edges; already partially possible with current data

---

## Detection Methodology Notes

### Data sources ranked by conflict signal strength
1. **Explicit role declaration** (lector list, board minutes) → strongest
2. **Co-credited on same funded film** → strong
3. **Same surname + overlapping institutional roles** → medium (needs verification)
4. **Festival + fund overlap** → medium-strong
5. **Role keyword match** (critic, faculty) in person registry → depends on source quality

### When to re-run
Run `python3 scripts/compute_derived_conflicts.py` after:
- New fund sources are scraped
- `entity_registry.json` is regenerated by `resolve_entities.py`
- New OSINT about individuals (journalist roles, family relationships)

### Edge type vocabulary
| Edge type | Direction | Meaning |
|---|---|---|
| `institutional` | person → fund | Formal gatekeeper role |
| `film_funded` | person → fund | Their film received money |
| `critic_committee` | person → fund | Critic + votes on funding |
| `family_conflict` | person ↔ person | Likely family relationship |
| `collab_committee` | person ↔ person | Co-worked + same committee |
| `festival_committee` | person → fund | Festival role + fund role |
| `affiliated_with` | person → school | Faculty/staff |
| `studied_at` | person → school | Alumni |
| `reviewed` | person → film | Critic reviewed the film |
| `crew_credit` | person → film | Worked on the film |
