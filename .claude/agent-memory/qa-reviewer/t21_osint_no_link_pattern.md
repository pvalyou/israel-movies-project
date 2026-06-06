---
name: t21-osint-no-link-pattern
description: T21 warns on OSINT notes for Film Council members (אריה צרנר, אסנת בוקופצר) that contain no <a href> — these are hand-written research notes with source refs embedded as plain text
metadata:
  type: project
---

T21 checks that OSINT notes >60 chars have at least one `<a href=` link.

In 2026-05-26 and 2026-05-29 runs: 4 issues triggered (2 notes × 2 appearances each — one in #sec-cross-people, one in #sec-film-conflicts or power map).

Affected profiles:
- `prof-אריה-צרנר` — long Film Council note (Wikidata, FIW allegation, film list)
- `prof-אסנת-בוקופצר` — two separate notes: (1) "Israeli actor and voice actor..." Film Council note, and (2) "Director of International Affairs and Co-Production at Israel Cinema Project / Rabinovich Foundation..." Rabinovich staff note. Both are plain text. The "Director of International Affairs" note text is for אסנת בוקופצר, not a new person.

Root cause: These OSINT notes were written as plain-text research summaries. They cite "Wikidata", "FIW article", "Ophir Award" etc. by name but the HTML does not wrap those citations in anchor tags. The `resolve_entities.py` OSINT note renderer does not auto-link source citations.

**Why:** These are genuine notes that need source links added to the HTML renderer or to the underlying data. The T21 WARN is correct — it is pointing at real missing attribution links, not false positives.

**How to apply:** Each WARN here is a real deficiency. The fix is either:
1. Add `<a href="...">` wrapping when rendering OSINT notes in `resolve_entities.py`, or
2. Store source URLs in the OSINT note data structure rather than embedding them as plain text.

**Not a false positive.** The two profiles (אריה צרנר, אסנת בוקופצר) have rich OSINT notes that should link to FIW articles and Wikidata entries. Track as open bug.
