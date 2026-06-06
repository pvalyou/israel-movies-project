#!/usr/bin/env python3
"""
enrich_film_pages.py — Fetch individual film pages and extract missing crew.

Identifies per-film pages that have a film entity but fewer than --min-people
people extracted. Fetches each page, extracts crew using Hebrew role patterns,
and appends enriched records to out/<source>/mentions.jsonl.

Usage:
    python3 enrich_film_pages.py                          # all sources, gaps only
    python3 enrich_film_pages.py --source nfct --limit 50
    python3 enrich_film_pages.py --source fdoc --dry-run
    python3 enrich_film_pages.py --min-people 2           # re-enrich thin pages too
"""

import argparse, datetime, hashlib, json, re, sys, time
import urllib.request, urllib.parse
from collections import defaultdict
from html.parser import HTMLParser

# ── Source config ─────────────────────────────────────────────────────────────

# Regex that matches an individual film-page URL (not a category/search page)
FILM_URL_RE: dict[str, re.Pattern] = {
    "nfct":          re.compile(r'/(?:blog/)?(?:en/)?movies?/[^/?]{3,}/?$'),
    "fdoc":          re.compile(r'/movie/[^/?]{3,}/?$'),
    "festival_data": re.compile(r'/films?/[^/?]{3,}/?$|/movies?/[^/?]{3,}/?$'),
    "gesher":        re.compile(r'/Page/\d+/?$'),
    "filmfund":      re.compile(r'movieId=\d+'),
    "makor":         re.compile(r'/films/[^/?]{3,}/?$'),
    "jff":           re.compile(r'/films?/[^/?]{3,}/?$'),
}

ORG_LABELS: dict[str, str] = {
    "nfct":          "הקרן החדשה לקולנוע וטלוויזיה",
    "makor":         "קרן מקור",
    "fdoc":          "הפורום הדוקומנטרי",
    "filmfund":      "הקרן הישראלית לקולנוע",
    "gesher":        "קרן גשר",
    "festival_data": "פסטיבלים",
    "jff":           "פסטיבל הסרטים בירושלים",
}

SOURCES_DEFAULT = ["nfct", "fdoc", "festival_data", "gesher", "filmfund", "makor", "jff"]

# ── Role mapping ──────────────────────────────────────────────────────────────

# Each entry: (regex matching Hebrew/English label, role_type)
ROLE_MAP = [
    (r'בימוי|הבים|ב[יי]מ[אה]י|Director|Directed by',          'director'),
    (r'(?<!מנהל )הפקה|מפי[קכ]|הופק|Produced? by|Producer',    'producer'),
    (r'הפקה מבצעת|מפיק בכיר|Executive Produc',                  'executive_producer'),
    (r'תסריט(?! ו)|תסריטאי|Screenplay|Script(?:writer)?',       'screenwriter'),
    (r'עריכה|עור[כך]|Edited? by|Editor',                       'editor'),
    (r'צילום|צל[מ]|Cinematograph|Director of Photography|D\.O\.P', 'cinematographer'),
    (r'מוסיקה|פסקול|Music|Composer|Sound Design',              'composer'),
    (r'שחקנ|קאסט|Cast|Actor|Starring',                         'actor'),
    (r'מנהל[ת]? הפקה|Production Manager',                      'production_manager'),
    (r'עיצוב אמנותי|Art Direct',                                'art_director'),
    (r'הפקת יצירה|יצירה|Co[- ]?Produc(?:er|tion)',              'co_producer'),
]

# ── HTML stripping ────────────────────────────────────────────────────────────

class _Stripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'nav', 'header', 'footer', 'aside'):
            self._skip += 1
        if tag in ('br', 'p', 'li', 'h1', 'h2', 'h3', 'h4', 'dt', 'dd', 'tr'):
            self._parts.append('\n')
        elif tag in ('div', 'section', 'article', 'span'):
            self._parts.append(' ')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'nav', 'header', 'footer', 'aside'):
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

# ── Name cleaning ─────────────────────────────────────────────────────────────

_HEB_CHAR = re.compile(r'[א-ת]')
_PAREN    = re.compile(r'\s*\([^)]{0,60}\)')
_JUNK_RE  = re.compile(r'^[\s\-–—,.:|/\\״\'"]+$')

# Tokens that indicate an org/company/school rather than a person name
_ORG_TOKENS = re.compile(
    r'הפקות?|פרסט|סרטי |אקדמי|בית.?ספר|ביה"ס|מכללה|אוניברסיט|'
    r'פילמס|Film[sz]?|Production[sz]?|Studio|Brothers|'
    r'כאן |ערוץ|רשת |הטלוויזי|מנשה|קולנוע\b',
    re.IGNORECASE,
)


