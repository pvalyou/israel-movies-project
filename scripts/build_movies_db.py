#!/usr/bin/env python3
"""
Build movies_db.json — merge raw_films.json from all sources.

Steps:
  1. Load raw records from EDB, JFC, CI
  2. Normalize titles, match films across sources
  3. Merge fields using source authority rules
  4. Resolve crew/cast names against entity_registry.json
  5. Write data/movies_db.json

Usage: python3 scripts/build_movies_db.py
"""

import json, os, re, unicodedata
from collections import defaultdict
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────────────

SOURCE_SECRETARY = {
    "edb": {
        "raw_path": "data/edb/raw_films.json",
        "priority": 1,
        "authoritative_for": ["funds", "festivals", "awards", "is_short", "edb_id"],
    },
    "ci": {
        "raw_path": "data/cinemaofisrael/raw_films.json",
        "priority": 2,
        "authoritative_for": ["title_en", "title_alt", "cast", "release_date_il",
                               "production_companies", "based_on", "color", "format"],
    },
    "jfc": {
        "raw_path": "data/jfc/raw_films.json",
        "priority": 3,
        "authoritative_for": ["description_he", "tags"],
    },
}

REGISTRY_PATH = "entity_registry.json"
OUTPUT_PATH = "data/movies_db.json"

# ── Helpers ──────────────────────────────────────────────────────────────────

