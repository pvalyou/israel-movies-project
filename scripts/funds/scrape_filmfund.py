#!/usr/bin/env python3
"""Scrape filmfund.org.il (הקרן הישראלית לקולנוע) by enumerating movieId integers.
Output: data/funds/filmfund_films.json

Usage: python3 scripts/funds/scrape_filmfund.py [--max-id N]
"""
import json, re, sys, time, os
import requests

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
BASE_URL = "https://www.filmfund.org.il/Movie?movieId={}"
OUTPUT = "data/funds/filmfund_films.json"
DEFAULT_MAX_ID = 650


def parse_film_page(html, movie_id):
    # Title: h1 or h2 — filmfund pages have the Hebrew title prominently
    title = ""
    for pat in [r'<h1[^>]*>(.*?)</h1>', r'<h2[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</h2>']:
        m = re.search(pat, html, re.DOTALL)
        if m:
            t = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            if t and len(t) > 1:
                title = t
                break

    # Also try og:title
    if not title:
        og = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html)
        if og:
            title = og.group(1).strip()

    # Year: often in parentheses after title, or in a detail field
    year = None
    year_pats = [
        r'<[^>]*class="[^"]*year[^"]*"[^>]*>.*?(\d{4})',
        r'שנת\s+(?:הפקה|יצירה)[^<\d]*(\d{4})',
        r'\((\d{4})\)',
    ]
    for pat in year_pats:
        m = re.search(pat, html, re.IGNORECASE | re.DOTALL)
        if m:
            yr = int(m.group(1))
            if 1970 <= yr <= 2026:
                year = yr
                break

    # Director
    director = ""
    dm = re.search(r'(?:בימוי|Directed by)[^<:]*:?\s*<[^>]+>([^<]{2,60})', html, re.IGNORECASE)
    if not dm:
        dm = re.search(r'(?:בימוי)[^<:\d]*:?\s*([^\n<]{2,60})', html)
    if dm:
        director = re.sub(r'<[^>]+>', '', dm.group(1)).strip()

    # English title — often in a subtitle p tag
    title_en = ""
    en_m = re.search(r'<p[^>]*class="[^"]*(?:subtitle|english|latin)[^"]*"[^>]*>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
    if en_m:
        title_en = re.sub(r'<[^>]+>', '', en_m.group(1)).strip()

    return {
        "fund": "filmfund",
        "movie_id": movie_id,
        "title_he": title,
        "title_en": title_en or None,
        "year": year,
        "director": director or None,
        "url": BASE_URL.format(movie_id),
    }


def is_missing_page(html, status_code):
    if status_code == 404:
        return True
    if status_code != 200:
        return True
    # Filmfund redirects invalid IDs or shows empty content
    if len(html) < 2000:
        return True
    if "לא נמצא" in html or "not found" in html.lower():
        return True
    return False


def main():
    max_id = DEFAULT_MAX_ID
    for a in sys.argv[1:]:
        if a.startswith("--max-id="):
            max_id = int(a.split("=")[1])

    os.makedirs("data/funds", exist_ok=True)

    done = {}
    if os.path.exists(OUTPUT):
        with open(OUTPUT, encoding="utf-8") as f:
            for r in json.load(f):
                mid = r.get("movie_id")
                if mid is not None:
                    done[mid] = r
        print(f"  Resuming: {len(done)} IDs already checked")

    ok_count = sum(1 for r in done.values() if r.get("title_he"))
    print(f"  {ok_count} films found so far, checking IDs 1–{max_id}\n")

    started = time.time()
    for mid in range(1, max_id + 1):
        if mid in done:
            continue

        url = BASE_URL.format(mid)
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=15, allow_redirects=True)
            if is_missing_page(r.text, r.status_code):
                done[mid] = {"fund": "filmfund", "movie_id": mid, "title_he": "", "status": "missing"}
            else:
                rec = parse_film_page(r.text, mid)
                done[mid] = rec
                if rec.get("title_he"):
                    print(f"  [{mid}] {rec['title_he']} ({rec.get('year', '?')})")
        except Exception as e:
            done[mid] = {"fund": "filmfund", "movie_id": mid, "title_he": "", "status": "error", "error": str(e)}

        if mid % 50 == 0:
            elapsed = time.time() - started
            with open(OUTPUT, "w", encoding="utf-8") as f:
                json.dump(list(done.values()), f, ensure_ascii=False, indent=2)
            ok_count = sum(1 for r in done.values() if r.get("title_he"))
            print(f"  [ID {mid}/{max_id}, {elapsed:.0f}s] {ok_count} films found")

        time.sleep(0.4)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(list(done.values()), f, ensure_ascii=False, indent=2)

    ok = [r for r in done.values() if r.get("title_he")]
    print(f"\nDone: {len(ok)} filmfund films → {OUTPUT}")


if __name__ == "__main__":
    main()
