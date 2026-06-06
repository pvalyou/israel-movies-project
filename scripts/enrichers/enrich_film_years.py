#!/usr/bin/env python3
"""
enrich_film_years.py
──────────────────────────────────────────────────────────────────────
Finds film mentions missing a year across all mentions.jsonl files and
attempts to fill them in using the TMDB API.

Results are written to:
  enriched/film_years.json      — {normalized_title: year} lookup
  enriched/film_years_log.json  — full TMDB response log per title

Usage:
  export TMDB_API_KEY=<your_key>         # https://www.themoviedb.org/settings/api
  python3 enrich_film_years.py           # dry run, prints matches
  python3 enrich_film_years.py --write   # also patches mentions.jsonl files in-place
  python3 enrich_film_years.py --source jerusalem_film_fund  # limit to one source

The enrichment lookup is consumed by resolve_entities.py via:
  enriched/film_years.json  →  load_enriched_years()
"""

import argparse
import glob
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

TMDB_BASE   = "https://api.themoviedb.org/3"
ENRICHED_DIR = Path("enriched")
YEARS_FILE   = ENRICHED_DIR / "film_years.json"
LOG_FILE     = ENRICHED_DIR / "film_years_log.json"

FILM_URL_KEYWORDS = ["/film/", "/movie/", "/סרטים/", "/סרט/", "film_id", "/productions/"]

# ── Helpers ────────────────────────────────────────────────────────────────────

def normalize_title(t: str) -> str:
    t = t.strip().lower()
    t = unicodedata.normalize("NFC", t)
    t = re.sub(r"[\s\-–—_]+", " ", t)
    return t


def tmdb_search(title: str, api_key: str, language: str = "he-IL") -> list:
    params = urllib.parse.urlencode({
        "api_key": api_key,
        "query": title,
        "language": language,
        "region": "IL",
    })
    url = f"{TMDB_BASE}/search/movie?{params}"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            return json.loads(resp.read()).get("results", [])
    except Exception as e:
        print(f"  TMDB error for '{title}': {e}", file=sys.stderr)
        return []


def best_year(results: list) -> str | None:
    for r in results[:3]:
        date = r.get("release_date", "")
        if date and len(date) >= 4:
            return date[:4]
    return None


def collect_missing(source_filter: str | None = None) -> list[dict]:
    """Return unique (source, title_he, title_en, url) dicts for film-page films missing year."""
    seen: set = set()
    out: list = []
    for path in sorted(glob.glob("out/*/mentions.jsonl")):
        source = path.split("/")[1]
        if source_filter and source != source_filter:
            continue
        with open(path) as f:
            for line in f:
                rec = json.loads(line)
                if rec.get("status") != "ok":
                    continue
                url = rec.get("url", "")
                if not any(kw in url for kw in FILM_URL_KEYWORDS):
                    continue
                for film in rec.get("data", {}).get("entities", {}).get("films", {}).values():
                    if film.get("year"):
                        continue
                    title_he = (film.get("title_he") or "").strip()
                    title_en = (film.get("title_en") or "").strip()
                    title = title_he or title_en
                    if not title or len(title) < 3:
                        continue
                    if title in {"סרטים", "סרטי", "סרט", "פרויקטים", "עבודות"}:
                        continue
                    key = (source, normalize_title(title))
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append({
                        "source": source,
                        "title_he": title_he,
                        "title_en": title_en,
                        "url": url,
                    })
    return out


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="Patch year back into mentions.jsonl files")
    parser.add_argument("--source", help="Limit to one source directory")
    args = parser.parse_args()

    api_key = os.environ.get("TMDB_API_KEY", "")
    if not api_key:
        print("ERROR: set TMDB_API_KEY environment variable", file=sys.stderr)
        sys.exit(1)

    ENRICHED_DIR.mkdir(exist_ok=True)

    # Load existing enrichment cache
    existing: dict = {}
    if YEARS_FILE.exists():
        existing = json.loads(YEARS_FILE.read_text())

    missing = collect_missing(args.source)
    print(f"Films missing year: {len(missing)}")

    log: list = []
    enriched: dict = dict(existing)
    found = 0

    for rec in missing:
        title_he = rec["title_he"]
        title_en = rec["title_en"]
        norm_he  = normalize_title(title_he) if title_he else None
        norm_en  = normalize_title(title_en) if title_en else None

        # Check cache first
        year = enriched.get(norm_he) or enriched.get(norm_en)
        if year:
            print(f"  [cache] {title_he or title_en} → {year}")
            found += 1
            continue

        # Try Hebrew title first, fall back to English
        results = []
        for title, lang in [(title_he, "he-IL"), (title_en, "en-US")]:
            if not title:
                continue
            results = tmdb_search(title, api_key, lang)
            if results:
                break
            time.sleep(0.25)

        year = best_year(results)
        entry = {
            "title_he": title_he,
            "title_en": title_en,
            "source": rec["source"],
            "url": rec["url"],
            "tmdb_results": results[:3],
            "matched_year": year,
        }
        log.append(entry)

        if year:
            if norm_he:
                enriched[norm_he] = year
            if norm_en:
                enriched[norm_en] = year
            print(f"  [tmdb]  {title_he or title_en} → {year}")
            found += 1
        else:
            print(f"  [miss]  {title_he or title_en} — not found")

        time.sleep(0.25)

    # Persist
    YEARS_FILE.write_text(json.dumps(enriched, ensure_ascii=False, indent=2))
    LOG_FILE.write_text(json.dumps(log, ensure_ascii=False, indent=2))
    print(f"\nEnriched: {found}/{len(missing)} films")
    print(f"Lookup written → {YEARS_FILE}")
    print(f"Log written    → {LOG_FILE}")

    if args.write:
        _patch_mentions(enriched)


def _patch_mentions(enriched: dict):
    """Write enriched years back into mentions.jsonl files (in-place)."""
    import tempfile, shutil
    patched_total = 0
    for path in sorted(glob.glob("out/*/mentions.jsonl")):
        lines_out = []
        patched = 0
        with open(path) as f:
            for line in f:
                rec = json.loads(line)
                if rec.get("status") == "ok":
                    for film in rec.get("data", {}).get("entities", {}).get("films", {}).values():
                        if not film.get("year"):
                            for field in ("title_he", "title_en"):
                                t = normalize_title(film.get(field) or "")
                                if t and t in enriched:
                                    film["year"] = enriched[t]
                                    patched += 1
                                    break
                lines_out.append(json.dumps(rec, ensure_ascii=False))
        if patched:
            tmp = path + ".tmp"
            with open(tmp, "w") as f:
                f.write("\n".join(lines_out) + "\n")
            shutil.move(tmp, path)
            print(f"  patched {patched} films in {path}")
            patched_total += patched
    print(f"Total patched: {patched_total} film records")


if __name__ == "__main__":
    main()
