#!/usr/bin/env python3
"""Cinema of Israel scraper: Sitemap → film pages → data/cinemaofisrael/raw_films.json

walks 110 sub-sitemaps, classifies each URL as film/person/company,
extracts structured film data from film pages.

Usage: python3 scripts/cinemaofisrael/scrape_cinemaofisrael.py           # Full run
       python3 scripts/cinemaofisrael/scrape_cinemaofisrael.py --limit N  # Test
"""

import json, os, re, sys, time
from urllib.parse import unquote

import requests

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
SITEMAP_INDEX = "https://cinemaofisrael.co.il/sitemap.xml"
CHECKPOINT = "data/cinemaofisrael/raw_films.json"
CHECKPOINT_INDEX = "data/cinemaofisrael/_sitemap_index.json"

ROLE_MAP = {
    "בימוי": "director", "תסריט": "screenwriter", "הפקה": "producer",
    "צילום": "cinematographer", "עריכה": "editor",
    "מוסיקה": "composer", "מוסיקה מקורית": "composer",
    "עיצוב פסקול": "sound_designer", "עיצוב אמנותי": "production_designer",
    "עיצוב תלבושות": "costume_designer",
}


def _empty_record(source_id="", url=""):
    return {
        "source_key": "cinemaofisrael",
        "source_id": source_id, "url": url,
        "title_he": "", "title_en": None, "title_alt": [], "title_original": None,
        "year": None, "release_date_il": None, "is_short": False, "duration_min": None,
        "genre": None, "genre_he": None,
        "description_he": None, "description_en": None,
        "country": ["ישראל"], "language": None, "subtitles": [], "color": None, "format": None,
        "based_on": None,
        "funds": [], "production_companies": [], "distribution_companies": [],
        "broadcaster": None, "budget": None, "box_office_il": None,
        "crew": [], "cast": [],
        "festivals": [], "awards": [],
        "tags": [],
        "poster_url": None, "trailer_url": None, "watch_url": None,
        "related_films": [], "related_interviews": [],
    }


def fetch_sub_sitemaps() -> list:
    """Get sub-sitemap URLs from index — only post sitemaps (where films live).
    Skip the mega-sitemap (0000-00) which has 10k person pages, no films.
    Sort recent-first so films get processed before stale sitemaps."""
    r = requests.get(SITEMAP_INDEX, headers={"User-Agent": UA}, timeout=30)
    urls = re.findall(r"<loc>([^<]+sitemap[^<]*)</loc>", r.text, re.IGNORECASE)
    urls = [u for u in urls
            if "pt-post" in u and "misc" not in u
            and "0000-00" not in u]
    # Recent first — films are more likely in recent sitemaps
    urls.sort(reverse=True)
    print(f"  {len(urls)} post sitemaps (0000-00 excluded, recent-first)")
    return urls


def classify_url(url: str) -> str:
    """Quick pre-classification: skip known non-film patterns.
    Actual film determination happens on page fetch."""
    if "/person/" in url or "/company/" in url or "/category/" in url or "/tag/" in url:
        return "skip"
    slug = url.rstrip("/").split("/")[-1]
    if len(slug) < 2:
        return "skip"
    return "maybe_film"


