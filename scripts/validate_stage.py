#!/usr/bin/env python3
"""
validate_stage.py — fail-fast schema checks at pipeline stage boundaries.

A malformed record otherwise surfaces as a weird card or missing film several
stages downstream; this catches it where it's produced. Wired into the Makefile
so a bad stage halts the build (non-zero exit).

Usage:
    python3 scripts/validate_stage.py <kind> <file> [<file> ...]
    kinds: mentions | registry | movies_db

Schemas are intentionally permissive (additionalProperties allowed) — they assert
the *shape downstream code relies on*, not the full record. Requires `jsonschema`.
"""
import json, sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:
    sys.exit("validate_stage.py needs jsonschema — run: pip install jsonschema")

# ── Schemas ────────────────────────────────────────────────────────────────────

PERSON = {"type": "object"}  # people maps are id -> object; values vary by source

MENTION_RECORD = {
    "type": "object",
    "properties": {
        "status": {"type": "string"},
        "url": {"type": ["string", "null"]},
        "data": {
            "type": ["object", "null"],
            "properties": {
                "entities": {
                    "type": ["object", "null"],
                    "properties": {
                        "people": {"type": ["object", "null"]},
                        "films":  {"type": ["object", "null"]},
                    },
                },
                "relationships": {"type": ["array", "null"]},
            },
        },
    },
}

REGISTRY = {
    "type": "object",
    "required": ["people", "organizations"],
    "properties": {
        "people":        {"type": "object"},
        "organizations": {"type": "object"},
        "film_conflicts": {"type": "array"},
    },
}

CREW_ROW = {
    "type": "object",
    "required": ["name_he"],
    "properties": {
        "name_he":     {"type": "string", "minLength": 1},
        "role":        {"type": ["string", "null"]},
        "role_he":     {"type": ["string", "null"]},
        "registry_id": {"type": ["string", "null"]},
    },
}
MOVIE = {
    "type": "object",
    "required": ["title_he"],
    "properties": {
        "film_id":  {"type": ["string", "null"]},
        "title_he": {"type": "string"},
        "year":     {"type": ["integer", "null"]},
        "funds":    {"type": "array", "items": {"type": "string"}},
        "crew":     {"type": "array", "items": CREW_ROW},
        "cast":     {"type": "array"},
    },
}

MAX_REPORT = 8  # how many distinct errors to print before truncating

def _check(validator, instance, label, errors):
    for err in validator.iter_errors(instance):
        loc = "/".join(str(p) for p in err.absolute_path)
        errors.append(f"  {label}{(' @ ' + loc) if loc else ''}: {err.message}")

def validate_mentions(paths):
    v = Draft202012Validator(MENTION_RECORD)
    errors, bad_lines, total = [], 0, 0
    for p in paths:
        for i, line in enumerate(Path(p).read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                rec = json.loads(line)
            except Exception as e:
                bad_lines += 1
                if len(errors) < MAX_REPORT:
                    errors.append(f"  {p}:{i}: invalid JSON ({e})")
                continue
            before = len(errors)
            if len(errors) < MAX_REPORT:
                _check(v, rec, f"{p}:{i}", errors)
            if len(errors) > before:
                bad_lines += 1
    return errors, f"{total} records, {bad_lines} invalid"

def validate_registry(paths):
    v = Draft202012Validator(REGISTRY)
    errors = []
    for p in paths:
        _check(v, json.loads(Path(p).read_text(encoding="utf-8")), p, errors)
    return errors, f"{len(paths)} file(s)"

def validate_movies_db(paths):
    v = Draft202012Validator(MOVIE)
    errors, bad, total = [], 0, 0
    for p in paths:
        db = json.loads(Path(p).read_text(encoding="utf-8"))
        if not isinstance(db, list):
            return [f"  {p}: top-level must be a list"], "0"
        for idx, film in enumerate(db):
            total += 1
            before = len(errors)
            if len(errors) < MAX_REPORT:
                _check(v, film, f"film[{idx}] ({film.get('title_he','?')})", errors)
            if len(errors) > before:
                bad += 1
    return errors, f"{total} films, {bad} invalid"

KINDS = {"mentions": validate_mentions, "registry": validate_registry,
         "movies_db": validate_movies_db}

def main():
    if len(sys.argv) < 3 or sys.argv[1] not in KINDS:
        sys.exit(f"usage: validate_stage.py {{{'|'.join(KINDS)}}} <file>...")
    kind, paths = sys.argv[1], sys.argv[2:]
    errors, summary = KINDS[kind](paths)
    if errors:
        print(f"✗ {kind} validation FAILED ({summary}):", file=sys.stderr)
        for e in errors[:MAX_REPORT]:
            print(e, file=sys.stderr)
        if len(errors) > MAX_REPORT:
            print(f"  … and more", file=sys.stderr)
        sys.exit(1)
    print(f"✓ {kind} OK ({summary})")

if __name__ == "__main__":
    main()
