#!/usr/bin/env python3
"""
query_films.py — Query movies_db.json by person or fund.

Usage:
  python3 scripts/query_films.py person "כליל כובש"
  python3 scripts/query_films.py person "אסף לפיד"
  python3 scripts/query_films.py fund makor
  python3 scripts/query_films.py fund galilee_film_fund
  python3 scripts/query_films.py film "שכבות"
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

DB = Path("data/movies_db.json")


def norm(s):
    if not s: return ""
    s = unicodedata.normalize("NFKD", s)
    s = re.sub(r'["\'"״׳.,!?:;()]', "", s)
    s = re.sub(r"[-–—]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def load():
    with open(DB, encoding="utf-8") as f:
        return json.load(f)


def query_person(movies, name_query):
    q = norm(name_query)
    results = []
    for m in movies:
        for person in (m.get("crew") or []) + (m.get("cast") or []):
            pname = person.get("name_he") or person.get("name_en") or ""
            if q in norm(pname):
                results.append((m, person))
                break
    return results


def query_fund(movies, fund_key):
    q = fund_key.lower().replace("-", "_")
    return [m for m in movies if q in [f.lower() for f in (m.get("funds") or [])]]


def query_film(movies, title_query):
    q = norm(title_query)
    return [m for m in movies if q in norm(m.get("title_he") or "") or q in norm(m.get("title_en") or "")]


def fmt_film(m, person=None):
    title = m.get("title_he") or m.get("title_en") or "?"
    year  = str(m.get("year") or "—")
    funds = ", ".join(m.get("funds") or []) or "—"
    role  = person.get("role_he") or person.get("role") or "" if person else ""
    crew  = "; ".join(f"{p.get('name_he')} ({p.get('role','')})"
                      for p in (m.get("crew") or [])[:4]) if not person else ""
    return f"  {title:40s} {year:6s}  funds=[{funds}]  {role or crew}"


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    mode  = sys.argv[1].lower()
    query = " ".join(sys.argv[2:])
    movies = load()

    if mode == "person":
        results = query_person(movies, query)
        print(f'\nFilms for "{query}": {len(results)}\n')
        for m, person in sorted(results, key=lambda x: x[0].get("year") or 0):
            print(fmt_film(m, person))

    elif mode == "fund":
        results = query_fund(movies, query)
        print(f'\nFilms funded by "{query}": {len(results)}\n')
        for m in sorted(results, key=lambda x: x.get("year") or 0):
            print(fmt_film(m))

    elif mode == "film":
        results = query_film(movies, query)
        print(f'\nFilms matching "{query}": {len(results)}\n')
        for m in results:
            print(fmt_film(m))
            crew = "; ".join(f"{p.get('name_he')} ({p.get('role','')})"
                             for p in (m.get("crew") or [])[:6])
            if crew: print(f"    crew: {crew}")

    else:
        print(f"Unknown mode: {mode}. Use: person / fund / film")


if __name__ == "__main__":
    main()
