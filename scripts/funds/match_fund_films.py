#!/usr/bin/env python3
"""Match fund film lists against movies_db.json and populate the funds field.

Reads:  data/funds/*_films.json
        data/movies_db.json
Writes: data/movies_db.json  (funds field updated per film)

Usage: python3 scripts/funds/match_fund_films.py [--dry-run]
"""
import json, re, sys, unicodedata, glob
from collections import defaultdict
from html import unescape

FUND_FILES = sorted(glob.glob("data/funds/*_films.json"))
DB_PATH    = "data/movies_db.json"


def normalize_title(title: str) -> str:
    if not title:
        return ""
    t = unescape(title)          # fix &quot; &#39; etc
    t = unicodedata.normalize("NFKD", t)
    t = re.sub(r'["\'״׳“”.,!?:;()]', "", t)
    t = re.sub(r'[-–—]', " ", t)
    t = re.sub(r'\s+', " ", t).strip()
    return t


def main():
    dry_run = "--dry-run" in sys.argv

    with open(DB_PATH, encoding="utf-8") as f:
        db = json.load(f)
    print(f"Loaded {len(db)} films from movies_db.json\n")

    # Build lookup indices
    by_title_year: dict[str, int] = {}
    by_title: dict[str, list[int]] = defaultdict(list)
    for i, film in enumerate(db):
        nt = normalize_title(film.get("title_he", ""))
        if not nt:
            continue
        yr = film.get("year")
        by_title_year[f"{nt}|{yr}"] = i
        by_title[nt].append(i)

    total_matched = 0
    total_seen = 0
    all_unmatched: list[dict] = []

    for fpath in FUND_FILES:
        with open(fpath, encoding="utf-8") as f:
            raw = json.load(f)
        fund_films = [r for r in raw if r.get("title_he")]
        if not fund_films:
            print(f"  {fpath}: no films with titles, skipping")
            continue

        fund_key = fund_films[0].get("fund", fpath)
        matched = 0
        unmatched = []

        for ff in fund_films:
            total_seen += 1
            nt = normalize_title(ff.get("title_he", ""))
            yr = ff.get("year")
            if not nt:
                continue

            idx = None
            # Pass 1: exact title + year
            if yr:
                idx = by_title_year.get(f"{nt}|{yr}")
            # Pass 2: title-only (unique match)
            if idx is None:
                candidates = by_title.get(nt, [])
                if len(candidates) == 1:
                    idx = candidates[0]
                elif len(candidates) > 1 and yr:
                    # pick closest year
                    idx = min(candidates, key=lambda i: abs((db[i].get("year") or 0) - yr))
                elif len(candidates) > 1:
                    idx = candidates[0]  # take first if no year to disambiguate

            if idx is not None:
                funds_list = db[idx].setdefault("funds", [])
                if fund_key not in funds_list:
                    funds_list.append(fund_key)
                    matched += 1
                    total_matched += 1
            else:
                unmatched.append({"fund": fund_key, "title": ff.get("title_he"), "year": yr})

        all_unmatched.extend(unmatched)
        print(f"  {fund_key}: {matched}/{len(fund_films)} matched ({len(unmatched)} unmatched)")

    print(f"\nTotal: {total_matched} new fund tags across {total_seen} fund-film records")

    if all_unmatched:
        print(f"\nUnmatched ({len(all_unmatched)}) — sample:")
        for u in all_unmatched[:20]:
            print(f"  [{u['fund']}] {u['title']} ({u['year']})")

    films_with_funds = sum(1 for f in db if f.get("funds"))
    print(f"\nFilms with funds field populated: {films_with_funds}/{len(db)}")

    if dry_run:
        print("\n[DRY RUN] — not writing movies_db.json")
        return

    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    print(f"→ {DB_PATH} updated")


if __name__ == "__main__":
    main()
