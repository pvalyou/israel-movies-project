#!/usr/bin/env python3
"""
import_jff_staff.py — Import Jerusalem Film Festival film-selection staff
into out/jff_staff/mentions.jsonl.

Covers: 2019, 2022, 2023, 2025  (2020, 2021, 2024 pages not publicly available)

Sources:
  2019: https://jff.org.il/he/article/6145
  2022: https://jff.org.il/he/מאמר/58098
  2023: https://jff.org.il/he/מאמר/68273
  2025: https://jff.org.il/he/מאמר/86793

Run: python3 scripts/importers/import_jff_staff.py [--dry-run]
"""

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

OUT_DIR     = Path("out/jff_staff")
OUT_JSONL   = OUT_DIR / "mentions.jsonl"
SOURCE_NAME = "jff_staff"
TODAY       = date.today().isoformat()

# ── Per-year data ─────────────────────────────────────────────────────────────
# Roles: festival_programmer = film selector/programmer (STRICT_INST_ROLE)
#        artistic_director   = artistic direction (SOFT_INST_ROLE)
#        ceo                 = executive director (STRICT_INST_ROLE)
# Only gatekeeping roles are included; general operational staff are omitted.

YEARS: dict[int, dict] = {

    2019: {
        "canonical_url": "https://jff.org.il/he/article/6145",
        "staff": [
            ("נועה רגב",           "ceo"),               # Executive Director
            ("אלעד סמורזיק",       "artistic_director"), # Artistic Director
            # International selection
            ("ויויאן אוסטרובסקי",  "festival_programmer"),
            ("טל מאירי",           "festival_programmer"),
            ("רוני מהדב-לוין",     "festival_programmer"),
            ("דניאלה תורגמן",      "festival_programmer"),
            ("דניאל זוז",          "festival_programmer"),
            ("אתי ציקו",           "festival_programmer"),
            ("נבו שנער",           "festival_programmer"),
            ("אמרי דקל-קדוש",      "festival_programmer"),
            # Israeli Narrative
            ("טובה אשר",           "festival_programmer"),
            ("רפאל נדג'רי",        "festival_programmer"),
            ("כליל כובש",          "festival_programmer"),
            # Israeli Documentary
            ("רנא אבו-פריחה",      "festival_programmer"),
            ("ראובן פלגי-הקר",     "festival_programmer"),
            ("יעל מונק",           "festival_programmer"),
            ("שקד גורן",           "festival_programmer"),
            # Short Films
            ("ליהי סבג",           "festival_programmer"),
            ("בעז פרנקל",          "festival_programmer"),
            ("נטע רנה מור",        "festival_programmer"),
            ("מיכאל רוזנוב",       "festival_programmer"),
            ("נבות ברנע",          "festival_programmer"),
            ("אדוה מגל-כהן",       "festival_programmer"),
            # Video Art & Experimental
            ("רונית עדן",          "festival_programmer"),
            ("רות פת'ר",           "festival_programmer"),
            ("חן שיינברג",         "festival_programmer"),
            # Pitch Point
            ("קרן שמש",            "festival_programmer"),
            ("סוהא עראף",          "festival_programmer"),
            ("שרון שמיר",          "festival_programmer"),
        ],
    },

    2022: {
        "canonical_url": "https://jff.org.il/he/%D7%9E%D7%90%D7%9E%D7%A8/58098",
        "staff": [
            ("רוני מהדב-לוין",     "ceo"),
            ("אלעד סמורזיק",       "artistic_director"),
            # International
            ("ויויאן אוסטרובסקי",  "festival_programmer"),
            ("דניאלה תורגמן",      "festival_programmer"),
            ("ג'ניפר אבסירה",      "festival_programmer"),
            ("אלה טל",             "festival_programmer"),
            # Israeli Narrative
            ("סמירה סרייה",        "festival_programmer"),
            ("אלעד קידן",          "festival_programmer"),
            ("בן טופח",            "festival_programmer"),
            ("גלי סמו",            "festival_programmer"),
            # Israeli Documentary
            ("ג'ולי שלז",          "festival_programmer"),
            ("קובי פרג'",          "festival_programmer"),
            ("ענת אבן",            "festival_programmer"),
            # Short Films
            ("מיה לנדסמן",         "festival_programmer"),
            ("נבות ברנע",          "festival_programmer"),
            ("יונתן דובק",         "festival_programmer"),
            ("סוהא עראף",          "festival_programmer"),
            ("רובי אלמליח",        "festival_programmer"),
            # Video Art
            ("יאן טיכי",           "festival_programmer"),
            ("דביר שקד",           "festival_programmer"),
            ("הדסה גולדויכט",      "festival_programmer"),
        ],
    },

    2023: {
        "canonical_url": "https://jff.org.il/he/%D7%9E%D7%90%D7%9E%D7%A8/68273",
        "staff": [
            ("רוני מהדב-לוין",     "ceo"),
            ("אלעד סמורזיק",       "artistic_director"),
            # International
            ("יובל פלוטקין",       "festival_programmer"),
            ("ויויאן אוסטרובסקי",  "festival_programmer"),
            ("דניאלה תורגמן-גלס",  "festival_programmer"),
            # Israeli Narrative
            ("דינה צבי-ריקליס",    "festival_programmer"),
            ("מיכאל מושונוב",      "festival_programmer"),
            ("בן טופח",            "festival_programmer"),
            # Israeli Documentary
            ("איריס זכי",          "festival_programmer"),
            ("דוד וקסמן",          "festival_programmer"),
            ("ג'ולי שלז",          "festival_programmer"),
            # Short Films
            ("ג'ניפר אבסירה",      "festival_programmer"),
            ("נבות ברנע",          "festival_programmer"),
            ("אור סיגולי",         "festival_programmer"),
            ("שירה הוכמן",         "festival_programmer"),
            ("שאדי חביב אללה",     "festival_programmer"),
            ("טליה גלאון",         "festival_programmer"),
            # Video Art
            ("טל יחס",             "festival_programmer"),
            ("עירית כרמון פופר",   "festival_programmer"),
            ("יוסי עטיה",          "festival_programmer"),
            # Pitch
            ("אווה קאהן",          "festival_programmer"),
            ("נועה רגב",           "festival_programmer"),
        ],
    },

    2025: {
        "canonical_url": "https://jff.org.il/he/%D7%9E%D7%90%D7%9E%D7%A8/86793",
        "staff": [
            ("רוני מהדב-לוין",     "ceo"),
            ("אור סיגולי",         "artistic_director"),
            # International
            # Israeli Narrative
            ("נור פיבק",           "festival_programmer"),
            ("נטע דבורקיס",        "festival_programmer"),
            ("מיכל חג'ג'",         "festival_programmer"),
            # Israeli Documentary
            ("אילנית סוויסה",      "festival_programmer"),
            ("אסף לפיד",           "festival_programmer"),
            ("עדי משניות",         "festival_programmer"),
            # Israeli Shorts
            ("נבות ברנע",          "festival_programmer"),
            ("אלה טל",             "festival_programmer"),
            ("עופר ליברגל",        "festival_programmer"),
            ("נעה גוסקוב",         "festival_programmer"),
            ("אלון רוזנבלום",      "festival_programmer"),
            ("אפרת רסנר",          "festival_programmer"),
            # Video Art
            ("שחר בן-נון",         "festival_programmer"),
            ("רינת אדלשטיין",      "festival_programmer"),
            ("רועי מנחם מרקוביץ", "festival_programmer"),
        ],
    },
}

