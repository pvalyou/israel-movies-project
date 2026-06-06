# Plan — Pipeline Refactor (source-of-truth, acyclic build, validation)

Status legend: ☐ todo · ◐ in progress · ☑ done · ⏸ blocked

Last updated: 2026-06-04

---

## Goal

Make `data/movies_db.json` the genuine single source of truth for film data, break
the resolve↔movies_db circular dependency, give the pipeline a one-command acyclic
build, and fail fast on bad data between stages.

Four work items, run in dependency order. **Phase 1 must land before Phase 2** (proven
by A/B: switching the report to movies_db today drops ~85%-real credits).

---

## Phase 0 — DONE (this session)

- ☑ Copied `resolve_entities.py` → `resolve_entities_v2.py` (baseline left untouched).
- ☑ Added movies_db index + `person_films()` to v2; rewrote the "קרדיטים בסרטים" block
  in `render_person_card` to source the filmography from `movies_db.json` by
  `registry_id` (+ normalized-name fallback).
- ☑ Fixed index bug: records with no `film_id` (1,782 / 20%, 9,083 crew rows) were
  skipped → now fall back to a `t|title|year` key.
- ☑ A/B harness written: `/tmp/ab_diff.py` (per-person film diff),
  `/tmp/ab_quality2.py` (loss classification).
- ☑ Verified detection unchanged: `entity_registry.json` + graph nodes/edges
  byte-identical between orig and v2 (only timestamps differ).
- ☑ Loss-quality verdict: of credits the switch drops, ~85%+ real, <9% likely-false
  (and those trace to real EDB person-page filmographies). See [TODO.md](../TODO.md).

---

## Phase 1 — Enrich movies_db.json crew (PREREQUISITE for the switch)  ☑ DONE 2026-06-04

**Result:** `scripts/enrich_movies_db_crew.py` (2 passes: edb_persons.json + fund/festival
mention /film/ pages). crew rows **18,581 → 51,976** (+180%), films 8,771 → 11,340.
A/B vs mention baseline: v2 filmography **+3,231 rows richer**; likely-real losses cut
4,146 → **65** (scattered singletons, no systematic gap); v2 correctly drops ~434
contamination credits (filmmaker-role / multi-film listing pages). Exit spot-check passed
(ליאון אדרי 151→158, יורם מילוא 41→58, דורון צברי 21→30, כליל כובש 9→10, אסף לפיד 19→18).
Two bugs found+fixed via A/B: (a) index skipped 1,782 no-`film_id` records; (b) slug guard
rejected English-slug+Hebrew-title fund pages — now only applied to multi-film pages.
**Note:** movies_db.json is now the enriched version (backup at data/movies_db.json.bak).

<details><summary>original sub-steps</summary>

**Why:** movies_db crew is director/producer-level (median 1/film). The report's
mention-derived filmography is ~85%+ real but movies_db doesn't hold it yet.

**Deliverable:** `scripts/enrich_movies_db_crew.py` → rewrites `data/movies_db.json`
with fuller crew, idempotently.

**Sources (priority order):**
1. `data/cinemaofisrael/raw_films.json` — 1,240 films with full crew (avg 22.5).
   `build_movies_db.py` currently drops most of this at merge.
