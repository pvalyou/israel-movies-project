#!/usr/bin/env python3
"""Phase 1a+1b: Collect all Israeli film IDs from EDB, then scrape each film's crew.

Usage:
  python3 scrape_edb.py             # Full run (collect IDs + scrape all)
  python3 scrape_edb.py --ids-only  # Only collect film IDs
  python3 scrape_edb.py --scrape-only  # Only scrape crews (requires edb_film_ids.json)
"""

import json
import os
import re
import sys
import time

import requests

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
BASE = "https://www.edb.co.il"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA})

ID_FILE = "data/edb/edb_film_ids.json"
CHECKPOINT = "data/edb/edb_films.json"

ROLE_MAP = {
    "בימוי": "director", "הפקה": "producer", "תסריט": "screenwriter",
    "עריכה": "editor", "צילום": "cinematographer",
    "מוסיקה מקורית": "composer", "עיצוב פסקול": "sound_designer",
    "שחקן": "actor", "שחקנית": "actor",
}


# ── Phase 1a: Collect film IDs ────────────────────────────────────────────────

def get_page_ids(url_template: str) -> set:
    all_ids, prev = set(), set()
    for page in range(1, 10000):
        url = url_template.format(page)
        try:
            resp = SESSION.get(url, timeout=15)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            print(f"  ERROR page {page}: {e}")
            break
        ids = set(re.findall(r'/title/(t\d+)/', html))
        if not ids or ids == prev:
            print(f"  done at page {page}, {len(all_ids)} films collected")
            break
        all_ids |= ids
        prev = ids
        if page % 10 == 0:
            print(f"  page {page}: {len(all_ids)} films so far")
        time.sleep(0.3)
    return all_ids


def collect_ids():
    print("=== Phase 1a: Collecting Israeli film IDs ===")
    print("  Fetching feature films (movies)...")
    film_ids = get_page_ids(BASE + "/browse/b/c/israel/t/movies/?p={}")
    print(f"  → {len(film_ids)} feature films")

    print("  Fetching shorts...")
    short_ids = get_page_ids(BASE + "/browse/b/c/israel/t/shorts/?p={}")
    print(f"  → {len(short_ids)} shorts")

    all_ids = film_ids | short_ids
    ids_obj = {
        "total": len(all_ids),
        "films": sorted(film_ids),
        "shorts": sorted(short_ids),
        "all": sorted(all_ids),
    }
    with open(ID_FILE, "w", encoding="utf-8") as f:
        json.dump(ids_obj, f, ensure_ascii=False, indent=2)
    print(f"Total: {len(all_ids)} films+shorts → {ID_FILE}")
    return ids_obj


# ── Phase 1b: Scrape each film's crew ─────────────────────────────────────────

def scrape_film(film_id: str, is_short: bool) -> dict | None:
    try:
        cast_resp = SESSION.get(f"{BASE}/title/{film_id}/cast/", timeout=15)
        cast_resp.raise_for_status()
        cast_html = cast_resp.text

        main_resp = SESSION.get(f"{BASE}/title/{film_id}/", timeout=15)
        main_resp.raise_for_status()
        main_html = main_resp.text
    except Exception as e:
        print(f"    ERROR {film_id}: {e}")
        return None

    title_m = re.search(r'og:title.*?content="([^"]+)"', main_html)
    year_m = re.search(r'\((\d{4})\)', main_html)
    if not year_m:
        year_m = re.search(r'"releaseYear":\s*"?(\d{4})', main_html)

    crew = []
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>', cast_html, re.DOTALL):
        name_m = re.search(r'href="/name/(n\d+)/"[^>]*>([^<]+)</a>', row)
        role_m = re.findall(r'<td[^>]*>\s*([^\n<]{2,40}?)\s*</td>', row)
        if name_m:
            role_he = role_m[-1].strip() if role_m else ""
            crew.append({
                "edb_id": name_m.group(1),
                "name_he": name_m.group(2).strip(),
                "role_he": role_he,
                "role": ROLE_MAP.get(role_he, "other"),
            })

    raw_title = title_m.group(1).split("(")[0].strip() if title_m else ""

    return {
        "film_id": film_id,
        "url": f"{BASE}/title/{film_id}/",
        "title": raw_title,
        "year": int(year_m.group(1)) if year_m else None,
        "is_short": is_short,
        "crew": crew,
    }


def scrape_crews(ids_obj):
    print("\n=== Phase 1b: Scraping film crews ===")
    if isinstance(ids_obj, dict):
        short_set = set(ids_obj.get("shorts", []))
        all_ids = ids_obj.get("all", [])
    else:
        short_set = set()
        all_ids = ids_obj

    done = {}
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT, encoding="utf-8") as f:
            existing = json.load(f)
        done = {f["film_id"]: f for f in existing}
        print(f"  loaded checkpoint: {len(done)} films already scraped")

    ids_todo = [i for i in all_ids if i not in done]
    print(f"  {len(ids_todo)} films to scrape, {len(done)} already done")

    started = time.time()
    for i, film_id in enumerate(ids_todo):
        is_short = film_id in short_set
        result = scrape_film(film_id, is_short)
        if result:
            done[film_id] = result

        if (i + 1) % 50 == 0:
            elapsed = time.time() - started
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            with open(CHECKPOINT, "w", encoding="utf-8") as f:
                json.dump(list(done.values()), f, ensure_ascii=False, indent=2)
            print(f"  checkpoint: {len(done)} films | {i+1}/{len(ids_todo)} "
                  f"({rate:.1f} films/min)")

        time.sleep(0.5)

    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(list(done.values()), f, ensure_ascii=False, indent=2)

    elapsed = time.time() - started
    total_films = len(done)
    total_crew = sum(len(f.get("crew", [])) for f in done.values())
    print(f"\nDone: {total_films} films, {total_crew} crew entries "
          f"in {elapsed/60:.1f} min → {CHECKPOINT}")
    return done


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ids_only = "--ids-only" in sys.argv
    scrape_only = "--scrape-only" in sys.argv

    if scrape_only:
        if not os.path.exists(ID_FILE):
            print(f"ERROR: {ID_FILE} not found. Run without --scrape-only first.")
            sys.exit(1)
        with open(ID_FILE, encoding="utf-8") as f:
            ids_obj = json.load(f)
        scrape_crews(ids_obj)
        return

    if ids_only:
        collect_ids()
        return

    ids_obj = collect_ids()
    scrape_crews(ids_obj)


if __name__ == "__main__":
    main()