def parse_ci(html: str, url: str) -> dict | None:
    """Parse a CI film page. Returns None if not a film page.
    Person pages have בימוי with film titles (with year in parentheses).
    Film pages have בימוי with crew names (no year)."""
    if "בימוי" not in html:
        return None
    # Person pages: בימוי section contains "(YYYY)" after film titles
    # Film pages: בימוי section contains crew names without years
    bimוי_start = html.find("בימוי")
    if bimוי_start > 0:
        bimוי_section = html[bimוי_start:bimוי_start + 2000]
        # Check if the בימוי section has year patterns like "(2020)" — person page
        if re.search(r'\(\d{4}\)', bimוי_section):
            return None

    rec = _empty_record()
    rec["url"] = url
    slug = url.rstrip("/").split("/")[-1]
    rec["source_id"] = slug

    # CI uses <td> based layout. Each crew field is:
    #   <td>LABEL</td> <td></td> <td><a>NAME</a></td>
    # Find all td-pairs with label→value
    td_rows = re.findall(
        r'<td[^>]*?color:#929496[^>]*?>\s*(בימוי|תסריט|הפקה|צילום|עריכה|מוסיקה|עיצוב פסקול|עיצוב אמנותי|עיצוב תלבושות)\s*</td>\s*<td[^>]*></td>\s*<td[^>]*?>(.*?)</td>',
        html, re.DOTALL
    )

    for role_he, values_html in td_rows:
        role_en = ROLE_MAP.get(role_he, "other")
        # Extract all names from this td
        names = re.findall(r'>([^<]{2,60})<', values_html)
        for name in names:
            name = name.strip()
            if name and len(name) > 1 and ";" not in name:
                rec["crew"].append({
                    "name_he": name, "role": role_en, "role_he": role_he, "edb_id": None
                })

    # Title: h1 contains everything, extract just the first part before 'במאי' or הופק
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
    if h1:
        raw = re.sub(r"<[^>]+>", "", h1.group(1)).strip()
        # Split at first known keyword
        for delimiter in ["במאי:", "במאי", "&rsaquo;", "›", "  "]:
            if delimiter in raw:
                rec["title_he"] = raw.split(delimiter)[0].strip()
                break
        if not rec["title_he"]:
            rec["title_he"] = raw

    # English title from "שם אחר" / "לועזי" td row
    en_m = re.search(
        r'<td[^>]*?>(?:שם אחר|לועזי)[^<]*</td>\s*<td[^>]*></td>\s*<td[^>]*?>\s*([^<]+)',
        html
    )
    if en_m:
        en = en_m.group(1).strip()
        if en and en != "-":
            rec["title_en"] = en
            rec["title_alt"].append(en)

    # Year / duration — strip HTML first since year/duration are in separate <span> tags
    clean_html = re.sub(r"<[^>]+>", " ", html)
    clean_html = re.sub(r"&rsaquo;", "›", clean_html)
    # Pattern: "YYYY / NNN דקות / ..." or "YYYY / NNNدقקות"
    yd = re.search(r"(\d{4})\s*/\s*(\d+)\s*דק", clean_html)
    if yd:
        year_val = int(yd.group(1))
        if 1900 <= year_val <= 2030:
            rec["year"] = year_val
        rec["duration_min"] = int(yd.group(2))
    else:
        # Fallback: itemprop="dateCreated" or "YYYY / NNN / -"
        yd2 = re.search(r'itemprop="dateCreated"[^>]*>(\d{4})<', html)
        if yd2:
            year_val = int(yd2.group(1))
            if 1900 <= year_val <= 2030:
                rec["year"] = year_val
        # Duration from itemprop
        dur_m = re.search(r'itemprop="duration"[^>]*>(\d+)', html)
        if dur_m:
            rec["duration_min"] = int(dur_m.group(1))

    # Language / color from year/duration line
    ydl = re.search(r"(\d{4})\s*/\s*(\d+)\s*דקות\s*/\s*(.*?)(?:<|$)", clean_html)
    if ydl:
        details = ydl.group(3).strip()
        parts = [p.strip() for p in details.split(",")]
        for p in parts:
            if p in ("עברית", "אנגלית", "ערבית", "צרפתית"):
                rec["language"] = [p]
            elif "צבע" in p:
                rec["color"] = True
            elif "שחור" in p:
                rec["color"] = False
            elif p in ("HD", "SD", "DCP", "35mm", "16mm"):
                rec["format"] = p

    # Cast — table rows under "משחק" section (td label="משחק" then cast table)
    cast_start = html.find(">משחק<")
    if cast_start > 0:
        cast_section = html[cast_start:cast_start + 10000]
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", cast_section, re.DOTALL)
        for row in rows:
            cells = re.findall(r"<td[^>]*?>\s*(.*?)\s*</td>", row, re.DOTALL)
            if len(cells) < 2:
                continue
            # Filter label rows
            if cells[0].strip() == "משחק":
                continue
            actor_raw = re.sub(r"<[^>]+>", "", cells[0]).strip()
            if len(actor_raw) < 2 or len(actor_raw) > 80:
                continue
            # Check if this is a label cell (not an actor name)
            if actor_raw in ("בימוי", "תסריט", "הפקה", "צילום", "עריכה", "מוסיקה",
                            "משחק", "חברה מפיקה", "תקציר"):
                continue
            character = re.sub(r"<[^>]+>", "", cells[1]).strip() if len(cells) >= 2 else None
            if character in ("-", ""):
                character = None
            rec["cast"].append({
                "name_he": actor_raw, "character": character, "edb_id": None
            })

    # Production company
    prod_m = re.search(
        r'<td[^>]*?>(?:חברת הפקה|חברה מפיקה)[^<]*</td>\s*<td[^>]*></td>\s*<td[^>]*?>\s*([^<]+)',
        html
    )
    if prod_m and prod_m.group(1).strip():
        rec["production_companies"] = [prod_m.group(1).strip()]

    # Release date
    rd_m = re.search(
        r'<td[^>]*?>(?:תאריך הפצה[^<]*)</td>\s*<td[^>]*></td>\s*<td[^>]*?>\s*([^<]+)',
        html
    )
    if rd_m:
        date_text = rd_m.group(1).strip()
        rd2 = re.search(r"(\d{4}-\d{2}-\d{2})", date_text)
        if rd2:
            rec["release_date_il"] = rd2.group(1)

    # Based on
    bo_m = re.search(
        r'<td[^>]*?>(?:מבוסס על)[^<]*</td>\s*<td[^>]*></td>\s*<td[^>]*?>\s*([^<]+)',
        html
    )
    if bo_m and bo_m.group(1).strip():
        rec["based_on"] = bo_m.group(1).strip()

    # Synopsis (under "תקציר" td)
    syn_start = html.find(">תקציר<")
    if syn_start > 0:
        # There's usually a <p> tag after the label row containing the text
        syn_area = html[syn_start:syn_start + 3000]
        syn_m = re.search(r'<p[^>]*>\s*(.*?)\s*</p>', syn_area, re.DOTALL)
        if syn_m:
            raw = re.sub(r"<[^>]+>", "", syn_m.group(1)).strip()
            if len(raw) > 20:
                rec["description_he"] = raw

    return rec


