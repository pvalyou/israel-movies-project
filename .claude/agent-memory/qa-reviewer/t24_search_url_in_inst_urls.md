---
name: t24-search-url-in-inst-urls
description: NFCT search URLs in inst_urls — FIXED 2026-05-29; both film-source-link and film-row-link sides clean
metadata:
  type: project
---

## Bug: search URLs in inst_urls — FIXED 2026-05-29

Previously: search-result URLs (e.g. `?keywords=Basketball`) appeared in `inst_urls` and rendered as `film-source-link` anchors.

Fix confirmed in 2026-05-29 QA run:
- `film-source-link` with search URLs: 0
- `film-row-link` with search URLs: 0
- `entity_registry.json` inst_urls search URLs: 0

## Historical context

The bug was: `extract_film_conflicts()` `staff_urls` filter only stripped path-based film URLs. The `is_search_page` guard only blocked film-crew side. The fix added `SEARCH_RESULT_RE` to `staff_urls` filter.

## T24 test scope note

T24 test scans `sec-film-conflicts` for `?keywords=`/`?search=` style search URLs in `href=` attributes. This catches both `film_url` and `inst_urls` rendered links. No need to extend T24 further.
