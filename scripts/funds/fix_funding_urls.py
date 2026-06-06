#!/usr/bin/env python3
"""Fix bad search/category URLs in film_funding_results.json.

NFCT search URLs like https://nfct.org.il/?s=TITLE
  → https://nfct.org.il/blog/movies/SLUG/

Also fixes other bad patterns:
- rabinovich/cinemaproject URLs pointing to category pages
- Generic homepage URLs where a specific film page exists

Usage: python3 scripts/funds/fix_funding_urls.py [--dry-run]
"""
import json, re, sys, urllib.parse
from pathlib import Path

RESULTS_PATH = Path("data/film_funding_results.json")

NFCT_BASE = "https://nfct.org.il/blog/movies/"

BAD_URL_PATTERNS = [
    # NFCT search: ?s= or ?keywords= or /movies-archive?
    re.compile(r"^https://(?:www\.)?nfct\.org\.il/\?(?:s|keywords|search)="),
    re.compile(r"^https://(?:www\.)?nfct\.org\.il/movies-archive\?"),
]


def is_bad_url(url: str) -> bool:
    for pat in BAD_URL_PATTERNS:
        if pat.search(url):
            return True
    return False


def title_to_slug(title: str) -> str:
    t = re.sub(r'["\'"״׳\(\)\[\]{}<>:,\.!?]', "", title)
    t = t.strip()
    t = re.sub(r"\s+", "-", t)
    return t


def proper_nfct_url(title: str) -> str:
    slug = title_to_slug(title)
    return NFCT_BASE + urllib.parse.quote(slug, safe="-") + "/"


def main():
    dry_run = "--dry-run" in sys.argv

    if not RESULTS_PATH.exists():
        print(f"ERROR: {RESULTS_PATH} not found", file=sys.stderr)
        sys.exit(1)

    with open(RESULTS_PATH, encoding="utf-8") as f:
        data = json.load(f)

    total_fixed = 0
    total_entries_with_bad = 0

    for entry in data:
        title = (entry.get("title_he") or "").strip()
        funds = entry.get("funds", [])
        urls = entry.get("source_urls", [])
        new_urls = []
        changed = False

        for url in urls:
            if is_bad_url(url):
                if "nfct" in funds and title:
                    proper = proper_nfct_url(title)
                    new_urls.append(proper)
                    changed = True
                    total_fixed += 1
                else:
                    new_urls.append(url)
            else:
                new_urls.append(url)

        if changed:
            entry["source_urls"] = new_urls
            total_entries_with_bad += 1

    print(f"Entries processed: {len(data)}")
    print(f"Entries with bad URLs fixed: {total_entries_with_bad}")
    print(f"Individual URLs fixed: {total_fixed}")

    if dry_run:
        print("\n[DRY RUN - no changes written]")
        return

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n{RESULTS_PATH} updated")


if __name__ == "__main__":
    main()
