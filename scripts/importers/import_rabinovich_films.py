#!/usr/bin/env python3
"""
import_rabinovich_films.py — Parse Rabinovich Cinema Project funded-films PDFs
and write synthetic mentions.jsonl records to out/rabinovich_cinema/mentions.jsonl.

Input: sources/rabinovich_cinema/files/rabinovich__films_ocr.json
  (keyed by label: films2023, projects2015, budget2020_2025)
  Each entry is a list of {"page": N, "text": "<Gemini JSON response>"}

Each Gemini page response is a JSON object with keys like:
  שמות_הסרטים, שנת_הסרט, שמות_הבמאים, שמות_המפיקים,
  גופי_מימון, סכומי_מענקים, שמות_אנשים
  (keys may vary; Gemini returns them in whatever language/format it chooses)

Run: python3 import_rabinovich_films.py [--dry-run]
"""

import hashlib
import json
import re
import sys
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

SOURCE_NAME = "rabinovich_cinema"
ORG_NAME_HE = "קרן רבינוביץ' לאמנויות - פרויקט הקולנוע"

OCR_FILE  = Path("sources/rabinovich_cinema/files/rabinovich__films_ocr.json")
OUT_JSONL = Path("out/rabinovich_cinema/mentions.jsonl")
CANONICAL_BASE = "manual://rabinovich_cinema/funded-films"

