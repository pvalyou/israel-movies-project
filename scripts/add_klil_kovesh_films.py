#!/usr/bin/env python3
"""Add כליל כובש filmography to relevant fund mentions.jsonl files.
Source: https://niveshetcohen.com/rep/כליל-כובש/
"""
import json, datetime
from pathlib import Path

TODAY = datetime.date.today().isoformat()
AGENCY_URL = "https://niveshetcohen.com/rep/%D7%9B%D7%9C%D7%99%D7%9C-%D7%9B%D7%95%D7%91%D7%A9/"

def make_film_record(person_name, film_title, film_year, fund_key, fund_label, role_type, notes, url):
    return {
        "file": f"{fund_key}__klil_kovesh_films__manual.md",
        "url": url,
        "source_name": fund_key,
        "status": "ok",
        "content_hash": "manual",
        "content_length": 0,
        "filter_info": {"reason": "manual_import"},
        "truncated": False,
        "elapsed_sec": 0,
        "data": {
            "metadata": {
                "source_url": url,
                "source_name": fund_key,
                "extraction_date": TODAY,
                "language": "he",
                "canonical_source": "agent_research_plan",
            },
            "entities": {
                "people": {
                    "person_001": {
                        "name_he": person_name,
                        "name_en": None,
                        "aliases": [],
                        "primary_roles": [role_type],
                        "context_sentence": f"{role_type} — {film_title} ({film_year}) — {notes}",
                        "sources": [url],
                    }
                },
                "organizations": {
                    "org_001": {
                        "name_he": fund_label,
                        "name_en": None,
                        "type": "fund",
                        "sources": [url],
                    }
                },
                "films": {
                    "film_001": {
                        "title_he": film_title,
                        "title_en": None,
                        "year": film_year,
                        "director_ids": ["person_001"] if role_type == "director" else [],
                        "sources": [url],
                    }
                },
                "events": {},
            },
            "roles": [
                {
                    "id": "role_001_screenwriter",
                    "person_id": "person_001",
                    "organization_id": "org_001",
                    "role_type": "screenwriter",
                    "start_year": film_year,
                    "end_year": film_year,
                    "notes": f"תסריטאית — {film_title}",
                    "sources": [url],
                },
                {
                    "id": "role_002_director",
                    "person_id": "person_001",
                    "organization_id": "org_001",
                    "role_type": "director",
                    "start_year": film_year,
                    "end_year": film_year,
                    "notes": f"במאית — {film_title}",
                    "sources": [url],
                },
            ],
            "relationships": [],
            "films": [],
        },
    }

def main():
    entries = [
        # (film_title, year, fund_key, fund_label, notes)
        ("נחל עמוד", 2025, "galilee_film_fund", "קרן קולנוע גליל",
         "Short film, post-production, supported by Galilee Film Fund + Lehat Family"),
        ("ילדי בר", None, "rabinovich_cinema", "קרן רבינוביץ' לאמנויות",
         "Feature film (90 min), post-production, Rabinowitz Foundation + Galilee Film Fund"),
        ("אורות", None, "rabinovich_cinema", "קרן רבינוביץ' לאמנויות",
         "Feature film (90 min), development, Rabinowitz Foundation development grant"),
    ]

    for film_title, year, fund_key, fund_label, notes in entries:
        out_path = Path(f"out/{fund_key}/mentions.jsonl")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        rec = make_film_record(
            person_name="כליל כובש",
            film_title=film_title,
            film_year=year,
            fund_key=fund_key,
            fund_label=fund_label,
            role_type="screenwriter",
            notes=notes,
            url=AGENCY_URL,
        )
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"Added {film_title} → out/{fund_key}/mentions.jsonl")

if __name__ == "__main__":
    main()
