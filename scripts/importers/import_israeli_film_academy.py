#!/usr/bin/env python3
"""
import_israeli_film_academy.py — Import Israeli Film Academy (Ophir Prize) board and staff
into out/israeli_film_academy/mentions.jsonl.

Source: https://israelfilmacademy.co.il/?section=590  (accessed 2026-05-27)

Run: python3 import_israeli_film_academy.py [--dry-run]
"""

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

OUT_DIR    = Path("out/israeli_film_academy")
OUT_JSONL  = OUT_DIR / "mentions.jsonl"
SOURCE_NAME = "israeli_film_academy"
TODAY      = date.today().isoformat()

MANUAL_URL_BOARD = "manual://israeli_film_academy/board-2026/"
MANUAL_URL_CEO   = "manual://israeli_film_academy/ceo-2026/"
CANONICAL_URL    = "https://israelfilmacademy.co.il/?section=590"

# Board of Directors (הוועד המנהל), accessed 2026-05-27
BOARD = [
    ("אסף אמיר",        "chairperson"),   # יו"ר האקדמיה
    ("אלון לשם",        "board_member"),
    ("אלון נוימן",      "board_member"),
    ("אוריאל סיני",     "board_member"),
    ("אריאל גלזר",      "board_member"),
    ("חגית בן יעקב",    "board_member"),
    ("יונתן רוזנבאום",  "board_member"),
    ("יוסף חיימוב",     "board_member"),
    ("יריב מוזר",       "board_member"),   # filmmaker — already in conflict graph
    ("כתריאל שחורי",    "board_member"),
    ("קובי מזרחי",      "board_member"),   # filmmaker — already in conflict graph
    ("לירית מאש בטיש",  "board_member"),
    ("עדי נבון",        "board_member"),   # also Producers Guild board
    ("עילית זקצר",      "board_member"),
    ("עמית גיצלטר",     "board_member"),
    ("רון פוגל",        "board_member"),
    # Audit committee (ועדת ביקורת)
    ("איתי קפלינסקי",   "committee_member"),
    ("גליה מלוברוצקי",  "committee_member"),
    ("חלי גולדנברג",    "committee_member"),
]

# Executive staff
CEO = [
    ("אסתר ונדר",   "ceo"),  # מנכ"לית
]


def build_entry(people_list: list, manual_url: str, entry_label: str) -> dict:
    people, roles = {}, []
    for idx, (name_he, role) in enumerate(people_list, 1):
        pid = f"person_{idx:03d}"
        people[pid] = {
            "name_he":       name_he,
            "name_en":       None,
            "aliases":       [],
            "primary_roles": [role],
            "sources":       [manual_url],
        }
        roles.append({
            "id":              f"role_{idx:03d}",
            "person_id":       pid,
            "organization_id": "org_001",
            "role_type":       role,
            "start_year":      2026,
            "end_year":        2026,
            "notes":           "",
            "sources":         [manual_url],
        })

    chash = hashlib.md5(manual_url.encode()).hexdigest()
    return {
        "file":           f"israeli_film_academy__{entry_label}__manual.md",
        "url":            manual_url,
        "source_name":    SOURCE_NAME,
        "status":         "ok",
        "content_hash":   chash,
        "content_length": 0,
        "filter_info":    {"reason": "manual_canonical_source"},
        "truncated":      False,
        "elapsed_sec":    0,
        "data": {
            "metadata": {
                "source_url":       manual_url,
                "source_name":      SOURCE_NAME,
                "extraction_date":  TODAY,
                "language":         "he",
                "canonical_source": CANONICAL_URL,
            },
            "entities": {
                "people": people,
                "organizations": {
                    "org_001": {
                        "name_he": "האקדמיה הישראלית לקולנוע וטלוויזיה",
                        "name_en": "Israeli Film & Television Academy (Ophir Prize)",
                        "type":    "professional_organization",
                        "subtype": "film_academy",
                        "sources": [manual_url],
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


def main():
    dry_run = "--dry-run" in sys.argv

    entries_spec = [
        (BOARD, MANUAL_URL_BOARD, "board-2026"),
        (CEO,   MANUAL_URL_CEO,   "ceo-2026"),
    ]

    if dry_run:
        for people, url, label in entries_spec:
            print(f"\n=== {label} ({url}) ===")
            for name, role in people:
                print(f"  {name:25s}  {role}")
        print("\n(dry run — nothing written)")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_urls = {MANUAL_URL_BOARD, MANUAL_URL_CEO}

    existing = []
    if OUT_JSONL.exists():
        for line in OUT_JSONL.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                if rec.get("url", "") in all_urls:
                    continue
            except Exception:
                pass
            existing.append(line)

    built = [build_entry(*args) for args in entries_spec]
    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for line in existing:
            f.write(line + "\n")
        for entry in built:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    total = sum(len(p) for p, *_ in entries_spec)
    print(f"Wrote {len(built)} entries ({total} people) to {OUT_JSONL}")


if __name__ == "__main__":
    main()
