# Makefile — Israeli Film Conflict pipeline (acyclic build)
#
# Encodes the full dependency DAG so `make` rebuilds only what changed, in the
# correct order. Replaces the old build.sh, which skipped build_movies_db.py +
# the enrich steps (leaving movies_db.json stale).
#
# Acyclic order (breaks the old resolve<->movies_db cycle via --phase):
#   resolve --phase resolve  ->  entity_registry.json
#   build_movies_db + enrich_from_funds + enrich_crew  ->  movies_db.json
#   resolve --phase render   ->  connections_report.html + network_graph.json
#   compute_derived_conflicts -> derived_conflicts.json
#   build_conflict_graph + precompute_layout -> conflict_graph.json
#   build_films_html -> films.html
#
# Usage:
#   make            # build all three HTML deliverables (incremental)
#   make serve      # serve on http://localhost:8000
#   make clean      # remove generated outputs
#   make validate   # run schema checks on current stage files

PY := python3

# Reproducible output: pin hash seed so set-ordering (and thus rendered URL/role
# choices) is identical run-to-run. Without this the reports differ every run and
# make would always treat them as changed.
export PYTHONHASHSEED := 0

MENTIONS := $(wildcard out/*/mentions.jsonl)
RAW      := data/edb/raw_films.json data/cinemaofisrael/raw_films.json data/jfc/raw_films.json
FACULTY  := film_faculty_data/faculty_members.json
VALIDATE := $(PY) scripts/validate_stage.py

.PHONY: all serve clean help validate
.DEFAULT_GOAL := all

all: films.html conflict_graph.json connections_report.html ## Build all deliverables

## ── Stage 3a — resolve entities (no movies_db read) ──────────────────────────
entity_registry.json: $(MENTIONS) $(FACULTY)
	$(PY) resolve_entities.py --phase resolve
	$(VALIDATE) registry entity_registry.json
ambiguous_pairs.json: entity_registry.json ;

## ── Stage 4 — consolidate films (build -> enrich funds -> enrich crew) ───────
data/movies_db.json: $(RAW) data/edb/edb_persons.json $(MENTIONS) entity_registry.json
	$(PY) scripts/build_movies_db.py
	$(PY) scripts/funds/enrich_movies_db_from_funds.py
	$(PY) scripts/enrich_movies_db_crew.py
	$(VALIDATE) movies_db data/movies_db.json

## ── Stage 3b — render report + network graph from FRESH movies_db ────────────
connections_report.html: entity_registry.json data/movies_db.json $(MENTIONS)
	$(PY) resolve_entities.py --phase render
network_graph.json: connections_report.html ;

## ── Derived conflicts ────────────────────────────────────────────────────────
data/derived_conflicts.json: entity_registry.json network_graph.json
	$(PY) scripts/compute_derived_conflicts.py

## ── Stage 5 — conflict graph (+ baked layout) ────────────────────────────────
conflict_graph.json: network_graph.json data/movies_db.json $(FACULTY) data/derived_conflicts.json
	$(PY) scripts/build_conflict_graph.py
	node scripts/precompute_layout.js

## ── Films browser ────────────────────────────────────────────────────────────
films.html: data/movies_db.json
	$(PY) scripts/build_films_html.py

validate: ## Re-run schema checks on current stage files
	$(VALIDATE) mentions $(MENTIONS)
	$(VALIDATE) registry entity_registry.json
	$(VALIDATE) movies_db data/movies_db.json

serve: ## Serve the deliverables locally
	$(PY) -m http.server 8000

clean: ## Remove generated outputs (keeps movies_db.json + registry)
	rm -f connections_report.html network_graph.json conflict_graph.json films.html \
	      data/derived_conflicts.json

help: ## List targets
	@grep -E '^[a-zA-Z_./-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	 awk 'BEGIN{FS=":.*?## "}{printf "  %-26s %s\n", $$1, $$2}'
