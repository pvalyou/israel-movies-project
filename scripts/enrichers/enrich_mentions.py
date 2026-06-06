#!/usr/bin/env python3
"""
enrich_mentions.py — Enrich existing mentions.jsonl in-place with:

  1. Year on roles — when start_year AND end_year are both null, infer from:
       a) Film year on the same page (most reliable — person worked on this film)
       b) Year in URL path  /(20XX)/
       c) Year in metadata extraction_date

  2. Gender on person entities — add 'gender': 'f'|'m'|'unknown'
     using Hebrew name lookup + morphological heuristics.

Idempotent: re-running is safe — already-set fields are not overwritten.

Usage:
    python3 enrich_mentions.py [--glob "out/*/mentions.jsonl"] [--dry-run] [--source nfct]
"""

import argparse
import glob
import json
import re
import sys
from pathlib import Path

# ── Hebrew name gender tables ──────────────────────────────────────────────────

FEMALE_NAMES = {
    "שרה", "רבקה", "לאה", "רחל", "מרים", "דבורה", "חנה", "תמר", "נעמי", "רות",
    "אסתר", "נועה", "מיכל", "אביגיל", "דינה", "ענת", "יעל", "גלית", "אורית", "מיה",
    "לי", "אילנה", "יפית", "ציפי", "ריקי", "ורד", "דפנה", "רונית", "אפרת", "טלי",
    "שיר", "עינב", "כרמית", "ליאת", "ניצן", "שירה", "עדי", "הילה", "ענבל",
    "תמי", "שולמית", "פנינה", "שושנה", "עליזה", "רינה", "ניצה", "אסנת", "אורנה",
    "לירון", "מיטל", "אהובה", "נירית", "אמירה", "גאולה", "אדוה",
    "יונית", "רחלי", "נעמה", "שרון", "נגה", "אורה", "ברכה", "גילה", "זהבה",
    "טובה", "יהודית", "כוכבה", "מרגלית", "נחמה", "ציפורה", "תרצה", "בתיה", "חיה",
    "מינה", "עדינה", "פרידה", "צביה", "קלרה", "רוזה", "שיינדל", "ויקטוריה",
    "ג׳ניפר", "סוזן", "פאולה", "אירית", "גנית", "מאיה", "נירה", "עינת", "צליל",
    "קטי", "רינת", "שנית", "תהילה", "יפה", "חגית", "רחמה", "זוהרה", "רוני",
    "אגם", "דנה", "לירי", "נטע", "איילת", "אביטל", "שושי", "חנית", "ורדית",
    "הדסה", "יעלי", "ציונה", "אורלי", "בלה", "לילך", "אלמה", "נורית",
    "נאוה", "ליהי", "רותם", "ספיר", "מיכאלה",
    "אביבה", "אביבית", "שלומית", "גבריאלה", "נטלי", "ריטה", "ורוניקה",
    "מרגו", "אנה", "יוליה", "קסניה", "נינה", "מרינה", "אלנה", "אירנה",
    "חמוטל", "ענבר", "שירן", "טליה",
    "לימור", "רוית", "יפעת", "כלנית", "דניאלה", "נטליה",
    "שני", "גאיה", "אלה",
    # Common names missing from original list
    "מעיין", "מירי", "צמרת", "לי-אור", "מור", "זהר",
    "אביה", "שילה", "שחרית", "לינור", "ירדנה",
    "דליה", "ציפה", "מרב", "רוית", "כלנית",
    "איריס", "ליבי", "סיגל", "רותי", "עדנה",
    "ופא", "מייסם", "נדאא", "אמל", "רים", "חנאן", "מרוה",
    "סנא", "לובנה", "אסמאא", "שרין", "ראמה", "ולאא", "בתל",
    "ג'ולי", "שירלי", "סופי", "קארן", "לינדה", "מוניקה",
    "רויטל", "אסתי", "מיטל", "הדר", "שלי", "אילת",
    "קציעה", "טובית", "זמירה", "פנינית", "יפעת", "חמוטל",
    "מורן", "יפה", "נוף", "למיס", "ספאא", "לינא", "סואר",
    "אסיל", "דימה", "ניבין", "אמאל", "ריהאם",
}