_URL_RE     = re.compile(r'https?://|www\.|\.org\.il|\.co\.il|\.com|nfct\.')
_CODE_RE    = re.compile(r'^_|__|[<>{}\[\]()]|\bfunction\b|\bvar\b|doPostBack|javascript')
_EXTRA_INFO = re.compile(r'[.]\s+[א-תa-zA-Z]|ע"פ|מבוסס על|בשיתוף|ייעוץ|יוצרים:|מפיקה? שותפ')


def _split_names(raw: str) -> list[str]:
    # Strip secondary role info after period or keywords like ע"פ / מבוסס על
    raw = _EXTRA_INFO.split(raw)[0]
    raw = _PAREN.sub('', raw)
    parts = re.split(r'[,،،\n|]+', raw)
    out = []
    for p in parts:
        p = p.strip(' \t\r‏‎‬‫–—.')
        if len(p) < 2 or len(p) > 40:
            continue
        if _JUNK_RE.match(p):
            continue
        if _URL_RE.search(p):
            continue
        if _CODE_RE.search(p):
            continue
        if not re.search(r'[א-תA-Za-z]', p):
            continue
        if _ORG_TOKENS.search(p):
            continue
        # Hebrew names: reject if more than 4 words (likely a phrase, not a name)
        if _HEB_CHAR.search(p) and len(p.split()) > 4:
            continue
        out.append(p)
    return out

# ── Crew extraction ───────────────────────────────────────────────────────────

def extract_crew(text: str) -> list[dict]:
    """
    Parse plain text from a film page and return a list of crew dicts:
      {name_he, name_en, primary_roles, gender}
    """
    # Normalise whitespace while keeping newlines
    text = re.sub(r'[ \t]+', ' ', text)

    crew: dict[str, dict] = {}   # lower-name → entry

    for label_re, role in ROLE_MAP:
        pattern = re.compile(
            r'(?:^|(?<=\n))[^\n]{0,30}(?:' + label_re + r')[^\n]{0,10}[:\-–]\s*([^\n]{2,120})',
            re.IGNORECASE | re.MULTILINE,
        )
        for m in pattern.finditer(text):
            for name in _split_names(m.group(1)):
                key = name.strip().lower()
                if key not in crew:
                    is_he = bool(_HEB_CHAR.search(name))
                    crew[key] = {
                        "name_he":      name if is_he else "",
                        "name_en":      name if not is_he else "",
                        "primary_roles": [],
                        "gender":       "unknown",
                    }
                if role not in crew[key]["primary_roles"]:
                    crew[key]["primary_roles"].append(role)

    return list(crew.values())

# ── Local page index ─────────────────────────────────────────────────────────

# Cache: src → {normalized_url: md_path}
_LOCAL_INDEX: dict[str, dict[str, str]] = {}


def _norm_url(url: str) -> str:
    """Normalize a URL for index lookup: strip fragment, lowercase, strip trailing slash."""
    url = url.strip()
    # Strip fragment (#UA...) — local files are stored without it
    if "#" in url:
        url = url[:url.index("#")]
    url = url.rstrip("/")
    # Decode percent-encoding for consistent matching
    url = urllib.parse.unquote(url)
    return url.lower()


def _build_local_index(src: str) -> dict[str, str]:
    """Build {normalized_url: md_file_path} from sources/<src>/pages/*.meta.json."""
    pages_dir = f"sources/{src}/pages"
    index: dict[str, str] = {}
    try:
        import os
        for fname in os.listdir(pages_dir):
            if not fname.endswith(".meta.json"):
                continue
            meta_path = os.path.join(pages_dir, fname)
            try:
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                continue
            page_url = meta.get("url") or ""
            if not page_url:
                continue
            if meta.get("status") != "ok":
                continue
            md_path = meta_path.replace(".meta.json", ".md")
            index[_norm_url(page_url)] = md_path
    except FileNotFoundError:
        pass
    return index


# Sources to check as fallback for a given src (e.g. nfct_new has newer nfct pages)
_FALLBACK_SOURCES: dict[str, list[str]] = {
    "nfct": ["nfct_new"],
}


def local_text(src: str, url: str) -> str | None:
    """Return page content from local scraper cache, or None if not cached."""
    for candidate_src in [src] + _FALLBACK_SOURCES.get(src, []):
        if candidate_src not in _LOCAL_INDEX:
            _LOCAL_INDEX[candidate_src] = _build_local_index(candidate_src)
        md_path = _LOCAL_INDEX[candidate_src].get(_norm_url(url))
        if not md_path:
            continue
        try:
            with open(md_path, encoding="utf-8") as f:
                raw = f.read().strip()
            if not raw:
                continue
            # Pages are stored as JSON objects with a "content" field
            if raw.startswith("{"):
                d = json.loads(raw)
                text = (d.get("content") or "").strip()
            else:
                text = raw
            if text:
                return text
        except Exception:
            continue
    return None


