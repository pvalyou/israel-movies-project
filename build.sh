#!/bin/bash
# Rebuild the pipeline. Thin wrapper around the Makefile (the real DAG lives there).
# `./build.sh` builds everything; `./build.sh clean`, `./build.sh serve`, etc. also work.
#
# The Makefile encodes the full acyclic dependency graph and rebuilds only what
# changed, in correct order (resolve --phase resolve → build_movies_db + enrich →
# resolve --phase render → conflict graph → films.html). The old hand-ordered steps
# that skipped build_movies_db.py are gone.
set -e
cd "$(dirname "$0")"
exec make "$@"
