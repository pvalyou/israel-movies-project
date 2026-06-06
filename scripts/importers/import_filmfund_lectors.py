#!/usr/bin/env python3
"""
import_filmfund_lectors.py — Import filmfund lectors from lecturers_israel.json
into out/filmfund/mentions.jsonl as a single canonical synthetic entry.

Run: python3 import_filmfund_lectors.py [--dry-run]
"""

import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

SOURCE_JSON = Path("sources/filmfund/lecturers_israel.json")
OUT_JSONL   = Path("out/filmfund/mentions.jsonl")
SOURCE_NAME = "filmfund"
ORG_NAME_HE = "הקרן הישראלית לקולנוע"
ORG_NAME_EN = "Israel Film Fund"
CANONICAL_URL = "https://www.filmfund.org.il/ContentPage?id=49"
MANUAL_URL    = "manual://filmfund/lectors-list-2026-05/all"
CANONICAL_BASE = "manual://filmfund/lectors-list-2026-05"


def parse_years(year_str: str) -> tuple[int, int]:
    """Parse '2018-2024' → (2018, 2024), '2019' → (2019, 2019)."""
    parts = re.findall(r'\d{4}', year_str)
    if len(parts) >= 2:
        return int(parts[0]), int(parts[-1])
    elif len(parts) == 1:
        return int(parts[0]), int(parts[0])
    return 2018, 2024


def main():
    dry_run = "--dry-run" in sys.argv
    today   = date.today().isoformat()

    data = json.loads(SOURCE_JSON.read_text(encoding="utf-8"))
    lectors = data["lecturers"]
    print(f"Loaded {len(lectors)} lectors from {SOURCE_JSON}")

    people = {}
    roles  = []
    for idx, rec in enumerate(lectors, 1):
        pid  = f"person_{idx:03d}"
        name_he = rec["hebrew_name"].strip()
        name_en = rec.get("english_name", "").strip() or None
        start_year, end_year = parse_years(rec.get("year", ""))
        details = rec.get("details", "").strip()

        people[pid] = {
            "name_he":      name_he,
            "name_en":      name_en,
            "aliases":      [],
            "primary_roles": ["lector"],
            "sources":      [MANUAL_URL],
        }
        roles.append({
            "id":              f"role_{idx:03d}",
            "person_id":       pid,
            "organization_id": "org_001",
            "role_type":       "lector",
            "start_year":      start_year,
            "end_year":        end_year,
            "notes":           details,
            "sources":         [MANUAL_URL],
        })

        if dry_run:
            yr = f"{start_year}" if start_year == end_year else f"{start_year}-{end_year}"
            print(f"  {name_he:20s}  ({yr})  {details[:60]}")

    if dry_run:
        print(f"\n(dry run — nothing written)")
        return

    chash = hashlib.md5(MANUAL_URL.encode()).hexdigest()
    entry = {
        "file":           "filmfund__lectors-2018-2024__manual.md",
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
                "source_url":       MANUAL_URL,
                "source_name":      SOURCE_NAME,
                "extraction_date":  today,
                "language":         "he",
                "canonical_source": "Israel Film Fund lectors list, scraped 05/2026",
            },
            "entities": {
                "people": people,
                "organizations": {
                    "org_001": {
                        "name_he": ORG_NAME_HE,
                        "name_en": ORG_NAME_EN,
                        "type":    "fund",
                        "subtype": "public_film_fund",
                        "sources": [MANUAL_URL],
                    }
                },
                "films":  {},
                "events": {},
            },
            "roles":         roles,
            "relationships": [],
            "films":         [],
        },
    }

    # Strip only the "all" and "tova-ascher" entries (regenerated here).
    # Supplemental entries (e.g. supplemental-2023) are historical and must be preserved.
    REGENERATED_SUFFIXES = {"/all", "/tova-ascher"}
    existing = []
    if OUT_JSONL.exists():
        for line in OUT_JSONL.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                u = rec.get("url", "")
                if u.startswith(CANONICAL_BASE) and any(
                    u == CANONICAL_BASE + s for s in REGENERATED_SUFFIXES
                ):
                    continue
            except Exception:
                pass
            existing.append(line)

    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for line in existing:
            f.write(line + "\n")
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"Wrote 1 synthetic entry ({len(lectors)} lectors) to {OUT_JSONL}")


if __name__ == "__main__":
    main()
