#!/usr/bin/env python3
"""Quick batch scraper for festival URLs."""
import hashlib, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import requests

SCRAPER_URL = "https://crawl4ai-wrapper-559961100092.europe-west1.run.app"
API_KEY = ""
_env = Path(".env")
if _env.exists():
    for line in _env.read_text().splitlines():
        if line.startswith("CRAWL4AI_API_KEY="):
            API_KEY = line.split("=", 1)[1].strip()

def slug(url):
    p = urlparse(url).path.strip("/") or "root"
    return re.sub(r"[^a-zA-Z0-9\u0590-\u05FF-]", "_", p).strip("_")[:100]

def phash(url):
    return hashlib.md5(url.encode()).hexdigest()[:8]

def crawl(url):
    for attempt in range(3):
        try:
            r = requests.post(f"{SCRAPER_URL}/scrape",
                json={"url":url,"format":"markdown","fit_markdown":False,"ignore_links":False,"include_media":False,"include_links":True,"follow_links":False,"max_depth":0},
                headers={"X-API-Key":API_KEY} if API_KEY else {},
                timeout=120)
            if r.status_code == 429:
                time.sleep(10*(attempt+1)); continue
            r.raise_for_status()
            d = r.json()
            md = d.get("markdown","") or d.get("content","") or ""
            return {"ok":bool(md.strip()),"md":md,"url":d.get("url",url),"err":d.get("error","")}
        except Exception as e:
            if attempt<2: time.sleep(10); continue
            return {"ok":False,"md":"","url":url,"err":str(e)}

def save(url, res, pages_dir, prefix):
    s = slug(url); h = phash(url); b = f"{prefix}__{s}__{h}"
    if res["ok"]:
        (pages_dir/f"{b}.md").write_text(res["md"], encoding="utf-8")
    (pages_dir/f"{b}.meta.json").write_text(json.dumps({
        "url":url,"stable_id":b,"fetched_at":datetime.now(timezone.utc).isoformat(),
        "status":"ok" if res["ok"] else "error","md_bytes":len(res["md"].encode("utf-8")),
        "error":res["err"]
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return b

def main():
    url_file = sys.argv[1] if len(sys.argv)>1 else "sources/festival_data/all_urls.txt"
    source_id = sys.argv[2] if len(sys.argv)>2 else "festival_data"
    pages_dir = Path(f"sources/{source_id}/pages")
    pages_dir.mkdir(parents=True, exist_ok=True)
    prefix = source_id

    with open(url_file) as f:
        urls = [l.strip() for l in f if l.strip().startswith("http")]
    # Skip already saved
    new = []
    for u in urls:
        b = f"{prefix}__{slug(u)}__{phash(u)}"
        if not (pages_dir/f"{b}.md").exists():
            new.append(u)
    print(f"Total: {len(urls)}, New: {len(new)}")

    stats = {"ok":0,"fail":0,"bytes":0}
    done = 0
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(crawl, u): u for u in new}
        for f in as_completed(futures):
            url = futures[f]; done += 1
            try: r = f.result()
            except Exception as e: stats["fail"]+=1; print(f"  [{done}/{len(new)}] X {url}"); continue
            if r["ok"]:
                stats["ok"]+=1; stats["bytes"]+=len(r["md"].encode("utf-8"))
                save(url, r, pages_dir, prefix)
                label = url[:80]
                print(f"  [{done}/{len(new)}] V {label}")
            else:
                stats["fail"]+=1; save(url, r, pages_dir, prefix)
                print(f"  [{done}/{len(new)}] X {url[:80]}: {r['err'][:60]}")

    print(f"\nOK={stats['ok']}, FAIL={stats['fail']}, BYTES={stats['bytes']:,}")

if __name__=="__main__":
    main()