2. EDB person pages — `edb_persons.json` (1,803 persons' filmographies). Source of
   most real non-headline credits (sound/dop/editor) that film-page crew misses.
3. (Optional) `data/jfc/raw_films.json` crew.

**Match key:** normalized `title_he` + `year` (reuse `normalize_film_title`). For
person-page sources, attach the person to each listed film's crew with their role.

**Steps:**
- ☐ 1.1 Write `enrich_movies_db_crew.py`: load movies_db, build title|year → film index,
  union in crew from CI raw + edb_persons; dedupe crew by (normalized name, role).
- ☐ 1.2 Populate `registry_id` on new crew rows via the same registry map
  `build_movies_db.py` uses (so the report join stays exact, not just name-fallback).
- ☐ 1.3 **Decision needed:** films present in sources but absent from movies_db —
  add them, or only enrich existing films? (see Decisions below)
- ☐ 1.4 Run enricher; record before/after crew-per-film stats.
- ☐ 1.5 Re-run A/B (`ab_diff.py` + `ab_quality2.py`); target: remaining real-loss ≈ 0,
  contamination (likely-false) correctly dropped.
- ☐ 1.6 Wire enricher into the pipeline after `build_movies_db.py` /
  `enrich_movies_db_from_funds.py`.

**Exit criteria:** A/B shows v2 filmography ⊇ orig real credits (losses are only the
<9% contamination); per-person spot-check on 5 known people (ליאון אדרי, יורם מילוא,
דורון צברי, כליל כובש, אסף לפיד) passes.
</details>

---

## Phase 2 — Promote the film-source rewrite  ☑ DONE 2026-06-04

Promoted v2 → `resolve_entities.py` (baseline kept at `resolve_entities_orig_backup.py`
until QA passes). Removed dead `_load_film_fund_lookup`/`_FILM_FUND_LOOKUP` (no refs).
`url_to_film` kept (still used by other card sections). `resolve_entities_v2.py` deleted.
**Finding:** report output is non-reproducible across runs due to `PYTHONHASHSEED`
set-ordering — *pre-existing* (orig backup also differs); fixed by pinning
`PYTHONHASHSEED=0` in the Makefile (Phase 4). With the seed pinned, new code is
byte-identical run-to-run. ☐ 2.3 qa-reviewer still to run after full rebuild.

<details><summary>original sub-steps</summary>

- ☐ 2.1 Fold v2's index + `person_films` + rewritten film block into
  `resolve_entities.py` (or make v2 canonical and retire the old film-map code +
  its now-dead helpers: `films_match`, `film_priority`, `_subtitle_key`, the
  transliteration/search-page filters in `render_person_card`).
- ☐ 2.2 Remove the now-unused `url_to_film` plumbing from the film display path
  (keep where still used elsewhere — verify with grep first).
- ☐ 2.3 Run `qa-reviewer` agent against the regenerated `connections_report.html`
  (per QA workflow); add QA_TESTS.md entries for any new bug.
- ☐ 2.4 Delete `resolve_entities_v2.py` once folded in.
</details>

---

## Phase 3 — Break the circular dependency (resolve / render split)  ☑ DONE 2026-06-04

Added `--phase {resolve,render,all}` to `main()` (default `all`). `resolve` writes
entity_registry.json + ambiguous_pairs.json and never reads movies_db.json; `render`
writes connections_report.html + network_graph.json sourcing filmographies from a fresh
movies_db.json. Verified each phase writes only its outputs; chosen design = re-run
resolution in-memory (D2). Acyclic order: resolve → build_movies_db → enrich → enrich_crew
→ render.

<details><summary>original sub-steps</summary>

**Cycle today:** `resolve_entities.py` reads `movies_db.json` (fund badges) but
writes `entity_registry.json`, which `build_movies_db.py` needs to build
`movies_db.json`. So the report reads a *stale* movies_db.

**Fix:** split `resolve_entities.py` outputs into two phases driven by a flag:
- `--phase resolve` → resolution only; writes `entity_registry.json` +
  `ambiguous_pairs.json`. No HTML, no graph, does NOT read movies_db.
- `--phase render` → re-runs the (deterministic, ~1.7s) in-memory resolution, then
  reads the now-fresh `movies_db.json` and writes `connections_report.html` +
  `network_graph.json`.

Acyclic order becomes: resolve → build_movies_db → enrich → enrich_crew → render.

- ☐ 3.1 Add `--phase {resolve,render,all}` to `main()` (default `all` = current behavior).
- ☐ 3.2 Confirm render phase reads fresh movies_db; verify outputs unchanged vs `all`.
- ☐ 3.3 **Decision:** re-run resolution in render phase (simple, +1.7s) vs serialize
  intermediates (faster, fragile). Default: re-run. (see Decisions)
</details>

---

## Phase 4 — Build orchestrator (acyclic DAG, incremental)  ☑ DONE 2026-06-05

Wrote `Makefile` (GNU make) encoding the full DAG; `make` rebuilds only what changed,
in acyclic order, and a second `make all` is a no-op (verified — no rebuild loops).
`build.sh` now `exec make "$@"`. Pinned `export PYTHONHASHSEED := 0` for reproducible
output. Targets: `entity_registry.json`, `data/movies_db.json` (build→enrich_funds→
enrich_crew), `connections_report.html`/`network_graph.json`, `data/derived_conflicts.json`,
`conflict_graph.json` (+precompute_layout), `films.html`; plus `serve`/`clean`/`validate`/
`help`. **Bug fixed downstream:** richer movies_db produced `fund_recipient` edges to fund
nodes that weren't materialized → Cytoscape "nonexistent target" crash; `build_conflict_graph.py`
now materializes the fund node on first reference (0 dangling edges).

## Phase 5 — Inter-stage schema validation (fail fast)  ☑ DONE 2026-06-05

Wrote `scripts/validate_stage.py` (jsonschema) with permissive schemas for
mentions / registry / movies_db; wired into Makefile recipes (registry + movies_db gate
the build; `make validate` runs all three incl. mentions). **Immediately caught a real
pre-existing data bug:** two JSON records concatenated on one line in
`out/festival_data/mentions.jsonl:233` — split + re-validated clean.

## Phase 2.3 — QA  ☑ DONE 2026-06-05

qa-reviewer run on the rebuilt report. Found + fixed **T26/T53 regression**: cross-source
duplicate film entries (same film under `edb:…` vs `cinemaofisrael:…` ids) — `person_films`
now collapses by normalized title (231 dup cards → 0, one benign season-collision left).
Added T53 to QA_TESTS.md. Open data-coverage notes (not bugs): ~89 people with film
careers absent from movies_db crew (e.g. שמוליק דובדבני); 664 unlinked film chips
(makor/edb_persons films have no per-film URL) — tracked, acceptable.

---

<details><summary>original Phase 4 detail</summary>

`build.sh` today skips `build_movies_db.py` + enrich entirely, so movies_db goes stale.

**Deliverable:** a `Makefile` encoding the full DAG with file prerequisites, so
`make` rebuilds only what changed in correct order. `build.sh` becomes `exec make`.

DAG (targets → prerequisites):
```
entity_registry.json   : out/*/mentions.jsonl                      (resolve --phase resolve)
movies_db.json         : raw_films(edb,ci,jfc) entity_registry.json (build_movies_db → enrich → enrich_crew)
connections_report.html: entity_registry.json movies_db.json out/*  (resolve --phase render)
network_graph.json     : entity_registry.json movies_db.json        (resolve --phase render)
conflict_graph.json    : network_graph.json movies_db.json faculty derived_conflicts (build_conflict_graph)
films.html             : movies_db.json                             (build_films_html)
graph.html             : conflict_graph.json                        (precompute_layout)
```

- ☐ 4.1 Write `Makefile` with the above; `make`, `make clean`, `make serve`.
- ☐ 4.2 Update `build.sh` → `exec make "$@"`.
- ☐ 4.3 Update `PIPELINE.md` rebuild section to reference `make` + new acyclic order.

---

### (original Phase 5 sub-steps)

- 5.1 mentions schema · 5.2 registry schema · 5.3 movies_db schema · 5.4 wire into make
  · 5.5 jsonschema dependency. (Done — note: schemas are inline dicts in
  `validate_stage.py` rather than separate `schemas/*.json`, simpler for 3 schemas.)

</details>

---

## Phase 6 — films.html QA + foreign-film cleanup  ☑ DONE 2026-06-05

User QA of films.html surfaced 5 issues, all traced to Phase 1's edb_persons enrichment
under D1 "add everything". Fixes:
1. **Dup films** (curly vs straight apostrophe, e.g. "The Ambassador's Wife") — folded
   curly quotes ‘’“” + stripped `[..]`/`(ש.ל.ר)` in `normalize_film_title`
   (resolve_entities) and `_norm_title` (build_films_html). 3→2 (remaining is a genuine
   cross-language Hebrew/English pair, no shared year/id — not auto-mergeable).
2. **Missing year** — backfilled 82 from edb_persons by title; 635 remain (genuine source
   gaps: makor/fund pages omit year). films.html renders blank year cleanly.
3. **Test entry** (filmfund `movieId=505`, title "TEST") — dropped by cleanup pass.
4. **Foreign films** (Fast & Furious etc.) — **D1 REVISED → "drop actor-only edb_persons":**
   dropped 2,934 films that are edb_persons-only with no crew role (Israeli actors'
   Hollywood credits). Also stripped EDB "(ש.ל.ר)" title markers.
5. **edb_persons source** — explained: EDB person-page filmographies folded in by
   `enrich_movies_db_crew.py`. Now 3,075 edb_persons-only films remain (all have real crew).

movies_db 10,610 → **7,676 films**; all validators pass, 0 dangling edges, T53 holds.
**Note:** `(ש.ל.ר)` exact expansion unconfirmed — treated as an EDB title artifact.

---

## Decisions — CONFIRMED 2026-06-04

| # | Decision | Choice |
|---|----------|--------|
| D1 | Phase 1.3 — films missing from movies_db | **Add everything** — add all films from all sources (incl. ~23k thin CI records), not just existing/EDB. |
| D2 | Phase 3.3 — render phase resolution | **Re-run resolution in-memory** (deterministic, +1.7s, no fragile format). |
| D3 | Phase 4 — orchestrator | **Makefile** (free DAG + incremental rebuild). |
| D4 | Phase 5 — validation library | **jsonschema** + JSON Schema files in `schemas/`. |

**D1 implication to watch:** movies_db.json will grow from 8,771 to ~26k films. Downstream
stages that read it (films.html, build_conflict_graph, network_graph) must stay performant
and not surface thin/junk records as conflicts. Verify films.html search + graph build after
Phase 1; add a `min crew/credits` or `is_israeli` gate at the *report/graph* layer if junk
films appear, rather than dropping them from the DB.

---

## Risk / rollback

- Phase 1 rewrites `data/movies_db.json` (source of truth). Mitigation: enricher is
  idempotent and writes a `.bak` first; A/B + spot-check gate before accepting.
- Baseline `resolve_entities.py` stays untouched until Phase 2.4.
- Each phase has an explicit verify step; nothing deploys without passing it.