# Labels in OCR file → source year label
LABEL_YEARS = {
    "films2023":      "2023",
    "projects2015":   "2015",
    "budget2020_2025": "budget-2020-2025",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_json_from_text(text: str) -> dict | list | None:
    """Try to extract JSON from Gemini's response (may be wrapped in ```json ... ```)."""
    # Strip markdown code fences
    stripped = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    # Try direct parse
    for candidate in [stripped, text.strip()]:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    # Try extracting first {...} or [...] block
    m = re.search(r"(\{[\s\S]+\}|\[[\s\S]+\])", stripped)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return None


# Hebrew name heuristic: 2+ words, all Hebrew chars/spaces
HE_NAME_RE = re.compile(r'^[א-ת\s\-\'\"״׳]{4,40}$')

def looks_like_person_name(s: str) -> bool:
    s = s.strip()
    if not s or len(s.split()) < 2:
        return False
    return bool(HE_NAME_RE.match(s))


def flatten_values(obj) -> list[str]:
    """Recursively collect all string values from a dict/list."""
    result = []
    if isinstance(obj, str):
        result.append(obj)
    elif isinstance(obj, list):
        for item in obj:
            result.extend(flatten_values(item))
    elif isinstance(obj, dict):
        for v in obj.values():
            result.extend(flatten_values(v))
    return result


# ── OCR data parsing ──────────────────────────────────────────────────────────

# Possible key names for each field (lowercased, spaces/underscores normalised)
_TITLE_KEYS   = {"title", "film_title", "movie_title", "שם_הסרט", "שם_סרט",
                 "כותרת", "name", "שם", "project_title", "project_name"}
_DIR_KEYS     = {"director", "director_name", "director_names", "directors",
                 "בימוי", "במאי", "במאים", "שם_הבמאי", "שמות_הבמאים",
                 "director_he"}
_PROD_KEYS    = {"producer", "producers", "producer_name",
                 "הפקה", "מפיק", "מפיקה", "מפיקים", "שם_המפיק"}
_FUND_KEYS    = {"fund", "funds", "funding_body", "supporting_funds",
                 "גופים_תומכים", "גוף_מממן", "קרן", "קרנות", "מממן"}
_AMOUNT_KEYS  = {"grant", "grant_amount", "amount", "amount_ils",
                 "סכום", "סכום_מענק", "מענק", "סכומי_מענקים", "grant_ils"}
_YEAR_KEYS    = {"year", "production_year", "שנה", "שנת_ייצור", "שנת_הסרט"}


def _nk(k: str) -> str:
    """Normalize key: lowercase, strip, replace spaces/dashes with underscore."""
    return k.strip().lower().replace(" ", "_").replace("-", "_")


def _sv(v) -> str | None:
    """Return scalar string value, or None."""
    if isinstance(v, str):
        return v.strip() or None
    if isinstance(v, (int, float)):
        return str(v)
    return None


def _get_field(d: dict, key_set: set) -> str | None:
    """Get first matching scalar from a dict using a key set."""
    nkeys = {_nk(k) for k in key_set}
    for k, v in d.items():
        if _nk(k) in nkeys:
            s = _sv(v)
            if s:
                return s
            # list → join
            if isinstance(v, list):
                parts = [_sv(x) for x in v if _sv(x)]
                if parts:
                    return ", ".join(parts)
    return None


def _collect_film_objects(obj, depth: int = 0) -> list[dict]:
    """
    Recursively collect dicts that look like film records
    (have at least a title or director field).
    Returns a list of normalized {title, director, producer, funds, amount, year}.
    """
    if depth > 5:
        return []
    results = []

    if isinstance(obj, list):
        for item in obj:
            results.extend(_collect_film_objects(item, depth + 1))
        return results

    if isinstance(obj, dict):
        title    = _get_field(obj, _TITLE_KEYS)
        director = _get_field(obj, _DIR_KEYS)
        producer = _get_field(obj, _PROD_KEYS)
        funds    = _get_field(obj, _FUND_KEYS)
        amount   = _get_field(obj, _AMOUNT_KEYS)
        year     = _get_field(obj, _YEAR_KEYS)

        # If both title and director present, this is a film record
        if title and director:
            results.append({
                "title": title, "director": director,
                "producer": producer, "funds": funds,
                "amount": amount, "year": year,
            })
            return results  # don't recurse further into this object

        # If only title, still record it
        if title and not director:
            results.append({
                "title": title, "director": None,
                "producer": producer, "funds": funds,
                "amount": amount, "year": year,
            })
            return results

        # Otherwise recurse into values
        for v in obj.values():
            if isinstance(v, (dict, list)):
                results.extend(_collect_film_objects(v, depth + 1))

    return results


def parse_page_data(page_json) -> list[dict]:
    """Extract list of film records from a page's Gemini JSON."""
    return _collect_film_objects(page_json)


# ── JSONL record builder ──────────────────────────────────────────────────────

def split_names(name_str: str) -> list[str]:
    """Split a director/producer string that may contain multiple names."""
    if not name_str:
        return []
    # Split on comma, /, 'and', 'ו', 'או'
    parts = re.split(r'[,/]|\s+ו\s+|\s+and\s+', name_str)
    results = []
    for p in parts:
        p = p.strip().strip("'\"")
        if p and len(p) >= 3:
            results.append(p)
    return results


def make_record(label: str, year_label: str, page_num: int,
                film_items: list[dict]) -> dict:
    url = f"{CANONICAL_BASE}/{year_label}/page-{page_num}"
    content = json.dumps(film_items, ensure_ascii=False)
    content_hash = hashlib.md5(content.encode()).hexdigest()

    people = {}
    films  = {}
    orgs   = {}
    pidx = fidx = oidx = 1

    for item in film_items:
        title    = item.get("title", "")
        director = item.get("director", "")
        producer = item.get("producer", "")
        funds    = item.get("funds", "")
        amount   = item.get("amount")
        year_s   = item.get("year", "")

        # Film
        year_int = None
        if year_s:
            m = re.search(r'\b(19|20)\d{2}\b', str(year_s))
            if m:
                year_int = int(m.group(0))
        if title and len(title.strip()) >= 2:
            films[f"film_{fidx:03d}"] = {
                "title_he": title.strip(),
                "title_en": None,
                "year": year_int,
                "grant_amount": amount,
                "sources": [url],
            }
            fidx += 1

        # Director(s)
        for name in split_names(director):
            if len(name) >= 3:
                people[f"person_{pidx:03d}"] = {
                    "name_he": name,
                    "name_en": None,
                    "aliases": [],
                    "primary_roles": ["director"],
                    "sources": [url],
                }
                pidx += 1

        # Producer(s)
        for name in split_names(producer):
            if len(name) >= 3:
                people[f"person_{pidx:03d}"] = {
                    "name_he": name,
                    "name_en": None,
                    "aliases": [],
                    "primary_roles": ["producer"],
                    "sources": [url],
                }
                pidx += 1

        # Funding body
        if funds and len(funds.strip()) >= 2:
            orgs[f"org_{oidx:03d}"] = {
                "name_he": funds.strip(),
                "name_en": None,
                "type": "fund",
                "sources": [url],
            }
            oidx += 1

    return {
        "file": f"rabinovich_cinema__films-{year_label}-p{page_num}__manual.md",
        "url": url,
        "source_name": SOURCE_NAME,
        "status": "ok",
        "content_hash": content_hash,
        "content_length": len(content),
        "filter_info": {"reason": "manual_canonical_source"},
        "truncated": False,
        "elapsed_sec": 0,
        "data": {
            "metadata": {
                "source_url": url,
                "source_name": SOURCE_NAME,
                "extraction_date": "2026-05-20",
                "language": "he",
                "canonical_source": f"Rabinovich Cinema Project funded films PDF ({year_label})",
            },
            "entities": {
                "people": people,
                "organizations": orgs,
                "films": films,
                "events": {},
            },
            "roles": [],
            "relationships": [],
        },
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    dry_run = "--dry-run" in sys.argv

    if not OCR_FILE.exists():
        print(f"OCR file not found: {OCR_FILE}", file=sys.stderr)
        sys.exit(1)

    ocr_data = json.loads(OCR_FILE.read_text(encoding="utf-8"))
    print(f"Loaded OCR data: {list(ocr_data.keys())}")

    # Read existing mentions, strip any earlier funded-films manual records
    existing = []
    if OUT_JSONL.exists():
        with open(OUT_JSONL, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if CANONICAL_BASE in rec.get("url", ""):
                        continue  # drop old funded-film records
                    existing.append(rec)
                except json.JSONDecodeError:
                    pass
    print(f"Existing records (after stripping funded-films): {len(existing)}")

    new_records = []
    total_people = 0

    for label, pages in ocr_data.items():
        year_label = LABEL_YEARS.get(label, label)
        print(f"\n=== {label} ({len(pages)} pages) ===")

        for page_data in pages:
            page_num = page_data.get("page", 0)
            text = page_data.get("text", "")
            if page_data.get("error") or not text:
                continue

            parsed_json = extract_json_from_text(text)
            if not parsed_json:
                print(f"  Page {page_num}: could not parse JSON (text len {len(text)})")
                # Fall through — might still have useful data in raw text
                continue

            film_items = parse_page_data(parsed_json)
            # Count distinct people (directors + producers)
            n_people = sum(
                1 for item in film_items
                for _name_list in [
                    split_names(item.get("director") or ""),
                    split_names(item.get("producer") or ""),
                ]
                for name in _name_list if len(name) >= 3
            )
            n_films = len([f for f in film_items if f.get("title")])
            print(f"  Page {page_num}: {n_films} films, {n_people} people")

            if dry_run:
                for item in film_items[:3]:
                    print(f"    {item.get('title','?')} — {item.get('director','?')}")
                continue

            if film_items:
                rec = make_record(label, year_label, page_num, film_items)
                new_records.append(rec)
                total_people += n_people

    if dry_run:
        print(f"\nDry run complete. Would add {len(new_records)} records.")
        return

    all_records = existing + new_records
    with open(OUT_JSONL, "w", encoding="utf-8") as f:
        for rec in all_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(all_records)} records ({len(new_records)} new, {total_people} persons)")
    print(f"Output: {OUT_JSONL}")


if __name__ == "__main__":
    main()
