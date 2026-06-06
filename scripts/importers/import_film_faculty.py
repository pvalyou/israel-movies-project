#!/usr/bin/env python3
"""
import_film_faculty.py — Import film school faculty from film_faculty_data/faculty_members.json
into out/film_schools/mentions.jsonl.

Sources: Sam Spiegel Film School, Sapir College, Tel Aviv University (TAU)

Run: python3 import_film_faculty.py [--dry-run]
"""

import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

OUT_JSONL   = Path("out/film_schools/mentions.jsonl")
SOURCE_FILE = Path("film_faculty_data/faculty_members.json")
SOURCE_NAME = "film_schools"
TODAY       = date.today().isoformat()

MANUAL_URLS = {
    "sam_spiegel":         "manual://film_schools/sam-spiegel-faculty-2026/",
    "sapir_college":       "manual://film_schools/sapir-faculty-2026/",
    "tel_aviv_university": "manual://film_schools/tau-faculty-2026/",
    "minshar":             "manual://film_schools/minshar-faculty-2026/",
    "beit_berl":           "manual://film_schools/beit-berl-faculty-2026/",
    "tau_arts_admin":      "manual://film_schools/tau-arts-admin-2026/",
    "bezalel_academy":     "manual://film_schools/bezalel-faculty-2026/",
    "seminar_hakibbutzim": "manual://film_schools/seminar-hakibbutzim-faculty-2026/",
    "ariel_university":    "manual://film_schools/ariel-university-faculty-2026/",
    "open_university":     "manual://film_schools/open-university-faculty-2026/",
    "outside_the_frame":   "manual://film_schools/outside-the-frame-faculty-2026/",
    "high_school_cinema":  "manual://film_schools/high-school-cinema-teachers-2026/",
}
CANONICAL_URLS = {
    "sam_spiegel":         "https://www.jsfs.co.il/teaching-staff",
    "sapir_college":       "https://www.sapir.ac.il/ba/cinema",
    "tel_aviv_university": "https://arts.tau.ac.il/filmTV/stf",
    "minshar":             "https://minshar.org.il/film-studies/faculty-members",
    "beit_berl":           "https://www.beitberl.ac.il/colleges/arts",
    "tau_arts_admin":      "https://arts.tau.ac.il/administration",
    "bezalel_academy":     "https://www.bezalel.ac.il",
    "seminar_hakibbutzim": "https://www.smkb.ac.il",
    "ariel_university":    "https://www.ariel.ac.il",
    "open_university":     "https://www.openu.ac.il",
    "outside_the_frame":   "manual://outside-the-frame",
    "high_school_cinema":  "https://meyda.education.gov.il",
}
INST_NAMES_HE = {
    "sam_spiegel":         "בית הספר סם שפיגל לקולנוע וטלוויזיה",
    "sapir_college":       "מכללת ספיר – בית הספר לאמנויות הקול והמסך",
    "tel_aviv_university": "אוניברסיטת תל אביב – בית הספר לקולנוע וטלוויזיה",
    "minshar":             "מנשר לאמנות – בית הספר לקולנוע וטלוויזיה",
    "beit_berl":           "מכללת בית ברל – המחלקה לאמנות",
    "tau_arts_admin":      "אוניברסיטת תל אביב – פקולטה לאמנויות (מינהל)",
    "bezalel_academy":     "אקדמיית בצלאל לאמנות ועיצוב – המחלקה לאמנויות המסך",
    "seminar_hakibbutzim": "סמינר הקיבוצים – החוג לתקשורת וקולנוע",
    "ariel_university":    "אוניברסיטת אריאל – בית הספר לתקשורת",
    "open_university":     "האוניברסיטה הפתוחה – לימודי קולנוע",
    "outside_the_frame":   'סדרות הרצאות "מחוץ לפריים"',
    "high_school_cinema":  "משרד החינוך – מורי קולנוע בתי ספר תיכוניים",
}
INST_NAMES_EN = {
    "sam_spiegel":         "Sam Spiegel Film & TV School Jerusalem",
    "sapir_college":       "Sapir College – School of Screen Arts",
    "tel_aviv_university": "Tel Aviv University – Steve Tisch School of Film and Television",
    "minshar":             "Minshar School of Art – Film & Television",
    "beit_berl":           "Beit Berl College – Art Department",
    "tau_arts_admin":      "Tel Aviv University – Faculty of Arts (Administration)",
    "bezalel_academy":     "Bezalel Academy of Arts and Design – Screen-Based Arts",
    "seminar_hakibbutzim": "Seminar HaKibbutzim College – Cinema & Communication",
    "ariel_university":    "Ariel University – School of Communication",
    "open_university":     "The Open University of Israel – Film Studies",
    "outside_the_frame":   "Outside the Frame — Public Lecture Series",
    "high_school_cinema":  "Israel MoE — High-school Cinema Teachers",
}

