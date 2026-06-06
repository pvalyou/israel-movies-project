---
name: t34-broken-test-years-by-src
description: T34 breaks with ImportError (SOURCE_COLORS) and years_by_src is not in entity_registry.json; test always fails or skips
metadata:
  type: project
---

## T34 is a broken test (found 2026-05-29, updated 2026-05-29)

Two separate breakages:

1. **ImportError:** `QA_TESTS.md` T34 imports `SOURCE_COLORS` from `resolve_entities`, but the current code exports `source_color(source, color_map)` as a function (not a dict). The import raises `ImportError: cannot import name 'SOURCE_COLORS'`. The correct call is `source_color(src, color_map)` but `color_map` is a dynamic runtime dict built during rendering — not available in a standalone test script.

2. **Schema mismatch:** T34 originally checked `entity_registry.json` for `years_by_src` fields, but `years_by_src` is computed in memory during the render pass and **never persisted to entity_registry.json**. Person entries in the registry have no `years_by_src`.

**Why:** T34 was written against an older schema and an older `SOURCE_COLORS` constant that was replaced by the `source_color()` function.

**How to apply:** When investigating "year 2026 appearing for wrong sources", check the HTML directly: count `<span class="resume-entry-year">2026</span>` occurrences (236 as of 2026-05-29) and manually verify a sample. Cannot automate without access to the runtime color_map.

**Fix needed:** T34 in QA_TESTS.md should be updated to either:
(a) Remove the `SOURCE_COLORS` import and instead scan HTML for 2026 year spans, matching nearby source badge colors against a hardcoded list of inferred-source colors (but colors are dynamic).
(b) Persist `source_color_map` to `entity_registry.json` as a side-channel for testing.
(c) Drop T34 and accept that this edge case needs manual verification.
