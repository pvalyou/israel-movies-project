#!/usr/bin/env python3
"""
import_writers_guild_board.py — Import Israeli Screenwriters Guild board into
out/writers_guild/mentions.jsonl.

Source: Wikipedia / writersguild.org.il (accessed 2026-05-27)
Board composition confirmed via:
  - https://he.wikipedia.org/wiki/%D7%90%D7%99%D7%92%D7%95%D7%93_%D7%94%D7%AA%D7%A1%D7%A8%D7%99%D7%98%D7%90%D7%99%D7%9D
  - Individual author pages on writersguild.org.il

Run: python3 import_writers_guild_board.py [--dry-run]
"""

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

OUT_DIR     = Path("out/writers_guild")
OUT_JSONL   = OUT_DIR / "mentions.jsonl"
SOURCE_NAME = "writers_guild"
TODAY       = date.today().isoformat()

MANUAL_URL_BOARD = "manual://writers_guild/board-2025/"
MANUAL_URL_CEO   = "manual://writers_guild/ceo-2025/"
CANONICAL_URL    = "https://writersguild.org.il/"

# Board of Directors (ועד נבחר), as of 2025
# Source: Wikipedia + individual guild author pages
BOARD = [
    ("נדב בן סימון",  "chairperson"),   # יו"ר מאז 2021
    ("עדן גוריון",    "board_member"),
    ("ענבל ארבל",     "board_member"),
    ("תומר שריג",    "board_member"),
    ("מתן שירם",     "board_member"),
    ("חיים אידיסיס",  "board_member"),   # לשעבר יו"ר
    ("דניאל לפין",    "board_member"),   # לשעבר יו"ר
    ("יארון ארזי",   "board_member"),
    ("אלון נוימן",    "board_member"),
    ("ניר ברגר",     "board_member"),
]

# Executive staff
CEO = [
    ("ליאור תמם",    "ceo"),  # מנכ"לית (עו"ד)
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
            "start_year":      2025,
            "end_year":        2025,
            "notes":           "",
            "sources":         [manual_url],
        })

    chash = hashlib.md5(manual_url.encode()).hexdigest()
    return {
        "file":           f"writers_guild__{entry_label}__manual.md",
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
                        "name_he": "איגוד תסריטאי הקולנוע והטלוויזיה בישראל",
                        "name_en": "Israeli Screenwriters Guild",
                        "type":    "professional_organization",
                        "subtype": "screenwriters_guild",
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
        (BOARD, MANUAL_URL_BOARD, "board-2025"),
        (CEO,   MANUAL_URL_CEO,   "ceo-2025"),
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