# Prefixes/suffixes to strip from names
_STRIP_PREFIX = re.compile(
    r"""^(ד["״]ר|פרופ['׳]?\s*חבר|פרופ['׳]|פרופסור\s*חבר|פרופסור|ד["״]ר\s+)""",
    re.UNICODE,
)
_STRIP_SUFFIX = re.compile(
    r"""\s*[–—-]\s*(עמית\s*הוראה|עוזר\s*הוראה|סגל\s*אקדמי.*|מרצה.*|פרופסור.*|בדימוס|אמריטוס|.*?\bstatus\b.*)$""",
    re.UNICODE,
)
_WHITESPACE = re.compile(r"\s+")


def clean_name(raw: str) -> str | None:
    """Strip academic titles/role suffixes from a raw name string."""
    s = raw.strip()
    s = _STRIP_PREFIX.sub("", s).strip()
    s = _STRIP_SUFFIX.sub("", s).strip()
    s = _WHITESPACE.sub(" ", s).strip()
    # Skip if looks like an org, role phrase, or too short
    if len(s) < 3 or any(x in s for x in ["@", "http", "בוגרים", "קורס", "מחלקת"]):
        return None
    return s


def reverse_name(name: str) -> str:
    """Reverse 'Family Given' → 'Given Family' for Sam Spiegel inverted format."""
    parts = name.split()
    if len(parts) == 2:
        return f"{parts[1]} {parts[0]}"
    if len(parts) == 3:
        # Could be "Ben Porat Shira" → "Shira Ben Porat" or compound family name
        # Heuristic: if first part is short (<4 chars), treat as compound: keep as-is
        if len(parts[0]) >= 4:
            return f"{parts[-1]} {' '.join(parts[:-1])}"
    return name  # leave compound names as-is


def role_for(role_str: str) -> str:
    """Map a Hebrew role string to our taxonomy."""
    s = role_str.strip()
    # Academic / teaching — "דקאן" only when it's the role itself, not "לשכת דקאן"
    if s.startswith("דקאן") or any(x in s for x in [
                              'ראש ביה"ס', 'ראש בי"ס', "ראש בית",
                              "ראש מסלול", "ראשת מסלול", "ראש חטיבה",
                              "ראש התכנית", "סגל אקדמי", "אמריטוס",
                              "בדימוס", "עמית הוראה", "מרצה", "מורה"]):
        return "faculty"
    # Cinematheque / film library
    if "סינימטק" in s:
        return "cinematheque_director"
    # Archive
    if "ארכיון" in s:
        return "archivist"
    # Library
    if any(x in s for x in ["ספרן", "ספריי", "ספרייה", "ספרי"]):
        return "librarian"
    # IT / computing / technical / facilities / maintenance
    if any(x in s for x in ["טכנאי", "מחשוב", "טכני", "תחזוקה", "מולטימדיה",
                              "מאגרי מידע", "דיגיטל", "מנהל גוש", "מנהל בית",
                              "סגן מנהל גוש", "אחראי סדנ"]):
        return "technician"
    # Everything else (coordinators, managers, HR, production staff, etc.)
    return "administrator"