MALE_NAMES = {
    "דוד", "משה", "אברהם", "יצחק", "יעקב", "יוסף", "שלמה", "אהרון", "לוי", "שמעון",
    "דניאל", "גבריאל", "מיכאל", "רפאל", "אורי", "רון", "יואב", "איתן", "עמיר", "גיל",
    "אבי", "נתן", "ניר", "אייל", "אלון", "אמיר", "ארז", "ברק", "גד",
    "דרור", "הראל", "זיו", "חגי", "יואל", "כפיר", "לירן", "מורן",
    "פיני", "צור", "קובי", "רועי", "שחר", "תום", "אדם", "בן", "דן",
    "הדר", "חן", "ידין", "יניב", "כרם", "לב", "מאור", "נמרוד", "ענר", "פז", "צבי",
    "אבנר", "בועז", "גדעון", "דב", "הלל", "ויקטור", "זאב",
    "חיים", "טוביה", "יהודה", "כלב", "מנחם", "נחום", "עזרא", "פינחס", "צדוק", "קיש",
    "ראובן", "שמואל", "ישי", "אביב", "אופיר", "אליאב", "בנימין", "גרשון", "הרצל",
    "ויצמן", "זכריה", "חנוך", "יורם", "כדורי", "לאור", "מרדכי", "נסים", "עמוס",
    "פרץ", "ציון", "קלמן", "רמי", "שלו", "תמיר", "אסף", "אורן", "ירון", "יריב",
    "שלומי", "יאיר", "עידו", "גיורא", "אמנון", "נחמן", "יהושע", "פנחס",
    "שמשון", "גדליה", "מתתיהו", "אלחנן", "ירמיהו", "יחזקאל",
    "אלי", "עמנואל", "שמעון", "אביחי", "רועי",
    "יגאל", "בנצי", "גרי", "מיכי", "צחי", "אלדד", "עדו",
    "אריאל", "שגיא", "רן",
    "יובל", "עוז", "ידיד", "ניב", "איל",
    "דורון", "ניסן", "פרדי", "מרסל", "ז׳ק", "ז׳אן", "אנדרה", "רוברט",
    "ג׳ק", "מארק", "פול", "פטריק", "ז׳ן", "בוריס", "אלכסנדר",
    "אלכס", "מקסים", "ולדימיר", "סרגיי", "אנטון", "ויקטור", "ניקולאי",
    # More Israeli male names
    "גיא", "יונתן", "יהונתן", "איתי", "ערן", "יוסי", "דני", "תומר", "נדב",
    "עידן", "יותם", "עמרי", "רונן", "אילן", "גלעד",
    "אריק", "אלכס", "איתמר", "אוהד", "עומרי", "רוי", "מתן", "עופר",
    "עודד", "אלעד", "אמרי", "אודי", "מאיר", "אסי", "מוטי",
    "ניב", "שגיא", "יגאל", "נעם", "אלי",
    "ג'ונתן", "ג'וני", "ג'אד", "פייר",
    # Arabic male names
    "חליל", "ואיל", "ראמי", "נאדר", "בשיר", "פאדי", "מחמוד", "זיאד",
    "יאסר", "ח'אלד", "ג'מאל", "פואד", "סאמי", "חנא", "ואליד", "נדאל",
    "רפיק", "בסאם", "נאיף", "כמאל", "עאדל", "טארק", "מאזן", "האני",
    # More Israeli male names
    "רובי", "בני", "עמיקם", "רם", "ארי", "פלג", "רן",
    "יוחנן", "אשר", "דולב", "ארקדי", "דידי", "עמי", "ספי",
    "שאול", "גדי", "שמעיה", "פייסל", "חמד", "בדר",
}

UNISEX_NAMES = {
    "טל", "עמית", "שי", "גל", "קרן", "עומר", "נועם", "אביב", "עדן", "שחר",
    "ליאור", "ניצן", "נוי", "ים", "רום", "שקד", "ראם", "אור", "בר", "גיא",
    "רון", "דן", "חן", "הדר",
}

MALE_HE_EXCEPTIONS = {
    "משה", "יהודה", "אליהו", "נחמיה", "זכריה", "ירמיה", "ישעיה", "עובדיה", "מנשה",
}

JUNK_NAME_RE = re.compile(
    r"^(שם|name|full name|לקטורים|יועצים|חברי|הועדה|"
    r"שם מלא|שם פרטי|שם משפחה)$",
    re.IGNORECASE,
)

URL_YEAR_RE   = re.compile(r"/(20\d{2})/")
DATE_YEAR_RE  = re.compile(r"^(20\d{2})")
FILM_URL_RE   = re.compile(r"/(film|films|movie|movies|סרט|סרטים)/", re.IGNORECASE)


def infer_gender(name_he: str) -> str:
    if not name_he:
        return "unknown"
    first = name_he.strip().split()[0]
    if first in UNISEX_NAMES:
        return "unknown"
    if first in FEMALE_NAMES:
        return "f"
    if first in MALE_NAMES:
        return "m"
    if first.endswith("ית"):
        return "f"
    if len(first) > 2 and first.endswith("ה") and first not in MALE_HE_EXCEPTIONS:
        return "f"
    return "unknown"


def is_junk_name(name: str) -> bool:
    if not name or len(name.strip()) < 3:
        return True
    if JUNK_NAME_RE.match(name.strip()):
        return True
    words = name.strip().split()
    if len(words) > 6 or len(words) == 1:
        return True
    return False


def infer_year_from_url(url: str) -> int | None:
    m = URL_YEAR_RE.search(url or "")
    if m:
        y = int(m.group(1))
        if 2000 <= y <= 2030:
            return y
    return None


