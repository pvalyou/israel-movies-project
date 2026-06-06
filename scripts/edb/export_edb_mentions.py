#!/usr/bin/env python3
"""Export EDB data → out/edb/mentions.jsonl

Phase 1 (film crew): edb_films.json → one record per film with production crew.
Phase 3 (actors):    edb_persons.json → one record per person who has actor credits.

Collaborator edges (מרבה לעבוד עם) are handled separately in build_network_graph()
inside resolve_entities.py, which reads edb_persons.json directly.
"""

import json
import os
from datetime import date

INPUT_FILMS   = "data/edb/edb_films.json"
INPUT_PERSONS = "data/edb/edb_persons.json"
OUTPUT_FILE   = "out/edb/mentions.jsonl"

EDB_TITLE_URL  = "https://www.edb.co.il/title/{film_id}/"
EDB_PERSON_URL = "https://www.edb.co.il/name/{edb_id}/"


def export_film_crew(films: list, out) -> int:
    """Emit one JSONL record per film (production crew only)."""
    count = 0
    for film in films:
        if not film.get("crew"):
            continue

        people = {}
        for i, c in enumerate(film["crew"]):
            pid = f"person_{i+1:03d}"
            people[pid] = {
                "name_he":       c["name_he"],
                "name_en":       None,
                "aliases":       [],
                "primary_roles": [c["role"]],
                "sources":       [film["url"]],
                "gender":        "unknown",
                "edb_id":        c["edb_id"],
            }

        record = {
            "file":           "",
            "url":            film["url"],
            "source_name":    "edb",
            "status":         "ok",
            "data": {
                "metadata": {
                    "source_url":      film["url"],
                    "source_name":     "edb",
                    "extraction_date": str(date.today()),
                    "language":        "he",
                },
                "entities": {
                    "people": people,
                    "films": {
                        "film_001": {
                            "title_he": film["title"],
                            "title_en": None,
                            "year":     film["year"],
                            "url":      film["url"],
                            "edb_id":   film["film_id"],
                            "is_short": film.get("is_short", False),
                            "crew": [
                                {
                                    "name_he": c["name_he"],
                                    "role":    c["role"],
                                    "role_he": c.get("role_he", ""),
                                    "edb_id":  c["edb_id"],
                                }
                                for c in film["crew"]
                            ],
                        }
                    },
                },
                "roles":         [],
                "relationships": [],
            },
        }
        out.write(json.dumps(record, ensure_ascii=False) + "\n")
        count += len(film["crew"])
    return count


_SKIP_ROLES = {"other", "self", "character", "fictional_character", "film_subject"}


def export_person_credits(persons: list, known_film_ids: set, out) -> tuple[int, int]:
    """Emit one JSONL record per person who has credits in edb_persons.json.

    For actor roles: always emit (these are only on person pages, not film crew pages).
    For all other meaningful roles: only emit films NOT already in edb_films.json so we
    don't duplicate data that was already exported by export_film_crew().

    Returns (persons_exported, total_film_credits).
    """
    persons_out = 0
    credits_out = 0

    for person in persons:
        actor_films = [f for f in person.get("films", []) if f.get("role") == "actor"]
        extra_films = [
            f for f in person.get("films", [])
            if f.get("role") not in _SKIP_ROLES
            and f.get("role") != "actor"
            and f["film_id"] not in known_film_ids
        ]

        eligible = actor_films + extra_films
        # Deduplicate by (film_id, role)
        seen: set[tuple] = set()
        unique_films = []
        for f in eligible:
            key = (f["film_id"], f.get("role", ""))
            if key not in seen:
                seen.add(key)
                unique_films.append(f)

        if not unique_films:
            continue

        edb_id = person["edb_id"]
        url    = EDB_PERSON_URL.format(edb_id=edb_id)

        # Infer primary roles from the eligible films
        all_roles = list({f.get("role", "other") for f in unique_films if f.get("role") not in _SKIP_ROLES})
        if not all_roles:
            all_roles = ["other"]

        films_dict = {}
        for i, f in enumerate(unique_films):
            film_url = EDB_TITLE_URL.format(film_id=f["film_id"])
            films_dict[f"film_{i+1:03d}"] = {
                "title_he": f["title"],
                "title_en": None,
                "year":     f.get("year"),
                "url":      film_url,
                "edb_id":   f["film_id"],
                "is_short": False,
                "crew": [{
                    "name_he": person["name_he"],
                    "role":    f.get("role", "other"),
                    "role_he": f.get("role_he") or "",
                    "edb_id":  edb_id,
                }],
            }

        record = {
            "file":           "",
            "url":            url,
            "source_name":    "edb",
            "status":         "ok",
            "data": {
                "metadata": {
                    "source_url":      url,
                    "source_name":     "edb",
                    "extraction_date": str(date.today()),
                    "language":        "he",
                },
                "entities": {
                    "people": {
                        "person_001": {
                            "name_he":       person["name_he"],
                            "name_en":       person.get("name_en"),
                            "aliases":       [],
                            "primary_roles": all_roles,
                            "sources":       [url],
                            "gender":        "unknown",
                            "edb_id":        edb_id,
                        }
                    },
                    "films": films_dict,
                },
                "roles":         [],
                "relationships": [],
            },
        }
        out.write(json.dumps(record, ensure_ascii=False) + "\n")
        persons_out += 1
        credits_out += len(unique_films)
    return persons_out, credits_out


def main():
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    if not os.path.exists(INPUT_FILMS):
        print(f"ERROR: {INPUT_FILMS} not found. Run scrape_edb.py first.")
        return

    with open(INPUT_FILMS, encoding="utf-8") as f:
        films = json.load(f)

    persons = []
    if os.path.exists(INPUT_PERSONS):
        with open(INPUT_PERSONS, encoding="utf-8") as f:
            persons = json.load(f)
    else:
        print(f"Warning: {INPUT_PERSONS} not found — person credits not exported.")

    known_film_ids = {f["film_id"] for f in films}

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        crew_total = export_film_crew(films, out)
        print(f"Film crew:  {len(films)} films, {crew_total} crew entries")

        if persons:
            p_out, c_out = export_person_credits(persons, known_film_ids, out)
            print(f"Persons:    {p_out} persons, {c_out} film credits (actors + extra films)")

    print(f"→ {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
