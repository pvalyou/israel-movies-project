#!/usr/bin/env python3
"""
import_gesher_lectors.py — Parse the Gesher lectors page and write synthetic
mentions.jsonl entries (one per round/event) to out/gesher/mentions.jsonl.

This handles the page gesher__Page-45__2e34bce2.md which the LLM returned 0
people for (content too long + format not recognized), and covers all years
2015-2025 including those truncated off in LLM extraction.

Run: python3 import_gesher_lectors.py [--dry-run]
"""

import json
import re
import sys
import hashlib
from datetime import date
from pathlib import Path

SOURCE_PAGE_URL = "https://gesherfilmfund.org.il/Page/45/"
SOURCE_NAME = "gesher"
ORG_NAME_HE = "קרן גשר"
ORG_NAME_EN = "Gesher Multicultural Film Fund"
LECTORS_PAGE_MD = Path("sources/gesher/pages/gesher__Page-45__2e34bce2.md")
OUT_JSONL = Path("out/gesher/mentions.jsonl")
CANONICAL_BASE = "manual://gesher/lectors-list-2026-05"


def make_synthetic_url(year: int, slug: str) -> str:
    return f"{CANONICAL_BASE}/year-{year}/round-{slug}"


def slugify(s: str) -> str:
    s = s.strip()
    s = re.sub(r'\s+', '-', s)
    s = re.sub(r'[^\w֐-׿-]', '', s)
    return s[:60]


def parse_lectors_page(text: str) -> list[dict]:
    """
    Returns list of dicts:
      {year, track, event_name, date_str, names: [str]}
    """
    # Strip everything before the "## לקטורים" heading
    start = text.find("## לקטורים")
    if start == -1:
        raise ValueError("לקטורים heading not found")
    text = text[start:]

    # Stop at the address/footer section
    footer = text.find("**משרדים:**")
    if footer != -1:
        text = text[:footer]

    # Preprocess: collapse multi-line **_content\n...\n_** into **_content_**
    # (2025 headings span multiple lines with trailing spaces)
    text = re.sub(
        r'\*\*_([^\n*]+?)\s*\n[\s\n]*_\*\*',
        lambda m: f'**_{m.group(1).strip()}_**',
        text,
    )

    rounds = []
    current_year = None
    current_track = None

    lines = text.splitlines()

    # Regex patterns
    year_re = re.compile(r'^\*\*_(\d{4})_\*\*\s*$')
    track_re = re.compile(r'^\*\*_(.+?)_\*\*\s*$')
    # Round line: event (date): names — date may be MM/YYYY, DD/MM/YYYY, or YYYY
    round_re = re.compile(
        r'^(.+?)'                                    # event name
        r'[\s\(（\[（]'                               # opening bracket or space
        r'(\d{1,2}/\d{1,2}/\d{4}|\d{1,2}/\d{4}|\d{4})'  # DD/MM/YYYY or MM/YYYY or YYYY
        r'[\)\]）]?'                                  # optional closing bracket
        r'\s*[:\-]\s*'                               # colon or dash separator
        r'(.+)$'                                     # names
    )

    def is_name_list(line: str) -> bool:
        """Heuristic: line is a comma-separated Hebrew name list."""
        if line.startswith('#') or line.startswith('*') or line.startswith('['):
            return False
        if line.startswith('_') and line.endswith('_'):
            return False
        hebrew_chars = sum(1 for c in line if 'א' <= c <= 'ת')
        return hebrew_chars > 8 and line.count(',') >= 1

    def extract_names(raw: str) -> list[str]:
        names = [n.strip() for n in re.split(r'[,،]', raw) if n.strip()]
        names = [n for n in names if not re.search(r'יועצ[תן]?\s+משלים', n)]
        names = [n for n in names if len(n) > 2]
        return names

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line:
            continue

        # Year heading: **_2025_**
        m = year_re.match(line)
        if m:
            candidate = int(m.group(1))
            if 2010 <= candidate <= 2030:
                current_year = candidate
                current_track = None
            continue

        # Track heading: **_תחום ייעודי_**
        m = track_re.match(line)
        if m:
            candidate_track = m.group(1).strip()
            if not re.match(r'^\d{4}$', candidate_track):
                current_track = candidate_track
            continue

        # Round/event line with date and names
        m = round_re.match(line)
        if m and current_year:
            event_name = m.group(1).strip().rstrip(':').strip()
            date_str = m.group(2).strip()
            # Normalize DD/MM/YYYY → MM/YYYY
            parts = date_str.split('/')
            if len(parts) == 3:
                date_str = f"{parts[1]}/{parts[2]}"
            names = extract_names(m.group(3))
            if names:
                rounds.append({
                    "year": current_year,
                    "track": current_track or "",
                    "event_name": event_name,
                    "date_str": date_str,
                    "names": names,
                })
            continue

        # Flat name list (years with minimal structure or flat annual lists)
        if current_year and is_name_list(line):
            names = extract_names(line)
            if names:
                rounds.append({
                    "year": current_year,
                    "track": current_track or "",
                    "event_name": "רשימה שנתית",
                    "date_str": str(current_year),
                    "names": names,
                })

    return rounds


