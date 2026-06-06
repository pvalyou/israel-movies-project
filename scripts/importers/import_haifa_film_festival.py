#!/usr/bin/env python3
"""
import_haifa_film_festival.py — Import Haifa Film Festival staff/board (manual)
and jurors (parsed from the scraped שופטים page) into
out/haifa_film_festival/mentions.jsonl.

Run: python3 import_haifa_film_festival.py [--dry-run]

Sources:
- Staff/board: https://www.haifaff.co.il/צוות_הפסטיבל (manual, 2026-05-26)
- Jurors:      sources/haifa_film_festival/pages/*שופטים*.md (scraped)
"""

import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

OUT_DIR    = Path("out/haifa_film_festival")
OUT_JSONL  = OUT_DIR / "mentions.jsonl"
SOURCE_NAME = "haifa_film_festival"
TODAY = date.today().isoformat()

MANUAL_URL_STAFF = "manual://haifa_film_festival/staff-2026/"
CANONICAL_URL    = "https://www.haifaff.co.il/%D7%A6%D7%95%D7%95%D7%AA_%D7%94%D7%A4%D7%A1%D7%98%D7%99%D7%91%D7%9C"

JURORS_URL       = "https://www.haifaff.co.il/%D7%A9%D7%95%D7%A4%D7%98%D7%99%D7%9D"
JURORS_PAGES_DIR = Path("sources/haifa_film_festival/pages")
JURORS_YEAR      = 2026  # festival dates on page are 26.09.26 → 03.10.26

# ---------------------------------------------------------------------------
# Data  (from haifaff.co.il/צוות_הפסטיבל, 2026-05-26)
# ---------------------------------------------------------------------------

STAFF = [
    # (name_he, role)
    # Management
    ("ירון שמיר",           "festival_director"),   # Artistic Director + Cinematheque Manager
    ("יגאל זאבי",           "ceo"),                 # CEO of Ethos (operating company)
    ("נוגית אלטשולר",      "artistic_director"),   # Artistic Director of Haifa Cinematheque
    ("שרון לוגסי",          "staff"),               # Deputy Director of Operations
    ("אירנה ויסבך",         "staff"),               # Deputy Director of Finance
    # Board
    ("יוסי שלום",           "chairperson"),         # Board Chairman
    ("יוסי הניג",           "board_member",),
    ("קיריל קארטניק",      "board_member"),
    ("יעקב בורובסקי",      "board_member"),
    ("רג'א זעטרא",         "board_member"),
    ("דוד לוריא",           "board_member"),
    ("צילה ברוך",           "board_member"),
    ("עבד עודה",             "board_member"),
    ("טלי גולדשטיין אורגיל", "board_member"),
    ("צחי טרנו",            "board_member"),
    ("רים בלאן",            "board_member"),
    ("ערן מיכאל",           "board_member"),
    ("אלי לוטן",            "board_member"),
    # Repertoire Committee (select Israeli competition films)
    ("דנה מורג",            "festival_programmer"),
    ("עינת רודמן",          "festival_programmer"),
    ("יערה עוזרי",          "festival_programmer"),
    ("ניר נאמן",            "festival_programmer"),
    ("גולה ארדסטני",        "festival_programmer"),
]


