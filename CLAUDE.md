# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **web scraping and data pipeline project** for Israeli film organizations. It scrapes film fund/festival websites (starting with Arava Film Fund / קרן קולנוע נגב/ערבה), stores the content as Markdown + JSON metadata pairs, and feeds the data into a Python extraction pipeline that produces structured entity/relationship data.

## Running the Extraction Pipeline

The extraction scripts (`film_data_extractor.py`, `advanced_film_extractor.py`) live outside this repo (in `~/film_extraction/`). To process the scraped data:

```bash
# Basic run
python3 ~/film_extraction/film_data_extractor.py ./arava_film_fund/pages ~/output

# Full run with log
python3 ~/film_extraction/film_data_extractor.py ./arava_film_fund/pages ~/output 2>&1 | tee extraction.log
```

Output: `extracted_entities.json`, `relationships.csv`, `people.csv`

## Data Layout

```
arava_film_fund/
├── pages/          # Scraped content — pairs of .md + .meta.json files
└── runs/           # One subdirectory per scrape run (UTC timestamp)
    └── <timestamp>/
        ├── manifest.json   # Run config & stats (URLs, bytes, duration)
        └── extraction.log
```

**File naming convention for pages:**
`<source_id>__<slugified-url>__<hash>.{md,meta.json}`

Each `.meta.json` records: `url`, `fetched_at`, `final_url`, `cache_hit`, `status`, `md_hash`, `md_bytes`, `links_found`.

## Scraper Configuration

The remote scraper service (`crawl4ai-wrapper-559961100092.europe-west1.run.app`) is configured per-run via `manifest.json`:
- `concurrency`: 5 parallel requests
- `follow_links`: true, `max_depth`: 2
- `format`: markdown with links included
- `tier`: "A" = highest priority source

## Extraction Output Schema

The Python extractor outputs JSON with this structure:
```json
{
  "entities": {
    "people": { "<id>": { ... } },
    "organizations": { ... },
    "films": { ... }
  },
  "relationships": [ { "source", "target", "type", ... } ],
  "conflicts": [ ... ]
}
```

## Hebrew Text Patterns

The extractor uses pattern matching for Hebrew content. Key pattern categories in `film_data_extractor.py`:
- `roles`: job title patterns (מנהל, מנהלת, מנכ"ל, …)
- `fund_indicators`: funding-related terms (קרן, תמיכה, מימון, …)

To add patterns, edit the `self.hebrew_patterns` dict in the extractor script.
