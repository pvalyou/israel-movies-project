#!/usr/bin/env python3
"""
scrape_nfct_batch.py — Rate-limited batch scraper for NFCT URLs.

Reads URLs from a file, scrapes with concurrency=5 and retry on 429.

Usage:
    python3 scrape_nfct_batch.py <url_file> <source_id>
"""

import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

SCRAPER_URL = "https://crawl4ai-wrapper-559961100092.europe-west1.run.app"
API_KEY = os.environ.get("CRAWL4AI_API_KEY", "")
_env = Path(".env")
if _env.exists() and not API_KEY:
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line.startswith("CRAWL4AI_API_KEY="):
            API_KEY = line.split("=", 1)[1].strip()

CONCURRENCY = 3
MAX_RETRIES = 5
RETRY_DELAY = 10  # seconds

PAGES_DIR = Path("sources/nfct/pages")
PAGES_DIR.mkdir(parents=True, exist_ok=True)


def slugify_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        path = "root"
    slug = re.sub(r"[^a-zA-Z0-9\u0590-\u05FF-]", "_", path)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:100]


def page_hash(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()[:8]


def already_scraped(url: str) -> bool:
    slug = slugify_url(url)
    h = page_hash(url)
    base = f"nfct__{slug}__{h}"
    return (PAGES_DIR / f"{base}.md").exists()


def crawl_page(url: str) -> dict:
    payload = {
        "url": url,
        "format": "markdown",
        "fit_markdown": False,
        "ignore_links": False,
        "include_media": False,
        "include_links": True,
        "follow_links": False,
        "max_depth": 0,
    }
    headers = {}
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(
                f"{SCRAPER_URL}/scrape",
                json=payload,
                headers=headers,
                timeout=120,
            )
            if resp.status_code == 429:
                wait = RETRY_DELAY * (attempt + 1)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            md_content = data.get("markdown", "") or data.get("content", "") or ""
            return {
                "success": bool(md_content.strip()),
                "md_content": md_content,
                "final_url": data.get("url", url),
                "status": data.get("status", "ok"),
                "links": data.get("links", []),
                "error": data.get("error", ""),
            }
        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            return {
                "success": False,
                "md_content": "",
                "final_url": url,
                "status": "error",
                "links": [],
                "error": str(e),
            }


def save_page(url: str, result: dict) -> str:
    slug = slugify_url(url)
    h = page_hash(url)
    base = f"nfct__{slug}__{h}"
    md_path = PAGES_DIR / f"{base}.md"
    meta_path = PAGES_DIR / f"{base}.meta.json"

    if result["success"]:
        md_path.write_text(result["md_content"], encoding="utf-8")

    meta = {
        "url": url,
        "stable_id": base,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "scraper_url": SCRAPER_URL,
        "scraper_options": {"format": "markdown", "follow_links": False, "max_depth": 0},
        "final_url": result["final_url"],
        "cache_hit": False,
        "status": result["status"],
        "md_hash": hashlib.sha256(result["md_content"].encode("utf-8")).hexdigest() if result["md_content"] else None,
        "md_bytes": len(result["md_content"].encode("utf-8")),
        "links_found": len(result.get("links", [])),
        "error": result.get("error", ""),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return base


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <url_file> <source_id>")
        sys.exit(1)

    url_file = sys.argv[1]
    source_id = sys.argv[2]

    with open(url_file) as f:
        urls = [line.strip() for line in f if line.strip() and line.startswith("http")]

    # Skip already scraped
    urls = [u for u in urls if not already_scraped(u)]
    print(f"URLs to scrape: {len(urls)}")

    stats = {"succeeded": 0, "failed": 0, "empty": 0, "total_bytes": 0, "skipped": 0}
    details = []
    done = 0

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = {pool.submit(crawl_page, u): u for u in urls}
        for future in as_completed(futures):
            url = futures[future]
            done += 1
            try:
                r = future.result()
            except Exception as e:
                stats["failed"] += 1
                details.append({"url": url, "status": "exception", "error": str(e), "bytes": 0})
                print(f"  [{done}/{len(urls)}] ✗ {url}: {e}")
                continue

            if r["success"]:
                stats["succeeded"] += 1
                b = len(r["md_content"].encode("utf-8"))
                stats["total_bytes"] += b
                save_page(url, r)
                details.append({"url": url, "status": "ok", "error": "", "bytes": b})
                print(f"  [{done}/{len(urls)}] ✓ {url} ({b} bytes)")
            elif r.get("error"):
                stats["failed"] += 1
                save_page(url, r)
                details.append({"url": url, "status": "error", "error": r["error"], "bytes": 0})
                print(f"  [{done}/{len(urls)}] ✗ {url}: {r['error']}")
            else:
                stats["empty"] += 1
                save_page(url, r)
                details.append({"url": url, "status": "empty", "error": "", "bytes": 0})
                print(f"  [{done}/{len(urls)}] - {url}: empty")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"SUMMARY")
    print(f"{'=' * 60}")
    print(f"Succeeded: {stats['succeeded']}")
    print(f"Failed:    {stats['failed']}")
    print(f"Empty:     {stats['empty']}")
    print(f"Bytes:     {stats['total_bytes']:,}")

    # Write report
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "source_id": source_id,
        "url_file": url_file,
        "stats": stats,
        "details": details,
    }
    report_path = Path(f"sources/nfct/batch_report_{source_id}.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