# ── Fetching ──────────────────────────────────────────────────────────────────

_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (compatible; IsraeliFilmResearch/1.0)",
    "Accept-Language": "he,en;q=0.9",
    "Accept":          "text/html,application/xhtml+xml,*/*;q=0.8",
}

_SCRAPER_URL = "https://crawl4ai-wrapper-559961100092.europe-west1.run.app"

try:
    from pathlib import Path as _Path
    _API_KEY = ""
    _env = _Path(".env")
    if _env.exists():
        for _line in _env.read_text().splitlines():
            if _line.strip().startswith("CRAWL4AI_API_KEY="):
                _API_KEY = _line.strip().split("=", 1)[1].strip()
except Exception:
    _API_KEY = ""


def fetch_via_scraper(url: str, timeout: int = 60) -> str | None:
    """Fetch via the crawl4ai-wrapper service (returns markdown content)."""
    try:
        import requests as _req
    except ImportError:
        return None
    payload = {
        "url": url, "format": "markdown", "fit_markdown": False,
        "ignore_links": False, "include_links": True,
        "follow_links": False, "max_depth": 1,
    }
    headers: dict = {"X-API-Key": _API_KEY} if _API_KEY else {}
    try:
        resp = _req.post(f"{_SCRAPER_URL}/scrape", json=payload,
                         headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return (data.get("markdown") or data.get("content") or "").strip() or None
    except Exception:
        return None


def fetch_text(url: str, timeout: int = 20) -> str | None:
    """Fetch a URL: try crawl4ai-wrapper first, fall back to direct HTTP."""
    # Try the managed scraper service first (handles JS-rendered pages, rate limiting)
    text = fetch_via_scraper(url, timeout=60)
    if text:
        return text
    # Direct HTTP fallback
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE
    try:
        enc_url = urllib.parse.quote(url, safe=':/?=&%#+@!$,;')
        req = urllib.request.Request(enc_url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            html = resp.read().decode(charset, errors="replace")
        return strip_html(html)
    except Exception:
        return None

# ── Load existing data ────────────────────────────────────────────────────────

def load_source(src: str) -> tuple[dict[str, int], dict[str, dict]]:
    """
    Returns:
      url_to_npeople: {url: number_of_people_extracted}
      url_to_film:    {url: {title, year}}
    """
    pattern   = FILM_URL_RE.get(src)
    out_path  = f"out/{src}/mentions.jsonl"
    url_np: dict[str, int]  = {}
    url_fm: dict[str, dict] = {}

    try:
        with open(out_path, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("status") != "ok":
                    continue
                url = d.get("url") or ""
                if not url or url.startswith("manual://"):
                    continue
                if pattern and not pattern.search(url):
                    continue
                data    = d.get("data") or {}
                films   = (data.get("entities") or {}).get("films")   or {}
                people  = (data.get("entities") or {}).get("people")  or {}
                if films:
                    best = next(iter(films.values()), {}) or {}
                    url_fm[url] = {
                        "title": (best.get("title_he") or best.get("title_en") or "").strip(),
                        "year":  best.get("year"),
                    }
                    url_np[url] = url_np.get(url, 0) + len(people)
    except FileNotFoundError:
        pass

    return url_np, url_fm

# ── Record builder ────────────────────────────────────────────────────────────

def _make_record(url: str, src: str, film: dict, crew: list[dict]) -> dict:
    today     = datetime.date.today().isoformat()
    org_label = ORG_LABELS.get(src, src)
    film_title = film.get("title", "")
    film_year  = film.get("year")
    is_he_title = bool(_HEB_CHAR.search(film_title))

    people_ents: dict[str, dict] = {}
    roles_list:  list[dict] = []

    for i, person in enumerate(crew, 1):
        pid = f"person_{i:03d}"
        people_ents[pid] = {
            "name_he":      person.get("name_he", ""),
            "name_en":      person.get("name_en", ""),
            "aliases":      [],
            "primary_roles": person["primary_roles"],
            "gender":       person.get("gender", "unknown"),
            "sources":      [url],
        }
        for role in person["primary_roles"]:
            roles_list.append({
                "id":              f"role_{i:03d}_{role}",
                "person_id":       pid,
                "organization_id": "org_001",
                "role_type":       role,
                "start_year":      film_year,
                "end_year":        film_year,
                "notes":           f'{role} — {film_title}',
                "sources":         [url],
            })

    director_ids = [
        pid for pid, p in people_ents.items()
        if "director" in p["primary_roles"]
    ]

    return {
        "file":           f"{src}__enriched__{hashlib.md5(url.encode()).hexdigest()[:8]}.md",
        "url":            url,
        "source_name":    src,
        "status":         "ok",
        "content_hash":   hashlib.md5(url.encode()).hexdigest(),
        "content_length": 0,
        "filter_info":    {"reason": "enrichment_pass"},
        "truncated":      False,
        "elapsed_sec":    0,
        "data": {
            "metadata": {
                "source_url":      url,
                "source_name":     src,
                "extraction_date": today,
                "language":        "he",
                "canonical_source": f"enrich_film_pages.py pass {today}",
            },
            "entities": {
                "people": people_ents,
                "organizations": {
                    "org_001": {
                        "name_he": org_label,
                        "type":    "fund" if src not in ("festival_data", "jff") else "festival",
                        "sources": [url],
                    }
                },
                "films": {
                    "film_001": {
                        "title_he":    film_title if is_he_title else "",
                        "title_en":    film_title if not is_he_title else "",
                        "year":        film_year,
                        "director_ids": director_ids,
                        "sources":     [url],
                    }
                },
                "events": {},
            },
            "roles":         roles_list,
            "relationships": [],
            "films":         [],
        },
    }

# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source",      default=None,  help="Single source to process")
    ap.add_argument("--limit",       type=int, default=0,
                    help="Max URLs to fetch per source (0 = all)")
    ap.add_argument("--min-people",  type=int, default=1,
                    help="Re-fetch pages with <= this many people (default 1 = gaps only)")
    ap.add_argument("--dry-run",     action="store_true",
                    help="Fetch and extract but don't write to mentions.jsonl")
    ap.add_argument("--delay",       type=float, default=0.4,
                    help="Seconds between requests (default 0.4)")
    args = ap.parse_args()

    sources = [args.source] if args.source else SOURCES_DEFAULT

    grand_added = 0
    grand_skip  = 0
    grand_fail  = 0

    for src in sources:
        if src not in FILM_URL_RE:
            print(f"[WARN] Unknown source: {src}", file=sys.stderr)
            continue

        url_np, url_fm = load_source(src)
        to_fetch = sorted(
            [u for u, film in url_fm.items() if url_np.get(u, 0) <= args.min_people],
            key=lambda u: url_np.get(u, 0)   # gaps first
        )
        if args.limit:
            to_fetch = to_fetch[:args.limit]

        print(f"\n{'='*65}")
        print(f"Source: {src:15s} | {len(url_fm):5d} film pages | {len(to_fetch):4d} to enrich")
        if not to_fetch:
            print("  Nothing to do.")
            continue

        src_added = src_skip = src_fail = 0
        out_path  = f"out/{src}/mentions.jsonl"

        for i, url in enumerate(to_fetch, 1):
            film     = url_fm[url]
            existing = url_np.get(url, 0)
            title    = (film.get("title") or "?")[:36]
            print(f"  [{i:4d}/{len(to_fetch)}] {title:36s} (had {existing})  ", end="", flush=True)

            # Prefer local cached page; fall back to HTTP only if not cached
            text = local_text(src, url)
            if text is not None:
                source_tag = "local"
            else:
                text = fetch_text(url)
                source_tag = "http"
                time.sleep(args.delay)

            if text is None:
                print("FETCH FAIL")
                src_fail += 1
                continue

            crew = [c for c in extract_crew(text)
                    if c.get("name_he") or c.get("name_en")]

            if not crew:
                print(f"no crew [{source_tag}]")
                src_skip += 1
                continue

            names_preview = ", ".join(
                (c.get("name_he") or c.get("name_en", ""))[:14]
                for c in crew[:4]
            )
            print(f"+{len(crew):2d} crew [{source_tag}]: {names_preview}")

            if not args.dry_run:
                record = _make_record(url, src, film, crew)
                with open(out_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")

            src_added += len(crew)

        grand_added += src_added
        grand_skip  += src_skip
        grand_fail  += src_fail
        print(f"\n  → +{src_added} crew members added, {src_skip} no-crew, {src_fail} fetch-fail")

    print(f"\n{'='*65}")
    print(f"TOTAL: +{grand_added} crew members, {grand_skip} no-crew pages, {grand_fail} fetch failures")
    if not args.dry_run:
        print("Run: python3 resolve_entities.py")


if __name__ == "__main__":
    main()
