# Israeli Film Industry — Entity & Relationship Extraction Pipeline

**Project status as of:** May 2026
**Owner:** Moran (P-Valyou)
**Goal:** Build a relationship-mapping platform for the Israeli film industry — people, funds, films, governance bodies, and the connections (employment, funding, conflicts of interest) between them.

---

## Context

This work expands the existing P-Valyou prototype (`pvalyou.github.io/israel-movies-project/`) from its initial two-source kernel (the client's Hebrew document + Tafnit 2017 report) into a corpus-scale system that ingests **~70,000 scraped web pages** across ~16 source domains.

The prototype is positioned strictly as a **relationship-mapping capability demonstration**, not verified investigative findings. All schema and pipeline decisions preserve this distinction (e.g. `evidence_strength` field, source provenance on every claim, mentions-vs-entities separation).

---

## Source corpus

70K pages across these source directories (one per scraped site):

```
sources/
├── arava_film_fund/       (~600 pages — completed first test run)
├── cash_rebate/
├── council_protocols/
├── film_council/
├── filmfund/
├── galilee_film_fund/
├── gesher/
├── guidestar/             (NGO financial filings)
├── jerusalem_film_fund/
├── lectors_database/
├── makor/
├── ministry_of_culture/
├── nfct/
├── rabinovich_cinema/
└── rabinovich_foundation/
```

Each source has a `pages/` subdirectory with pairs of files per scraped page:
- `<source>__<path-slug>__<hash>.md` — content (JSON-wrapped with markdown body)
- `<source>__<path-slug>__<hash>.meta.json` — scraping metadata (url, title, dates)

Scrape run metadata lives alongside in `runs/<timestamp>/` (`manifest.json`, `extraction.log`).

**Filename quirk:** Hebrew URL path segments are URL-percent-encoded with `%` replaced by `-`. Example: `arava_film_fund__movies-d7-a7-d7-96-d7-91-d7-9c-d7-a0-d7-94.md` decodes to `arava_film_fund__moviesקזבלנה.md` ("Casablanca").

---

## Architectural decisions

### Mentions vs. entities

A **page is a mention source**, not an authoritative entity record. Per-page LLM output gets stored as "claims observed on this page" with page-local IDs (`person_001`, `person_002` reset per page). Entity resolution and canonical-graph assembly are explicit downstream stages, never collapsed into the extraction stage. This is the reason the per-page output is called `mentions.jsonl`, not `entities.json`.

### Per-source isolation

Each source runs independently into `out/<source_name>/`. Reasons:
- Independent cost tracking, resumability, parallelism
- Source-specific tuning (seed terms, max_chars) without affecting others
- One source failing doesn't block others
- Sources can be run in parallel from separate terminals or via `xargs -P3`

### Graph schema (target final output)

Designed in a previous conversation step. Key principles:

- **Roles are first-class objects**, not properties on people. A person can hold multiple overlapping roles at different organizations over time. The whole scandal pattern (lector + filmmaker + council member, simultaneously) is encoded as joins between roles and relationships.
- **Relationships are a flat array** with typed edges (`funded`, `produced`, `served_as_lector`, `co_occurred_in_committee`, `transferred_funds_to`, etc.). Symmetric edges use a `participants` array instead of source/target.
- **Flags are separate from relationships.** A conflict-of-interest finding is a *judgment about* relationships and roles, not a relationship itself. Keeping them separate allows showing raw facts independently of interpretation — essential to the "demonstration not verified findings" framing.
- **Every record has a `sources` array.** Page references in format `<source>__<file>` or `<source>__<file>#<location>`.
- **`evidence_strength`** on every relationship: `documented` (primary source) | `reported` (Tafnit-style secondary) | `alleged` (unsourced claim).

### Pipeline stages

1. **Filter** (deterministic, free) — pre-LLM pass to drop irrelevant pages. ✅ Built.
2. **Per-page extraction** (LLM, cheap — Gemini 2.5 Flash Lite via OpenRouter) — emit `mentions.jsonl` with page-local IDs. ✅ Built.
3. **Entity resolution** (mostly deterministic, some LLM for ambiguous pairs) — map mentions → canonical entities. 🔲 Not built yet.
4. **Relationship aggregation** (deterministic) — group claims by (entity_pair, type); evidence strength derives from citation count + source diversity. 🔲 Not built yet.
5. **Graph assembly** (deterministic) — produce the final unified graph JSON. 🔲 Not built yet.
6. **Flag analysis** (capable LLM, e.g. Sonnet/Opus, over the small structured graph) — generate conflict-of-interest findings. 🔲 Not built yet.

Only stages 1-2 are implemented so far.

---

## The extraction script: `llm_extract.py`

Single CLI script, per-source runner. Final delivered version is ~759 lines.

### Core design

- **Iterates `*.md` files** (not `*.meta.json`). The `.meta.json` sidecar is read opportunistically to pick up the URL but is never the iteration unit. Pages without a meta sidecar still get processed.
- **Resumable via JSONL append.** Each page result is written to `mentions.jsonl` immediately before the next page starts. On restart, the script scans existing JSONL, builds a set of done filenames, and skips them. Ctrl-C anytime — partial results survive.
- **Concurrent (12 workers default).** `ThreadPoolExecutor`; API calls are I/O-bound. Thread-safe usage counters, log writes, and JSONL appends via `threading.Lock`.
- **Structured output mode** — `response_format={"type": "json_object"}` eliminates most malformed-JSON retries. One retry path retained as fallback.
- **Live log file** — `tail -f out/<source>/run.log` from another terminal shows real-time per-page status, periodic running totals every 50 pages with rate + ETA + cost.
- **Per-source summary JSON** at end (`run_summary.json`) for orchestration.

### Pre-filter logic (layered)

A page passes iff **any** of:

1. **Always-pass via filename or decoded filename**: matches `root | about | home | index | team | leadership | members | staff | lectors | catalog | אודות | צוות | לקטורים | חברי | מועצה | דירקטוריון`
2. **Always-pass via URL path** (URL-only to avoid false-matching source-name prefixes like `arava_film_fund`): `/movies/`, `/films/`, `/people/`, `/cast/`, `/crew/`, `/director(s)/`, `/producer(s)/`, `/program/`, `/supported-films/`, `/סרטים/`, `/בית/`
3. **Specific entity hit** (≥1): Rabinovich, Gesher, Edery, Eini, Abramovitz, Cohen, Naveh, United King, Cinema City, Ministry of Culture, etc.
4. **Generic vocabulary hit** (≥2): film/funding terminology in Hebrew AND English. Hebrew matched as-is; English matched case-insensitively (so `Director`/`Producer` capitalized in film credits matches the lowercase seed).

### Per-record fields in `mentions.jsonl`

```jsonc
{
  "file": "arava_film_fund__movies-d7-a7-d7-96-d7-91-d7-9c-d7-a0-d7-94.md",
  "url": "https://aravaff.co.il/movies/קזבלנה/",
  "source_name": "arava_film_fund",
  "status": "ok | filtered | empty_content | load_error | llm_error",
  "content_length": 4827,
  "content_preview": "...",  // first 200 chars, only on filtered records
  "filter_info": {
    "reason": "always_pass | pass | filter",
    "matched_pattern": "...",  // when always_pass
    "decoded_name": "...",     // when filename had encoded Hebrew
    "generic_hits": 3,
    "specific_hits": 0,
    "matched_generic": [...], "matched_specific": [...]
  },
  "truncated": false,
  "elapsed_sec": 2.4,
  "data": { /* the LLM-extracted graph fragment */ }
}
```

### CLI

```bash
export OPENROUTER_API_KEY=your_key_here

# Full run on one source (input is always .../pages/)
python3 llm_extract.py ./sources/arava_film_fund/pages ./out \
    --source-name arava_film_fund

# Smoke test — first 50 pages only
python3 llm_extract.py ./sources/rabinovich_foundation/pages ./out \
    --source-name rabinovich_foundation --max-pages 50

# More workers / longer pages
python3 llm_extract.py ./sources/filmfund/pages ./out \
    --source-name filmfund --workers 16 --max-chars 12000

# Skip pre-filter (every page goes to the LLM)
python3 llm_extract.py ./sources/gesher/pages ./out --source-name gesher --no-filter

# Monitor progress in another terminal
tail -f ./out/arava_film_fund/run.log
```

Arguments: `<source_pages_dir>` (the `pages/` folder), `<output_root>` (writes to `<output_root>/<source_name>/`).

Optional flags: `--source-name NAME` (recommended — avoids `source_name: "pages"` if you omit it), `--max-pages N`, `--workers N` (default 12), `--max-chars N` (default 8000), `--no-filter`.

Defaults: 12 workers, max_chars=8000, pre-filter on.

### Logging format

Each page produces a 3-line block — the real filename (copy-pasteable for `cat`) is always shown on its own line, decoded Hebrew shown in brackets as a reading hint:

```
[554/602] SKIP (g=1 s=0) matched=['סרט']
          file: arava_film_fund__movies-d7-a7-d7-96-d7-91-d7-9c-d7-a0-d7-94.md  [arava_film_fund__moviesקזבלנה.md]
          url:  https://aravaff.co.il/movies/קזבלנה/
```

### Filename decoder

`decode_filename()` converts scraper's `-XX-XX` percent-encoded Hebrew back to readable form. Only triggers on runs of ≥2 consecutive `-XX` hex pairs that produce Hebrew chars, so hash-like fragments (`fb252d5f`, `f1-b2-c3-d4`) are left alone.

---

## Critical bugs found and fixed (in order discovered)

1. **Was iterating `.meta.json` instead of `.md`.** Pages without a meta sidecar were silently dropped. Fixed: iterate `.md`, treat meta as optional URL source.

2. **`arava_film_fund__root__fb252d5f.md` got filtered** despite being the homepage. Fixed: added `ALWAYS_PASS_PATTERNS` for root/about/home/index, including Hebrew `אודות`/`בית`.

3. **Log filenames truncated at 55 chars made encoded names indistinguishable.** Several different pages all showed identical truncated prefixes. Fixed: removed truncation, added `decode_filename()`, log shows full real name + decoded hint.

4. **English film pages (`/en/movies/...`) entirely missed by Hebrew-only seed list.** Files with rich English content (`Director: ...`, `Producers: ...`, `Actors: ...`) were filtered with zero hits. Fixed: added English terms to `GENERIC_TERMS` (case-insensitive matching), added URL-path always-pass for `/movies/`, `/people/`, `/lectors/`, etc.

5. **`_film_` inside source-name prefix (`arava_FILM_fund`) caused every file in that source to false-trigger the always-pass.** Discovered when `cookies-policy.md` wrongly passed. Fixed: split always-pass into two groups — safe terms match filename+URL, ambiguous terms (`films?`, `movies?`, `people`, etc.) match URL paths only.

6. **`NameError: meta_files` at end of run** — stale reference from rename. Data was already saved, only the `run_summary.json` write failed. Fixed.

---

## Cost / performance benchmarks (real data)

**arava_film_fund — first full run (602 pages, after all fixes):**
- Wall time: 4.7 min with 12 workers
- Status: 316 ok, 286 filtered, 0 errors, 5 JSON retries
- Tokens: 1.07M input, 1.46M output
- Cost: **$0.69** (~$0.00115 per page processed, ~$0.0022 per ok-extraction)
- Throughput: ~127 pages/min

**Extrapolation for 70K pages:**
- At ~$0.00115/page average: **~$80** if all pages reach the LLM
- With ~50% pre-filter rate (observed on arava): **~$40**
- Wall time per source ≈ pages / 7600 hours single-machine; running 4 sources in parallel finishes the whole corpus in roughly 1.5-2 hours

Pricing: Gemini 2.5 Flash Lite — $0.10 / 1M input tokens, $0.40 / 1M output.

---

## Repository state

Working files in this repo:
- `llm_extract.py` — the production extractor
- `sources/<source_name>/pages/` — scraped input (`.md` + `.meta.json` pairs)
- `sources/<source_name>/runs/` — scrape run manifests and logs
- `out/<source_name>/mentions.jsonl` — per-source extraction output (resumable)
- `out/<source_name>/run.log` — live log file
- `out/<source_name>/run_summary.json` — written at end of each run

The previous tool `llm_comparison.py` was the multi-model comparison harness for the 30-page sample run that produced the $0.028 cost benchmark. Superseded by `llm_extract.py` for production runs.

---

## What hasn't been built yet (next steps)

### Immediate: finish extraction on remaining sources

Run `llm_extract.py` on each remaining source. Priority order (highest investigative value first):

1. `rabinovich_foundation` — fund decisions, lector lists, financial reports
2. `council_protocols` — actual meeting minutes, highest-value source
3. `filmfund` — grant recipients, committee decisions
4. `gesher` — fund decisions, supported films
5. `lectors_database` — who evaluated what
6. `ministry_of_culture` — policy documents, הוראת שעה
7. `guidestar` — NGO financials, Rabinovich revenue inflation evidence
8. Remaining regional funds (galilee, jerusalem, makor, nfct, etc.)

For each source: test on `--max-pages 50` first, check filter rate and top people names, then run full.

**Source-specific seed term additions needed:**
- `guidestar` — add `עמותה`, `מחזור`, `דוח שנתי`, `נכסים`
- `council_protocols` — add `פרוטוקול`, `החלטה`, `ישיבה`
- `ministry_of_culture` — add `מבחני תמיכה`, `הוראת שעה`, `תקנות`

**Always run with explicit `--source-name`** to avoid the `pages` labeling bug:
```bash
python3 llm_extract.py ./sources/rabinovich_foundation/pages ./out \
    --source-name rabinovich_foundation
```

**Known signal check** — after each central source run, verify these names appear in top-20 people:
`גיורא עיני`, `יואב אברמוביץ`, `משה אדרי`, `אתי כהן`, `זיו נווה`
If they don't appear → filter too aggressive or prompt needs tuning for that source.

---

## Stage 3: Entity resolution (to build next)

### The problem

Each `mentions.jsonl` has page-local IDs that reset per page. The same person appears as `person_001` on 47 different pages with spelling variants:

```
"גיורא עיני"        (rabinovich_foundation, 23 pages)
"ג. עיני"           (council_protocols, 8 pages)
"Giora Eini"        (english pages, 4 pages)
"גיורא עיני מנכל"   (filmfund, 2 pages)
```

Resolution maps all of these to one `canonical_person_0042` with a stable ID used everywhere downstream.

### Resolution methods (in order of cost, apply sequentially)

**Method 1 — Exact match (free):** same Hebrew string → same entity. Catches ~60-70%.

**Method 2 — Normalized match (free):** strip punctuation, titles (`ד"ר`, `מר`, `גב'`), normalize quotes and whitespace before comparing. Catches another 15-20%.

```python
normalize("ד\"ר גיורא עיני") == normalize("גיורא עיני")  →  merge
normalize("קרן רבינוביץ'")   == normalize("קרן רבינוביץ") →  merge
```

**Method 3 — Fuzzy match (cheap):** token-sort ratio via `rapidfuzz`. Produces *candidate pairs* above threshold (~85), not automatic merges.

```python
fuzz.token_sort_ratio("ג עיני", "גיורא עיני")  →  85  →  candidate
```

**Method 4 — LLM resolution (for ambiguous pairs only):** batch 20-30 pairs per call with role context:

```
Are these the same person?
1. "ג. עיני" (ceo at קרן רבינוביץ') vs "גיורא עיני" (council protocols)
2. "י. אברמוביץ" (lector, rabinovich) vs "יואב אברמוביץ'" (producer, filmfund)
```

Estimated ~200-500 ambiguous pairs total. Cost: a few dollars.

### Resolution script inputs/outputs

**Input:** all `out/*/mentions.jsonl` files combined.

**Intermediate outputs:**
- `person_mentions.tsv` — every person mention with source, file, URL, name_he, name_en, roles
- `org_mentions.tsv` — same for organizations
- `ambiguous_pairs.json` — pairs above fuzzy threshold, needs LLM review

**Final outputs:**
- `entity_registry.json` — canonical entities with stable IDs, all aliases, all source pages
- `mentions_resolved/` — rewritten JSONL files with canonical IDs replacing page-local IDs

### Flatten command (prerequisite)

```bash
# Combine all source mentions into one flat file
cat out/*/mentions.jsonl > all_mentions.jsonl

# Quick inventory
jq -r '.status' all_mentions.jsonl | sort | uniq -c
```

### Extract mentions to TSV (prerequisite)

```bash
# All person mentions with provenance
jq -r 'select(.status=="ok") |
  .source_name as $src | .file as $f | .url as $url |
  .data.entities.people | to_entries[] |
  [$src, $f, $url, .value.name_he, (.value.name_en // ""), (.value.primary_roles | join("|"))] |
  @tsv' all_mentions.jsonl > person_mentions.tsv

# All org mentions
jq -r 'select(.status=="ok") |
  .source_name as $src | .file as $f |
  .data.entities.organizations | to_entries[] |
  [$src, $f, .value.name_he, .value.type] |
  @tsv' all_mentions.jsonl > org_mentions.tsv
```

### The resolver script (`resolve_entities.py`) — to be built

Will implement the 4-method resolution pipeline above and output `entity_registry.json`.

---

## Stage 4-5: Relationship aggregation and graph assembly (to build after resolution)

### Aggregation logic

After resolution, every relationship claim has canonical entity IDs. Group by `(canonical_source_id, canonical_target_id, relationship_type)`:

```python
key = (canonical_person_0042, canonical_org_0003, "ceo")
citations = [list of source pages asserting this]
evidence_strength = "documented" if any citation has a primary source footnote
                    else "reported" if from Tafnit or secondary aggregation
                    else "alleged"
```

A relationship asserted across 23 pages and 4 source domains is rock-solid evidence — you get `evidence_strength` from citation count for free, no LLM judgment needed.

### Cross-source connections the aggregation will surface

These are the investigative findings that are only visible after resolution:

| Person | Source A role | Source B role | Conflict |
|---|---|---|---|
| גיורא עיני | CEO at Rabinovich (`rabinovich_foundation`) | Lector (`filmfund`) | Evaluated grants to own fund's films |
| משה אדרי | Producer (`filmfund`) | Owner United King (`guidestar`) | 49% of Rabinovich grants |
| אתי כהן | Ministry official (`ministry_of_culture`) | Council director (`council_protocols`) | Controlled both sides of oversight |
| יואב אברמוביץ | Art director Rabinovich (`rabinovich_foundation`) | Lector (`filmfund`) | Evaluated while employed by fund |

### Final graph assembly

Merge `entity_registry.json` + `aggregated_relationships.json` → `israeli_film_industry_graph.json` using the schema defined earlier (entities, roles, relationships, flags sections).

---

## Stage 6: Flag analysis (to build last)

Run Sonnet/Opus over the **small structured graph** (not the raw corpus) to identify and write the `flags` records:

- `conflict_of_interest` — person holds role at fund + evaluated that fund's applications
- `concentration_of_funding` — single producer receives outsized share
- `tenure_violation` — manager exceeded term limits per הוראת שעה
- `committee_composition_issue` — same lector in original review + appeal
- `financial_irregularity` — Rabinovich/United King transfer discrepancies

Input to LLM: the graph (maybe 500KB JSON). Not the 70K-page corpus.

---

## Arava Film Fund — extraction results and lessons

**First completed source run (602 pages):**
- 316 ok, 286 filtered, 0 errors
- Cost: $0.69, 4.7 min, 12 workers

**What arava_film_fund actually contains:**
The Arava Film Fund is a small regional festival that screens international films. Its website is mostly a film catalog — directors are Michel Franco, Roman Polanski, Jean-Luc Godard, etc. (international auteurs, not Israeli industry insiders). Top orgs are `קרן הקולנוע נגב`, accommodation resorts, `פסטיבל קאן`.

**Investigative value: LOW.** Useful for establishing the Arava/Negev fund as a graph entity and linking some Israeli filmmakers to their films. Not useful for lector conflict-of-interest patterns, Rabinovich/Gesher concentration findings, or Ministry governance issues.

**Lesson:** The current prompt treats film credits (Director/Producer of individual films) with equal weight to institutional roles (fund manager, lector, council member). For the central investigative sources, add this to the prompt:

> For Israeli film industry pages: prioritize people who hold INSTITUTIONAL roles (fund managers, lectors, council members, ministry officials) over directors/actors of individual films. A person's role at a fund matters more than their creative credits.

**`source_name` labeling bug:** Running without `--source-name` when the input dir is literally named `pages` sets `source_name: "pages"` in every record. Always pass `--source-name <source>`. Fix existing records: `jq -c '.source_name = "arava_film_fund"' out/arava_film_fund/mentions.jsonl > fixed.jsonl && mv fixed.jsonl out/arava_film_fund/mentions.jsonl`.

---

## Stage 7: Visualization integration

Feed the final `israeli_film_industry_graph.json` into the existing prototype at `pvalyou.github.io/israel-movies-project/`. The graph schema was designed to be directly consumable by the platform's existing D3/vis.js relationship mapper.

---

After each run:

```bash
# Status distribution
jq -r '.status' out/<source>/mentions.jsonl | sort | uniq -c

# Top relationship types extracted
jq -r 'select(.status=="ok") | .data.relationships[]?.type' \
    out/<source>/mentions.jsonl | sort | uniq -c | sort -rn | head

# Top people mentioned across the source
jq -r 'select(.status=="ok") | .data.entities.people | to_entries[] | .value.name_he' \
    out/<source>/mentions.jsonl | sort | uniq -c | sort -rn | head -20

# Audit filtered pages — sample to verify they're really junk
jq -r 'select(.status=="filtered") |
       "FILE: \(.file)\nURL:  \(.url // "")\nPREV: \(.content_preview // "" | .[:120])\n---"' \
    out/<source>/mentions.jsonl | head -40

# Truncated pages — candidates for re-run with higher --max-chars
jq -r 'select(.truncated == true) | "\(.content_length)\t\(.file)"' \
    out/<source>/mentions.jsonl | sort -rn | head -10

# Total cost across all sources
cat out/*/run_summary.json | jq -s 'map(.cost_usd) | add'
```

To re-process previously-filtered pages after improving the filter logic:

```bash
# Strip filtered records so they get re-evaluated; keep ok/error records
jq -c 'select(.status != "filtered")' out/<source>/mentions.jsonl > out/<source>/mentions.tmp
mv out/<source>/mentions.tmp out/<source>/mentions.jsonl
python3 llm_extract.py ./sources/<source>/pages ./out --source-name <source>  # only filtered pages re-run
```

---

## Key principles to preserve in future work

1. **Per-page output is mentions, not entities.** Never collapse the resolution step.
2. **Source provenance on every claim.** No orphan facts. `sources` field is mandatory.
3. **Evidence strength preserved end-to-end.** Documented vs. reported vs. alleged.
4. **The prototype is a demonstration, not verified findings.** Language and UI choices must keep this distinction visible. Moran has rejected framings that imply ongoing surveillance or assert findings as verified.
5. **Don't over-engineer.** Earlier in the conversation I suggested a 5-pass chunked approach that was overkill — single-pass with concurrency and resumability is the right architecture at this scale.