def collect_sam_spiegel(info: dict) -> list[tuple[str, str]]:
    """Return [(name_he, role), ...] for Sam Spiegel (inverted name format)."""
    results = []
    for raw in info.get("teaching_staff", []):
        if isinstance(raw, dict):
            name = clean_name(raw.get("name", ""))
            role = raw.get("role", "faculty")
        else:
            name = clean_name(str(raw))
            role = "faculty"
        if not name:
            continue
        # Sam Spiegel lists are "Family Given" — reverse to "Given Family"
        normal = reverse_name(name)
        results.append((normal, role_for(role)))
    return results


def collect_sapir(info: dict) -> list[tuple[str, str]]:
    results = []
    # leadership — dicts with name + role
    for item in info.get("leadership", []):
        if isinstance(item, dict):
            name = clean_name(item.get("name", ""))
            role = item.get("role", "faculty")
        else:
            name = clean_name(str(item))
            role = "faculty"
        if name:
            results.append((name, role_for(role)))

    # flat lists: professors, senior_lecturers, lecturers_and_adjunct
    for key in ("professors", "senior_lecturers", "lecturers_and_adjunct"):
        for raw in info.get(key, []):
            name = clean_name(str(raw) if not isinstance(raw, str) else raw)
            if name:
                results.append((name, "faculty"))
    return results


def collect_tau(info: dict) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(raw, role="faculty"):
        if isinstance(raw, dict):
            name = clean_name(raw.get("name", ""))
            r = raw.get("role", role)
        else:
            name = clean_name(str(raw))
            r = role
        if not name or name in seen:
            return
        seen.add(name)
        results.append((name, role_for(r)))

    for item in info.get("leadership", []):
        add(item)
    for raw in info.get("senior_faculty", []):
        add(raw)
    # Deduplicate across teaching_staff and junior pages
    for key in ("teaching_staff_page1", "teaching_staff_page2_junr",
                "junior_staff_page1", "junior_staff_page2",
                "junior_staff_page3", "junior_staff_page4"):
        for raw in info.get(key, []):
            add(raw)
    return results


def collect_flat(info: dict) -> list[tuple[str, str]]:
    """Collect from schools using leadership (dicts) + faculty (flat strings)."""
    results: list[tuple[str, str]] = []
    seen: set[str] = set()

    for item in info.get("leadership", []):
        if isinstance(item, dict):
            name = clean_name(item.get("name", ""))
            role = item.get("role", "faculty")
        else:
            name = clean_name(str(item))
            role = "faculty"
        if name and name not in seen:
            seen.add(name)
            results.append((name, role_for(role)))

    for raw in info.get("faculty", []):
        name = clean_name(str(raw) if not isinstance(raw, str) else raw)
        if name and name not in seen:
            seen.add(name)
            results.append((name, "faculty"))

    return results


def collect_tau_arts_admin(info: dict) -> list[tuple[str, str]]:
    """Collect all staff from the TAU Faculty of Arts administration page."""
    results: list[tuple[str, str]] = []
    seen: set[str] = set()
    SECTION_KEYS = [
        "leadership", "administration", "senior_academic_staff",
        "film_tv_staff", "theater_staff", "music_school_staff",
        "architecture_school_staff", "gallery_archives_staff",
        "students_programs_staff", "art_history_staff", "facilities_it_staff",
        "other_staff",
    ]
    for key in SECTION_KEYS:
        for item in info.get(key, []):
            if isinstance(item, dict):
                name = clean_name(item.get("name", ""))
                role = item.get("role", "faculty")
            else:
                name = clean_name(str(item))
                role = "faculty"
            if not name or name in seen:
                continue
            seen.add(name)
            results.append((name, role_for(role)))
    return results


COLLECTORS = {
    "sam_spiegel_film_school": ("sam_spiegel",         collect_sam_spiegel),
    "sapir_college":           ("sapir_college",        collect_sapir),
    "tel_aviv_university":     ("tel_aviv_university",  collect_tau),
    "minshar_art_school":      ("minshar",              collect_flat),
    "beit_berl_college":       ("beit_berl",            collect_flat),
    "tau_arts_admin":          ("tau_arts_admin",        collect_tau_arts_admin),
    "bezalel_academy":         ("bezalel_academy",      collect_flat),
    "seminar_hakibbutzim":     ("seminar_hakibbutzim",  collect_flat),
    "ariel_university":        ("ariel_university",     collect_flat),
    "open_university":         ("open_university",      collect_flat),
    "outside_the_frame":       ("outside_the_frame",    collect_flat),
    "high_school_cinema":      ("high_school_cinema",   collect_flat),
}


