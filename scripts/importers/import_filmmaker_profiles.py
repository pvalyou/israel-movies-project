#!/usr/bin/env python3
"""
import_filmmaker_profiles.py — Import complete filmmaker profiles from
directors-guild / agent pages into out/filmmaker_profiles/mentions.jsonl.

Each profile provides: full filmography, fund sources, prizes.
Films get per-film manual:// URLs so they appear individually in the report.

Run: python3 scripts/importers/import_filmmaker_profiles.py [--dry-run]
"""

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

OUT_DIR    = Path("out/filmmaker_profiles")
OUT_JSONL  = OUT_DIR / "mentions.jsonl"
SOURCE_NAME = "filmmaker_profiles"
TODAY = date.today().isoformat()

# ── Profile data ──────────────────────────────────────────────────────────────
# Each profile: page_url, person name+roles, films list
# Film fields: title_he, title_en, year, is_short, role, funds[], prizes[], slug

PROFILES = [
    {
        "page_url":    "https://directorsguild.org.il/user/klil/",
        "source_urls": [
            "https://directorsguild.org.il/user/klil/",
            "https://niveshetcohen.com/rep/%D7%9B%D7%9C%D7%99%D7%9C-%D7%9B%D7%95%D7%91%D7%A9/",
        ],
        "name_he":  "כליל כובש",
        "name_en":  "Klil Kovesh",
        "roles":    ["director", "screenwriter", "composer"],
        "films": [
            # Feature films
            {
                "slug":     "ילדי-בר",
                "title_he": "ילדי בר",
                "title_en": "Bar Children",
                "year":     2024,
                "is_short": False,
                "role":     "director",
                "funds":    ["rabinovich_cinema", "galilee_film_fund"],
                "prizes":   [],
                "notes":    "סרט עלילתי; הפקה",
            },
            {
                "slug":     "אורות",
                "title_he": "אורות",
                "title_en": "Lights",
                "year":     None,
                "is_short": False,
                "role":     "director",
                "funds":    ["rabinovich_cinema"],
                "prizes":   [],
                "notes":    "פיתוח; מענק פיתוח קרן רבינוביץ",
            },
            # Short films
            {
                "slug":     "שכבות-2024",
                "title_he": "שכבות",
                "title_en": "Layers",
                "year":     2024,
                "is_short": True,
                "role":     "director",
                "ext_url":  "https://jff.org.il/he/movie/75247",
                "funds":    ["arava_film_fund", "galilee_film_fund", "makor"],
                "prizes": [
                    "פרס סרט הקצר הטוב ביותר – פסטיבל הקולנוע ירושלים 2024",
                    "פרס השחקנית הטובה ביותר – פסטיבל הקולנוע ירושלים 2024",
                    "Tokyo SSFF",
                    "פסטיבל ירושלים לסרטי נשים",
                    "פסטיבל גליל",
                    "פסטיבל ערבה",
                ],
                "notes":    "23 דקות",
            },
            {
                "slug":     "נחל-עמוד-2025",
                "title_he": "נחל עמוד",
                "title_en": "Nahal Amud",
                "year":     2025,
                "is_short": True,
                "role":     "director",
                "funds":    ["galilee_film_fund"],
                "prizes":   [],
                "notes":    "15 דקות; פוסט-פרודקשן",
            },
            {
                "slug":     "אחו-2020",
                "title_he": "אחו",
                "title_en": "Meadow",
                "year":     2020,
                "is_short": True,
                "role":     "director",
                "ext_url":  "https://jff.org.il/he/movie/40507",
                "funds":    [],
                "prizes": [
                    "פרס התסריט הטוב ביותר – פסטיבל הסרטים הבינלאומי לסטודנטים",
                    "פרס הסרט הטוב ביותר – Robinson Pittsburgh Short Film Competition",
                    "פסטיבל הקולנוע ירושלים",
                ],
                "notes":    "26 דקות",
            },
            {
                "slug":     "ליזהלה-2017",
                "title_he": "ליזה'לה",
                "title_en": "Lizaleh",
                "year":     2017,
                "is_short": True,
                "role":     "director",
                "funds":    [],
                "prizes":   ["Hot 8", "פסטיבל הסרטים הבינלאומי לסטודנטים"],
                "notes":    "15 דקות; דוקומנטרי",
            },
            {
                "slug":     "מסיבת-פרידה-2017",
                "title_he": "מסיבת פרידה",
                "title_en": "Farewell Party",
                "year":     2017,
                "is_short": True,
                "role":     "director",
                "funds":    [],
                "prizes":   ["Indie Prague (הצטיינות)", "פסטיבל דזנצנו, איטליה"],
                "notes":    "28 דקות",
            },
            {
                "slug":     "קראנו-לו-בית-2016",
                "title_he": "קראנו לו בית",
                "title_en": "We Called It Home",
                "year":     2016,
                "is_short": True,
                "role":     "director",
                "funds":    [],
                "prizes":   ["פסטיבל ורשה"],
                "notes":    "17 דקות",
            },
            {
                "slug":     "נינו-2015",
                "title_he": "נינו",
                "title_en": "Nino",
                "year":     2015,
                "is_short": True,
                "role":     "director",
                "funds":    [],
                "prizes":   ["Long Short Festival (פרמיירה)"],
                "notes":    "10 דקות",
            },
        ],
    },
]

