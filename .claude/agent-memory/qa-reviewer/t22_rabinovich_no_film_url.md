---
name: t22-rabinovich-no-film-url
description: T22 warns on 309 film entries without URL — these are all from rabinovich_cinema manual:// pages which never carry film_url; this is structural, not a bug
metadata:
  type: project
---

T22 checks for `<span class="resume-film-title"><span><span dir="rtl">` (no `<a href>` wrapper) as a WARN condition.

In the 2026-05-29 run: 359 entries triggered this, from 25 unique film titles (up from 309/24 on 2026-05-26 — increase is due to more cross-source people having those films in their profiles, not new sources).

Investigation showed:
- All 25 unique titles originate from `rabinovich_cinema` source, all from `manual://rabinovich_cinema/funded-films/...` pages.
- These manual pages are budget allocation spreadsheets imported as structured JSON. They list film titles + budget amounts but have no per-film web URLs — the source data itself has `film_url: null`.
- Count growth over time is expected as more people are added to the cross-source registry.

**Why:** The rabinovich_cinema manual import was designed for budget transparency, not web indexing. Film URLs were never available for this source.

**How to apply:** When T22 fires, first check if the unlinked titles all trace back to `rabinovich_cinema` manual:// pages. If yes, this is expected behavior and should be classified WARN (not FAIL) with a note that the source has no per-film URLs. If new unlinked titles appear from sources that DO have film URLs (e.g., gesher, nfct, makor), that is a genuine bug.

**Confirmed false-positive sources:** rabinovich_cinema (all manual:// funded-films pages).
