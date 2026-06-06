#!/usr/bin/env python3
"""
scrape_from_sitemap.py — Fetch a sitemap XML, extract all <loc> URLs, and
scrape them using the existing crawl4ai-wrapper service.

Each URL is scraped with follow_links=false and max_depth=1 (single page).
Results are saved as .md + .meta.json pairs in sources/<source_id>/pages/,
using the same file-naming convention as scrape.py.

Already-scraped URLs (where the .md file already exists) are skipped unless
--force is given.

Usage:
    python3 scrape_from_sitemap.py <source_id> <source_name_he> <sitemap_url>
    python3 scrape_from_sitemap.py fdoc "הפורום הדוקומנטרי" https://www.fdoc.org.il/movie-sitemap.xml

Options:
    --dry-run        List URLs without scraping
    --force          Re-scrape even if .md file already exists
    --concurrency N  Parallel requests (default: 5)
    --limit N        Scrape at most N URLs (for testing)
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests

# ── Config ────────────────────────────────────────────────────────────────────

SCRAPER_URL = os.environ.get(
    "SCRAPER_URL",
    "https://crawl4ai-wrapper-559961100092.europe-west1.run.app",
)
API_KEY = os.environ.get("CRAWL4AI_API_KEY", "")

# Load .env if present
_env = Path(".env")
if _env.exists() and not API_KEY:
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line.startswith("CRAWL4AI_API_KEY="):
            API_KEY = _line.split("=", 1)[1].strip()

SOURCES_DIR = Path("sources")

# ── URL utilities (mirrored from scrape.py) ───────────────────────────────────

def slugify_url(url: str) -> str:
    """Create a filesystem-safe slug from a URL (same logic as scrape.py)."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        path = "root"
    slug = re.sub(r"[^a-zA-Z0-9֐-׿-]", "_", path)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:80]


def page_hash(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()[:8]


def make_basename(source_id: str, url: str) -> str:
    return f"{source_id}__{slugify_url(url)}__{page_hash(url)}"


# ── Sitemap fetching ──────────────────────────────────────────────────────────

def fetch_sitemap_urls(sitemap_url: str) -> list[str]:
    """
    Fetch a sitemap XML and return all <loc> URLs.
    Handles both standard sitemaps and sitemap index files (sitemapindex).
    Works with or without XML namespaces.
    """
    print(f"Fetching sitemap: {sitemap_url}")
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SitemapBot/1.0)"}
    try:
        resp = requests.get(sitemap_url, headers=headers, timeout=30)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"ERROR fetching sitemap: {e}", file=sys.stderr)
        sys.exit(1)

    content = resp.text

    # Fast path: extract <loc> values with a simple regex (handles all namespace variants)
    loc_values = re.findall(r"<loc>\s*(https?://[^\s<]+)\s*</loc>", content)
    if not loc_values:
        # Try with CDATA or encoded content
        loc_values = re.findall(r"<loc[^>]*>\s*(https?://[^<]+)\s*</loc>", content)

    if not loc_values:
        # Fall back to XML parsing with namespace stripping
        # Replace namespace declarations so ElementTree can parse without prefixes
        content_clean = re.sub(r'\sxmlns(?::[a-zA-Z0-9]+)?="[^"]*"', "", content)
        content_clean = re.sub(r"\sxmlns(?::[a-zA-Z0-9]+)?='[^']*'", "", content_clean)
        # Remove namespace prefixes from tags (e.g. <sm:url> → <url>)
        content_clean = re.sub(r"<(/?)(?:[a-zA-Z0-9]+:)", r"<\1", content_clean)
        try:
            root = ET.fromstring(content_clean)
        except ET.ParseError as e:
            print(f"ERROR parsing sitemap XML: {e}", file=sys.stderr)
            sys.exit(1)

        # Sitemap index: recurse into child sitemaps
        if root.tag.endswith("sitemapindex") or any(
            c.tag.endswith("sitemap") for c in root
        ):
            urls: list[str] = []
            for child in root:
                loc = child.find("loc")
                if loc is not None and loc.text:
                    urls.extend(fetch_sitemap_urls(loc.text.strip()))
            return urls

        # Regular sitemap
        loc_values = []
        for url_elem in root:
            loc = url_elem.find("loc")
            if loc is not None and loc.text:
                loc_values.append(loc.text.strip())

    # If the result looks like a sitemap index (all locs end in .xml), recurse
    if loc_values and all(u.endswith(".xml") for u in loc_values):
        urls = []
        for child_url in loc_values:
            urls.extend(fetch_sitemap_urls(child_url))
        return urls

    return [u.strip() for u in loc_values if u.strip()]


# ── Scraping (mirrored from scrape.py) ───────────────────────────────────────

