---
name: t22-nfct-malformed-source-entries
description: T22 WARN on NFCT-sourced films — 56 nfct source list items are malformed (URL + quoted crew text concatenated), causing film_credits to be empty and film titles to render without links
metadata:
  type: project
---

Observed 2026-06-03: 56 nfct source entries across 45 people have the form:
  `https://nfct.org.il/blog/movies/<slug>/ \"<film title> במאי: ...`

The URL and the scraped crew text are concatenated into a single string. The film_credits parser fails to extract a URL from these, so `film_credits` is empty and the film appears in profile cards without a clickable link.

Affected T22 films (non-rabinovich batch): ממלכת עדני, אוצר באושוויץ, אורות, קראנו לו בית, ליזה׳לה, אל-ג׳יסר, האשה מהסינמטק.

**Why:** The NFCT scraper or importer is concatenating the source URL with the page's text snippet rather than storing them in separate fields. The `\"` escape sequences suggest a JSON serialization artifact where the crew text was embedded inline.

**How to apply:** When T22 WARNs on NFCT-sourced films (not rabinovich_cinema), check `entity_registry.json` for the affected persons' `sources.nfct` list. If items contain `\"` after the URL, this is the malformed-entry bug. Fix is in the NFCT importer: split URL from crew text before storing in the source list, or in the film_credits parser: extract just the URL prefix up to the first whitespace/`\"`.

This is distinct from the rabinovich_cinema no-URL pattern (which is structural — batch pages have no per-film URL). See [[t22-rabinovich-no-film-url]].