def build_entry(school_key: str, people: list[tuple[str, str]]) -> dict:
    manual_url    = MANUAL_URLS[school_key]
    canonical_url = CANONICAL_URLS[school_key]

    people_dict: dict[str, dict] = {}
    roles_list:  list[dict]      = []
    for idx, (name_he, role) in enumerate(people, 1):
        pid = f"person_{idx:03d}"
        people_dict[pid] = {
            "name_he":       name_he,
            "name_en":       None,
            "aliases":       [],
            "primary_roles": [role],
            "sources":       [manual_url],
        }
        roles_list.append({
            "id":              f"role_{idx:03d}",
            "person_id":       pid,
            "organization_id": "org_001",
            "role_type":       role,
            "start_year":      None,
            "end_year":        None,
            "notes":           "",
            "sources":         [manual_url],
        })

    chash = hashlib.md5(manual_url.encode()).hexdigest()
    return {
        "file":           f"film_schools__{school_key}__manual.md",
        "url":            manual_url,
        "source_name":    SOURCE_NAME,
        "status":         "ok",
        "content_hash":   chash,
        "content_length": 0,
        "filter_info":    {"reason": "manual_canonical_source"},
        "truncated":      False,
        "elapsed_sec":    0,
        "data": {
            "metadata": {
                "source_url":       manual_url,
                "source_name":      SOURCE_NAME,
                "extraction_date":  TODAY,
                "language":         "he",
                "canonical_source": canonical_url,
            },
            "entities": {
                "people": people_dict,
                "organizations": {
                    "org_001": {
                        "name_he": INST_NAMES_HE[school_key],
                        "name_en": INST_NAMES_EN[school_key],
                        "type":    "educational_institution",
                        "subtype": "film_school",
                        "sources": [manual_url],
                    }
                },
                "films":  {},
                "events": {},
            },
            "roles":         roles_list,
            "relationships": [],
            "films":         [],
        },
    }


def main():
    dry_run = "--dry-run" in sys.argv

    data = json.loads(SOURCE_FILE.read_text(encoding="utf-8"))

    entries: list[dict] = []
    all_manual_urls: set[str] = set()

    for json_key, (school_key, collector) in COLLECTORS.items():
        info = data.get(json_key, {})
        if not info:
            print(f"Warning: {json_key} not found in JSON", file=sys.stderr)
            continue
        people = collector(info)
        # Deduplicate by name within school
        seen: set[str] = set()
        unique = []
        for name, role in people:
            if name not in seen:
                seen.add(name)
                unique.append((name, role))
        if dry_run:
            print(f"\n=== {INST_NAMES_HE[school_key]} ({MANUAL_URLS[school_key]}) ===")
            print(f"  {len(unique)} unique people")
            for name, role in unique[:10]:
                print(f"    {name:30s}  {role}")
            if len(unique) > 10:
                print(f"    … and {len(unique)-10} more")
        else:
            entry = build_entry(school_key, unique)
            entries.append(entry)
            all_manual_urls.add(MANUAL_URLS[school_key])
            print(f"{school_key}: {len(unique)} people")

    if dry_run:
        print("\n(dry run — nothing written)")
        return

    # Read existing, strip old faculty imports
    existing: list[str] = []
    if OUT_JSONL.exists():
        for line in OUT_JSONL.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                if rec.get("url", "") in all_manual_urls:
                    continue
            except Exception:
                pass
            existing.append(line)

    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for line in existing:
            f.write(line + "\n")
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    total = sum(len(e["data"]["entities"]["people"]) for e in entries)
    print(f"Wrote {len(entries)} entries ({total} people) to {OUT_JSONL}")


if __name__ == "__main__":
    main()
