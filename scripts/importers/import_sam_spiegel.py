#!/usr/bin/env python3
"""
import_sam_spiegel.py — Parse Sam Spiegel Film School teaching-staff page
and write faculty to out/sam_spiegel/mentions.jsonl.

Names on the page are in Israeli academic convention: Family Given (reversed).
This script reverses them to standard Given Family order.

Source: https://www.jsfs.co.il/teaching-staff  (scraped → sources/sam_spiegel/pages/)
Output: out/sam_spiegel/mentions.jsonl

Run: python3 scripts/importers/import_sam_spiegel.py [--dry-run]
"""

import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

PAGES_GLOB  = "sources/sam_spiegel/pages/*.md"
OUT_JSONL   = Path("out/sam_spiegel/mentions.jsonl")
SOURCE_NAME = "sam_spiegel"
CANONICAL   = "https://www.jsfs.co.il/teaching-staff"
MANUAL_URL  = "manual://sam_spiegel/teaching-staff"
TODAY       = date.today().isoformat()

# Strip academic titles before reversing
_TITLE_RE = re.compile(r"""^(ד["״]ר|פרופ['׳]|פרופסור|ד['׳]['׳]ר)\s+""", re.UNICODE)

# Lines that are not names (navigation, cookies, etc.)
_SKIP_RE = re.compile(
    r"^(top of page|bottom of page|קובצי עוגיות|מדיניות|הגדרות|דחה|קבל|סגירה"
    r"|Links|Internal|External|\*|\s*$)",
    re.UNICODE
)


def reverse_name(raw: str) -> str:
    """'Family Given' → 'Given Family' (Israeli academic directory convention)."""
    name = _TITLE_RE.sub("", raw).strip()
    parts = name.split()
    if len(parts) >= 2:
        # last token = given name, everything before = family name
        return " ".join([parts[-1]] + parts[:-1])
    return name


def extract_names_from_md(path: Path) -> list[str]:
    names = []
    for line in path.read_text(encoding="utf-8").splitlines():
        # Names appear as ## headings
        if not line.startswith("##"):
            continue
        raw = line.lstrip("#").strip()
        if _SKIP_RE.match(raw):
            continue
        if not raw:
            continue
        # Skip if it looks like a URL or non-name
        if raw.startswith("http") or len(raw) < 2:
            continue
        names.append(reverse_name(raw))
    return names


def build_entry(names: list[str], source_url: str) -> dict:
    people, roles = {}, []
    for idx, name_he in enumerate(names, 1):
        pid = f"person_{idx:03d}"
        people[pid] = {
            "name_he":       name_he,
            "name_en":       None,
            "aliases":       [],
            "primary_roles": ["faculty"],
            "sources":       [source_url],
            "institution":   "סם שפיגל",
        }
        roles.append({
            "id":              f"role_{idx:03d}",
            "person_id":       pid,
            "organization_id": "org_001",
            "role_type":       "faculty",
            "start_year":      None,
            "end_year":        None,
            "notes":           "סגל הוראה — בית הספר סם שפיגל",
            "sources":         [source_url],
        })

    chash = hashlib.md5(source_url.encode()).hexdigest()
    return {
        "file":           f"sam_spiegel__teaching-staff__manual.md",
        "url":            source_url,
        "source_name":    SOURCE_NAME,
        "status":         "ok",
        "content_hash":   chash,
        "content_length": 0,
        "filter_info":    {"reason": "manual_canonical_source"},
        "truncated":      False,
        "elapsed_sec":    0,
        "data": {
            "metadata": {
                "source_url":       source_url,
                "source_name":      SOURCE_NAME,
                "extraction_date":  TODAY,
                "language":         "he",
                "canonical_source": CANONICAL,
            },
            "entities": {
                "people": people,
                "organizations": {
                    "org_001": {
                        "name_he": "בית הספר סם שפיגל לקולנוע וטלוויזיה",
                        "name_en": "Sam Spiegel Film and Television School",
                        "type":    "school",
                        "sources": [source_url],
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
    import glob

    md_files = sorted(glob.glob(PAGES_GLOB))
    if not md_files:
        print(f"No pages found at {PAGES_GLOB}", file=sys.stderr)
        sys.exit(1)

    all_names = []
    for path in md_files:
        names = extract_names_from_md(Path(path))
        print(f"  {path}: {len(names)} names")
        all_names.extend(names)

    # Deduplicate while preserving order
    seen, unique = set(), []
    for n in all_names:
        if n not in seen:
            seen.add(n)
            unique.append(n)

    print(f"\nTotal unique faculty: {len(unique)}")
    for n in unique:
        print(f"  {n}")

    if dry_run:
        print("\n[dry-run] no files written")
        return

    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    entry = build_entry(unique, MANUAL_URL)
    with OUT_JSONL.open("w", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"\nWrote {len(unique)} faculty → {OUT_JSONL}")


if __name__ == "__main__":
    main()
