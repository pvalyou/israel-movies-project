# scripts/scrapers/

Fetch raw web content and convert it to `.md` + `.meta.json` pairs in `sources/<source_id>/pages/`. These pairs are the input to `scripts/llm_extract.py`.

All scripts read `CRAWL4AI_API_KEY` from the environment or `.env`.

---

## scrape.py

General-purpose batch scraper. Calls the `crawl4ai-wrapper` service, follows links up to `MAX_DEPTH` levels, and saves results.

```bash
# Scrape a single site
python3 scripts/scrapers/scrape.py docaviv "דוקאביב" https://www.docaviv.co.il/

# Read URLs from a file (one URL per line)
python3 scripts/scrapers/scrape.py --file data/urls/urls_festivals.txt
```

Output: `sources/<source_id>/pages/<prefix>__<slug>__<hash>.{md,meta.json}`

Env overrides: `SCRAPER_URL`, `CRAWL4AI_API_KEY`, `SCRAPER_CONCURRENCY` (default 5), `SCRAPER_MAX_DEPTH` (default 2), `SCRAPER_FOLLOW_LINKS` (default true).

---

## scrape_festivals.py

Lightweight batch scraper for festival URLs. Same crawl4ai-wrapper backend as `scrape.py` but simpler (no link-following, 3-retry logic, no env config). Good for quick one-off festival scrapes.

```bash
python3 scripts/scrapers/scrape_festivals.py data/urls/urls_festivals.txt festival_data
```

Output: `sources/festival_data/pages/`

---

## scrape_from_sitemap.py

Fetches a sitemap XML, extracts all `<loc>` URLs, and scrapes each one as a single page (no link-following). Skips already-scraped URLs unless `--force` is given.

```bash
python3 scripts/scrapers/scrape_from_sitemap.py \
    fdoc "הפורום הדוקומנטרי" https://www.fdoc.org.il/movie-sitemap.xml

# Options
--dry-run         List URLs without scraping
--force           Re-scrape existing pages
--concurrency N   Parallel requests (default 5)
--limit N         Cap at N URLs (for testing)
```

Output: `sources/<source_id>/pages/`

---

## pdf_to_pages.py

Converts PDFs and DOCX files in `sources/*/files/` into `.md` + `.meta.json` pairs in `sources/*/pages/` so they can be processed by `llm_extract.py`. Skips scanned/image-only PDFs (below `MIN_CHARS = 100` characters extracted).

Requires: `PyMuPDF` (`pip install pymupdf`), optionally `python-docx`.

```bash
python3 scripts/scrapers/pdf_to_pages.py              # all sources
python3 scripts/scrapers/pdf_to_pages.py --source gesher
python3 scripts/scrapers/pdf_to_pages.py --dry-run
```
