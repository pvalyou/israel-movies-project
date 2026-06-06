# Agent Research Plan — PDF Analysis Follow-up
*Created: 2026-06-02*

## Context

Three PDFs were analyzed against our entity registry and the web. The PDFs appear AI-generated from real research data. The factual/personnel claims in them are mostly verified against our DB; the analytical framing ("cartel", Gramsci/Bourdieu) is interpretive and cannot be verified. This plan covers only the **verifiable claims** that are either new to our DB or explicitly checkable via public records.

---

## Priority 1 — Verify & add: גידי אורשר

**PDF claim:** "מבקר הקולנוע המיתולוגי של גלי צה"ל" served as **project manager at Rabinowitz Cinema Fund** (קרן רבינוביץ' לקולנוע). If true: major critic_committee conflict — the most prominent public critic ran the fund he should have been watching.

**He is already in our registry** (`p_464c9a69`) with role `critic` only.

**Tasks:**
1. Search `גידי אורשר רבינוביץ'` + `גידי אורשר קולנוע` + `גidi orsher rabinowitz` to find any reference confirming the Rabinowitz role (press articles, LinkedIn, CVs)
2. Check `edb.co.il` for his profile — does it list a producer/manager role?
3. If confirmed: add a JSONL record to `out/rabinovich_cinema/mentions.jsonl`:
   ```json
   {"person": "גידי אורשר", "role": "manager", "fund": "קרן רבינוביץ' לקולנוע", "source_url": "<url>", "year": "<year if found>", "notes": "מנהל פרויקט קולנוע - מאושש מ<source>"}
   ```
4. Also add to `out/critics/mentions.jsonl` (or whichever source holds his critic role) a note confirming the Galei Tzahal connection if not already there.

---

## Priority 2 — Verify: אביטל בקרמן structural conflict

**She is in our registry** (`p_53c7135c`) as `lector` at Israeli Film Fund.

**PDF claim (specific and checkable):**
- She is **Head of Development, Reading & Sorting** at the Israeli Film Fund (מנהלת הפיתוח, הקריאה והמיון)
- She also **teaches courses that train filmmakers how to write applications** to that same fund
- She is co-creator of **"מאגר עדויות הקולנוע הישראלי"** with מרט פרחומובסקי — allegedly funded by the same funds

**Tasks:**
1. Search `אביטל בקרמן קרן קולנוע ישראלי` + `אביטל בקרמן קורס` + `אביטל בקרמן הגשות`
2. Check `filmfund.org.il/ContentPage?id=49` (lectors page) for her name and title
3. Search `"מאגר עדויות הקולנוע הישראלי" מימון` — who funded it?
4. If the course-teaching is confirmed: update her record with role `instructor` and add `lector_filmmaker`-style conflict note
5. Add her full title to the registry if not already there

---

## Priority 3 — Check public record: אתי כהן (משרד התרבות)

**PDF claim:** Former head of the Cinema Department at the Ministry of Culture. Faced **formal disciplinary complaints** alleging biased intervention favoring Rabinowitz Fund and Gesher Fund.

**Tasks:**
1. Search `"אתי כהן" "משרד התרבות" + "ערעור" OR "תלונה" OR "ועדת בדיקה"` in Hebrew
2. Search State Comptroller reports (`mevaker.gov.il`) for any mention of her
3. Search Haaretz/Calcalist/TheMarker for any investigative coverage
4. **If** confirmed: add her to `out/ministry_culture/mentions.jsonl` (create if not exists) with role `ministry_official` and conflict note
5. **If not confirmed:** document as "unverified claim from PDF" — do not add

---

## Priority 4 — Verify: אורן רייך — multi-fund gatekeeper

**PDF claim:** Served **simultaneously** on committees at: קרן שומרון, קרן נגב, קרן ערבה — and also as lector at Gesher. A case of peripheral-market concentration: one person controls access across the entire periphery.

**He may or may not be in our registry** — check first.