def normalize_title(title: str) -> str:
    """Normalize Hebrew film title for cross-source matching."""
    if not title:
        return ""
    t = unicodedata.normalize("NFKD", title)
    t = re.sub(r"[\"'״׳.,!?״׳:;()]", "", t)
    t = re.sub(r"[\-–—]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def normalize_name(name: str) -> str:
    if not name:
        return ""
    n = name.strip()
    n = re.sub(r"^ד[\"״״]ר|פרופ[''׳]?|מר|גב[''׳]|עו[\"״״]ד|רו[\"״״]ח\s+", "", n)
    n = re.sub(r"[\"'״׳׳״.,]", "", n)
    n = re.sub(r"[\-–—]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _match_key(rec: dict) -> str:
    """Primary matching key: normalized title + year."""
    return normalize_title(rec.get("title_he", "")) + "|" + str(rec.get("year", ""))


def _title_key(rec: dict) -> str:
    return normalize_title(rec.get("title_he", ""))


# ── Load raw records ─────────────────────────────────────────────────────────

def load_raw(source_key: str) -> list:
    path = SOURCE_SECRETARY[source_key]["raw_path"]
    if not Path(path).exists():
        print(f"  {source_key}: no raw data ({path} not found)")
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    ok = [r for r in data if not r.get("status") == "failed" and r.get("title_he")]
    print(f"  {source_key}: {len(ok)} ok / {len(data)} total")
    return ok


# ── Resolve people ───────────────────────────────────────────────────────────

def build_registry_map() -> dict:
    """norm_name → registry_id for all people in entity_registry.json."""
    if not Path(REGISTRY_PATH).exists():
        return {}
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        reg = json.load(f)
    m = {}
    for pid, info in reg.get("people", {}).items():
        canonical = info.get("canonical_name_he", "")
        if canonical:
            m[normalize_name(canonical)] = pid
    return m


def resolve_people(films: list, registry_map: dict):
    """Populate crew[].registry_id and cast[].registry_id."""
    resolved = 0
    total = 0
    for film in films:
        for person in film.get("crew", []) + film.get("cast", []):
            total += 1
            key = normalize_name(person.get("name_he", ""))
            pid = registry_map.get(key)
            if pid:
                person["registry_id"] = pid
                resolved += 1
    return resolved, total


# ── Merge ────────────────────────────────────────────────────────────────────

def merge_films(source_records: dict, key: str) -> dict:
    """Merge all source records for the same film into one canonical record."""
    # EDB is authoritative → start with EDB if available
    records = source_records[key]
    records.sort(key=lambda r: SOURCE_SECRETARY.get(r["source_key"], {}).get("priority", 99))

    merged = {
        "film_id": None, "sources": [],
        "title_he": "", "title_en": None, "title_alt": [], "title_original": None,
        "year": None, "release_date_il": None, "is_short": False, "duration_min": None,
        "genre": None, "genre_he": None, "tags": [],
        "based_on": None,
        "description_he": None, "description_en": None,
        "country": [], "language": [], "subtitles": [], "color": None, "format": None,
        "funds": [], "production_companies": [], "distribution_companies": [],
        "broadcaster": None, "budget": None, "box_office_il": None,
        "crew": [], "cast": [],
        "festivals": [], "awards": [],
        "related_films": [], "related_interviews": [],
        "poster_url": None, "trailer_url": None, "watch_url": None,
        "urls": {},
    }

    for rec in records:
        src = rec["source_key"]
        merged["sources"].append(src)
        if src not in merged["urls"]:
            merged["urls"][src] = rec.get("url", "")

    # Determine canonical ID
    edb_rec = next((r for r in records if r["source_key"] == "edb" and r.get("edb_ids")), None)
    if edb_rec:
        edb_ids = edb_rec.get("edb_ids", [])
        merged["film_id"] = f"edb:{edb_ids[0]}" if edb_ids else None

    # For each field: authoritative source first, then first non-empty
    simple_fields = [
        "title_he", "title_en", "year", "release_date_il", "is_short",
        "duration_min", "genre", "genre_he", "based_on",
        "description_he", "description_en",
        "budget", "box_office_il", "color", "format",
        "poster_url", "trailer_url", "watch_url",
    ]
    for field in simple_fields:
        for rec in records:
            val = rec.get(field)
            if val is not None and val != "" and val != [] and val != 0:
                merged[field] = val
                break

    # List fields: authoritative source first, then accumulate
    list_fields = [
        "title_alt", "tags", "country", "language", "subtitles",
        "funds", "production_companies", "distribution_companies",
    ]
    for field in list_fields:
        seen = set()
        for rec in records:
            val = rec.get(field) or []
            if isinstance(val, str):
                val = [val]
            for v in val:
                if v and v not in seen:
                    seen.add(v)
                    merged.setdefault(field, []).append(v)

    # Personnel: authoritative source first
    for field in ("crew", "cast"):
        seen_names = set()
        for rec in records:
            for p in rec.get(field, []):
                name = p.get("name_he", "")
                if name and name not in seen_names:
                    seen_names.add(name)
                    merged.setdefault(field, []).append(p)

    # Complex objects: take first non-empty
    for field in ("festivals", "awards", "related_films", "related_interviews"):
        for rec in records:
            val = rec.get(field)
            if val:
                merged[field] = val
                break

    return merged


def main():
    print("=== Build movies_db.json ===\n")

    # Load raw data
    print("Loading raw data...")
    all_records: dict[str, list] = {}
    for src in SOURCE_SECRETARY:
        raw = load_raw(src)
        for r in raw:
            title_he = r.get("title_he", "")
            if not title_he:
                continue
            mk = _match_key(r)
            if mk not in all_records:
                all_records[mk] = []
            all_records[mk].append(r)

    # Pass 2: merge records that have no year into the best title+year group.
    # A no-year record matches a titled group when the year gap is acceptable
    # (or the other group also has no year).
    no_year_keys = [mk for mk in list(all_records) if mk.endswith("|None")]
    by_title: dict[str, list[str]] = defaultdict(list)  # title → list of match-keys
    for mk in all_records:
        tk = mk.rsplit("|", 1)[0]
        by_title[tk].append(mk)

    merged_into = 0
    for nk in no_year_keys:
        tk = nk.rsplit("|", 1)[0]
        siblings = [mk for mk in by_title[tk] if mk != nk]
        if not siblings:
            continue
        # Pick the sibling with a known year (any; there's usually just one)
        target = next((s for s in siblings if not s.endswith("|None")), siblings[0])
        all_records[target].extend(all_records.pop(nk))
        by_title[tk] = [mk for mk in by_title[tk] if mk != nk]
        merged_into += 1

    print(f"\n  {len(all_records)} unique films across all sources "
          f"({merged_into} no-year records merged into titled groups)")
    for mk, recs in all_records.items():
        if len(recs) > 1:
            sources = [r["source_key"] for r in recs]
            title = recs[0].get("title_he", "")[:50]
            print(f"  multi-source: {title} ← {sources}")

    # Merge
    print("\nMerging films...")
    merged = []
    for mk in sorted(all_records.keys()):
        m = merge_films(all_records, mk)
        merged.append(m)

    # Clean CI genre tags embedded in titles: [תיעודי], [סדרה תיעודית], [סדרת טלוויזיה]
    CI_GENRE_TAGS = {
        "תיעודי": "תיעודי",
        "סדרה תיעודית": "סדרה תיעודית",
        "סדרת טלוויזיה": "סדרת טלוויזיה",
    }
    for film in merged:
        title = film.get("title_he") or ""
        for tag, genre in CI_GENRE_TAGS.items():
            pattern = rf"\s*\[{re.escape(tag)}\]\s*"
            if re.search(pattern, title):
                film["title_he"] = re.sub(pattern, "", title).strip()
                if not film.get("genre_he"):
                    film["genre_he"] = genre
                break

    # Resolve people against registry
    print("Resolving people against entity_registry.json...")
    registry_map = build_registry_map()
    resolved, total = resolve_people(merged, registry_map)
    print(f"  Resolved: {resolved}/{total} ({100*resolved/total:.1f}%)")

    # Save
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    # Stats
    with_crew = sum(1 for f in merged if f.get("crew"))
    with_cast = sum(1 for f in merged if f.get("cast"))
    with_funds = sum(1 for f in merged if f.get("funds"))
    multi_source = sum(1 for f in merged if len(f.get("sources", [])) > 1)
    print(f"\n{'='*60}")
    print(f"movies_db.json built: {len(merged)} films")
    print(f"  Multi-source: {multi_source}")
    print(f"  With crew: {with_crew}, With cast: {with_cast}")
    print(f"  With fund data: {with_funds}")
    print(f"  People resolution: {resolved}/{total} ({100*resolved/total:.1f}%)")
    print(f"  → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()