def make_entry(round_data: dict, today: str) -> dict:
    year = round_data["year"]
    track = round_data["track"]
    event = round_data["event_name"]
    date_str = round_data["date_str"]
    names = round_data["names"]

    notes_label = f"{event} ({date_str})"
    if track:
        notes_label = f"{track} — {notes_label}"

    slug = slugify(f"{year}-{track}-{event}-{date_str}")
    url = make_synthetic_url(year, slug)

    # Stable hash from url
    chash = hashlib.md5(url.encode()).hexdigest()

    people = {}
    roles = []
    for idx, name in enumerate(names, 1):
        pid = f"person_{idx:03d}"
        people[pid] = {
            "name_he": name,
            "name_en": None,
            "aliases": [],
            "primary_roles": ["lector"],
            "sources": [url],
        }
        roles.append({
            "id": f"role_{idx:03d}",
            "person_id": pid,
            "organization_id": "org_001",
            "role_type": "lector",
            "start_year": year,
            "end_year": year,
            "notes": notes_label,
            "sources": [url],
        })

    return {
        "file": f"gesher__lectors-{year}-{slugify(event)}__manual.md",
        "url": url,
        "source_name": SOURCE_NAME,
        "status": "ok",
        "content_hash": chash,
        "content_length": 0,
        "filter_info": {"reason": "manual_canonical_source"},
        "truncated": False,
        "elapsed_sec": 0,
        "data": {
            "metadata": {
                "source_url": url,
                "source_name": SOURCE_NAME,
                "extraction_date": today,
                "language": "he",
                "canonical_source": "Gesher lectors page, scraped 05/2026",
            },
            "entities": {
                "people": people,
                "organizations": {
                    "org_001": {
                        "name_he": ORG_NAME_HE,
                        "name_en": ORG_NAME_EN,
                        "type": "fund",
                        "subtype": "public_film_fund",
                        "sources": [url],
                    }
                },
                "films": {},
                "events": {},
            },
            "roles": roles,
            "relationships": [],
            "films": [],
        },
    }


def main():
    dry_run = "--dry-run" in sys.argv

    text = LECTORS_PAGE_MD.read_text(encoding="utf-8")
    rounds = parse_lectors_page(text)
    today = date.today().isoformat()

    # Summary stats
    total_names = sum(len(r["names"]) for r in rounds)
    print(f"Parsed {len(rounds)} rounds, {total_names} lector slots")

    year_counts: dict[int, int] = {}
    for r in rounds:
        year_counts[r["year"]] = year_counts.get(r["year"], 0) + len(r["names"])
    for yr in sorted(year_counts):
        print(f"  {yr}: {year_counts[yr]} names")

    if dry_run:
        print("\n(dry run — nothing written)")
        for r in rounds:
            print(f"  {r['year']} | {r['track'][:20]:20s} | {r['event_name'][:25]:25s} | {r['date_str']:10s} | {len(r['names'])} names")
        return

    entries = [make_entry(r, today) for r in rounds]

    # Read existing mentions.jsonl, strip any previous manual://gesher entries
    existing_lines = []
    if OUT_JSONL.exists():
        for line in OUT_JSONL.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("url", "").startswith(CANONICAL_BASE):
                    continue  # remove old synthetic entries
            except Exception:
                pass
            existing_lines.append(line)

    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for line in existing_lines:
            f.write(line + "\n")
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(entries)} synthetic entries to {OUT_JSONL}")


if __name__ == "__main__":
    main()
