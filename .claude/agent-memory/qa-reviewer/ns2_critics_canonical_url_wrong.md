---
name: ns2-critics-canonical-url-wrong
description: Critics canonical URL was haaretz.co.il (placeholder) — FIXED 2026-05-29; 0 haaretz links in HTML
metadata:
  type: project
---

## NS-2 critics canonical URL — FIXED 2026-05-29

In a prior run, `CANONICAL_DOC_URLS` mapped `"manual://critics/israeli-film-critics-2026"` to `"https://www.haaretz.co.il/"`. This caused profile cards for critics to show an org link pointing to Haaretz homepage.

Fix confirmed in 2026-05-29 QA run: 0 occurrences of `href="https://www.haaretz.co.il/"` in the HTML.

**How to apply:** When a new manual source is added, verify its CANONICAL_DOC_URLS entry points to the actual authoritative page for that data, not a placeholder.
