---
name: t05-junk-role-heading-profile-card
description: T05 — "מנהלת הקרן" (fund manager title) leaks into entity_registry and renders as a profile card; is_junk_name() misses role-title phrases that don't start with a junk prefix
metadata:
  type: project
---

In the 2026-05-27 run, `id="prof-מנהלת-הקרן"` renders in the HTML as a person profile card with 2 sources (gesher, nfct) and 60 appearances. The display name is "מנהלת הקרן" (fund manager — a role title, not a person name).

Additional similar names survive in entity_registry but do NOT render as profile cards (below render threshold or excluded at render time):
- 'מנהל האמנותי של הקרן' (makor)
- 'מנהלים-אמנותיים' / 'מנהלי הקרן החדשה לקולנוע וטלוויזיה' (nfct)
- 'המנהלת האמנותית' (nfct)
- 'מנהלת ההפקות' (nfct)
- 'שם מלא בעברית' (nfct) — also a placeholder, not a name

**Why:** `is_junk_name()` in `resolve_entities.py` filters names starting with certain prefixes (like "מנהל הק", "לקטורים", etc.) but the exact string "מנהלת הקרן" starts with "מנהלת" which is not in the current junk prefix list. The LLM on gesher and nfct pages extracts this as a person because the page says "מנהלת הקרן [Name]" and the LLM sometimes captures the role phrase instead of the name.

**How to apply:** When T05 fires with "מנהלת" or "מנהל" + "הקרן/האמנותי/האמנותית", these are role-title extractions, not people. Add these patterns to `is_junk_name()`:
- `r"^מנהלת?\s+(ה|ה?אמנותית?|ההפקות|הקרן)"` 
- `r"^שם\s+מלא\s+בעברית"`

**Impact:** The rendered card "מנהלת הקרן" appears in #sec-cross-people with role chips "מנהל הקרן" and "במאי". Not in film_conflicts. Low severity but pollutes the person index.
