#!/usr/bin/env python3
"""Scrape labs.jsfs.co.il sitemap and extract people/film entities.
Uses proper HTML parsing for clean text extraction.

Usage: python3 scripts/scrape_jsfs_labs.py [--limit N] [--dry-run] [--reparse]
"""
import argparse
import datetime
import json
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests library required. pip install requests", file=sys.stderr)
    sys.exit(1)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
OUTPUT = Path("out/jsfs_labs/mentions.jsonl")
SOURCE_NAME = "jsfs_labs"
TODAY = datetime.date.today().isoformat()

SUB_SITEMAPS = [
    "dynamic-participants_p_ba2bdb7a_0e2d_4286_8a8d_b71d00e789ee_0_5000-sitemap.xml",
    "dynamic-filmslabs_p_7918578a_fe22_4f4b_9d25_e9cc22a93fe9_0_5000-sitemap.xml",
    "dynamic-seriesparticipants_p_50d83a62_1bd8_4254_a106_b614fa696b4b_0_5000-sitemap.xml",
    "dynamic-participants-filmlab-catalog_p_e722d553_567e_47d9_8013_1da7507b27c0_0_5000-sitemap.xml",
]

# ── HTML parser ───────────────────────────────────────────────────────────────

class _Stripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'nav', 'header', 'footer', 'aside', 'svg'):
            self._skip += 1
        if tag in ('br', 'p', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'dt', 'dd', 'tr'):
            self._parts.append('\n')
        elif tag in ('div', 'section', 'article'):
            self._parts.append(' ')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'nav', 'header', 'footer', 'aside', 'svg'):
            self._skip = max(0, self._skip - 1)

    def handle_data(self, data):
        if not self._skip:
            self._parts.append(data)

    def text(self) -> str:
        return ''.join(self._parts)


def strip_html(html: str) -> str:
    s = _Stripper()
    try:
        s.feed(html)
    except Exception:
        pass
    return s.text()


def fetch_page_html(url, timeout=20):
    """Fetch raw HTML from a URL."""
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"  WARN: {e}", file=sys.stderr)
        return ""


def clean_text(html):
    """Convert HTML to clean structured text."""
    text = strip_html(html)
    # Normalize whitespace
    lines = [l.strip() for l in text.split('\n')]
    lines = [l for l in lines if l]
    return '\n'.join(lines)


# ── Entity extraction ─────────────────────────────────────────────────────────

def extract_people_from_text(text):
    """Extract people names and roles from clean text."""
    people = {}

    # Pattern: "Name\nRole" on separate lines (common in these pages)
    # Pattern: "Director: Name" or "Producer: Name"
    # Pattern: "Name Producer" or "Name Director" (same line)

    lines = text.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        # Check for role labels on this line
        role = None
        name = None

        # "Director: Name" pattern
        m = re.match(r'^(Director|Producer|Screenwriter|Writer|Creator)[:\s]+(.+)', line, re.IGNORECASE)
        if m:
            role = m.group(1).lower()
            if role == 'creator':
                role = 'director'
            name = m.group(2).strip()
            # Clean name - remove trailing role words
            name = re.sub(r'\s+(Producer|Director|Screenwriter|Writer)$', '', name).strip()

        # "Name Role" pattern (role on same line after name)
        if not name:
            m = re.match(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})\s+(Producer|Director|Screenwriter|Writer|Lab Edition)\b', line)
            if m:
                name = m.group(1).strip()
                role = m.group(2).lower()
                if role == 'lab edition':
                    role = None
                    name = None

        # Role on this line, name on previous line
        if not name and i > 0:
            m = re.match(r'^(Producer|Director|Screenwriter|Writer|Creator)$', line, re.IGNORECASE)
            if m:
                prev = lines[i-1].strip()
                # Previous line should look like a name (2-4 capitalized words)
                if re.match(r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}$', prev):
                    name = prev
                    role = m.group(1).lower()
                    if role == 'creator':
                        role = 'director'

        # "Producer/s Name1, Name2" pattern
        if not name:
            m = re.match(r'^Producer/s?:?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+(?:\s*,\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)*)', line)
            if m:
                names = [n.strip() for n in m.group(1).split(',')]
                for n in names[:2]:
                    if re.match(r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}$', n):
                        people[n] = 'producer'
                continue

        if name and role:
            # Validate name looks like a person name
            if (re.match(r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}$', name)
                and name.lower() not in ('the film', 'the project', 'the director', 'lab edition',
                                          'back to', 'production company', 'production budget',
                                          'about the', "director's note", 'log line',
                                          'series lab', 'film lab', 'participation',
                                          'application', 'rules', 'regulation')):
                people[name] = role

    return people