def main():
    limit = None
    for a in sys.argv[1:]:
        if a.startswith("--limit="):
            limit = int(a.split("=")[1])

    sub_sitemaps = fetch_sub_sitemaps()
    if limit:
        sub_sitemaps = sub_sitemaps[: max(1, limit // 50)]
        print(f"  TEST MODE: limited to {len(sub_sitemaps)} sitemaps")

    # Load checkpoint
    done = {}
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT, encoding="utf-8") as f:
            done = {d["url"]: d for d in json.load(f)}
        print(f"  Resuming from checkpoint: {len(done)} films already scraped")

    # Load sitemap index checkpoint (which sitemaps we've already fetched)
    sitemap_done = set()
    if os.path.exists(CHECKPOINT_INDEX):
        with open(CHECKPOINT_INDEX, encoding="utf-8") as f:
            sitemap_done = set(json.load(f))
        print(f"  {len(sitemap_done)} sitemaps already fetched")

    started = time.time()
    films_found = 0
    fetched_urls = set()

    for sm_idx, sm_url in enumerate(sub_sitemaps):
        if sm_url in sitemap_done:
            continue

        try:
            r = requests.get(sm_url, headers={"User-Agent": UA}, timeout=30)
            page_urls = re.findall(r"<loc>([^<]+)</loc>", r.text)
        except Exception as e:
            print(f"  ERROR sitemap {sm_url}: {e}")
            continue

        # Fetch each URL to classify by content
        for url in page_urls:
            if classify_url(url) == "skip":
                continue
            if url in done or url in fetched_urls:
                continue
            fetched_urls.add(url)

            try:
                r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
                if r.status_code != 200:
                    done[url] = {"source_key": "cinemaofisrael", "url": url,
                                 "status": "failed", "code": r.status_code}
                    continue

                rec = parse_ci(r.text, url)
                if rec is None:
                    done[url] = {"source_key": "cinemaofisrael", "url": url,
                                 "status": "not_a_film"}
                    continue

                films_found += 1
                done[url] = rec

            except Exception as e:
                done[url] = {"source_key": "cinemaofisrael", "url": url,
                             "status": "failed", "error": str(e)}

            time.sleep(0.3)

            # Save checkpoint every 10 URLs (not just per sitemap)
            if len(fetched_urls) % 10 == 0:
                with open(CHECKPOINT, "w", encoding="utf-8") as f:
                    json.dump(list(done.values()), f, ensure_ascii=False, indent=2)

        # Save sitemap checkpoint
        sitemap_done.add(sm_url)
        with open(CHECKPOINT_INDEX, "w", encoding="utf-8") as f:
            json.dump(sorted(sitemap_done), f)

        with open(CHECKPOINT, "w", encoding="utf-8") as f:
            json.dump(list(done.values()), f, ensure_ascii=False, indent=2)

        elapsed = time.time() - started
        ok = [d for d in done.values() if d.get("title_he")]
        print(f"  [{sm_idx+1}/{len(sub_sitemaps)}] {films_found} films from sitemap, "
              f"total OK: {len(ok)}, {elapsed/60:.0f}min")

        if limit and films_found >= limit:
            print(f"  Reached limit of {limit} films, stopping")
            break

    elapsed = time.time() - started
    ok = [d for d in done.values() if d.get("title_he")]
    with_crew = sum(1 for d in ok if d.get("crew"))
    with_cast = sum(1 for d in ok if d.get("cast"))
    print(f"\nDone: {len(ok)} CI films in {elapsed/60:.1f} min")
    print(f"  With crew: {with_crew}, with cast: {with_cast}")
    print(f"  → {CHECKPOINT}")


if __name__ == "__main__":
    main()