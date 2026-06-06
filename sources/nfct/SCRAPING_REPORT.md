# NFCT מידע מקצועי — Scrape Report

**Generated:** 2026-05-18  
**Source:** https://nfct.org.il/מידע-מקצועי/  
**Scraper:** crawl4ai-wrapper (Google Cloud Run)

---

## Summary

| Metric | Value |
|---|---|
| Total `.md` + `.meta.json` pairs on disk | **69,212** (138,424 files) |
| Unique URLs (deduplicated) | **26,556** |
| Successful scrapes (status=ok) | **68,506** (98.9%) |
| Failed scrapes | **678** (1.0%) |
| Total content size | **959.0 MB** |
| מידע מקצועי related pages | **20,422** |
| מידע מקצועי content size | **614.8 MB** |

---

## מידע מקצועי — Category Breakdown

| Category | Pages | Description |
|---|---|---|
| `/movies-archive` | 9,020 | Film archive entries (past funded films) |
| `/en` | 6,517 | English version pages |
| `/blog` | 4,614 | Blog posts (festival reports, announcements) |
| `/movies` | 136 | Individual film pages |
| `/documents` | 49 | PDF documents and forms |
| `/submissions` | 6 | Submission guidelines pages |
| `/about` | 4 | About pages |
| `/weil-bloch-film-award` | 3 | Weil Bloch Film Award pages |
| `/מועדי-הגשה` | 3 | Submission deadlines |
| `/wb-film-award` | 2 | Weil Bloch Film Award (alt URLs) |

### Professional Info Pages (direct children of מידע מקצועי)

| Page | Status | Content |
|---|---|---|
| `/מידע-מקצועי/` | ✓ | Landing page (18 KB) |
| `/נהלי-המוסד/` | ✓ | Fund regulations (45 KB) |
| `/לקטורים/` | ✓ | Lectors list (13 KB) |
| `/טפסים-מסמכים-וחוזים/` | ✓ | Forms, documents, contracts (13 KB) |
| `/שותפים-ותומכים/` | ✓ | Partners and supporters (20 KB) |
| `/חקיקה-ואמנות/` | ✓ | Legislation and arts (18 KB) |
| `/חממות/` | ✓ | Incubators (scraped) |
| `/קולנוע-מדרום/` | ✓ | Southern cinema (scraped) |
| `/מדריך-הפצה-לדוקומנטריסט-ית/` | ✓ | Distribution guide (scraped) |
| `/סרטי-הקרן/` | ✓ | Fund films (scraped) |
| `/סרטים-גמר-סטודנטים/` | ✓ | Student graduation films (scraped) |
| `/סרטי-תעודה/` | ✓ | Certificate films (scraped) |
| `/צפייה-ישירה-בסרטי-הקרן/` | ✓ | Direct viewing of fund films (scraped) |
| `/תחום-ייעודי/` | ✓ | Dedicated field (scraped) |
| `/תרשים-מבנה-הארגון/` | ✓ | Org chart (scraped) |
| `/טיפים-להגשה/` | ✓ | Submission tips (scraped) |
| `/תקנות-הקולנוע-הכרה-בסרט-כסרט-ישראלי-ת/` | ✓ | Film regulations (21 KB) |
| `/weil-bloch-film-award/` | ✓ | Weil Bloch Award (30 KB) |
| `/investors/` | ✓ | Investors page (16 KB) |
| `/lectors/` | ✓ | Lectors page (13 KB) |
| `/nfctsupport/` | ✓ | NFCT Support (9 KB) |
| `/contact/` | ✓ | Contact page (8 KB) |
| `/privacy-policy/` | ✓ | Privacy policy (27 KB) |
| `/terms-of-use/` | ✓ | Terms of use (33 KB) |
| `/accessibility/` | ✓ | Accessibility (10 KB) |
| `/לוגו/` | ✓ | Logo page (14 KB) |
| `/ארכיון-ניוזלטר/` | ✓ | Newsletter archive (30 KB) |
| `/news/` | ✓ | News page (164 KB) |

---

## New Pages Discovered & Scraped (this session)

| Metric | Value |
|---|---|
| URLs discovered from מידע מקצועי landing page | 22 |
| Additional sub-links from existing pages | 44 |
| Total new URLs discovered | 1,549 (cleaned) |
| Already scraped (deduplicated) | 1,511 |
| **Truly new URLs** | **1,511** |
| New pages scraped this session | ~20 (in progress) |
| New content bytes this session | ~604,867 |

### New URL Categories

| Category | Count |
|---|---|
| `/blog` posts | 1,332 |
| `/en` pages | 199 |
| `/root` (query params) | 10 |
| `/events` | 3 |
| `/movies` | 2 |
| `/movies-archive` | 2 |
| Other (forms, guidelines) | 13 |

---

## Failed URLs

| URL | Error |
|---|---|
| `https://nfct.org.il/about/` | Read timeout (120s) |

---

## Notes

1. **Rate limiting**: The scraper service returns `429 Too Many Requests` when concurrency > 3. Batch scraping at 3 concurrent workers processes ~5-6 URLs/minute.

2. **Encoding variations**: Many URLs appear multiple times with different percent-encoding (uppercase vs lowercase Hebrew chars). These are deduplicated by normalizing to lowercase decoded form.

3. **Fragment URLs**: URLs with `#UAmlxHHRM1`, `#UAMainContent`, etc. are Disqus/WordPress comment anchors — same page, different fragments.

4. **Remaining to scrape**: ~1,490 blog posts and English pages remain. At current rate (~5 URLs/min, 3 concurrent), estimated completion time: **~5 hours**.

---

## File Locations

| Path | Description |
|---|---|
| `sources/nfct/pages/*.md` | Scraped markdown content (69,212 files) |
| `sources/nfct/pages/*.meta.json` | Metadata with URLs, timestamps, link counts |
| `sources/nfct/professional_scrape_report.json` | This session's discovery report |
| `sources/nfct/new_urls_clean.txt` | 1,549 cleaned URLs discovered |
| `sources/nfct/truly_new_urls.txt` | 1,511 URLs not yet scraped |
| `sources/nfct/batch_scrape.log` | Live batch scraping log |
