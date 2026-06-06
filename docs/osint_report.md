# OSINT Report — Israeli Film Industry Conflict Investigation
*Session: 2026-05-23 / 2026-05-24*

---

## Background

Starting point: article at `filmindustrywatch.org` alleging corruption and conflicts of interest in Israeli film funds (Rabinovich, Gesher). Goal: verify specific claims using open-source data, identify confirmed conflicts, and find what's missing.

---

## What We Searched

| Target | Methods Used | Result |
|---|---|---|
| גיורא עיני / גיורא איני (Rabinovich CEO) | Walla, Ynet, Haaretz, Maariv, Guidestar, ICA registry, rabinovichfoundation.org.il, DuckDuckGo | ✅ Found — name misspelled in article; correct: **גיורא עיני** |
| Film Council (מועצת הקולנוע) membership | gov.il (Cloudflare blocked), Wayback Machine | ✅ Full 2024 list retrieved |
| ציו נבה (Gesher CEO) | gesherfilmfund.org.il | ✅ Confirmed |
| JFF 2021 jury | jff.org.il past festival pages | ❌ 404 / not found |
| Haifa Film Festival 2021–2022 jury | Multiple URL patterns | ❌ 404 / not found |
| Guidestar financial data (fund concentration claim) | guidestar.org.il | ❌ Wrong org number initially; correct number found: **580035756** |

---

## Key Findings

### 1. גיורא עיני — Rabinovich Cinema Fund CEO (מנכ"ל)

**The article spelled his name as "גיורא איני" (with א). Correct spelling: גיורא עיני (with ע).**

- Appointed by former Tel Aviv mayor **רוני מילוא**, encouraged by **יצחק רבין**
- Longtime CEO of קרן יהושע רבינוביץ לאמנויות — פרויקט קולנוע
- Sources: EverybodyWiki, FDOC meeting notes (July 2019), DDG search, Scribd PDF titled "גיורא עיני - מנהל קרן רבינוביץ"
- Confirmed: signed an open letter together with Gesher's ציו נבה

**Also found:** יואב אברמוביץ = Artistic Director (מנהל אמנותי) of Rabinovich Cinema Fund

---

### 2. Film Council (מועצה הישראלית לקולנוע) — Full 2024 Membership

Source: Wayback Machine snapshot of gov.il, 2024-01-18 (last updated 2023-08-20).

| Role | Name |
|---|---|
| יו"ר | **ד"ר עליזה לביא** |
| מנהלת (Ministry rep) | **קרן כרמל** (kerenca@most.gov.il) |
| חבר/חברת מועצה | יואב דוניץ, אברהם חיון, אבי שמש, מנשה סמירה, נפתלי אלטר, יונה אליאן, מוטי שקלאר, **ענבל שוקי**, רוקיה סבח, נועם שנהב, חנוך גנן, טלי אוברמן, גיל סמסונוב, חתונה קיפניס, חלי סממה פדידה, רוני חורי, מתנאל מזור, מיטל לוגסי, **עמיחי חסון** |

---

### 3. Film Council Conflicts Found

#### עמיחי חסון — ⚑ CONFIRMED CONFLICT (flagged in report)
- **Film Council board member** (חבר מועצה)
- **Director / filmmaker** on FDOC-funded films ("אדם אדמה" 2023) and NFCT films
- **Detected automatically** by the pipeline: board_member + filmmaker = conflict

#### ענבל שוקי — Tier-2 conflict (not auto-detected)
- **Film Council board member**
- **Costume designer** on 2 Israel Film Fund films: "אסיה" (2020) and "נאנדאורי" (2025)
- Not automatically flagged because `costume_designer` is not in the CREATIVE_ROLES set (producers/directors only)
- The Film Council sets funding *policy*, not individual grants — conflict is structural, not direct

---

### 4. Gesher Fund Leadership

| Name | Role | Period | Source |
|---|---|---|---|
| ציו נבה (Ziv Nave) | Executive Director | until 2025 | gesherfilmfund.org.il/Page/15/ |
| Ruth Diskin (רות דיסקין) | Executive Director | 2025– | Gesher website |
| Rabbi Dr. Daniel Tropper | Founder | — | Gesher about page |

---

### 5. Israel Film Fund

| Name | Role | Source |
|---|---|---|
| Dr. Noah Regev | CEO | scraped |
| Amnon Dick | Board Chair (since 2025) | scraped |

---

### 6. Pipeline Bug Fixed This Session

**T02 — Government bodies appearing as people in the report**

`is_junk_name()` now filters names containing government keywords (משרד/ממשלת/עיריית/הרשות) even when the LLM assigns `government_official` role instead of `government_body`. Previously 32 junk entries (e.g., "משרד התרבות והספורט") were leaking into the entity registry and HTML report.

---

## What's Still Missing

| Item | Status | Notes |
|---|---|---|
| JFF 2021 jury | ❌ Not found | URL returns 404 |
| Haifa 2021/2022 jury | ❌ Not found | URL returns 404 |
| Guidestar financial filings | ❌ Pending | Correct org number now known: 580035756 |
| ₪104M Aderi concentration claim | ❌ Unverified | Needs Guidestar annual reports 2015–2022 |
| אסנת בוקובצר, אריה חרנר, גבריאל עמראני גור, נילי פאלר | ❌ Not in DB | Mentioned in article, not yet found in sources |

---

## Database Additions This Session

| Person | Role | Source |
|---|---|---|
| גיורא עיני | CEO, Rabinovich Cinema | manual entry (confirmed multi-source) |
| יואב אברמוביץ | Artistic Director, Rabinovich Cinema | FDOC meeting page 2019 |
| ציו נבה | Gesher CEO until 2025 | gesherfilmfund.org.il |
| Ruth Diskin | Gesher CEO 2025– | gesherfilmfund.org.il |
| ד"ר עליזה לביא + 20 council members | Film Council 2024 | gov.il via Wayback Machine |

---

*All 8 QA tests pass on current connections_report.html (2026-05-23 23:49)*
