#!/usr/bin/env python3
"""Scrape NFCT (הקרן החדשה לקולנוע וטלוויזיה) film list via sitemaps.
Output: data/funds/nfct_films.json

Usage: python3 scripts/funds/scrape_nfct.py [--limit N]
"""
import json, re, sys, time, os
import requests

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
SITEMAPS = [
    "https://nfct.org.il/movies-sitemap.xml",
    "https://nfct.org.il/movies-sitemap2.xml",
]
OUTPUT = "data/funds/nfct_films.json"


def fetch_sitemap_urls():
    urls = []
    for sm in SITEMAPS:
        r = requests.get(sm, headers={"User-Agent": UA}, timeout=30)
        # <loc> entries may be CDATA-wrapped: <loc><![CDATA[url]]></loc>
        found = re.findall(r"<loc>(?:<!\[CDATA\[)?(https://nfct\.org\.il/blog/movies/[^<\]]+?)(?:\]\]>)?</loc>", r.text)
        urls.extend(found)
        print(f"  {sm}: {len(found)} URLs")
    return sorted(set(urls))


def parse_film_page(html, url):
    # Title: og:title is cleanest (already stripped of site name)
    title = ""
    og = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html)
    if og:
        title = og.group(1).strip()
        # Remove trailing " - NFCT" or similar site suffix
        title = re.sub(r'\s*[\-–|]\s*(?:nfct|הקרן החדשה|NFCT).*$', '', title, flags=re.IGNORECASE).strip()
    if not title:
        h1 = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
        if h1:
            title = re.sub(r'<[^>]+>', '', h1.group(1)).strip()

    # Year: look for structured field patterns in the page
    year = None
    for pat in [
        r'(?:שנה|year)[^<:\d]*:?\s*<[^>]*>(\d{4})',
        r'(?:שנה|year)[^<:\d]*:?\s*(\d{4})',
        r'"dateCreated"\s*:\s*"(\d{4})',
        r'<time[^>]*datetime="(\d{4})',
        r'\b((?:19|20)\d{2})\b',   # fallback: any year in range
    ]:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            yr = int(m.group(1))
            if 1980 <= yr <= 2026:
                year = yr
                break

    # Director: "בימוי:" label
    director = ""
    dm = re.search(r'<strong>\s*בימוי\s*:?\s*</strong>\s*:?\s*([^<\n]{2,60})', html)
    if not dm:
        dm = re.search(r'בימוי\s*:\s*([^<\n]{2,60})', html)
    if dm:
        director = re.sub(r'<[^>]+>', '', dm.group(1)).strip().rstrip(',')

    # Genre from p tag near film card
    genre = ""
    gm = re.search(r'<p[^>]*>\s*(עלילתי|תיעודי|אנימציה|קצר|סטודנטים|ניסיוני)', html)
    if gm:
        genre = gm.group(1)

    return {
        "fund": "nfct",
        "title_he": title,
        "year": year,
        "director": director,
        "genre": genre,
        "url": url,
    }


def main():
    limit = None
    for a in sys.argv[1:]:
        if a.startswith("--limit="):
            limit = int(a.split("=")[1])

    os.makedirs("data/funds", exist_ok=True)

    done = {}
    if os.path.exists(OUTPUT):
        with open(OUTPUT, encoding="utf-8") as f:
            for r in json.load(f):
                done[r["url"]] = r
        print(f"  Resuming: {len(done)} already scraped")

    print("Fetching NFCT sitemaps...")
    urls = fetch_sitemap_urls()
    print(f"  {len(urls)} total film URLs")
    if limit:
        urls = urls[:limit]
        print(f"  TEST: limited to {limit}")
    todo = [u for u in urls if u not in done]
    print(f"  {len(todo)} to fetch\n")

    started = time.time()
    for i, url in enumerate(todo):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
            if r.status_code == 200:
                rec = parse_film_page(r.text, url)
                done[url] = rec
            else:
                done[url] = {"fund": "nfct", "url": url, "title_he": "", "status": f"http_{r.status_code}"}
        except Exception as e:
            done[url] = {"fund": "nfct", "url": url, "title_he": "", "status": "error", "error": str(e)}

        if (i + 1) % 50 == 0:
            elapsed = time.time() - started
            rate = (i + 1) / elapsed * 60
            with open(OUTPUT, "w", encoding="utf-8") as f:
                json.dump(list(done.values()), f, ensure_ascii=False, indent=2)
            ok = sum(1 for r in done.values() if r.get("title_he"))
            print(f"  [{i+1}/{len(todo)} @{rate:.0f}/min] {ok} with title")

        time.sleep(0.4)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(list(done.values()), f, ensure_ascii=False, indent=2)

    ok = [r for r in done.values() if r.get("title_he")]
    with_year = sum(1 for r in ok if r.get("year"))
    print(f"\nDone: {len(ok)} NFCT films, {with_year} with year → {OUTPUT}")


if __name__ == "__main__":
    main()
