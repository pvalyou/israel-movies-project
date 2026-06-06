#!/usr/bin/env python3
"""
import_critics.py — Import Israeli film critics from film_faculty_data/israeli_film_people.csv
into out/critics/mentions.jsonl.

CSV columns: קטגוריה, שם, תפקיד, איפה (outlet), מקור (source URL)
Only imports rows where קטגוריה == 'עיתונאים ומבקרים'.

Gender is inferred from תפקיד: מבקרת/פודקאסטרית → f, מבקר/פודקאסטר → m.

Run: python3 scripts/importers/import_critics.py [--dry-run]
"""

import csv
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

SOURCE_CSV  = Path("film_faculty_data/israeli_film_people.csv")
OUT_JSONL   = Path("out/critics/mentions.jsonl")
SOURCE_NAME = "critics"
MANUAL_URL  = "manual://critics/israeli-film-critics-2026"
TODAY       = date.today().isoformat()


def infer_gender(role_he: str) -> str:
    """Infer gender from Hebrew role title."""
    feminine_markers = ["מבקרת", "פודקאסטרית", "עורכת", "כתבת", "מנחת", "בלוגרית"]
    if any(m in role_he for m in feminine_markers):
        return "f"
    masculine_markers = ["מבקר", "פודקאסטר", "עורך", "כתב", "מנחה", "בלוגר"]
    if any(m in role_he for m in masculine_markers):
        return "m"
    return "unknown"


def load_critics() -> list[dict]:
    critics = []
    with SOURCE_CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("קטגוריה", "").strip() != "עיתונאים ומבקרים":
                continue
            name    = row.get("שם", "").strip()
            role_he = row.get("תפקיד", "").strip()
            outlet  = row.get("איפה", "").strip()
            src_url = row.get("מקור", "").strip()
            if not name:
                continue
            critics.append({
                "name_he": name,
                "role_he": role_he,
                "outlet":  outlet,
                "src_url": src_url,
                "gender":  infer_gender(role_he),
            })
    return critics


def build_entry(critics: list[dict]) -> dict:
    people, roles = {}, []
    for idx, c in enumerate(critics, 1):
        pid = f"person_{idx:03d}"
        people[pid] = {
            "name_he":       c["name_he"],
            "name_en":       None,
            "aliases":       [],
            "primary_roles": ["critic"],
            "sources":       [MANUAL_URL],
            "gender":        c["gender"],
            "outlet":        c["outlet"],
        }
        roles.append({
            "id":              f"role_{idx:03d}",
            "person_id":       pid,
            "organization_id": None,
            "role_type":       "critic",
            "start_year":      None,
            "end_year":        None,
            "notes":           c["outlet"],
            "sources":         [MANUAL_URL],
        })

    chash = hashlib.md5(MANUAL_URL.encode()).hexdigest()
    return {
        "file":           "critics__israeli-film-critics__manual.md",
        "url":            MANUAL_URL,
        "source_name":    SOURCE_NAME,
        "status":         "ok",
        "content_hash":   chash,
        "content_length": 0,
        "filter_info":    {"reason": "manual_canonical_source"},
        "truncated":      False,
        "elapsed_sec":    0,
        "data": {
            "metadata": {
                "source_url":      MANUAL_URL,
                "source_name":     SOURCE_NAME,
                "extraction_date": TODAY,
                "language":        "he",
            },
            "entities": {
                "people":        people,
                "organizations": {},
                "films":         {},
                "events":        {},
            },
            "roles":         roles,
            "relationships": [],
            "films":         [],
        },
    }


def main():
    dry_run = "--dry-run" in sys.argv

    if not SOURCE_CSV.exists():
        print(f"ERROR: {SOURCE_CSV} not found", file=sys.stderr)
        sys.exit(1)

    critics = load_critics()
    print(f"Loaded {len(critics)} critics from {SOURCE_CSV}")

    gender_counts = {"m": 0, "f": 0, "unknown": 0}
    for c in critics:
        gender_counts[c["gender"]] += 1
        print(f"  {c['name_he']:20s} | {c['gender']} | {c['outlet']}")

    print(f"\nGender: m={gender_counts['m']} f={gender_counts['f']} unknown={gender_counts['unknown']}")

    if dry_run:
        print("\n[dry-run] no files written")
        return

    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    entry = build_entry(critics)
    with OUT_JSONL.open("w", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"\nWrote {len(critics)} critics → {OUT_JSONL}")


if __name__ == "__main__":
    main()
