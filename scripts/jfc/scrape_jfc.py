#!/usr/bin/env python3
"""JFC scraper: fetches /movie-sitemap.xml → ~929 movie pages → data/jfc/raw_films.json

Usage: python3 scripts/jfc/scrape_jfc.py           # Full run
       python3 scripts/jfc/scrape_jfc.py --limit N  # Test with N films
"""

import json, os, re, sys, time
from html import unescape

import requests

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
SITEMAP_URL = "https://jfc.org.il/movie-sitemap.xml"
CHECKPOINT = "data/jfc/raw_films.json"

ROLE_LOOKUP = {
    "שחקן": "actor", "שחקנית": "actor",
    "במאי": "director", "בימוי": "director",
    "תסריטאי": "screenwriter", "תסריט": "screenwriter", "תסריטאית": "screenwriter",
    "מפיק": "producer", "הפקה": "producer", "מפיקה": "producer",
    "צלם": "cinematographer", "צילום": "cinematographer", "צלמת": "cinematographer",
    "עורך": "editor", "עריכה": "editor", "עורכת": "editor",
    "מלחין": "composer", "מוסיקה": "composer", "מוזיקה": "composer",
    "יוצר": "creator", "יוצרת": "creator", "יצירה": "creator",
    "עורך פסקול": "sound_designer", "עיצוב פסקול": "sound_designer",
}


def fetch_sitemap_urls() -> list:
    print("Fetching JFC movie sitemap...")
    r = requests.get(SITEMAP_URL, headers={"User-Agent": UA}, timeout=30)
    urls = re.findall(r"<loc>([^<]+/movie/[^<]*)</loc>", r.text)
    # Remove the root /movie/ entry
    urls = [u for u in urls if u.rstrip("/") != "https://jfc.org.il/movie"]
    urls = sorted(set(urls))
    print(f"  {len(urls)} unique movie URLs")
    return urls