def crawl_page(url: str) -> dict:
    """
    Send a single URL to the scraper service with follow_links=false, max_depth=1.
    Returns result dict.
    """
    payload = {
        "url": url,
        "format": "markdown",
        "fit_markdown": False,
        "ignore_links": False,
        "include_media": False,
        "include_links": True,
        "follow_links": False,
        "max_depth": 1,
    }
    try:
        headers: dict[str, str] = {}
        if API_KEY:
            headers["X-API-Key"] = API_KEY
        resp = requests.post(
            f"{SCRAPER_URL}/scrape",
            json=payload,
            headers=headers,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        md_content = data.get("markdown", "") or data.get("content", "") or ""
        final_url = data.get("url", url)
        status = data.get("status", "ok")
        links = data.get("links", [])

        return {
            "success": bool(md_content.strip()),
            "md_content": md_content,
            "final_url": final_url,
            "status": status,
            "links": links,
            "error": data.get("error", ""),
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "md_content": "",
            "final_url": url,
            "status": "error",
            "links": [],
            "error": str(e),
        }


def save_page(source_id: str, url: str, result: dict, pages_dir: Path) -> str:
    """Save a scraped page as .md + .meta.json. Returns file base name."""
    base = make_basename(source_id, url)
    md_path = pages_dir / f"{base}.md"
    meta_path = pages_dir / f"{base}.meta.json"

    if result["success"]:
        md_path.write_text(result["md_content"], encoding="utf-8")

    meta = {
        "url": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "final_url": result["final_url"],
        "cache_hit": False,
        "status": result["status"],
        "md_hash": (
            hashlib.md5(result["md_content"].encode("utf-8")).hexdigest()
            if result["md_content"]
            else None
        ),
        "md_bytes": len(result["md_content"].encode("utf-8")),
        "links_found": len(result.get("links", [])),
        "error": result.get("error", ""),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return base


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source_id",       help="Source identifier (e.g. fdoc)")
    parser.add_argument("source_name_he",  help="Hebrew source name")
    parser.add_argument("sitemap_url",     help="URL of the sitemap XML")
    parser.add_argument("--dry-run",       action="store_true", help="List URLs without scraping")
    parser.add_argument("--force",         action="store_true", help="Re-scrape already-scraped URLs")
    parser.add_argument("--concurrency",   type=int, default=5, help="Parallel requests (default: 5)")
    parser.add_argument("--limit",         type=int, default=0, help="Scrape at most N URLs (0 = no limit)")
    args = parser.parse_args()

    # Setup directories
    source_dir = SOURCES_DIR / args.source_id
    pages_dir  = source_dir / "pages"
    runs_dir   = source_dir / "runs"
    pages_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    # Fetch sitemap
    all_urls = fetch_sitemap_urls(args.sitemap_url)
    if not all_urls:
        print("No URLs found in sitemap.", file=sys.stderr)
        sys.exit(1)
    print(f"Found {len(all_urls)} URLs in sitemap")

    # Filter: skip already-scraped URLs unless --force
    if args.force:
        urls_to_scrape = all_urls
        skipped = 0
    else:
        urls_to_scrape = []
        skipped = 0
        for url in all_urls:
            base = make_basename(args.source_id, url)
            md_file = pages_dir / f"{base}.md"
            if md_file.exists():
                skipped += 1
            else:
                urls_to_scrape.append(url)
        if skipped:
            print(f"Skipping {skipped} already-scraped URLs (use --force to re-scrape)")

    # Apply limit
    if args.limit and args.limit > 0:
        urls_to_scrape = urls_to_scrape[: args.limit]
        print(f"Limiting to {args.limit} URLs (--limit)")

    print(f"URLs to scrape: {len(urls_to_scrape)}")

    if args.dry_run:
        print("\n(dry run — nothing scraped)")
        for url in urls_to_scrape[:20]:
            print(f"  {url}")
        if len(urls_to_scrape) > 20:
            print(f"  ... and {len(urls_to_scrape) - 20} more")
        return

    if not urls_to_scrape:
        print("Nothing to scrape.")
        return

    print(f"\nSource:      {args.source_id} ({args.source_name_he})")
    print(f"Scraper:     {SCRAPER_URL}")
    print(f"Concurrency: {args.concurrency}")
    print(f"Output:      {pages_dir}")
    print()

    # Run ID for manifest
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    start_time = time.time()
    stats = {"attempted": 0, "succeeded": 0, "failed": 0, "empty": 0}
    saved_bases: list[str] = []

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(crawl_page, url): url for url in urls_to_scrape}
        for future in as_completed(futures):
            url = futures[future]
            stats["attempted"] += 1
            try:
                result = future.result()
            except Exception as e:
                print(f"  ERROR {url}: {e}")
                stats["failed"] += 1
                continue

            base = save_page(args.source_id, url, result, pages_dir)

            if result["success"]:
                stats["succeeded"] += 1
                saved_bases.append(base)
                kb = len(result["md_content"].encode("utf-8")) / 1024
                print(f"  OK  [{stats['attempted']:4d}/{len(urls_to_scrape)}] {url}")
                print(f"       -> {base}.md ({kb:.1f} KB)")
            elif result.get("error"):
                stats["failed"] += 1
                print(f"  ERR [{stats['attempted']:4d}/{len(urls_to_scrape)}] {url}: {result['error']}")
            else:
                stats["empty"] += 1
                print(f"  --- [{stats['attempted']:4d}/{len(urls_to_scrape)}] {url}: empty")

    elapsed = time.time() - start_time

    # Write manifest
    manifest = {
        "run_id": run_id,
        "source_id": args.source_id,
        "source_name_he": args.source_name_he,
        "tier": "B",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "scraper_url": SCRAPER_URL,
        "concurrency": args.concurrency,
        "follow_links": False,
        "max_depth": 1,
        "sitemap_url": args.sitemap_url,
        "scrape_options": {
            "format": "markdown",
            "fit_markdown": False,
            "ignore_links": False,
            "include_media": False,
            "include_links": True,
        },
        "stats": {
            "urls_in_sitemap": len(all_urls),
            "urls_skipped": skipped,
            "urls_attempted": stats["attempted"],
            "urls_succeeded": stats["succeeded"],
            "urls_empty": stats["empty"],
            "urls_failed": stats["failed"],
            "cache_hits": 0,
            "files_downloaded": stats["succeeded"],
            "duration_seconds": round(elapsed, 1),
        },
        "urls": urls_to_scrape,
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nDone in {elapsed:.0f}s: "
          f"{stats['succeeded']} ok, {stats['failed']} failed, {stats['empty']} empty")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
