#!/usr/bin/env python3
"""
nfct_fix_film_urls.py — Fix bad NFCT film URLs in mentions.jsonl.

Problem: many NFCT film entities have sources[] pointing to search-result pages
  (e.g. /movies-archive?keywords=...) instead of the proper film page
  (https://nfct.org.il/blog/movies/TITLE-SLUG/).

Actions:
  1. Build a slug→scraped-path index from sources/nfct/pages/nfct__blog-movies-*.md
  2. For each film with a bad source URL, construct the correct URL from the Hebrew title
  3. If the proper page is already scraped → rewrite sources[] in mentions.jsonl
  4. Output a JSON file of missing film URLs to scrape

Usage:
    python3 nfct_fix_film_urls.py [--dry-run] [--scrape-list out/nfct/missing_film_urls.json]
"""

import argparse
import glob
import json
import re
import sys
import urllib.parse
from pathlib import Path

MENTIONS_FILE  = Path("out/nfct/mentions.jsonl")
PAGES_GLOB     = "sources/nfct/pages/nfct__blog-movies-*.md"
NFCT_FILM_BASE = "https://nfct.org.il/blog/movies/"

BAD_URL_RE     = re.compile(r"movies-archive|[?&](keywords|search|q)=", re.IGNORECASE)
FILM_PAGE_RE   = re.compile(r"/blog/movies/", re.IGNORECASE)
HEBREW_RE      = re.compile(r"[א-ת]")


def title_to_slug(title: str) -> str:
    """Convert Hebrew film title to NFCT URL slug."""
    # Keep Hebrew, digits, spaces; strip punctuation/quotes/brackets
    t = re.sub(r'["\'"״׳\(\)\[\]{}<>:,\.!?]', "", title)
    t = t.strip()
    t = re.sub(r"\s+", "-", t)
    return t


def title_to_nfct_url(title: str) -> str:
    slug = title_to_slug(title)
    return NFCT_FILM_BASE + urllib.parse.quote(slug, safe="-") + "/"


def normalize_url(u: str) -> str:
    """Decode + lowercase + strip fragment + trailing slash for comparison."""
    u = urllib.parse.unquote(u or "").lower()
    u = re.sub(r"#.*$", "", u).rstrip("/")
    return u


def build_scraped_index() -> dict:
    """Return {normalized_url: file_path} for all scraped /blog/movies/ pages."""
    index = {}
    for path in glob.glob(PAGES_GLOB):
        try:
            raw = open(path, encoding="utf-8").read()
            d   = json.loads(raw)
            url = d.get("url") or d.get("source_url") or ""
        except Exception:
            # Try reading as plain URL in first line
            try:
                first = open(path, encoding="utf-8").readline().strip()
                url = first if first.startswith("http") else ""
            except Exception:
                url = ""
        if not url:
            # Reconstruct URL from filename slug
            stem = Path(path).stem  # nfct__blog-movies-SLUG__HASH
            parts = stem.split("__")
            if len(parts) >= 2:
                slug = parts[1].replace("-", "%")  # rough decode
        nurl = normalize_url(url)
        if nurl and "/blog/movies/" in nurl:
            index[nurl] = path
    return index


def is_bad_url(url: str) -> bool:
    return bool(BAD_URL_RE.search(url or "")) or (
        "/movies" in (url or "") and not FILM_PAGE_RE.search(url or "")
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--scrape-list", default="out/nfct/missing_film_urls.json",
                        help="Output JSON file listing URLs to scrape")
    args = parser.parse_args()

    if not MENTIONS_FILE.exists():
        print(f"ERROR: {MENTIONS_FILE} not found", file=sys.stderr)
        sys.exit(1)

    print("Building scraped-page index...")
    scraped = build_scraped_index()
    print(f"  {len(scraped)} scraped /blog/movies/ pages indexed")

    lines_in    = MENTIONS_FILE.read_text(encoding="utf-8").splitlines()
    lines_out   = []

    stats = {
        "entries": 0, "films_checked": 0,
        "url_fixed": 0, "already_good": 0,
        "missing_scrape": 0, "no_hebrew_title": 0,
    }
    missing_urls: dict[str, str] = {}  # title → constructed URL

    for raw in lines_in:
        raw = raw.strip()
        if not raw:
            lines_out.append(raw)
            continue
        try:
            r = json.loads(raw)
        except json.JSONDecodeError:
            lines_out.append(raw)
            continue

        if r.get("status") != "ok":
            lines_out.append(raw)
            continue

        stats["entries"] += 1
        data     = r.get("data") or {}
        entities = data.get("entities") or {}
        films    = entities.get("films") or {}
        changed  = False

        for fid, film in (films or {}).items():
            if not film:
                continue
            title = (film.get("title_he") or "").strip()
            if not title or not HEBREW_RE.search(title):
                stats["no_hebrew_title"] += 1
                continue
            stats["films_checked"] += 1

            old_sources = film.get("sources") or []
            new_sources = []
            film_fixed  = False

            for src_url in old_sources:
                if not is_bad_url(src_url):
                    new_sources.append(src_url)
                    stats["already_good"] += 1
                    continue
                # Construct the proper URL
                proper_url  = title_to_nfct_url(title)
                proper_norm = normalize_url(proper_url)

                if proper_norm in scraped:
                    # We have this page scraped — replace the bad URL
                    new_sources.append(proper_url)
                    stats["url_fixed"] += 1
                    film_fixed = True
                    if not args.dry_run:
                        changed = True
                else:
                    # Not yet scraped — keep the old url for now, queue for scraping
                    new_sources.append(src_url)
                    stats["missing_scrape"] += 1
                    missing_urls[title] = proper_url

            if film_fixed:
                film["sources"] = new_sources

        if changed:
            entities["films"] = films
            data["entities"]  = entities
            r["data"]         = data
            lines_out.append(json.dumps(r, ensure_ascii=False))
        else:
            lines_out.append(raw)

    # Write updated jsonl
    if not args.dry_run:
        MENTIONS_FILE.write_text(
            "\n".join(lines_out) + "\n", encoding="utf-8"
        )
        print(f"Rewrote {MENTIONS_FILE}")

    # Write scrape list
    scrape_path = Path(args.scrape_list)
    scrape_path.parent.mkdir(parents=True, exist_ok=True)
    out_list = sorted(set(missing_urls.values()))
    scrape_path.write_text(
        json.dumps({"urls": out_list, "count": len(out_list)},
                   ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    tag = "(dry run)" if args.dry_run else "✓"
    print(f"\n{tag} Results:")
    print(f"  Entries processed : {stats['entries']:,}")
    print(f"  Films checked     : {stats['films_checked']:,}")
    print(f"  URLs fixed        : {stats['url_fixed']:,}  (proper page already scraped)")
    print(f"  Need scraping     : {stats['missing_scrape']:,}  ({len(out_list)} unique titles)")
    print(f"  Already correct   : {stats['already_good']:,}")
    print(f"\nScrape list written to: {scrape_path}")
    print(f"\nNext steps:")
    print(f"  1. Feed {scrape_path} to the scraper service")
    print(f"  2. python3 llm_extract.py sources/nfct/pages ./out --source-name nfct --reprocess-truncated")
    print(f"  3. python3 enrich_mentions.py --source nfct")
    print(f"  4. python3 resolve_entities.py")


if __name__ == "__main__":
    main()
