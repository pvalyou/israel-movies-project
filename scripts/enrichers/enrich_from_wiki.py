#!/usr/bin/env python3
"""
enrich_from_wiki.py — Enrich person records with Hebrew Wikipedia data.

For each person in the database, searches Hebrew Wikipedia and extracts:
  - wiki_url, wiki_title_he
  - birth_year (from infobox or article text)
  - key_roles, key_affiliations (from article intro)

Results written to enriched/wiki_persons.json, keyed by name_he.
resolve_entities.py reads this to add wiki_link and birth_year to person cards.

Usage:
    python3 enrich_from_wiki.py                  # all lector-priority persons
    python3 enrich_from_wiki.py --all            # all Hebrew persons
    python3 enrich_from_wiki.py --limit 200      # first N persons
    python3 enrich_from_wiki.py --name "אביגיל שפרבר"  # single lookup
    python3 enrich_from_wiki.py --dry-run        # show who would be looked up
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
from collections import defaultdict
from pathlib import Path

import requests

# ── Config ─────────────────────────────────────────────────────────────────────

WIKI_SEARCH_URL = "https://he.wikipedia.org/w/api.php"
WIKI_BASE       = "https://he.wikipedia.org/wiki/"
REQUEST_DELAY   = 5.0   # seconds between API calls (rate limiting)
MAX_SEARCH_HITS = 3     # candidates to check per name
MIN_INTRO_CHARS = 80    # minimum intro length to be useful
ENRICHED_DIR    = Path("enriched")
OUTPUT_FILE     = ENRICHED_DIR / "wiki_persons.json"
SOURCES_DIR     = Path("out")

# Names that are template placeholders, not real people
PLACEHOLDER_NAMES = {
    "שם מלא בעברית", "שם בעברית", "שם", "במאי", "מפיק", "תסריטאי",
    "צלם", "עורך", "שחקן", "שחקנית", "בימאי",
}

# Birth year patterns in Hebrew Wikipedia articles
BIRTH_YEAR_RE = re.compile(
    r'נולד(?:ה)?\s+ב-?\d{1,2}\s+ב[א-ת]+\s+(\d{4})|'  # נולד/ה ב-DD בחודש YYYY
    r'נולד(?:ה)?\s+(?:ב-?)?(\d{4})|'                   # נולד/ה ב-XXXX
    r'\((\d{4})[–—-]|'                                  # (YYYY–
    r'יליד(?:ת)?\s+(\d{4})|'                            # יליד/ת XXXX
    r'\|birth_year\s*=\s*(\d{4})|'                      # infobox |birth_year=
    r'\|תאריך לידה\s*=\s*(\d{4})'                       # infobox |תאריך לידה=
)


# ── Data loading ───────────────────────────────────────────────────────────────

def load_all_persons() -> dict[str, dict]:
    """
    Returns {name_he: {sources: set, roles: set, is_lector: bool}}
    """
    persons: dict[str, dict] = defaultdict(lambda: {
        "sources": set(), "roles": set(), "is_lector": False, "mention_count": 0
    })

    for jsonl_path in sorted(SOURCES_DIR.glob("*/mentions.jsonl")):
        source = jsonl_path.parent.name
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("status") != "ok":
                    continue
                for _pid, p in rec.get("data", {}).get("entities", {}).get("people", {}).items():
                    name = p.get("name_he", "").strip()
                    if not name or name in PLACEHOLDER_NAMES:
                        continue
                    if not any("א" <= c <= "ת" for c in name):
                        continue
                    if len(name) < 3:
                        continue
                    roles = set(p.get("primary_roles", []))
                    persons[name]["sources"].add(source)
                    persons[name]["roles"].update(roles)
                    persons[name]["mention_count"] += 1
                    if "lector" in roles:
                        persons[name]["is_lector"] = True

    return dict(persons)


def priority_sort_key(name: str, info: dict) -> tuple:
    """Higher priority = lower sort key."""
    is_lector = 0 if info["is_lector"] else 1
    multi_source = 0 if len(info["sources"]) > 1 else 1
    return (is_lector, multi_source, -info["mention_count"])


# ── Wikipedia API ──────────────────────────────────────────────────────────────

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "IsraeliFilmResearch/1.0 (research project)"})


def _wiki_get(params: dict, label: str, retries: int = 5) -> dict:
    """GET with exponential backoff on 429."""
    delay = 2.0
    for attempt in range(retries):
        try:
            r = SESSION.get(WIKI_SEARCH_URL, params=params, timeout=15)
            if r.status_code == 429:
                retry_after = int(r.headers.get("Retry-After", 0))
                wait = max(retry_after, delay * (2 ** attempt))
                print(f"  429 rate limit, waiting {wait:.0f}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            if attempt == retries - 1:
                print(f"  {label} error: {e}", file=sys.stderr)
        except Exception as e:
            print(f"  {label} error: {e}", file=sys.stderr)
            break
    return {}


def wiki_search(name: str) -> list[dict]:
    """Search Hebrew Wikipedia for name, return top hits."""
    params = {
        "action": "query",
        "list": "search",
        "srsearch": name,
        "srlimit": MAX_SEARCH_HITS,
        "srprop": "snippet|titlesnippet",
        "format": "json",
        "utf8": 1,
    }
    return _wiki_get(params, f"search '{name}'").get("query", {}).get("search", [])


def wiki_get_intro(page_title: str) -> str:
    """Fetch plain-text intro of a Wikipedia article."""
    params = {
        "action": "query",
        "titles": page_title,
        "prop": "extracts",
        "exintro": True,
        "explaintext": True,
        "exsectionformat": "plain",
        "format": "json",
        "utf8": 1,
    }
    data = _wiki_get(params, f"extract '{page_title}'")
    pages = data.get("query", {}).get("pages", {})
    for _pid, page in pages.items():
        if _pid == "-1":
            return ""
        return page.get("extract", "")
    return ""


def is_person_article(title: str, snippet: str, name: str) -> bool:
    """Heuristic: does this article seem to be about a person with this name?"""
    name_words = name.split()
    title_clean = re.sub(r'\s*\(.*?\)', '', title).strip()  # strip "(disambig)" etc.
    title_words = title_clean.split()

    if len(name_words) >= 2:
        # Both first AND last name must appear in the title (order-independent)
        first, last = name_words[0], name_words[-1]
        if first not in title_words or last not in title_words:
            return False
    else:
        # Single-word name: exact title match required
        if name_words[0] not in title_words:
            return False

    # Snippet should mention person-related Hebrew keywords
    person_signals = ["במאי", "מפיק", "תסריטאי", "שחקן", "שחקנית", "קולנוע",
                      "נולד", "נולדה", "ישראלי", "ישראלית", "פרס", "סרט",
                      "מנהל", "יוצר", "יוצרת", "צלם"]
    return any(sig in snippet for sig in person_signals)


def extract_birth_year(text: str) -> int | None:
    for m in BIRTH_YEAR_RE.finditer(text):
        year_str = next(g for g in m.groups() if g)
        y = int(year_str)
        if 1920 <= y <= 2005:
            return y
    return None


def extract_roles_affiliations(text: str) -> tuple[list[str], list[str]]:
    """Extract key roles and institutional affiliations from article intro."""
    roles = []
    affiliations = []

    role_patterns = [
        (r"במאי(?:ת)?", "director"),
        (r"מפיק(?:ה)?", "producer"),
        (r"תסריטאי(?:ת)?", "screenwriter"),
        (r"שחקן|שחקנית", "actor"),
        (r"עורך(?:ת)?\s+(?:קולנוע|סרטים|וידאו)", "editor"),
        (r"צלם(?:ת)?", "cinematographer"),
        (r"מנהל(?:ת)?\s+(?:אמנותי[ת]?|יצירתי[ת]?)", "artistic_director"),
        (r"מנכ[\"׳]ל(?:ית)?", "ceo"),
        (r"יו[\"׳]ר", "chair"),
        (r"פרופסור|ד[\"׳]ר", "academic"),
    ]

    org_patterns = [
        r"קרן\s+[֐-׿\s]+",
        r"(?:אוניברסיטת?|המכללה|בית\s+הספר|מכון|מרכז)\s+[֐-׿\s]{3,30}",
        r"(?:תאגיד|ערוץ|חברת?)\s+[֐-׿\s]{3,25}",
        r"פסטיבל\s+[֐-׿\s]{3,25}",
        r"הטלוויזיה\s+הישראלית|כאן\s+\d+|ערוץ\s+\d+",
    ]

    for pattern, role_name in role_patterns:
        if re.search(pattern, text):
            roles.append(role_name)

    for pattern in org_patterns:
        for m in re.finditer(pattern, text):
            aff = m.group(0).strip()
            if 3 < len(aff) < 40 and aff not in affiliations:
                affiliations.append(aff)

    return roles[:6], affiliations[:6]


def lookup_person(name: str) -> dict | None:
    """
    Look up a person on Hebrew Wikipedia.
    Returns enrichment dict or None if not found.
    """
    hits = wiki_search(name)
    time.sleep(REQUEST_DELAY)

    for hit in hits:
        title = hit.get("title", "")
        snippet = hit.get("snippet", "")

        if not is_person_article(title, snippet, name):
            continue

        intro = wiki_get_intro(title)
        time.sleep(REQUEST_DELAY)

        if len(intro) < MIN_INTRO_CHARS:
            continue

        birth_year = extract_birth_year(intro)
        roles, affiliations = extract_roles_affiliations(intro)
        wiki_url = WIKI_BASE + urllib.parse.quote(title.replace(" ", "_"))

        return {
            "wiki_title_he": title,
            "wiki_url": wiki_url,
            "birth_year": birth_year,
            "wiki_roles": roles,
            "wiki_affiliations": affiliations,
            "intro_snippet": intro[:300],
        }

    return None


# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true",
                        help="Look up all Hebrew persons, not just lector-priority")
    parser.add_argument("--limit", type=int, default=0,
                        help="Maximum number of persons to look up")
    parser.add_argument("--name", help="Look up a single person by name_he")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show who would be looked up, no API calls")
    args = parser.parse_args()

    ENRICHED_DIR.mkdir(exist_ok=True)

    # Load existing cache
    cache: dict[str, dict] = {}
    if OUTPUT_FILE.exists():
        try:
            cache = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    print(f"Existing cache: {len(cache)} entries")

    # Single name mode
    if args.name:
        result = lookup_person(args.name)
        if result:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            cache[args.name] = result
            OUTPUT_FILE.write_text(
                json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        else:
            print(f"Not found: {args.name}")
        return

    # Load all persons
    print("Loading persons from all sources...")
    all_persons = load_all_persons()
    print(f"Total unique Hebrew persons: {len(all_persons)}")

    # Filter to priority set
    if args.all:
        candidates = list(all_persons.items())
    else:
        # Default: lectors + multi-source persons
        candidates = [
            (name, info) for name, info in all_persons.items()
            if info["is_lector"] or len(info["sources"]) > 1
        ]
    print(f"Priority candidates: {len(candidates)}")

    # Sort by priority
    candidates.sort(key=lambda x: priority_sort_key(x[0], x[1]))

    # Skip already cached
    to_lookup = [(n, i) for n, i in candidates if n not in cache]
    print(f"To look up (not yet cached): {len(to_lookup)}")

    if args.limit:
        to_lookup = to_lookup[:args.limit]
        print(f"Limited to: {len(to_lookup)}")

    if args.dry_run:
        print("\nDry run — would look up:")
        for name, info in to_lookup[:30]:
            flag = "🔑" if info["is_lector"] else "  "
            print(f"  {flag} {name} (sources: {info['sources']}, mentions: {info['mention_count']})")
        if len(to_lookup) > 30:
            print(f"  ... and {len(to_lookup) - 30} more")
        return

    # Run lookups
    found = 0
    not_found = 0
    for i, (name, info) in enumerate(to_lookup, 1):
        flag = "[LECTOR]" if info["is_lector"] else ""
        print(f"  [{i}/{len(to_lookup)}] {name} {flag}...", end=" ", flush=True)

        result = lookup_person(name)
        if result:
            cache[name] = result
            found += 1
            print(f"✓ {result.get('wiki_title_he')} ({result.get('birth_year', '?')})")
        else:
            cache[name] = None
            not_found += 1
            print("✗")

        # Save incrementally every 50 lookups
        if i % 50 == 0:
            OUTPUT_FILE.write_text(
                json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"  [saved checkpoint: {found} found, {not_found} not found so far]")

    # Final save
    OUTPUT_FILE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nDone: {found} found, {not_found} not found")
    print(f"Cache: {len(cache)} total entries → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