ORG_HE = "פסטיבל הקולנוע ירושלים"
ORG_EN = "Jerusalem Film Festival"


def manual_url(year: int) -> str:
    return f"manual://jff_staff/selectors-{year}/"


def build_entry(year: int) -> dict:
    data = YEARS[year]
    canonical = data["canonical_url"]
    manual    = manual_url(year)
    staff     = data["staff"]

    # Deduplicate by name (same person may appear in multiple sections)
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for name, role in staff:
        if name not in seen:
            seen.add(name)
            unique.append((name, role))

    people: dict[str, dict] = {}
    roles:  list[dict]      = []
    for idx, (name_he, role) in enumerate(unique, 1):
        pid = f"person_{idx:03d}"
        people[pid] = {
            "name_he":       name_he,
            "name_en":       None,
            "aliases":       [],
            "primary_roles": [role],
            "sources":       [manual],
        }
        roles.append({
            "id":              f"role_{idx:03d}",
            "person_id":       pid,
            "organization_id": "org_001",
            "role_type":       role,
            "start_year":      year,
            "end_year":        year,
            "notes":           "",
            "sources":         [manual],
        })

    chash = hashlib.md5(manual.encode()).hexdigest()
    return {
        "file":           f"jff_staff__selectors-{year}__manual.md",
        "url":            manual,
        "source_name":    SOURCE_NAME,
        "status":         "ok",
        "content_hash":   chash,
        "content_length": 0,
        "filter_info":    {"reason": "manual_canonical_source"},
        "truncated":      False,
        "elapsed_sec":    0,
        "data": {
            "metadata": {
                "source_url":       manual,
                "source_name":      SOURCE_NAME,
                "extraction_date":  TODAY,
                "language":         "he",
                "canonical_source": canonical,
            },
            "entities": {
                "people": people,
                "organizations": {
                    "org_001": {
                        "name_he": ORG_HE,
                        "name_en": ORG_EN,
                        "type":    "festival",
                        "subtype": "film_festival",
                        "sources": [manual],
                    }
                },
                "films":  {},
                "events": {},
            },
            "roles":         roles,
            "relationships": [],
            "films":         [],
        },
    }


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    all_manual_urls = {manual_url(y) for y in YEARS}

    if dry_run:
        for year in sorted(YEARS):
            data   = YEARS[year]
            manual = manual_url(year)
            seen: set[str] = set()
            unique = [(n, r) for n, r in data["staff"] if not seen.add(n) and n not in seen or (seen.add(n) or n in seen)]
            # simpler dedup
            seen2: set[str] = set()
            uniq2 = []
            for n, r in data["staff"]:
                if n not in seen2:
                    seen2.add(n)
                    uniq2.append((n, r))
            print(f"\n=== JFF {year} ({manual}) ===")
            print(f"  {len(uniq2)} unique people")
            for name, role in uniq2:
                print(f"    {name:30s}  {role}")
        print("\n(dry run — nothing written)")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Strip old JFF entries, keep others
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

    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for line in existing:
            f.write(line + "\n")
        for year in sorted(YEARS):
            entry = build_entry(year)
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            n = len(entry["data"]["entities"]["people"])
            print(f"JFF {year}: {n} people → {manual_url(year)}")

    total = sum(len(build_entry(y)["data"]["entities"]["people"]) for y in YEARS)
    print(f"\nWrote {len(YEARS)} entries ({total} people) to {OUT_JSONL}")


if __name__ == "__main__":
    main()