def build_entry() -> dict:
    people, roles = {}, []
    for idx, row in enumerate(STAFF, 1):
        name_he, role = row[0], row[1]
        pid = f"person_{idx:03d}"
        people[pid] = {
            "name_he":       name_he,
            "name_en":       None,
            "aliases":       [],
            "primary_roles": [role],
            "sources":       [MANUAL_URL_STAFF],
        }
        roles.append({
            "id":              f"role_{idx:03d}",
            "person_id":       pid,
            "organization_id": "org_001",
            "role_type":       role,
            "start_year":      2026,
            "end_year":        2026,
            "notes":           "",
            "sources":         [MANUAL_URL_STAFF],
        })

    chash = hashlib.md5(MANUAL_URL_STAFF.encode()).hexdigest()
    return {
        "file":           "haifa_film_festival__staff-2026__manual.md",
        "url":            MANUAL_URL_STAFF,
        "source_name":    SOURCE_NAME,
        "status":         "ok",
        "content_hash":   chash,
        "content_length": 0,
        "filter_info":    {"reason": "manual_canonical_source"},
        "truncated":      False,
        "elapsed_sec":    0,
        "data": {
            "metadata": {
                "source_url":       MANUAL_URL_STAFF,
                "source_name":      SOURCE_NAME,
                "extraction_date":  TODAY,
                "language":         "he",
                "canonical_source": CANONICAL_URL,
            },
            "entities": {
                "people": people,
                "organizations": {
                    "org_001": {
                        "name_he": "פסטיבל הקולנוע הבינלאומי חיפה",
                        "name_en": "Haifa International Film Festival",
                        "type":    "festival",
                        "subtype": "film_festival",
                        "sources": [MANUAL_URL_STAFF],
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


# ---------------------------------------------------------------------------
# Jurors parser — reads sources/haifa_film_festival/pages/*שופטים*.md
# ---------------------------------------------------------------------------

# Category line on the שופטים page: bold text containing " - חבר השופטים".
# Person line: bold text with a person's name (no " - " separator).
CATEGORY_MARKER = "חבר השופטים"


def _normalize_category(raw: str) -> str:
    """Strip the trailing '- חבר השופטים' and surrounding whitespace."""
    text = raw.strip().rstrip("*").lstrip("*").strip()
    # Collapse internal whitespace (some headers span multiple lines).
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*-\s*" + CATEGORY_MARKER + r"\s*$", "", text).strip()
    return text


def _find_jurors_page() -> Path | None:
    if not JURORS_PAGES_DIR.exists():
        return None
    # The שופטים page slug starts with "D7_A9_D7_95_D7_A4_D7_98_D7_99_D7_9D"
    # (URL-encoded שופטים). Match by slug fragment.
    candidates = list(JURORS_PAGES_DIR.glob("*D7_A9_D7_95_D7_A4_D7_98_D7_99_D7_9D*.md"))
    if not candidates:
        return None
    # Pick the most recently fetched if multiple.
    return max(candidates, key=lambda p: p.stat().st_mtime)


def parse_jurors(md_text: str) -> list[tuple[str, str]]:
    """Return [(name_he, category_he), ...] from the שופטים markdown.

    Person names and category headers are full-line bold (`**X**` alone on a
    line). Bold runs that share a line with other text (e.g. film titles
    inside a biography paragraph) are ignored.
    """
    # Block-level bold: `**...**` that starts at the beginning of a line and
    # ends at end-of-line, possibly spanning multiple lines internally. This
    # captures full-line names AND multi-line category headers like
    #     **
    #     קולנוע ישראלי - חבר השופטים**
    # while skipping inline bold inside biography paragraphs.
    # The captured group disallows internal `**` so we don't accidentally
    # bridge across a biography paragraph (which contains inline bold like
    # `**film title**` mid-line) to the next standalone bold block.
    block_bold = re.compile(
        r"(?:^|\n)[ \t]*\*\*[ \t]*((?:(?!\*\*).)+?)[ \t]*\*\*[ \t]*(?=\n|$)",
        flags=re.DOTALL,
    )

    jurors: list[tuple[str, str]] = []
    current_category: str | None = None

    for m in block_bold.finditer(md_text):
        raw = m.group(1)
        text = re.sub(r"\s+", " ", raw).strip()
        if not text:
            continue
        if CATEGORY_MARKER in text:
            current_category = _normalize_category(raw)
            continue
        # Skip stray section labels that lack the category marker.
        if " - " in text:
            continue
        jurors.append((text, current_category or "חבר שופטים"))

    return jurors


def build_jurors_entry(jurors: list[tuple[str, str]]) -> dict:
    people, roles = {}, []
    for idx, (name_he, category) in enumerate(jurors, 1):
        pid = f"person_{idx:03d}"
        notes = f"חבר/ת שופטים – {category} – פסטיבל חיפה {JURORS_YEAR}" if category else ""
        people[pid] = {
            "name_he":         name_he,
            "name_en":         None,
            "aliases":         [],
            "primary_roles":   ["jury_member"],
            "context_sentence": notes,
            "sources":         [JURORS_URL],
        }
        roles.append({
            "id":              f"role_{idx:03d}_jury_member",
            "person_id":       pid,
            "organization_id": "org_001",
            "role_type":       "jury_member",
            "start_year":      JURORS_YEAR,
            "end_year":        JURORS_YEAR,
            "notes":           notes,
            "sources":         [JURORS_URL],
        })

    return {
        "file":           "haifa_film_festival__shoftim__scraped.md",
        "url":            JURORS_URL,
        "source_name":    SOURCE_NAME,
        "status":         "ok",
        "content_hash":   "scraped",
        "content_length": 0,
        "filter_info":    {"reason": "scraped_jurors_page"},
        "truncated":      False,
        "elapsed_sec":    0,
        "data": {
            "metadata": {
                "source_url":       JURORS_URL,
                "source_name":      SOURCE_NAME,
                "extraction_date":  TODAY,
                "language":         "he",
                "canonical_source": JURORS_URL,
            },
            "entities": {
                "people": people,
                "organizations": {
                    "org_001": {
                        "name_he": "פסטיבל הקולנוע הבינלאומי חיפה",
                        "name_en": "Haifa International Film Festival",
                        "type":    "festival",
                        "subtype": "film_festival",
                        "sources": [JURORS_URL],
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

    # Parse jurors from the scraped page (if available)
    jurors: list[tuple[str, str]] = []
    page = _find_jurors_page()
    if page is not None:
        jurors = parse_jurors(page.read_text(encoding="utf-8"))
    else:
        print(f"WARNING: no שופטים page found under {JURORS_PAGES_DIR}", file=sys.stderr)

    if dry_run:
        print(f"=== פסטיבל הקולנוע הבינלאומי חיפה ({MANUAL_URL_STAFF}) ===")
        for row in STAFF:
            print(f"  {row[0]:25s}  {row[1]}")
        print(f"\n=== שופטים ({JURORS_URL}) ===")
        for name, cat in jurors:
            print(f"  {name:25s}  [{cat}]")
        print(f"\n(dry run — nothing written)")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    staff_entry  = build_entry()
    jurors_entry = build_jurors_entry(jurors) if jurors else None

    replace_urls = {MANUAL_URL_STAFF, JURORS_URL}
    existing = []
    if OUT_JSONL.exists():
        for line in OUT_JSONL.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                if rec.get("url", "") in replace_urls:
                    continue
            except Exception:
                pass
            existing.append(line)

    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for line in existing:
            f.write(line + "\n")
        f.write(json.dumps(staff_entry, ensure_ascii=False) + "\n")
        if jurors_entry:
            f.write(json.dumps(jurors_entry, ensure_ascii=False) + "\n")

    n = 1 + (1 if jurors_entry else 0)
    print(f"Wrote {n} entries ({len(STAFF)} staff, {len(jurors)} jurors) to {OUT_JSONL}")


if __name__ == "__main__":
    main()
