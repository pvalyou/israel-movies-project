---
name: ns1-critic-role-no-hebrew-label
description: "critic" role missing from ROLE_LABELS_HE — FIXED 2026-05-29; also documents a broader class of 472 English roles missing from ROLE_LABELS_HE
metadata:
  type: project
---

## NS-1 "critic" role — FIXED 2026-05-29

`"critic"` was added to `SOFT_INST_ROLES` but was not in `ROLE_LABELS_HE`.
Fix confirmed in 2026-05-29 QA run: 0 `critic` English chips, 0 `critic` English role rows.

## Broader class: English roles missing from ROLE_LABELS_HE (updated 2026-05-29)

In the 2026-05-29 QA run, 122 English chip labels appear in `resume-chip-soft` slots (76 unique labels). Reduction from 629 → 122 due to prior fixes (T28 ROLE_LABELS_HE additions). Root cause: `other_r` (roles not in STRICT_INST_ROLES | SOFT_INST_ROLES | CREATIVE_ROLES) gets passed to `_dedup_chips` with `he_role()` fallback — any role not in ROLE_LABELS_HE renders as raw English.

Current most-affected roles (by chip count): `casting` x7, `sound` x5, `xr creator` x4, `sound designer` x4, `editing consultant` x3, `speaker` x3, `host` x3, `consultant` x3.

Additionally, 23 cards show multiple English soft chips. Several are semantic duplicates (same role under different string variants):
- `edit_counselor` + `editing consultant` (prof-אסף-לפיד)
- `editing_advisor` + `editor_advisor` (prof-אריק-להב-ליבוביץ)
- `sound` + `sound designer` (3 cards: מיכאל גורביץ, יובל בר-און, עמי ארד, אורי קדישאי)
- `color_and_image_design` + `color_grading` + `image_and_color_design` (prof-אבי-לוי)
- `initiator` + `project_initiator` (prof-עמית-גורן)
- `musical_arrangement` + `musical_arranger` (prof-יסמין-אבן)
- `original story writer` + `storywriter` (prof-אתגר-קרת)

These semantic duplicates pass T18 (which only detects same-string duplicates) but display as two chips.

Top impacting institutional roles appearing in `resume-entry-role` spans:
- `contact_person` x13 (should be "איש קשר" or hidden)
- `fund_director` x2 (should be "מנהל הקרן" — same as `foundation_director`)
- `staff` x1 (should be "צוות")
- `directing_mentor` x1 (should be "מנטור במאי")

**Why:** The 472 unmapped roles come from film-crew data (LLM scraped them from film credits). Most are `other_r` (soft chips). No ROLE_LABELS_HE coverage for these film-specific crew roles.

**Fix options:**
1. Add the ~20 high-frequency crew roles to ROLE_LABELS_HE (minimal fix)
2. Add a SUPPRESS_CHIP_ROLES set and exclude film-crew roles (subject, self, character, cast, filming) from the chip display
3. Both: suppress junk roles + translate crew roles that are meaningful

**Junk roles appearing as chips (should be suppressed):**
- `self` x4, `character` x2, `subject` x3, `cast` x9, `actress` x6, `voice_actor` x9
- These are film-subject roles, not a person's professional identity

**How to apply:** When adding a new source that introduces new roles, always:
1. Add entries to ROLE_LABELS_HE for roles that will appear in chips
2. Add truly junk roles (self, character, subject, fictional_character) to a suppress list
