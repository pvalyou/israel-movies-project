#!/usr/bin/env python3
"""
scrape_nfct_professional.py — Deep scrape of NFCT מידע מקצועי section.

Fetches the landing page, extracts all internal links, recursively scrapes
every sub-page, and writes a detailed report.

Usage:
    python3 scrape_nfct_professional.py
"""

import hashlib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

# ── Config ────────────────────────────────────────────────────────────────────

SCRAPER_URL = "https://crawl4ai-wrapper-559961100092.europe-west1.run.app"
API_KEY = os.environ.get("CRAWL4AI_API_KEY", "")
_env = Path(".env")
if _env.exists() and not API_KEY:
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line.startswith("CRAWL4AI_API_KEY="):
            API_KEY = line.split("=", 1)[1].strip()

CONCURRENCY = 8
BASE_URL = "https://nfct.org.il"
LANDING_URL = "https://nfct.org.il/מידע-מקצועי/"
PAGES_DIR = Path("sources/nfct/pages")
REPORT_FILE = Path("sources/nfct/professional_scrape_report.json")

PAGES_DIR.mkdir(parents=True, exist_ok=True)

# ── Helpers ───────────────────────────────────────────────────────────────────

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

def is_internal(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc in ("nfct.org.il", "www.nfct.org.il", "")

def is_relevant(url: str) -> bool:
    """Only scrape pages that look like professional content, not admin/assets."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    skip = [
        "/wp-content/", "/wp-includes/", "/wp-admin/", "/wp-json/",
        "/feed/", "/xmlrpc.php",
        ".jpg", ".jpeg", ".png", ".gif", ".svg", ".pdf", ".zip",
        ".css", ".js",
    ]
    for s in skip:
        if s in path:
            return False
    return True

def crawl_page(url: str, depth: int = 0) -> dict:
    """Send a single URL to the scraper service (depth=0, no link following)."""
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
        data = resp.json()

        md_content = data.get("markdown", "") or data.get("content", "") or ""
        final_url  = data.get("url", url)
        links      = data.get("links", [])
        status     = data.get("status", "ok")

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

def extract_links_from_md(md_content: str, base_url: str) -> list:
    """Extract href URLs from markdown links [text](url)."""
    urls = set()
    for match in re.finditer(r'\[([^\]]*)\]\(([^)]+)\)', md_content):
        url = match.group(2).strip()
        if url.startswith('#'):
            continue
        full = urljoin(base_url, url)
        if is_internal(full) and is_relevant(full):
            # Strip fragment
            full = full.split('#')[0]
            urls.add(full)
    return list(urls)

def save_page(url: str, result: dict) -> str:
    """Save scraped page as .md + .meta.json."""
    slug = slugify_url(url)
    h = page_hash(url)
    base = f"nfct__{slug}__{h}"

    md_path  = PAGES_DIR / f"{base}.md"
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

# ── Already scraped? ─────────────────────────────────────────────────────────

def already_scraped(url: str) -> bool:
    """Check if a URL was already scraped in the existing NFCT data."""
    slug = slugify_url(url)
    h = page_hash(url)
    base = f"nfct__{slug}__{h}"
    return (PAGES_DIR / f"{base}.md").exists() or (PAGES_DIR / f"{base}.meta.json").exists()

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("NFCT מידע מקצועי — Deep Scrape")
    print("=" * 60)

    # Step 1: Crawl landing page
    print(f"\n[1] Fetching landing page: {LANDING_URL}")
    result = crawl_page(LANDING_URL)

    if not result["success"]:
        print(f"    FAILED: {result.get('error', 'unknown')}")
        return

    save_page(LANDING_URL, result)
    print(f"    OK — {len(result['md_content'])} chars, {len(result.get('links', []))} links in response")

    # Step 2: Extract links from markdown content + response links
    discovered = set()

    # From markdown links
    md_links = extract_links_from_md(result["md_content"], LANDING_URL)
    discovered.update(md_links)
    print(f"\n[2] Extracted {len(md_links)} internal links from markdown content")

    # From scraper response links
    for link in result.get("links", []):
        href = link.get("href", link.get("url", "")) if isinstance(link, dict) else link
        if href and is_internal(href) and is_relevant(href):
            href = href.split('#')[0]
            discovered.add(href)
    print(f"    + {len(result.get('links', []))} links from scraper response")

    # Step 3: Also check existing NFCT meta.json for URLs under מידע-מקצועי
    import glob as _glob
    existing_prof = set()
    for mf in _glob.glob("sources/nfct/pages/*.meta.json"):
        d = json.load(open(mf))
        u = d.get("url", "")
        if u and ("מידע-מקצועי" in u or "%D7%9E%D7%99%D7%93%D7%A2-%D7%9E%D7%A7%D7%A6%D7%95%D7%A2%D7%99" in u):
            clean = u.split('#')[0]
            existing_prof.add(clean)

    print(f"\n[3] Found {len(existing_prof)} existing pages under מידע-מקצועי")

    # Step 4: For each existing page, re-crawl to extract sub-links
    print(f"\n[4] Re-crawling existing pages to discover sub-links...")
    existing_urls = sorted(existing_prof)
    sub_links_found = 0

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = {pool.submit(crawl_page, u): u for u in existing_urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                r = future.result()
            except Exception:
                continue
            if r["success"]:
                # Extract sub-links
                sub = extract_links_from_md(r["md_content"], url)
                for s in sub:
                    if is_relevant(s):
                        discovered.add(s)
                        sub_links_found += 1
                save_page(url, r)

    print(f"    Found {sub_links_found} additional sub-links from existing pages")

    # Step 5: Deduplicate and filter
    all_urls = sorted(discovered - {LANDING_URL})
    # Remove URLs already scraped
    to_scrape = [u for u in all_urls if not already_scraped(u)]
    already = [u for u in all_urls if already_scraped(u)]

    print(f"\n[5] Discovery summary:")
    print(f"    Total unique URLs discovered: {len(all_urls)}")
    print(f"    Already scraped:              {len(already)}")
    print(f"    Need to scrape:               {len(to_scrape)}")

    # Step 6: Scrape new URLs
    if to_scrape:
        print(f"\n[6] Scraping {len(to_scrape)} new pages...")
        stats = {"succeeded": 0, "failed": 0, "empty": 0, "total_bytes": 0}
        details = []

        with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            futures = {pool.submit(crawl_page, u): u for u in to_scrape}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    r = future.result()
                except Exception as e:
                    stats["failed"] += 1
                    details.append({"url": url, "status": "exception", "error": str(e), "bytes": 0})
                    print(f"    ✗ {url}: {e}")
                    continue

                if r["success"]:
                    stats["succeeded"] += 1
                    b = len(r["md_content"].encode("utf-8"))
                    stats["total_bytes"] += b
                    save_page(url, r)
                    details.append({"url": url, "status": "ok", "error": "", "bytes": b})
                    print(f"    ✓ {url} ({b} bytes)")
                elif r.get("error"):
                    stats["failed"] += 1
                    save_page(url, r)
                    details.append({"url": url, "status": "error", "error": r["error"], "bytes": 0})
                    print(f"    ✗ {url}: {r['error']}")
                else:
                    stats["empty"] += 1
                    save_page(url, r)
                    details.append({"url": url, "status": "empty", "error": "", "bytes": 0})
                    print(f"    - {url}: empty")
    else:
        stats = {"succeeded": 0, "failed": 0, "empty": 0, "total_bytes": 0}
        details = []
        print(f"\n[6] No new pages to scrape!")

    # Step 7: Write report
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "landing_url": LANDING_URL,
        "discovery": {
            "total_unique_urls": len(all_urls),
            "already_scraped": len(already),
            "new_pages_scraped": stats["succeeded"],
            "new_pages_failed": stats["failed"],
            "new_pages_empty": stats["empty"],
            "total_new_bytes": stats["total_bytes"],
        },
        "all_discovered_urls": sorted(all_urls),
        "already_scraped_urls": sorted(already),
        "scrape_details": details,
    }

    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # Step 8: Print summary
    print(f"\n{'=' * 60}")
    print(f"REPORT")
    print(f"{'=' * 60}")
    print(f"Landing page:           {LANDING_URL}")
    print(f"Total URLs discovered:  {len(all_urls)}")
    print(f"Already scraped:        {len(already)}")
    print(f"New pages — succeeded:  {stats['succeeded']}")
    print(f"New pages — failed:     {stats['failed']}")
    print(f"New pages — empty:      {stats['empty']}")
    print(f"New content bytes:      {stats['total_bytes']:,}")
    print(f"Report saved to:        {REPORT_FILE}")

    # Print failed URLs
    failed = [d for d in details if d["status"] in ("error", "exception")]
    if failed:
        print(f"\nFailed URLs ({len(failed)}):")
        for f in failed:
            print(f"  ✗ {f['url']}: {f['error']}")

    # Print empty URLs
    empty = [d for d in details if d["status"] == "empty"]
    if empty:
        print(f"\nEmpty URLs ({len(empty)}):")
        for e in empty:
            print(f"  - {e['url']}")

if __name__ == "__main__":
    main()
