# scripts/

Organised by pipeline stage. All scripts must be **run from the project root** so relative paths to `out/`, `sources/`, `enriched/` resolve correctly.

```
scripts/
├── llm_extract.py     ← LLM extraction: pages → mentions.jsonl
├── scrapers/          ← Fetch raw content from the web
├── importers/         ← Write hand-curated data into mentions.jsonl
└── enrichers/         ← Fill gaps in existing mentions.jsonl records
```

---

## llm_extract.py

Sends scraped `.md` files through an LLM (via OpenRouter) and writes structured `mentions.jsonl` entries to `out/<source>/`.

- Resumable: skips pages already processed
- Concurrent: 12 worker threads by default
- Pre-filter: skips pages with no Hebrew film vocabulary (reduces LLM cost)
- Live progress: `tail -f out/<source>/run.log`

```bash
export OPENROUTER_API_KEY=your_key

# Run one source
python3 scripts/llm_extract.py sources/filmfund/pages out --source-name filmfund

# Test on first 100 pages
python3 scripts/llm_extract.py sources/arava_film_fund/pages out --max-pages 100

# Disable pre-filter (send every page)
python3 scripts/llm_extract.py sources/gesher/pages out --no-filter
```

---

See subdirectory READMEs for details on each stage.
