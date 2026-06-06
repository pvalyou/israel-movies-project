#!/usr/bin/env python3
"""Add missing faculty (from Gemini research) into faculty_members.json.
Adds names to existing institutions and creates new sections for Bezalel,
Seminar HaKibbutzim, Ariel U, Open U, Outside-the-Frame, and high school.
"""
import json
from pathlib import Path

FILE = Path("film_faculty_data/faculty_members.json")
data = json.loads(FILE.read_text(encoding="utf-8"))

# --- 1. Existing schools — append missing names to faculty lists ---

EXTEND = {
    # key in JSON → list of names + role override (or None for default 'faculty')
    "tel_aviv_university": ("junior_staff_page4", [
        "קטיה אריאלי",
        'ד"ר עלינא ברנשטיין',
    ]),
    "sapir_college": ("lecturers_and_adjunct", [
        "טל גדון",
        "יעקב אמזלג",
        "צבי סהר",
        "ערן יחזקאל",
        "רות פתיר",
    ]),
    "minshar_art_school": ("faculty", [
        "יעל ולובלסקי",
        "שרה בוזקוב",
        "מיכאל ליאני",
        "עמרי ון אסן",
        "שמרית גאון",
    ]),
    "beit_berl_college": ("faculty", [
        'ד"ר בני בן דוד',
        "הילה פלג",
        "גלעד מלצר",
        "אפרת גל-נור",
        "קרן גלר",
        "פרופ' אפרת ביברמן",
        'ד"ר ורד חרותי',
        'ד"ר רותי גינזבורג',
        'ד"ר דליה מרקוביץ\'',
        'ד"ר אירנה גורדון',
        "ליאת קפלן",
        "ליהי חן",
        "עופר טבצ'ניק",
        "רון עמיר",
        "רונית אטינגר",
    ]),
    "sam_spiegel_film_school": ("teaching_staff", [
        # leave as "Given Family" since importer reverses 2-token names; this stays as-is
        "בלנקשטיין כהן דנה",
    ]),
}

for school_key, (list_key, names) in EXTEND.items():
    section = data.get(school_key)
    if section is None:
        print(f"WARN: {school_key} not in JSON, skipped")
        continue
    target = section.setdefault(list_key, [])
    added = 0
    existing_norm = {(s if isinstance(s, str) else s.get("name", "")).strip() for s in target}
    for n in names:
        if n not in existing_norm:
            target.append(n)
            added += 1
    print(f"{school_key}.{list_key}: +{added}")

# --- 2. New institutions ---
NEW_INSTITUTIONS = {
    "bezalel_academy": {
        "institution": "אקדמיית בצלאל לאמנות ועיצוב — המחלקה לאמנויות המסך (Bezalel Academy – Screen-Based Arts)",
        "website": "https://www.bezalel.ac.il",
        "leadership": [
            {"name": "יעל עוזסיני", "role": "ראשת המחלקה לאמנויות המסך"},
            {"name": "יוסף קריספל", "role": "ראש המחלקה לאמנות"},
            {"name": "פרופ' מרב סלומון", "role": "פרופסור לאיור וראשת המרכז להוראת אמנות"},
        ],
        "faculty": [
            "אסיה איזנשטיין",
            "אסף אשרי",
            "שרון בלבן",
            "אפרת ברגר",
            "ניר ברגר",
            "נועה ברמן-הרצברג",
            "תמי ברנשטיין",
            "אייל גור-אריה",
            "שרון גזית",
            "נטע הררי נבון",
            "קובי ווגמן",
            "עופר וינטר",
            "משה זילברנגל",
            "ערן לזר",
            "עמית טריינין",
        ],
    },
    "seminar_hakibbutzim": {
        "institution": "סמינר הקיבוצים — החוג לתקשורת וקולנוע (Seminar HaKibbutzim College)",
        "website": "https://www.smkb.ac.il",
        "leadership": [
            {"name": "רועי ואטורי", "role": "ראש המגמה לעיצוב במה לקולנוע וטלוויזיה"},
            {"name": "פרידה שוהם", "role": "מייסדת המגמה ומרצה לעיצוב במה לקולנוע"},
            {"name": "ענת שוורץ", "role": "ראשת החוג לתקשורת ולקולנוע"},
        ],
        "faculty": [
            "דנה צרפתי",
            "מיטל אבוקסיס",
            "יובל אהרוני",
            "אלירן אליה",
            'ד"ר שרון אשכנזי',
            "אלה באואר",
            "אבנר ברנהיימר",
            "לב גולצר",
            "חן גורן עקביה",
            'ד"ר שגית דינר',
            'ד"ר דלית וסרמן-אמיר',
            "רוני ורטהיימר",
            "רן ישפה",
            "אריק לובצקי",
            "תמי ליברמן",
            "ליאור סורוקה",
            "ענבל פטל",
            'ד"ר גתית פרלמוטר',
            "דני לרנר",
            "יערה עוזרי",
            'ד"ר מאיה פנחסי',
            "מאיר ראובני",
            "דיקלה שטרית",
            "ג'ולי שלז",
            "ערן שפירא",
        ],
    },
    "ariel_university": {
        "institution": "אוניברסיטת אריאל — בית הספר לתקשורת (Ariel University – School of Communication)",
        "website": "https://www.ariel.ac.il",
        "leadership": [
            {"name": "פרופ' ליסיצה סבינה", "role": "ראשת בית הספר לתקשורת"},
            {"name": "פרופ' תמיר אילן", "role": "דיקן הסטודנטים ומרצה לתקשורת"},
            {"name": 'ד"ר לאור טל', "role": "ראשת מסלול רדיו והפקת תוכן"},
            {"name": 'ד"ר רוט-כהן אסנת', "role": "ראשת מסלול תקשורת שיווקית"},
            {"name": 'ד"ר קול עפרית', "role": "ראשת מסלול תקשורת דיגיטלית"},
            {"name": 'ד"ר בורס אייל', "role": "ראש מסלול קולנוע וטלוויזיה"},
            {"name": 'ד"ר ראשי צוריאל', "role": "ראש מסלול לתואר שני בתקשורת"},
            {"name": 'ד"ר צימנד-שיינר דורית', "role": "ראשת המסלול הבינלאומי לתואר שני"},
            {"name": "פרופ' רוזנברג חננאל", "role": "ראש ועדת הוראה ויועץ התואר השני"},
        ],
        "faculty": [
            'ד"ר שטיינפלד נילי',
            "פרופ' לב-און אזי",
            'ד"ר מדר גלית',
            'ד"ר לוינשטיין-ברקאי הילה',
            "פרופ' קמחי רמי",
            'ד"ר סבג בן-פורת חן',
            "פרופ' יואל כהן",
            "פרופ' מן רפי",
            'ד"ר להב תמר',
            "אודי רבינוביץ'",
            'ד"ר עמוס נבו',
            'ד"ר רון שלייפר',
            "חנה מששה",
            "אבישי פרוינד",
            "דקל מועלם",
            "תמר מור",
            "מנחם בן-עדי",
            "עמנואל קימיאגרוב",
            "זוהר עמיהוד",
            "דניאל צ'רניאק",
            "שרה הורוביץ",
            "ליאור זכרוב",
            "יוסי רונן",
            "אפרת פפר",
            "דני ליבר",
            "ליאור גרטי",
            "רן מורן",
        ],
    },
    "open_university": {
        "institution": "האוניברסיטה הפתוחה — לימודי קולנוע ותרבות (The Open University of Israel)",
        "website": "https://www.openu.ac.il",
        "leadership": [],
        "faculty": [
            'ד"ר דגנית בורובסקי שיבר',
            'ד"ר ענבר שחם',
            "פרופ' ליאת שטייר לבני",
            'ד"ר אריאל שיטרית',
            "יובל פרידמן",
        ],
    },
    "outside_the_frame": {
        "institution": 'סדרות הרצאות "מחוץ לפריים" — מרצי קולנוע, אמנות ותרבות (Public lecture series)',
        "website": "manual://outside-the-frame",
        "leadership": [],
        "faculty": [
            "רותי דיקרטור",
            'ד"ר דורון לוריא',
            'ד"ר סמדר שפי',
            "יואל שתרוג",
            "רחל אסתרקין",
            "נוי לוין",
            "נפתלי הילגר",
        ],
    },
    "high_school_cinema": {
        "institution": "משרד החינוך — מורי קולנוע בתי ספר תיכוניים (High-school cinema teachers)",
        "website": "https://meyda.education.gov.il",
        "leadership": [],
        "faculty": [
            "אורי יואלי",
        ],
    },
}