FUND_SOURCE_NAMES = {
    "rabinovich_cinema":  "קרן רבינוביץ",
    "galilee_film_fund":  "קרן הגליל",
    "arava_film_fund":    "קרן ערבה",
    "makor":              "קרן מקור",
    "filmfund":           "הקרן הישראלית לקולנוע",
    "nfct":               "הקרן החדשה לקולנוע וטלוויזיה",
    "gesher":             "קרן גשר",
    "jerusalem_film_fund":"קרן ירושלים לקולנוע",
}


def film_url(profile: dict, film: dict) -> str:
    return f"manual://filmmaker_profiles/{profile['name_en'].lower().replace(' ','-')}/{film['slug']}/"


def build_entry(profile: dict) -> dict:
    page_url = profile["page_url"]
    manual   = f"manual://filmmaker_profiles/{profile['name_en'].lower().replace(' ','-')}/profile/"

    people: dict  = {}
    films:  dict  = {}
    roles:  list  = []
    film_urls_for_person: list = []

    for idx, film in enumerate(profile["films"], 1):
        # Use real external URL if one is known (makes title clickable in report),
        # otherwise fall back to per-film manual:// URL for indexing only.
        furl = film.get("ext_url") or film_url(profile, film)
        film_urls_for_person.append(furl)

        fund_names = ", ".join(FUND_SOURCE_NAMES.get(f, f) for f in film["funds"])
        prize_str  = " | ".join(film["prizes"]) if film["prizes"] else ""
        notes_parts = []
        if fund_names:
            notes_parts.append(f"מימון: {fund_names}")
        if prize_str:
            notes_parts.append(f"פרסים: {prize_str}")
        if film.get("notes"):
            notes_parts.append(film["notes"])

        films[f"film_{idx:02d}"] = {
            "title_he":    film["title_he"],
            "title_en":    film.get("title_en"),
            "year":        film.get("year"),
            "is_short":    film.get("is_short", True),
            "url":         furl,
            "funds":       film.get("funds", []),
            "prizes":      film.get("prizes", []),
            "notes":       " · ".join(notes_parts),
        }
        roles.append({
            "id":              f"role_{idx:02d}",
            "person_id":       "person_001",
            "organization_id": None,
            "role_type":       film.get("role", "director"),
            "start_year":      film.get("year"),
            "end_year":        film.get("year"),
            "notes":           film["title_he"],
            "sources":         [furl],
        })

    people["person_001"] = {
        "name_he":       profile["name_he"],
        "name_en":       profile["name_en"],
        "aliases":       [],
        "primary_roles": profile["roles"],
        "film_urls":     film_urls_for_person,
        "sources":       [page_url],
    }

    chash = hashlib.md5(manual.encode()).hexdigest()
    return {
        "file":           f"filmmaker_profiles__{profile['name_en'].lower().replace(' ','-')}__manual.md",
        "url":            page_url,
        "source_name":    SOURCE_NAME,
        "status":         "ok",
        "content_hash":   chash,
        "content_length": 0,
        "filter_info":    {"reason": "manual_canonical_source"},
        "truncated":      False,
        "elapsed_sec":    0,
        "data": {
            "metadata": {
                "source_url":       page_url,
                "source_name":      SOURCE_NAME,
                "extraction_date":  TODAY,
                "language":         "he",
                "canonical_source": page_url,
            },
            "entities": {
                "people": people,
                "organizations": {},
                "films":         films,
                "events":        {},
            },
            "roles":         roles,
            "relationships": [],
            "films":         [],
        },
    }


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        for profile in PROFILES:
            print(f"\n=== {profile['name_he']} ({profile['page_url']}) ===")
            for film in profile["films"]:
                yr    = str(film.get("year") or "dev")
                funds = ", ".join(film.get("funds") or ["—"])
                prizes = len(film.get("prizes") or [])
                print(f"  {film['title_he']:20s}  {yr:6s}  funds={funds:40s}  prizes={prizes}")
        print("\n(dry run — nothing written)")
        return

    all_page_urls = {p["page_url"] for p in PROFILES}
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    existing: list[str] = []
    if OUT_JSONL.exists():
        for line in OUT_JSONL.read_text(encoding="utf-8").splitlines():
            if not line.strip(): continue
            try:
                rec = json.loads(line)
                if rec.get("url", "") in all_page_urls:
                    continue
            except Exception:
                pass
            existing.append(line)

    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for line in existing:
            f.write(line + "\n")
        for profile in PROFILES:
            entry = build_entry(profile)
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            print(f"{profile['name_he']}: {len(profile['films'])} films → {OUT_JSONL}")

    total_films = sum(len(p["films"]) for p in PROFILES)
    print(f"\nWrote {len(PROFILES)} profiles ({total_films} films) to {OUT_JSONL}")


if __name__ == "__main__":
    main()