def extract_year_duration(text: str) -> tuple:
    """Extract (year, duration_min) from page text."""
    # Pattern 1: "YYYY, NNN דקות" or "YYYY, NNNmin"
    m = re.search(r"(\d{4})[,\s]*(\d+)\s*דק", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    # Pattern 2: "NNN דקות, YYYY"
    m = re.search(r"(\d+)\s*דק[,\s]*(\d{4})", text)
    if m:
        return int(m.group(2)), int(m.group(1))
    return None, None


def parse_jfc(html: str, url: str) -> dict:
    """Parse a JFC movie page."""
    record = {
        "source_key": "jfc",
        "source_id": "",
        "url": url,
        "title_he": "", "title_en": None, "title_alt": [], "title_original": None,
        "year": None, "release_date_il": None, "is_short": False, "duration_min": None,
        "genre": None, "genre_he": None,
        "description_he": "", "description_en": None,
        "country": ["ישראל"], "language": None, "subtitles": [], "color": None, "format": None,
        "based_on": None,
        "funds": [], "production_companies": [], "distribution_companies": [], "broadcaster": None,
        "budget": None, "box_office_il": None,
        "crew": [], "cast": [],
        "festivals": [], "awards": [],
        "tags": [],
        "poster_url": None, "trailer_url": None, "watch_url": None,
        "related_films": [], "related_interviews": [],
    }

    # ID from URL
    m = re.search(r"/movie/([^/]+)", url)
    if m:
        record["source_id"] = m.group(1).rstrip("/")

    # Title from h1
    h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
    if h1_m:
        record["title_he"] = re.sub(r"<[^>]+>", "", h1_m.group(1)).strip()

    # JSON-LD extraction
    ld_match = re.search(
        r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL
    )
    if ld_match:
        try:
            data = json.loads(ld_match.group(1))
            if isinstance(data, dict):
                _extract_ld_data(data, record)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        _extract_ld_data(item, record)
        except json.JSONDecodeError:
            pass

    # Year / duration from page text (if not from LD).
    # Crop HTML before the history/carousel sidebar to avoid picking up years
    # Year / duration — extract from the film's own content_subtitle div.
    # Pattern: <div class="content_subtitle">62 דקות, 1995</div>
    if record["year"] is None:
        # Method 1: content_subtitle div (most reliable)
        sub_m = re.search(r'class="content_subtitle[^"]*">\s*(\d+)\s*דק(?:ות)?[,\s]+(\d{4})', html)
        if sub_m:
            dur_val = int(sub_m.group(1))
            year_val = int(sub_m.group(2))
            if 1900 <= year_val <= 2030:
                record["year"] = year_val
                record["duration_min"] = dur_val
        else:
            # Method 2: content_subtitle with year first
            sub_m2 = re.search(r'class="content_subtitle[^"]*">\s*(\d{4})[,\s]+(\d+)\s*דק', html)
            if sub_m2:
                year_val = int(sub_m2.group(1))
                dur_val = int(sub_m2.group(2))
                if 1900 <= year_val <= 2030:
                    record["year"] = year_val
                    record["duration_min"] = dur_val
            else:
                # Method 3: any "XX דקות, YYYY" in the main content area
                # Find the film's title position, then search nearby
                title_pos = html.find(record["title_he"])
                if title_pos > 0:
                    nearby = html[title_pos:title_pos+2000]
                    sub_m3 = re.search(r'(\d+)\s*דק(?:ות)?[,\s]+(\d{4})', nearby)
                    if sub_m3:
                        dur_val = int(sub_m3.group(1))
                        year_val = int(sub_m3.group(2))
                        if 1900 <= year_val <= 2030:
                            record["year"] = year_val
                            record["duration_min"] = dur_val

    # Tags from /topic/ links
    topic_links = re.findall(r'href="(/topic/[^"]+)"[^>]*>([^<]+)</a>', html, re.IGNORECASE)
    record["tags"] = sorted(set(t.strip() for _, t in topic_links if t.strip()))

    # Poster image
    og_img = re.search(r'<meta\s+property="og:image"[^>]*content="([^"]+)"', html)
    if og_img:
        record["poster_url"] = og_img.group(1)

    # Description from og:description
    og_desc = re.search(r'<meta\s+property="og:description"[^>]*content="([^"]+)"', html)
    if og_desc:
        desc = unescape(og_desc.group(1)).strip()
        if len(desc) > 50:
            record["description_he"] = desc

    # Structured role sections in JFC HTML
    role_sections = [
        ("בימוי", "director"), ("תסריט", "screenwriter"), ("הפקה", "producer"),
        ("צילום", "cinematographer"), ("עריכה", "editor"), ("מוזיקה", "composer"),
        ("משחק", "actor"),
    ]
    for role_he, role_en in role_sections:
        # Pattern: "Role: Name, Year" or "Role: Name" with links
        section_m = re.search(
            rf'{role_he}\s*:\s*<a[^>]*href="[^"]*"[^>]*>([^<]+)</a>',
            html
        )
        if section_m:
            name = section_m.group(1).strip()
            if name and name not in {"", " ", "-"}:
                existing = [c for c in record["crew"] if c["name_he"] == name and c["role"] == role_en]
                if not existing:
                    record["crew"].append({
                        "name_he": name, "role": role_en, "role_he": role_he, "edb_id": None
                    })

    return record


def _extract_ld_data(data: dict, record: dict):
    """Populate record from JSON-LD schema data.
    JFC nests Movie under @graph dict with integer mixin keys.
    """
    # JFC puts Movie fields inside the @graph dict (alongside integer-keyed items)
    graph = data.get("@graph", {})
    mov = None
    if isinstance(graph, dict):
        # Movie fields are directly on the @graph dict (mixed with WebPage/Breadcrumb/etc)
        if graph.get("director") or graph.get("actor") or graph.get("@type") == "Movie":
            mov = graph
        else:
            for key, item in graph.items():
                if isinstance(item, dict) and item.get("@type") == "Movie":
                    mov = item
                    break
    elif isinstance(graph, list):
        for item in graph:
            if isinstance(item, dict) and item.get("@type") == "Movie":
                mov = item
                break

    if mov is None:
        return

    if mov.get("name") and (not record["title_he"] or len(mov["name"]) > len(record["title_he"])):
        record["title_he"] = mov["name"]

    desc = mov.get("description", "")
    if desc and len(desc) > len(record.get("description_he", "") or ""):
        record["description_he"] = re.sub(r"<[^>]+>", " ", desc).strip()

    # Directors
    for d in mov.get("director", []):
        name = (d.get("name") if isinstance(d, dict) else str(d)) if d else None
        if name:
            existing = [c for c in record["crew"] if c["name_he"] == name and c["role"] == "director"]
            if not existing:
                record["crew"].append({"name_he": name, "role": "director", "role_he": "בימוי", "edb_id": None})

    # Actors
    for a in mov.get("actor", []):
        name = (a.get("name") if isinstance(a, dict) else str(a)) if a else None
        character = (a.get("characterName", "") if isinstance(a, dict) else "") if a else ""
        if name:
            existing = [c for c in record["cast"] if c["name_he"] == name]
            if not existing:
                record["cast"].append({"name_he": name, "character": character or None, "edb_id": None})

    # Date
    dc = mov.get("dateCreated")
    if dc and record["year"] is None:
        m = re.search(r"(\d{4})", str(dc))
        if m:
            record["year"] = int(m.group(1))

    # Duration (ISO 8601)
    dur = mov.get("duration", "")
    dur_m = re.search(r"(\d+)", str(dur))
    if dur_m and record["duration_min"] is None:
        record["duration_min"] = int(dur_m.group(1))

    # Genre
    genre = mov.get("genre", [])
    if genre:
        if isinstance(genre, list):
            genre = genre[0]
        if isinstance(genre, str):
            record["genre"] = genre.lower()


def main():
    limit = None
    for a in sys.argv[1:]:
        if a.startswith("--limit="):
            limit = int(a.split("=")[1])

    urls = fetch_sitemap_urls()
    if limit:
        urls = urls[:limit]
        print(f"  TEST MODE: limited to {limit} films")

    # Load checkpoint — but exclude failed entries so they get retried
    done = {}
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT, encoding="utf-8") as f:
            for r in json.load(f):
                if r.get("status") == "failed":
                    continue  # retry failed entries
                done[r["url"]] = r
        print(f"  Resuming from checkpoint: {len(done)} films already scraped")

    todo = [u for u in urls if u not in done]
    print(f"  {len(todo)} films to scrape (including retries)\n")

    started = time.time()
    for i, url in enumerate(todo):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
            if r.status_code != 200:
                done[url] = {"source_key": "jfc", "url": url, "status": "failed", "code": r.status_code}
            else:
                rec = parse_jfc(r.text, url)
                done[url] = rec
        except Exception as e:
            done[url] = {"source_key": "jfc", "url": url, "status": "failed", "error": str(e)}

        if (i + 1) % 50 == 0:
            elapsed = time.time() - started
            rate = (i + 1) / elapsed * 60 if elapsed > 0 else 0
            with open(CHECKPOINT, "w", encoding="utf-8") as f:
                json.dump(list(done.values()), f, ensure_ascii=False, indent=2)
            with_crew = sum(1 for r in done.values() if r.get("crew"))
            with_cast = sum(1 for r in done.values() if r.get("cast"))
            print(f"  [{i+1}/{len(todo)} @{rate:.0f}/min] crew:{with_crew} cast:{with_cast}")

        time.sleep(0.5)

    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(list(done.values()), f, ensure_ascii=False, indent=2)

    elapsed = time.time() - started
    ok = [r for r in done.values() if not r.get("status") == "failed"]
    with_crew = sum(1 for r in ok if r.get("crew"))
    with_cast = sum(1 for r in ok if r.get("cast"))
    with_desc = sum(1 for r in ok if r.get("description_he"))
    print(f"\nDone: {len(ok)} films in {elapsed/60:.1f} min")
    print(f"  With crew: {with_crew}, with cast: {with_cast}, with description: {with_desc}")
    print(f"  → {CHECKPOINT}")


if __name__ == "__main__":
    main()