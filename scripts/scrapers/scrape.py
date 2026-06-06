#!/usr/bin/env python3
"""
scrape.py — Batch scraper for Israeli film industry sources.

Uses the crawl4ai-wrapper service to fetch pages, saves results as
.md + .meta.json pairs in sources/<source_id>/pages/.

Usage:
    python3 scrape.py <source_id> <source_name_he> <url1> [url2 ...]
    python3 scrape.py --file urls.txt   # read URLs from file

Examples:
    python3 scrape.py docaviv "דוקאביב" https://www.docaviv.co.il/
    python3 scrape.py --file festivals.txt
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests

# ── Config ────────────────────────────────────────────────────────────────────

SCRAPER_URL = os.environ.get(
    "SCRAPER_URL",
    "https://crawl4ai-wrapper-559961100092.europe-west1.run.app"
)
API_KEY = os.environ.get("CRAWL4AI_API_KEY", "")
CONCURRENCY = int(os.environ.get("SCRAPER_CONCURRENCY", "5"))
MAX_DEPTH   = int(os.environ.get("SCRAPER_MAX_DEPTH", "2"))
FOLLOW_LINKS = os.environ.get("SCRAPER_FOLLOW_LINKS", "true").lower() == "true"

# Load .env if present (dotenv may not be installed)
_env = Path(".env")
if _env.exists() and not API_KEY:
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line.startswith("CRAWL4AI_API_KEY="):
            API_KEY = line.split("=", 1)[1].strip()

SOURCES_DIR = Path("sources")


def slugify_url(url: str) -> str:
    """Create a filesystem-safe slug from a URL."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        path = "root"
    # Replace Hebrew chars with percent-encoded, then clean
    slug = re.sub(r"[^a-zA-Z0-9\u0590-\u05FF-]", "_", path)
    # Collapse multiple underscores
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:80]


def page_hash(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()[:8]


def crawl_page(url: str, source_id: str, depth: int, follow: bool) -> dict:
    """Send a single URL to the scraper service and return result dict."""
    payload = {
        "url": url,
        "format": "markdown",
        "fit_markdown": False,
        "ignore_links": False,
        "include_media": False,
        "include_links": True,
        "follow_links": follow,
        "max_depth": depth,
    }

    try:
        headers = {}
        if API_KEY:
            headers["X-API-Key"] = API_KEY
        resp = requests.post(
            f"{SCRAPER_URL}/scrape",
            json=payload,
            headers=headers,
            timeout=120,
        )
        resp.raise_for_status()

        # Service returns JSON for crawl results, raw markdown for single-page fetches
        ct = resp.headers.get("Content-Type", "")
        if "application/json" in ct or resp.text.strip().startswith("{"):
            try:
                data = resp.json()
                md_content = data.get("markdown", "") or data.get("content", "") or ""
                final_url  = data.get("url", url)
                status     = data.get("status", "ok")
                links      = data.get("links", [])
                error      = data.get("error", "")
            except Exception:
                md_content = resp.text
                final_url, status, links, error = url, "ok", [], ""
        else:
            # Raw markdown response
            md_content = resp.text
            final_url, status, links, error = url, "ok", [], ""

        return {
            "success": bool(md_content.strip()),
            "md_content": md_content,
            "final_url": final_url,
            "status": status,
            "links": links,
            "error": error,
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
    """Save a scraped page as .md + .meta.json. Returns filename base."""
    slug = slugify_url(url)
    h = page_hash(url)
    base = f"{source_id}__{slug}__{h}"

    md_path  = pages_dir / f"{base}.md"
    meta_path = pages_dir / f"{base}.meta.json"

    if result["success"]:
        md_path.write_text(result["md_content"], encoding="utf-8")

    meta = {
        "url": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "final_url": result["final_url"],
        "cache_hit": False,
        "status": result["status"],
        "md_hash": hashlib.md5(result["md_content"].encode("utf-8")).hexdigest() if result["md_content"] else None,
        "md_bytes": len(result["md_content"].encode("utf-8")),
        "links_found": len(result.get("links", [])),
        "error": result.get("error", ""),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_id", nargs="?", help="Source identifier (e.g. docaviv)")
    parser.add_argument("source_name_he", nargs="?", help="Hebrew source name")
    parser.add_argument("urls", nargs="*", help="URLs to scrape")
    parser.add_argument("--file", "-f", help="File containing URLs (one per line)")
    parser.add_argument("--depth", type=int, default=MAX_DEPTH, help="Crawl depth")
    parser.add_argument("--no-follow", action="store_true", help="Don't follow links")
    args = parser.parse_args()

    # Collect URLs
    urls = list(args.urls) if args.urls else []
    if args.file:
        with open(args.file) as f:
            urls.extend(line.strip() for line in f if line.strip() and not line.startswith("#"))

    if not urls:
        parser.error("Provide URLs as arguments or via --file")

    if not args.source_id:
        # Auto-derive from first URL
        parsed = urllib.parse.urlparse(urls[0])
        args.source_id = parsed.netloc.replace("www.", "").split(".")[0]
        args.source_name_he = args.source_id

    depth = args.depth
    follow = not args.no_follow

    # Setup directories
    source_dir = SOURCES_DIR / args.source_id
    pages_dir  = source_dir / "pages"
    runs_dir   = source_dir / "runs"
    pages_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    # Run ID
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"Source: {args.source_id} ({args.source_name_he})")
    print(f"URLs:   {len(urls)}")
    print(f"Depth:  {depth}, Follow: {follow}")
    print(f"Output: {pages_dir}")
    print()

    # Crawl
    results = {"attempted": 0, "succeeded": 0, "failed": 0, "empty": 0}
    saved = []

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = {pool.submit(crawl_page, url, args.source_id, depth, follow): url for url in urls}
        for future in as_completed(futures):
            url = futures[future]
            results["attempted"] += 1
            try:
                result = future.result()
            except Exception as e:
                print(f"  ✗ {url}: {e}")
                results["failed"] += 1
                continue

            if result["success"]:
                results["succeeded"] += 1
                base = save_page(args.source_id, url, result, pages_dir)
                saved.append(base)
                print(f"  ✓ {url} → {base}.md ({len(result['md_content'].encode('utf-8'))} bytes)")
            elif result.get("error"):
                results["failed"] += 1
                save_page(args.source_id, url, result, pages_dir)
                print(f"  ✗ {url}: {result['error']}")
            else:
                results["empty"] += 1
                save_page(args.source_id, url, result, pages_dir)
                print(f"  - {url}: empty content")

    # Write manifest
    manifest = {
        "run_id": run_id,
        "source_id": args.source_id,
        "source_name_he": args.source_name_he,
        "tier": "B",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "scraper_url": SCRAPER_URL,
        "concurrency": CONCURRENCY,
        "follow_links": follow,
        "max_depth": depth,
        "scrape_options": {
            "format": "markdown",
            "fit_markdown": False,
            "ignore_links": False,
            "include_media": False,
            "include_links": True,
        },
        "stats": {
            "urls_discovered": len(urls),
            "urls_attempted": results["attempted"],
            "urls_succeeded": results["succeeded"],
            "urls_empty": results["empty"],
            "urls_failed": results["failed"],
            "cache_hits": 0,
            "total_md_bytes": 0,
            "files_downloaded": results["succeeded"],
            "files_failed": results["failed"],
            "total_file_bytes": 0,
            "duration_seconds": 0,
        },
        "urls": urls,
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nDone: {results['succeeded']} succeeded, {results['failed']} failed, {results['empty']} empty")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
