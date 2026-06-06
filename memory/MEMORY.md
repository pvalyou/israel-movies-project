# Memory Index

- [Project Purpose & Scope](project_purpose.md) — Network graph of Israeli film industry (D3/Sigma); PDF report is secondary; collect all data first, find conflicts by graph proximity
- [Project Learnings — Scraping & NER Pipeline](project_learnings.md) — Hebrew NER pitfalls, DictaBERT/heBERT setup, org extraction, context snippets, tokenizer prefix drop fix
- [Extraction Pipeline Status](pipeline_extraction_status.md) — Per-source extraction counts; writers_guild done; 243 role conflicts; T05/T06 QA fixes applied 2026-05-27
- [resolve_entities.py — UI/UX patterns and known fixes](resolve_entities_ui.md) — Resume-style cards, role label fixes (במאי/מפיק), chip tooltips, film dedup, T24-T26 tests (updated 2026-05-29)
- [EDB Scrape — plan and status](project_edb_scrape.md) — Other agent executing Phase 1; edb.co.il structure confirmed; resolve_entities.py needs build_network_graph() changes for film+co_credited
- [File organization — scripts/ and docs/ layout](project_file_organization.md) — scripts split into scrapers/importers/enrichers; docs/ for MDs; run scripts from project root
- [filmmaker role is ambiguous in film-page fallback](feedback_filmmaker_role.md) — LLM uses "filmmaker" to mean "appears in documentary", not authorship — exclude from FALLBACK_CREW_ROLES
- [QA workflow — run agent after every report, add tests for new bugs](feedback_qa_workflow.md) — qa-reviewer agent runs after every resolve_entities.py; new bugs → new QA_TESTS.md entry immediately
- [Film Council OSINT — 2024 membership, conflicts, missing גיורא איני](project_film_council_osint.md) — 21-member council confirmed from Wayback; עמיחי חסון conflict flagged; ענבל שוקי tier-2 conflict; Gesher CEOs added
- [Search-page film contamination fix](feedback_search_page_film_contamination.md) — `?keywords=` archive pages leaked false films into conflicts; fixed by `if is_search_page: continue` in extract_film_conflicts(); T24 QA test added
- [TODO workflow — check and update TODO.md for every task](feedback_todo_workflow.md) — Read TODO.md before starting, add entry if missing, mark done at end
- [graph.html — Cytoscape+fcose viz, conflict_graph.json pipeline](project_graph_viz.md) — 1,058 nodes, 2,710 edges; showcase concentric layout; lector_filmmaker edges enabled per-showcase; no "ממצאים מרכזיים" panel (updated 2026-05-31)
- [PIPELINE.md reference](reference_pipeline_md.md) — Project root has PIPELINE.md: 5-stage flow ending in 3 HTML deliverables (graph.html, films.html, connections_report.html)
- [Derived Conflicts Pipeline](project_derived_conflicts.md) — 7 new conflict patterns (critic+committee, family, collab, multi-fund, faculty, festival, exec filmmaker); new graph edges + report section; docs/conflict_patterns.md has 8 future patterns
- [Research Agent Findings — Rounds 1-12](project_research_agent.md) — 83+ conflicts found; "גבעה 24" 4-way case; 5 verified family pairs; קטריאל שורי CEO-wife scandal; lector_filmmaker type added (272 people); round 13 targets: ענבל שוקי sources, Academy board
- [Graph showcase UX patterns](feedback_graph_showcase_ux.md) — enableEdgeTypes per showcase; concentric layout with position save/restore; no edge labels on hl/shared-edge; lector_filmmaker in openDetail ORDER
- [EDB-only film funding gaps](project_film_funding_gaps.md) — 205 films have no fund data; plan at data/plan_find_film_funding.md; merge into movies_db.json after research
- [movies_db.json is the source of truth for all reports](feedback_movies_db_source_of_truth.md) — Film data must come from movies_db.json; do not add films by patching resolve_entities or mentions.jsonl directly
