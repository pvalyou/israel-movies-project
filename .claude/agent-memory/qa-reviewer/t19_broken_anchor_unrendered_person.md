---
name: t19-broken-anchor-unrendered-person
description: T19 fails when a derived-conflict (family link) points to a person who gets no profile card because they are not cross-source, not power, and not in film_conflicts
metadata:
  type: project
---

Observed 2026-06-03: card `prof-נואית-גבע` emits a family-conflict link `href="#prof-דן-גבע"` but דן גבע has no rendered profile card — entity `p_1122a1f0` has `is_cross_source=None`, `is_power=None`, `roles=None`, no film_conflict entry.

The derived-conflicts pipeline generates href anchors to family members without checking whether those members will actually receive a rendered card.

**Why:** The derived-conflict renderer and the profile-card renderer have no shared gating check. Any person named in a family pair gets linked even if they never pass the card-render threshold.

**How to apply:** When T19 fails on a `prof-X` that has no anchor, first check if X appears in any derived_conflicts entry (family, collab, multi-fund). If so, the fix is in the derived-conflict link emitter: guard with `if slug in rendered_card_set` before emitting `<a href>`. If X should have a card (cross-source data exists), the fix is upstream in entity classification.

See also: [[t19]] general broken anchors pattern.
