---
name: ns3-role-alias-hyphen-underscore
description: Hyphen vs underscore role variants show as separate chips (co-director + co_director) — found 2026-05-29; 5 cards affected
metadata:
  type: project
---

## Bug: hyphen/space vs underscore role spellings show as duplicate chips

Found 2026-05-29. `ROLE_NORMALIZE` does not map hyphenated/spaced forms to their underscore equivalents, so both variants pass `_dedup_chips` as distinct labels.

Affected pairs (5 profile cards):
- `prof-ראובן-ברודסקי`: `'co-director'` and `'co_director'`
- `prof-אבי-בללי`: `'music composer'` and `'music_composer'`
- `prof-דביר-בנדק`: `'voice actor'` and `'voice_actor'`
- `prof-ליאב-ביטן`: `'sound editor'` and `'sound_editor'`
- `prof-יוני-גודמן`: `'animation director'` and `'animation_director'`

**Why:** `role_set()` calls `ROLE_NORMALIZE.get(r, r)` but the hyphenated/spaced variants are not entries in ROLE_NORMALIZE. They survive as distinct values in `roles_by_src`. The dedup in `_dedup_chips` compares rendered labels — but since neither form is in ROLE_LABELS_HE, both fall back to their raw string (which are different), so both pass the `lbl not in seen_labels` check.

**Fix:** Add entries to ROLE_NORMALIZE in resolve_entities.py:
```python
"co-director":          "co_director",
"co-producer":          "co_producer",
"co-founder":           "co_founder",
"music composer":       "music_composer",
"sound editor":         "sound_editor",
"sound designer":       "sound_designer",
"voice actor":          "voice_actor",
"online editor":        "online_editor",
"animation director":   "animation_director",
"soundtrack composer":  "soundtrack_composer",
"script editor":        "script_editor",
"executive producer":   "executive_producer",
"original soundtrack":  "original_soundtrack",
"visual effects":       "visual_effects",
"animation designer":   "animation_designer",
```

**How to apply:** Whenever a new English chip appears twice for the same person (once with hyphen/space, once with underscore), the fix is ROLE_NORMALIZE — not ROLE_LABELS_HE.