def extract_film_info(text, url):
    """Extract film/series title and metadata from text."""
    info = {}

    # Title is usually the first meaningful line
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if lines:
        title = lines[0]
        # Skip generic titles
        if title.lower() not in ('go', 'top of page', 'bottom of page'):
            info['title'] = title

    # Year
    m = re.search(r'Year of release:\s*(\d{4})', text)
    if m:
        info['year'] = int(m.group(1))

    # Country
    m = re.search(r'Country:?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', text)
    if m:
        info['country'] = m.group(1)

    # Lab edition
    m = re.search(r'Lab Edition\s*(\d+)', text)
    if m:
        info['lab_edition'] = int(m.group(1))

    # Genre
    m = re.search(r'Genre:?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', text)
    if m:
        info['genre'] = m.group(1)

    return info


def build_record(url, people, film_info, page_type):
    """Create a mentions.jsonl record."""
    entities = {"people": {}, "films": {}, "organizations": {}}
    roles_list = []

    for i, (name, role_type) in enumerate(people.items(), 1):
        pid = f"person_{i:03d}"
        title = film_info.get('title', '')
        entities["people"][pid] = {
            "name_he": name,
            "name_en": name,
            "aliases": [],
            "primary_roles": [role_type],
            "context_sentence": f"{role_type} — {title} — JSFS {page_type}",
            "sources": [url],
        }
        roles_list.append({
            "id": f"role_{i:03d}_{role_type}",
            "person_id": pid,
            "organization_id": "org_001",
            "role_type": role_type,
            "start_year": None,
            "end_year": None,
            "notes": f"{role_type} — {title}",
            "sources": [url],
        })

    title = film_info.get('title', '')
    if title:
        entities["films"]["film_001"] = {
            "title_he": "",
            "title_en": title,
            "year": film_info.get('year'),
            "director_ids": [pid for pid, p in entities["people"].items()
                             if "director" in p["primary_roles"]],
            "sources": [url],
        }

    org_name = "Sam Spiegel Film Lab" if page_type != "Series Lab" else "Sam Spiegel Series Lab"
    entities["organizations"]["org_001"] = {
        "name_he": "",
        "name_en": org_name,
        "type": "film_lab",
        "sources": [url],
    }

    return {
        "file": f"jsfs_labs__{url.rstrip('/').split('/')[-1]}__manual.md",
        "url": url,
        "source_name": SOURCE_NAME,
        "status": "ok",
        "content_hash": "manual",
        "content_length": 0,
        "filter_info": {"reason": "manual_import"},
        "truncated": False,
        "elapsed_sec": 0,
        "data": {
            "metadata": {
                "source_url": url,
                "source_name": SOURCE_NAME,
                "extraction_date": TODAY,
                "language": "en",
                "canonical_source": "scrape_jsfs_labs.py",
            },
            "entities": entities,
            "roles": roles_list,
            "relationships": [],
            "films": [],
        },
    }


def get_page_type(url):
    if "/seriesparticipants/" in url:
        return "Series Lab"
    elif "/filmslabs/" in url or "/participants-filmlab-catalog/" in url:
        return "Film Lab"
    else:
        return "Film Lab"


def fetch_sitemap_urls(base_url, sitemap_path):
    url = f"{base_url}/{sitemap_path}"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        return [loc.text for loc in root.findall(".//s:loc", ns) if loc.text]
    except Exception as e:
        print(f"  WARN: {e}", file=sys.stderr)
        return []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reparse", action="store_true", help="Reparse existing raw HTML files")
    parser.add_argument("--delay", type=float, default=0.3)
    args = parser.parse_args()

    # Collect URLs
    all_urls = []
    for sp in SUB_SITEMAPS:
        urls = fetch_sitemap_urls("https://labs.jsfs.co.il", sp)
        print(f"  {sp[:40]}...: {len(urls)} URLs")
        all_urls.extend(urls)

    all_urls = list(dict.fromkeys(all_urls))
    print(f"\nTotal unique URLs: {len(all_urls)}")
    if args.limit:
        all_urls = all_urls[:args.limit]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    total_people = 0
    total_films = 0
    processed = 0
    errors = 0

    for url in all_urls:
        html = fetch_page_html(url)
        if not html or len(html) < 200:
            errors += 1
            continue

        text = clean_text(html)
        if len(text) < 50:
            errors += 1
            continue

        page_type = get_page_type(url)
        people = extract_people_from_text(text)
        film_info = extract_film_info(text, url)

        if people or film_info.get('title'):
            record = build_record(url, people, film_info, page_type)
            if not args.dry_run:
                with open(OUTPUT, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            total_people += len(people)
            if film_info.get('title'):
                total_films += 1
            processed += 1

        if processed % 20 == 0 and processed > 0:
            print(f"  [{processed}/{len(all_urls)}] {total_people} people, {total_films} films")

        time.sleep(args.delay)

    print(f"\nDone: {processed} pages, {total_people} people, {total_films} films")
    print(f"Errors: {errors}")
    if not args.dry_run:
        print(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()
