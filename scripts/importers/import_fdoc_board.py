#!/usr/bin/env python3
"""
import_fdoc_board.py — Import Forum for Documentary (fdoc) board of directors
into out/fdoc/mentions.jsonl as a canonical manual entry.

These board members already appear in the fdoc source via scraped film pages,
but this import adds the official board page as canonical institutional evidence.

Run: python3 import_fdoc_board.py [--dry-run]

Source: https://www.fdoc.org.il/הנהלה/  (accessed 2026-05-26, term 2024-2026)
"""

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

OUT_JSONL   = Path("out/fdoc/mentions.jsonl")
SOURCE_NAME = "fdoc"
TODAY = date.today().isoformat()

MANUAL_URL   = "manual://fdoc/board-2024-2026/"
CANONICAL_URL = "https://www.fdoc.org.il/%D7%94%D7%A0%D7%94%D7%9C%D7%94/"

# Board of Directors 2024-2026 (from fdoc.org.il/הנהלה/, accessed 2026-05-26)
BOARD = [
    ("רוני אבולעפיה",  "chairperson"),   # Forum Chair
    ("ציפי ביידר",     "board_member"),  # Vice Chair
    ("אבי דבאח",       "board_member"),
    ("דנה הכהן",       "board_member"),
    ("צבי לנצמן",      "board_member"),
    ("אסף לפיד",       "board_member"),
    ("אודי ניר",        "board_member"),
    ("קרין קיינר",     "board_member"),
    ("נטע שושני",      "board_member"),
    ("עידית אברהמי",   "board_member"),
]


def main():
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print(f"=== פורום הדוקומנטרי — הנהלה 2024-2026 ({MANUAL_URL}) ===")
        for name, role in BOARD:
            print(f"  {name:20s}  {role}")
        print(f"\n(dry run — nothing written)")
        return

    people, roles = {}, []
    for idx, (name_he, role) in enumerate(BOARD, 1):
        pid = f"person_{idx:03d}"
        people[pid] = {
            "name_he":       name_he,
            "name_en":       None,
            "aliases":       [],
            "primary_roles": [role],
            "sources":       [MANUAL_URL],
        }
        roles.append({
            "id":              f"role_{idx:03d}",
            "person_id":       pid,
            "organization_id": "org_001",
            "role_type":       role,
            "start_year":      2024,
            "end_year":        2026,
            "notes":           "",
            "sources":         [MANUAL_URL],
        })

    chash = hashlib.md5(MANUAL_URL.encode()).hexdigest()
    entry = {
        "file":           "fdoc__board-2024-2026__manual.md",
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
                "extraction_date":  TODAY,
                "language":         "he",
                "canonical_source": CANONICAL_URL,
            },
            "entities": {
                "people": people,
                "organizations": {
                    "org_001": {
                        "name_he": "הפורום הדוקומנטרי",
                        "name_en": "Forum for Documentary",
                        "type":    "professional_organization",
                        "subtype": "documentary_forum",
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

    existing = []
    if OUT_JSONL.exists():
        for line in OUT_JSONL.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                if rec.get("url", "") == MANUAL_URL:
                    continue
            except Exception:
                pass
            existing.append(line)

    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for line in existing:
            f.write(line + "\n")
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"Wrote 1 entry ({len(BOARD)} people) to {OUT_JSONL}")


if __name__ == "__main__":
    main()