**Tasks:**
1. `grep "אורן רייך" out/*/mentions.jsonl` — find existing mentions
2. Search `"אורן רייך" קרן קולנוע` + `"אורן רייך" גשר` + `"אורן רייך" שומרון` + `"אורן רייך" ערבה`
3. If confirmed in 2+ funds: add JSONL records for each confirmed fund, then run `python3 resolve_entities.py` — he should appear with multi-fund connections

---

## Priority 5 — Add missing Israeli Film Fund staff

**These people appeared in the PDFs and are either missing or incomplete in our registry.** All roles are at the Israeli Film Fund (קרן הקולנוע הישראלי).

Add to `out/filmfund/mentions.jsonl` (check existing entries first with `grep "<name>" out/filmfund/mentions.jsonl`):

| Person | Hebrew | Role | Notes |
|--------|--------|------|-------|
| דורלי אלמגור | Dorit Almog | `board_chair` | יו"ר הוועד המנהל — highest governance role |
| אלעד גולדמן | Elad Goldman | `head_of_production` | מנהל הפקות, from 2023 |
| ד"ר יסמין ששון | Dr. Yasmine Shashon | `development_coordinator` | רכזת פיתוח |
| דנה גורן סולומון | Dana Goren-Solomon | `special_projects` | מנהלת פרויקטים מיוחדים |
| ברית הראל | Brit Ha'arel | `international_relations` | קשרי חוץ + עוזרת מנכ"לית |

**Source URL to use:** `https://www.filmfund.org.il/ContentPage/?id=13` (staff page)

**Format for each record:**
```json
{"person": "<hebrew name>", "role": "<role>", "fund": "קרן הקולנוע הישראלי", "source_url": "https://www.filmfund.org.il/ContentPage/?id=13", "year": "2025"}
```

---

## Priority 6 — Add NFCT board & management 2025

**Check first:** `grep "NFCT\|nfct" out/*/mentions.jsonl | head -20`

Add to `out/nfct/mentions.jsonl` if not already present:

**Board (2025):**

| Person | Hebrew | Role |
|--------|--------|------|
| דורית ענבר | Dorit Inbar | `board_chair` (promoted from CEO) |
| אודי ירושלמי | Udi Yerushalmi | `board_member` (2024) |
| אורה סטיבה | Ora Stibbe | `board_member` (2020) |
| אלן פרימן | Alan Freeman | `board_member` (2022) |
| דניאל מימראן | Danny Mimran | `board_member` (2024) |
| מיכל פורר | Michal Fuhrer | `board_member` (2020) |
| רונית לבנת | Ronit Livnat | `board_member` (2022) |
| שירית כשר | Shirith Kasher | `board_member` (2023) |

**Management (2025):**

| Person | Hebrew | Role |
|--------|--------|------|
| אוראל טורנר | Orel Turner | `ceo` (appointed 2025, at NFCT since 2004) |
| אירית שמרת | Irit Shimrat | `artistic_director` |
| מיטל קרופניק | Maytal Krupnik | `production_manager` (2025) |
| רוני בהט | Roni Bahat | `head_of_scripted` |

**Source URL:** `https://nfct.org.il/about/management/`

---

## After all additions

```bash
python3 resolve_entities.py
```

Check output for:
- גידי אורשר — should now show `critic_committee` edge to Rabinowitz
- אורן רייך — should show multi-fund connections
- New NFCT board members appearing in registry

---

## What NOT to add

The PDFs also contain claims that are **analytical/unverifiable** — do not add these to the DB:

- "קרטל" framing or cartel claims
- Appeal committee statistics (26 appeals by אברמוביץ', etc.) — can only be added if public protocols found
- "הומוגניזציה אמנותית" — interpretive, not factual
- Any claim sourced only from the PDFs without a corroborating public URL

---

## Files to ignore/delete

These files in `sources/arava_film_fund/pages/` were left by an unreliable external agent and contain no new data:
- `missing_people_connections.md`
- `bernstein_award_committees_2025.md`
- `bernstein_award_committees_2025.meta.json`
- `WORK_DOCUMENTATION_e3f8a1b2.md`
- `nfct_management_verified.md`

All people in those files are already in our registry. The work documentation shows the agent hallucinated API keys and search queries.
