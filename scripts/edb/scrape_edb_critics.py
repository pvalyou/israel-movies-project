#!/usr/bin/env python3
"""Phase 2: EDB blog review scraper (robust version with retry).
Outputs → out/edb_critics/mentions.jsonl
"""

import json
import os
import re
import sys
import time
from datetime import date

import requests

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
BASE = "https://www.edb.co.il"
CHECKPOINT = "data/edb/edb_blog_reviews.json"
OUTPUT_FILE = "out/edb_critics/mentions.jsonl"
ARTICLE_RANGE = range(18746, 30025)


def load_israeli_film_ids():
    if not os.path.exists("data/edb/edb_film_ids.json"):
        return None
    with open("data/edb/edb_film_ids.json", encoding="utf-8") as f:
        data = json.load(f)
    return set(data) if isinstance(data, list) else set(data.get("all", []))


def fetch(url, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
            return r
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise e


def scrape_article(aid):
    try:
        r = fetch(f"{BASE}/blog/archives/{aid}")
        if r.status_code == 404:
            return {"article_id": aid, "film_ids": []}
        if r.status_code != 200 or len(r.text) < 5000:
            return None
        html = r.text
    except Exception:
        return None

    title_m = re.search(r'og:title\s+content="([^"]+)"', html)
    date_m = re.search(r"(\d{1,2})\s+ב(\S+)\s+(\d{4})", html)

    # Author: internal EDB critic (/name/nXXXX/) or external
    m = re.search(
        r'מאת\s*<span\s+class="author_card_name"[^>]*>\s*<a\s+[^>]*href="[^"]*?/name/(n\d+)/"[^>]*>([^<]+)</a>',
        html)
    if not m:
        m = re.search(
            r'מאת\s*<span\s+class="author_card_name"[^>]*>\s*<a\s+[^>]*href="[^"]*"[^>]*>([^<]+)</a>',
            html)
    if not m:
        m = re.search(r'מאת\s*<a\s+href="[^"]*?/name/(n\d+)/"[^>]*>([^<]+)</a>', html)

    film_ids = sorted(set(re.findall(r"/title/(t\d+)/", html)))
    if not film_ids:
        return None  # Don't save — no film refs = not a review

    author_name = ""
    author_edb_id = ""
    if m:
        groups = m.groups()
        if len(groups) == 2:
            author_edb_id, author_name = groups[0], groups[1].strip()
        else:
            author_name = groups[0].strip()

    return {
        "article_id": aid,
        "title": title_m.group(1).strip() if title_m else "",
        "date": f"{date_m.group(1)} {date_m.group(2)} {date_m.group(3)}" if date_m else "",
        "year": int(date_m.group(3)) if date_m else None,
        "author_name": author_name,
        "author_edb_id": author_edb_id,
        "film_ids": film_ids,
        "url": f"{BASE}/blog/archives/{aid}",
    }


def export_reviews(done):
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    reviews = [d for d in done.values() if d.get("author_name") and d.get("film_ids")]
    print(f"\nExporting {len(reviews)} reviews to {OUTPUT_FILE}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        exported = 0
        for article in reviews:
            record = {
                "file": "",
                "url": article["url"],
                "source_name": "edb_critics",
                "status": "ok",
                "data": {
                    "metadata": {
                        "source_url": article["url"],
                        "source_name": "edb_critics",
                        "extraction_date": str(date.today()),
                        "language": "he",
                    },
                    "entities": {
                        "people": {
                            "critic_001": {
                                "name_he": article["author_name"],
                                "name_en": None,
                                "aliases": [],
                                "primary_roles": ["critic"],
                                "sources": [article["url"]],
                                "gender": "unknown",
                                "edb_id": article["author_edb_id"],
                            }
                        },
                        "films": {},
                    },
                    "roles": [],
                    "relationships": [
                        {
                            "source_id": "critic_001",
                            "source_type": "person",
                            "target_id": fid,
                            "target_type": "film",
                            "relationship_type": "reviewed",
                            "outlet": "edb",
                            "year": article.get("year"),
                        }
                        for fid in article["film_ids"]
                    ],
                },
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            exported += 1
    print(f"Exported {exported} reviews")


def main():
    israeli_ids = load_israeli_film_ids()
    print(f"Israeli film IDs loaded: {len(israeli_ids) if israeli_ids else 0}")

    done = {}
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT, encoding="utf-8") as f:
            done = {d["article_id"]: d for d in json.load(f)}
        print(f"Resuming from checkpoint: {len(done)} articles")

    todo = [i for i in ARTICLE_RANGE if i not in done]
    print(f"{len(todo)} articles to scan")

    started = time.time()
    consecutive_errors = 0
    for i, aid in enumerate(todo):
        result = scrape_article(aid)
        if result is None:
            consecutive_errors += 1
            if consecutive_errors > 50:
                print(f"  TOO MANY ERRORS ({consecutive_errors}), stopping")
                break
        else:
            consecutive_errors = 0
            if result.get("film_ids") and israeli_ids:
                il_films = set(result["film_ids"]) & israeli_ids
                result["israeli_films"] = sorted(il_films)

            done[aid] = result

        if (i + 1) % 100 == 0:
            elapsed = time.time() - started
            rate = (i + 1) / elapsed * 60 if elapsed > 0 else 0
            with open(CHECKPOINT, "w", encoding="utf-8") as f:
                json.dump(list(done.values()), f, ensure_ascii=False, indent=2)

            with_reviews = sum(1 for d in done.values() if d.get("author_name") and d.get("film_ids"))
            with_il = sum(1 for d in done.values()
                          if d.get("israeli_films") and len(d.get("israeli_films", [])) > 0)
            print(f"  [{len(done)}/{i+1}@{rate:.0f}/min] reviews:{with_reviews} il_reviews:{with_il}")

        time.sleep(0.1)

    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(list(done.values()), f, ensure_ascii=False, indent=2)

    elapsed = time.time() - started
    print(f"\nDone: {len(done)} articles in {elapsed/60:.1f} min")
    export_reviews(done)


if __name__ == "__main__":
    main()