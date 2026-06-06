#!/usr/bin/env python3
"""Phase 4: Extract film funding amounts from existing scraped pages.

Reads pages from sources/*/pages/*.md that contain ₪ amounts + film references.
Produces fund_recipient records in the mentions format.

Output: out/funding_amounts/mentions.jsonl
"""

import glob
import json
import os
import re
from datetime import date

OUTPUT_FILE = "out/funding_amounts/mentions.jsonl"

# Sources to check for film funding pages
SOURCE_PATTERNS = {
    "filmfund": "sources/filmfund/pages/filmfund__Movie_movieId-*.md",
    "makor": "sources/makor/pages/*.md",
    "nfct": "sources/nfct/pages/*.md",
    "rabinovich_cinema": "sources/rabinovich_cinema/pages/*.md",
    "rabinovich_foundation": "sources/rabinovich_foundation/pages/*.md",
    "jerusalem_film_fund": "sources/jerusalem_film_fund/pages/*.md",
    "gesher": "sources/gesher/pages/*.md",
    "galilee_film_fund": "sources/galilee_film_fund/pages/*.md",
    "arava_film_fund": "sources/arava_film_fund/pages/*.md",
}

# Patterns for extracting film name, year, and ₪ amount
SHEKEL_RE = re.compile(r'([\d,]+)\s*(?:ש"ח|שקלים|שקל|₪|מענק|ILS|NIS)')
SHEKEL_SYMBOL_RE = re.compile(r'₪\s*([\d,]+)')
AMOUNT_CONTEXT_RE = re.compile(r'(?:תקציב|מימון|מענק|השתתפות|תמיכה|סכום|עלות)[^₪\d]*?([\d,]+)')

# Film title patterns
FILM_NAME_BOLD = re.compile(r'\*\*(.+?)\*\*')
FILM_NAME_H1 = re.compile(r'#\s*(.+?)(?:\n|$)')


def extract_amounts(text: str) -> list[int]:
    amounts = []
    # Pattern 1: number followed by shekel indicator
    for m in SHEKEL_RE.finditer(text):
        try:
            val = int(m.group(1).replace(",", ""))
            if 10000 <= val <= 50000000:
                amounts.append(val)
        except ValueError:
            pass
    # Pattern 2: shekel symbol followed by number
    for m in SHEKEL_SYMBOL_RE.finditer(text):
        try:
            val = int(m.group(1).replace(",", ""))
            if 10000 <= val <= 50000000 and val not in amounts:
                amounts.append(val)
        except ValueError:
            pass
    # Pattern 3: budget/amount keywords near numbers
    for m in AMOUNT_CONTEXT_RE.finditer(text):
        try:
            val = int(m.group(1).replace(",", ""))
            if 10000 <= val <= 50000000 and val not in amounts:
                amounts.append(val)
        except ValueError:
            pass

    # Remove duplicates (same film might mention amount multiple times)
    return sorted(amounts)


def extract_films(text: str) -> list[str]:
    """Extract film titles from markdown content."""
    films = set()
    for m in FILM_NAME_BOLD.finditer(text):
        name = m.group(1).strip()
        if len(name) >= 2 and not any(kw in name for kw in ["http", "jpg", "png", "הפקה", "בימוי"]):
            films.add(name)
    for m in FILM_NAME_H1.finditer(text):
        name = m.group(1).strip()
        if len(name) >= 2 and not any(kw in name for kw in ["http", "jpg", "png"]):
            films.add(name)
    return sorted(films)


def main():
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    total_records = 0
    total_amount = 0

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        for source, pattern in SOURCE_PATTERNS.items():
            files = sorted(glob.glob(pattern))
            print(f"\n{source}: {len(files)} pages")

            source_records = 0
            for fp in files:
                try:
                    with open(fp, encoding="utf-8") as f:
                        content = f.read()
                except Exception:
                    continue

                amounts = extract_amounts(content)
                if not amounts:
                    continue

                films = extract_films(content)
                url_match = re.search(r'"url":"([^"]+)"', content)
                page_url = url_match.group(1) if url_match else ""

                for amount in amounts:
                    record = {
                        "file": os.path.basename(fp),
                        "url": page_url,
                        "source_name": source,
                        "status": "ok",
                        "data": {
                            "metadata": {
                                "source_url": page_url,
                                "source_name": source,
                                "extraction_date": str(date.today()),
                                "language": "he",
                            },
                            "entities": {
                                "films": {},
                                "organizations": {
                                    "fund_001": {
                                        "name_he": source,
                                        "type": "fund",
                                    }
                                },
                            },
                            "relationships": [
                                {
                                    "source_id": "film_001",
                                    "source_type": "film",
                                    "target_id": "fund_001",
                                    "target_type": "organization",
                                    "relationship_type": "fund_recipient",
                                    "amount_ils": amount,
                                    "year": None,
                                }
                            ],
                        },
                    }

                    # If we found film names, add the first one as context
                    if films:
                        record["data"]["entities"]["films"]["film_001"] = {
                            "title_he": films[0],
                            "title_en": None,
                        }

                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
                    source_records += 1
                    total_amount += amount

            print(f"  → {source_records} funding records, ₪{total_amount:,.0f} total")
            total_records += source_records

    print(f"\nTotal: {total_records} funding records, ₪{total_amount:,.0f}")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()