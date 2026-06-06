#!/usr/bin/env python3
"""
import_jerusalem_cinematheque.py — Import Jerusalem Cinematheque staff and board
into out/jerusalem_cinematheque/mentions.jsonl as synthetic manual entries.

Run: python3 import_jerusalem_cinematheque.py [--dry-run]

Sources:
  Staff: https://jer-cin.org.il/he/מאמר/4202  (accessed 2026-05-26)
  Board: https://jer-cin.org.il/he/מאמר/4204  (accessed 2026-05-26)
"""

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

OUT_DIR    = Path("out/jerusalem_cinematheque")
OUT_JSONL  = OUT_DIR / "mentions.jsonl"
SOURCE_NAME = "jerusalem_cinematheque"
TODAY = date.today().isoformat()

MANUAL_URL_STAFF = "manual://jerusalem_cinematheque/staff-2026/"
MANUAL_URL_BOARD = "manual://jerusalem_cinematheque/board-2026/"
CANONICAL_STAFF  = "https://jer-cin.org.il/he/%D7%9E%D7%90%D7%9E%D7%A8/4202"
CANONICAL_BOARD  = "https://jer-cin.org.il/he/%D7%9E%D7%90%D7%9E%D7%A8/4204"

# ---------------------------------------------------------------------------
# Data (accessed 2026-05-26)
# ---------------------------------------------------------------------------

# Staff: (name_he, role)
# Note: אור סיגולי is the JFF Artistic Director, listed on the jer-cin staff page.
# נבות ברנע is Monthly Programming Editor — selects films for the cinematheque.
STAFF = [
    ("רוני מהדב-לוין",   "ceo"),
    ("אור סיגולי",        "artistic_director"),   # JFF Artistic Director — already in JFF conflicts
    ("נבות ברנע",          "festival_programmer"), # Monthly programming editor (selects films)
    ("תמר פרימן",          "festival_programmer"), # Programming staff
    ("מאיר רוסו",          "staff"),               # Israeli Film Archive Director
    ("אילה בנימין",        "staff"),               # Education Department Head
    ("קרול דרייפוס",      "staff"),               # Chief Producer & Events
    ("עינת סנפירי",        "staff"),               # CEO Assistant
    ("דניאל כהן",          "staff"),               # Coordinator & External Relations
]

# Board: (name_he, role)
BOARD = [
    ("דניאל מימרן",         "chairperson"),   # Chairman of the Board
    ("שמעון אלון",          "board_member"),
    ("תמי בן-דוד",         "board_member"),
    ("עמרי בן-עמי",        "board_member"),
    ("מיכאל מנקין",        "board_member"),
    ("רות דיסקין",         "board_member"),   # also a film distributor
    ("רות חסין",           "board_member"),
    ("דפנה יגלום",         "board_member"),
    ("דורית ענבר",         "board_member"),
    ("חדוה פוגל",          "board_member"),
    ("פיליפה קוברסקי",     "board_member"),   # also a film distributor
    ("דניאלה בן-עטר",      "board_member"),
]


def build_entry(people_list: list, manual_url: str, canonical_url: str,
                entry_label: str) -> dict:
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
        "file":           f"jerusalem_cinematheque__{entry_label}__manual.md",
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
                "canonical_source": canonical_url,
            },
            "entities": {
                "people": people,
                "organizations": {
                    "org_001": {
                        "name_he": "סינמטק ירושלים",
                        "name_en": "Jerusalem Cinematheque",
                        "type":    "cultural_institution",
                        "subtype": "cinematheque",
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

    entries = [
        (STAFF, MANUAL_URL_STAFF, CANONICAL_STAFF, "staff-2026"),
        (BOARD, MANUAL_URL_BOARD, CANONICAL_BOARD, "board-2026"),
    ]

    if dry_run:
        for people_list, url, _, label in entries:
            print(f"\n=== {label} ({url}) ===")
            for name, role in people_list:
                print(f"  {name:25s}  {role}")
        print(f"\n(dry run — nothing written)")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    URLS = {MANUAL_URL_STAFF, MANUAL_URL_BOARD}

    existing = []
    if OUT_JSONL.exists():
        for line in OUT_JSONL.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                if rec.get("url", "") in URLS:
                    continue
            except Exception:
                pass
            existing.append(line)

    built = [build_entry(*args) for args in entries]
    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for line in existing:
            f.write(line + "\n")
        for entry in built:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    total = sum(len(p) for p, *_ in entries)
    print(f"Wrote {len(built)} entries ({total} people) to {OUT_JSONL}")


if __name__ == "__main__":
    main()
