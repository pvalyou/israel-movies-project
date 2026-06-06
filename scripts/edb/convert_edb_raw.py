#!/usr/bin/env python3
"""Convert EDB data to unified raw_films.json format.

Reads edb_films.json, edb_persons.json → data/edb/raw_films.json
"""

import json, os, sys

IN_FILMS = "data/edb/edb_films.json"
IN_PERSONS = "data/edb/edb_persons.json"
OUT = "data/edb/raw_films.json"


def main():
    if not os.path.exists(IN_FILMS):
        print(f"ERROR: {IN_FILMS} not found")
        sys.exit(1)

    with open(IN_FILMS, encoding="utf-8") as f:
        films = json.load(f)

    # Build EDB ID → person name map from edb_persons.json (for fallback names)
    edb_name_map = {}
    if os.path.exists(IN_PERSONS):
        with open(IN_PERSONS, encoding="utf-8") as f:
            persons = json.load(f)
        for p in persons:
            edb_name_map[p.get("edb_id", "")] = p.get("name_he", "")

    raw = []
    for film in films:
        rec = {
            "source_key": "edb",
            "source_id": film.get("film_id", ""),
            "url": film.get("url", ""),
            "title_he": film.get("title", ""),
            "title_en": None, "title_alt": [], "title_original": None,
            "year": film.get("year"),
            "release_date_il": None,
            "is_short": film.get("is_short", False),
            "duration_min": None,
            "genre": None, "genre_he": None,
            "description_he": None, "description_en": None,
            "country": ["ישראל"], "language": None, "subtitles": [],
            "color": None, "format": None, "based_on": None,
            "funds": [], "production_companies": [], "distribution_companies": [],
            "broadcaster": None, "budget": None, "box_office_il": None,
            "crew": [], "cast": [],
            "festivals": [], "awards": [],
            "tags": [],
            "poster_url": None, "trailer_url": None, "watch_url": None,
            "related_films": [], "related_interviews": [],
            "edb_ids": [film.get("film_id", "")] if film.get("film_id") else [],
        }

        for c in film.get("crew", []):
            name = c.get("name_he", "")
            if not name:
                name = edb_name_map.get(c.get("edb_id", ""), "")
            if name:
                rec["crew"].append({
                    "name_he": name,
                    "name_en": None,
                    "role": c.get("role", "other"),
                    "role_he": c.get("role_he", ""),
                    "edb_id": c.get("edb_id", ""),
                })

        raw.append(rec)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)

    print(f"Converted {len(raw)} films → {OUT}")
    print(f"  With crew: {sum(1 for r in raw if r['crew'])} ({sum(len(r['crew']) for r in raw)} total)")
    print(f"  Shorts: {sum(1 for r in raw if r['is_short'])}")


if __name__ == "__main__":
    main()