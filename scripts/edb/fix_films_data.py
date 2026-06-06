#!/usr/bin/env python3
"""Fix edb_films.json in place: expand role mapping, fix is_short flags.
No re-scraping needed."""

import json
import re

INPUT = "data/edb/edb_films.json"
IDS = "data/edb/edb_film_ids.json"

ROLE_MAP = {
    # Core roles — plain Hebrew
    "בימוי":              "director",
    "הפקה":               "producer",
    "תסריט":             "screenwriter",
    "עריכה":              "editor",
    "צילום":              "cinematographer",
    "מוסיקה מקורית":      "composer",
    "עיצוב פסקול":        "sound_designer",
    "שחקן":               "actor",
    "שחקנית":             "actor",

    # Parenthetical technical roles
    "(עריכה)":            "editor",
    "(צילום)":            "cinematographer",
    "(עיצוב פסקול)":      "sound_designer",
    "(עיצוב פסקול ועירבול)": "sound_designer",
    "(עיצוב אמנותי)":     "production_designer",
    "(עיצוב תלבושות)":    "costume_designer",
    "(ליהוק)":            "casting_director",
    "(איפור)":            "makeup_artist",
    "(מאפר/ת ראשי/ת)":   "makeup_artist",
    "(עריכת תסריט)":      "script_editor",
    "(עריכת פסקול)":      "sound_editor",
    "(עריכת אונליין)":    "online_editor",
    "(הקלטה)":            "sound_recordist",
    "(מקליט/ה ראשי/ת)":   "sound_recordist",
    "(עוזר/ת בימוי)":     "assistant_director",
    "(עוזר/ת בימוי ראשונ/ה)": "first_ad",
    "(עיצוב תמונה)":      "production_designer",
    "(הפקת פוסט)":        "post_producer",
    "(תחקיר)":            "researcher",
    "(צילום סטילס)":      "still_photographer",
    "(תאורנ/ית ראשי/ת)": "gaffer",
    "(סט דרסר)":          "set_decorator",
    "(ניהול הפקה)":       "production_manager",
    "(ניהול אמנותי)":     "art_manager",
    "(ניהול תסריט)":      "script_supervisor",
    "(עורכ/ת ראשי/ת)":   "editor",

    # Gender-neutral slash notation
    "מפיק/ה שותפ/ה":      "co_producer",
    "מפיק/ה ראשי/ת":      "executive_producer",
    "מפיק/ה אחראי/ת":     "line_producer",
    "צלמ/ת ראשי/ת":       "cinematographer",
    "תסריטאי/ת ראשי/ת":   "screenwriter",

    # Other production roles
    "הפקה בפועל":         "line_producer",
    "הפקת ליין":          "line_producer",
    "מפיק שותף":          "co_producer",
    "עיצוב אמנותי":       "production_designer",
    "יצירה":              "creator",

    # Performance
    "עצמו":               "self",
    "עצמה":               "self",

    # Voice
    "קול":                "voice_actor",

    # Distribution / other
    "(צוות אחר, מנהלת הפצה)": "distribution_manager",
    "(צוות אחר, ניהול הפצה)":  "distribution_manager",
}

# Junk role strings that should map to "other"
JUNK_ROLES = {"...", "", "נטלי", "שלומי", "עדן", "נעמי"}  # first names mistakenly parsed as roles


def re_role(role_he: str) -> str:
    if role_he in JUNK_ROLES:
        return "other"
    if role_he in ROLE_MAP:
        return ROLE_MAP[role_he]
    # General parenthetical fallback: strip parens, first token as role
    if role_he.startswith("(") and role_he.endswith(")"):
        return "other"
    # Unknown role
    return "other"


def main():
    # Load short IDs
    with open(IDS, encoding="utf-8") as f:
        ids_data = json.load(f)
    if isinstance(ids_data, list):
        short_ids = set()
    elif isinstance(ids_data, dict):
        short_ids = set(ids_data.get("shorts", ids_data.get("short_ids", [])))
    else:
        short_ids = set()

    with open(INPUT, encoding="utf-8") as f:
        films = json.load(f)

    # Fix is_short and roles
    role_counts = {}
    fixed_shorts = 0
    for film in films:
        film_id = film.get("film_id", "")
        if film_id in short_ids and not film.get("is_short"):
            film["is_short"] = True
            fixed_shorts += 1

        for c in film.get("crew", []):
            old_role = c.get("role", "")
            new_role = re_role(c.get("role_he", ""))
            c["role"] = new_role
            role_counts[new_role] = role_counts.get(new_role, 0) + 1

    with open(INPUT, "w", encoding="utf-8") as f:
        json.dump(films, f, ensure_ascii=False, indent=2)

    print(f"Fixed is_short: {fixed_shorts} films")
    print(f"Role distribution:")
    for role, count in sorted(role_counts.items(), key=lambda x: -x[1]):
        pct = count / sum(role_counts.values()) * 100
        print(f"  {count:4d} ({pct:4.1f}%)  {role}")
    print(f"\nSaved: {INPUT}")
    print(f"Now run: python3 export_edb_mentions.py")


if __name__ == "__main__":
    main()