for k, v in NEW_INSTITUTIONS.items():
    if k in data:
        print(f"SKIP: {k} already present")
        continue
    data[k] = v
    print(f"+ added new institution: {k} ({len(v.get('faculty', []))} faculty + {len(v.get('leadership', []))} leadership)")

# Update _meta with new sources
meta = data.setdefault("_meta", {})
sources = meta.setdefault("sources", {})
sources["bezalel_academy"] = {
    "url": "manual://bezalel/screen-arts-faculty-2026",
    "notes": "Bezalel — Screen-Based Arts department + Art department faculty (Gemini research, 2026-06)",
    "names_collected": len(NEW_INSTITUTIONS["bezalel_academy"]["faculty"]) + len(NEW_INSTITUTIONS["bezalel_academy"]["leadership"]),
}
sources["seminar_hakibbutzim"] = {
    "url": "manual://seminar-hakibbutzim/cinema-tv-faculty-2026",
    "notes": "Seminar HaKibbutzim — Cinema/TV/Communication faculty (Gemini research, 2026-06)",
    "names_collected": len(NEW_INSTITUTIONS["seminar_hakibbutzim"]["faculty"]) + len(NEW_INSTITUTIONS["seminar_hakibbutzim"]["leadership"]),
}
sources["ariel_university"] = {
    "url": "manual://ariel-university/communication-faculty-2026",
    "notes": "Ariel University — School of Communication faculty incl. Film & TV track (Gemini research, 2026-06)",
    "names_collected": len(NEW_INSTITUTIONS["ariel_university"]["faculty"]) + len(NEW_INSTITUTIONS["ariel_university"]["leadership"]),
}
sources["open_university"] = {
    "url": "manual://open-university/cinema-faculty-2026",
    "notes": "Open University of Israel — cinema coordinators and lecturers (Gemini research, 2026-06)",
    "names_collected": len(NEW_INSTITUTIONS["open_university"]["faculty"]),
}
sources["outside_the_frame"] = {
    "url": "manual://outside-the-frame/2026",
    "notes": "מחוץ לפריים — public cinema/art lecture series (Gemini research, 2026-06)",
    "names_collected": len(NEW_INSTITUTIONS["outside_the_frame"]["faculty"]),
}
sources["high_school_cinema"] = {
    "url": "manual://moe/high-school-cinema-teachers-2026",
    "notes": "High-school cinema teachers (Israeli MoE)",
    "names_collected": len(NEW_INSTITUTIONS["high_school_cinema"]["faculty"]),
}

FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print("\nWrote", FILE)