def infer_year_from_metadata(meta: dict) -> int | None:
    date_str = (meta.get("extraction_date") or "")[:10]
    m = DATE_YEAR_RE.match(date_str)
    if m:
        y = int(m.group(1))
        if 2000 <= y <= 2030:
            return y
    return None


def best_film_year(films: dict) -> int | None:
    years = []
    for f in films.values():
        if f and f.get("year"):
            try:
                y = int(f["year"])
                if 2000 <= y <= 2030:
                    years.append(y)
            except (TypeError, ValueError):
                pass
    return min(years) if years else None


def enrich_entry(r: dict) -> tuple[dict, bool]:
    """Return (enriched_record, changed)."""
    changed = False
    if r.get("status") != "ok":
        return r, False

    data = r.get("data") or {}
    meta = data.get("metadata") or {}
    entities = data.get("entities") or {}
    people = entities.get("people") or {}
    films = entities.get("films") or {}
    roles = data.get("roles") or []
    url = r.get("url") or ""

    # ── Year inference ────────────────────────────────────────────────────────
    url_year  = infer_year_from_url(url)
    film_year = best_film_year(films)
    meta_year = infer_year_from_metadata(meta)
    is_film_page = bool(FILM_URL_RE.search(url))

    # Pick the best year source:
    # - film pages: film_year is most accurate (the actual film's release year)
    # - non-film pages: url_year (blog post date), then meta_year as weak fallback
    if is_film_page and film_year:
        inferred_year = film_year
    elif url_year:
        inferred_year = url_year
    elif film_year:
        inferred_year = film_year
    else:
        inferred_year = None  # meta_year is too weak (just scrape date), skip

    if inferred_year:
        for role in roles:
            if role.get("start_year") is None and role.get("end_year") is None:
                role["start_year"] = inferred_year
                role["end_year"]   = inferred_year
                changed = True

    # ── Gender enrichment ─────────────────────────────────────────────────────
    for eid, p in people.items():
        if not p or not p.get("name_he"):
            continue
        name = p["name_he"].strip()
        if is_junk_name(name):
            continue
        if "gender" not in p:
            p["gender"] = infer_gender(name)
            changed = True

    if changed:
        data["roles"] = roles
        entities["people"] = people
        data["entities"] = entities
        r["data"] = data

    return r, changed


def process_file(path: str, dry_run: bool) -> dict:
    stats = {"lines": 0, "changed": 0, "year_filled": 0, "gender_added": 0}
    lines_out = []

    with open(path, encoding="utf-8") as f:
        raw_lines = f.readlines()

    for raw in raw_lines:
        raw = raw.rstrip("\n")
        if not raw.strip():
            lines_out.append(raw)
            continue
        try:
            r = json.loads(raw)
        except json.JSONDecodeError:
            lines_out.append(raw)
            continue

        stats["lines"] += 1

        # Count pre-enrichment nulls for stats
        roles_before = sum(
            1 for ro in ((r.get("data") or {}).get("roles") or [])
            if ro.get("start_year") is None and ro.get("end_year") is None
        )
        people_before = sum(
            1 for p in ((r.get("data") or {}).get("entities", {}).get("people") or {}).values()
            if p and "gender" not in p
        )

        r, changed = enrich_entry(r)

        if changed:
            stats["changed"] += 1
            roles_after = sum(
                1 for ro in ((r.get("data") or {}).get("roles") or [])
                if ro.get("start_year") is None and ro.get("end_year") is None
            )
            stats["year_filled"]  += roles_before - roles_after
            stats["gender_added"] += people_before

        lines_out.append(json.dumps(r, ensure_ascii=False))

    if not dry_run:
        with open(path, "w", encoding="utf-8") as f:
            for line in lines_out:
                f.write(line + "\n")

    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--glob", default="out/*/mentions.jsonl",
                        help="Glob pattern for mentions.jsonl files")
    parser.add_argument("--source", help="Restrict to one source (e.g. nfct)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print stats but don't write files")
    args = parser.parse_args()

    paths = sorted(glob.glob(args.glob))
    if args.source:
        paths = [p for p in paths if f"/{args.source}/" in p]
    if not paths:
        print("No files matched.", file=sys.stderr)
        sys.exit(1)

    total = {"lines": 0, "changed": 0, "year_filled": 0, "gender_added": 0}

    for path in paths:
        src = Path(path).parent.name
        stats = process_file(path, args.dry_run)
        tag = "(dry)" if args.dry_run else "✓"
        print(f"  {tag} {src:30s}  "
              f"entries={stats['lines']:5d}  "
              f"changed={stats['changed']:5d}  "
              f"years_filled={stats['year_filled']:6d}  "
              f"gender_added={stats['gender_added']:6d}")
        for k in total:
            total[k] += stats[k]

    print(f"\nTotal: {total['lines']} entries, {total['changed']} changed, "
          f"{total['year_filled']} year-roles filled, {total['gender_added']} genders added")
    if args.dry_run:
        print("(dry run — nothing written)")


if __name__ == "__main__":
    main()
