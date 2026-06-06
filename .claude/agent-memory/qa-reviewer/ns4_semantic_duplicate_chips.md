---
name: ns4-semantic-duplicate-chips
description: Semantic duplicate English chips (edit_counselor+editing consultant, sound+sound designer, etc.) — T18 does not catch these since labels differ as strings
metadata:
  type: project
---

## NS-4: Semantic duplicate English chips (found 2026-05-29)

T18 only catches exact-string duplicate chips. Several cards show semantically equivalent role variants as separate chips because both strings lack Hebrew labels (so `_dedup_chips` can't unify them).

**23 cards** show multiple English soft chips; at least 10 are semantic duplicates:

| Card | Duplicate pair |
|------|---------------|
| prof-אסף-לפיד | `edit_counselor` + `editing consultant` |
| prof-אריק-להב-ליבוביץ | `editing_advisor` + `editor_advisor` |
| prof-יובל-בר-און | `sound` + `sound designer` |
| prof-עמי-ארד | `sound` + `sound designer` |
| prof-אורי-קדישאי | `sound` + `sound designer` |
| prof-מיכאל-גורביץ | `sound designer` + `soundtrack_creator` |
| prof-אבי-לוי | `color_and_image_design` + `color_grading` + `image_and_color_design` |
| prof-עמית-גורן | `initiator` + `project_initiator` |
| prof-יסמין-אבן | `musical_arrangement` + `musical_arranger` |
| prof-אתגר-קרת | `original story writer` + `storywriter` |

**Root cause:** `_dedup_chips` deduplicates by rendered Hebrew label. When both variants fall through to raw English (not in ROLE_LABELS_HE), they render as different strings and both pass the `lbl not in seen_labels` check.

**Fix (two-pronged):**
1. Add Hebrew translations to ROLE_LABELS_HE for the role pairs so `he_role()` maps them to the same Hebrew string — `_dedup_chips` will then unify them.
2. Alternatively, add the variant forms to ROLE_NORMALIZE so they canonicalize before reaching `_dedup_chips`.

For `sound` + `sound designer`: map `sound` → `sound_designer` in ROLE_NORMALIZE.
For `edit_counselor` + `editing consultant`: add `"editing consultant": "edit_counselor"` in ROLE_NORMALIZE, then add `edit_counselor` → Hebrew in ROLE_LABELS_HE.

**Why it matters:** A person showing 3-4 English chip variants for what is essentially the same role (color grading, sound design) looks unprofessional and inflates chip counts toward the T35 threshold.

**How to apply:** [[ns1-critic-role-no-hebrew-label]] and [[ns3-role-alias-hyphen-underscore]] cover related cases — consult before adding new ROLE_NORMALIZE entries to avoid conflicts.
