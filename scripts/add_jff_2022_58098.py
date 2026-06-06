#!/usr/bin/env python3
"""Add JFF 2022 staff to out/jff/mentions.jsonl.
Extracted from https://jff.org.il/he/מאמר/58098 (צוות הפסטיבל 2022).
"""
import json, datetime
from pathlib import Path

URL = "https://jff.org.il/he/%D7%9E%D7%90%D7%9E%D7%A8/58098"
SOURCE = "jff"
YEAR = 2022
TODAY = datetime.date.today().isoformat()

people = [
    # הנהלה
    ("רוני מהדב-לוין",          "ceo",                  'מנכ"ל בפועל'),
    ("אלעד סמורזיק",             "artistic_director",     "מנהל אמנותי"),
    ("אריאל רביבו",              "fund_manager",          "מנהל כספים וחשב"),
    ("ויויאן אוסטרובסקי",        "artistic_director",     "יעוץ אמנותי"),
    ("עינת סנפירי",              "producer",              "רכזת הנהלה והפקת קטלוג"),
    # הפקה
    ("אלה טל",                   "producer",              "מפיקה ראשית"),
    ("הילה בר-חיים",             "producer",              "מפיקה בפועל"),
    ("הראל בן-מלך",              "producer",              "מנהלת הפקה"),
    ("יאן בירברייר",             "producer",              "ניהול הפקת חוצות"),
    ("אנה גורליק גוטרמן",        "producer",              "הפקה בפועל חוצות"),
    ("שגיא אלמוג",               "producer",              "מנהל הפקה חוצות"),
    ("נטע שלזינגר",              "producer",              "ניהול הפקה אירוע פתיחה"),
    ("יוחאי צמיר",               "producer",              "הפקה טכנית אירוע פתיחה"),
    ("בובי לקס",                 "director",              "בימוי אירוע פתיחה"),
    ("אינה בישבסקיה",            "producer",              "תיאום הפקה חוצות"),
    ("קרן לויט",                 "producer",              "ניהול פרויקט משאיות קולנוע בשכונות"),
    ("אורי וקנין",               "producer",              "הפקה טכנית משאיות קולנוע בשכונות"),
    ("רותם פז",                  "producer",              "הפקת אירועי רסטורציה"),
    ("דוד רחמני",                "producer",              "ניהול והפקה תוכן משלים"),
    # מחלקת קשרי אורחים
    ("יפעת טובי",                "producer",              "מנהלת המחלקה ואירועי תעשייה"),
    ("דוד כהן אלעזר",            "producer",              "מפיק מחלקת אירוח"),
    ("איתמר פולמן",              "other",                 "מתאם צוותי שיפוט"),
    ("חמי קרן",                  "other",                 "אקרדיטציה"),
    ("אן בן-יהודה",              "other",                 "תיאום הסעות"),
    # קשרי חוץ
    ("דניאל כהן",                "executive_producer",    "מנהל קשרי חוץ והפצה"),
    ("דניאלה תורגמן-גלס",        "other",                 "ניהול קשרי תורמים"),
    # קולנוע ישראלי
    ("בן טופח",                  "festival_programmer",   "מנהל מסגרות הקולנוע הישראלי"),
    ("גלי סמו",                  "producer",              "מפיקת מסגרות הקולנוע הישראלי ואירועי תעשייה"),
    ("אילה בנימין",              "other",                 "מנהלת מחלקת חינוך ותחרות היצירה הצעירה"),
    ("אלעד חן",                  "other",                 "תיאום והפקת תחרות היצירה הצעירה"),
    ("רוני לוין",                "other",                 "עוזרת הפקה"),
    # שיווק ומיתוג
    ("מירי קפילוטו פדהצור",      "other",                 "מנהלת שיווק ופרסום"),
    ("ורד בן-ציון",              "other",                 "עוזרת שיווק"),
    ("רן רהב",                   "other",                 "ניהול יחסי ציבור"),
    ("יפעת רובינשטיין",          "other",                 "תקשורת ויחצ\"צ"),
    ("לין פדובה",                "other",                 "תקשורת ויחצ\"צ"),
    ("מתן שליטא",                "other",                 "עיצוב גרפי ומיתוג"),
    ("מאיה בר יהודה",            "other",                 "עיצוב גרפי ומיתוג"),
    ("עמית סטורלזי",             "other",                 "מעצב פסלון הפרס"),
    ("תם וינטראוב לוק",          "other",                 "צילום"),
    # מנהלה
    ("קרול דרייפוס",             "producer",              "מפיקת הסינמטק ומנהלת אירועים"),
    ("אוהד לטקו",                "other",                 "ניהול משרד ראשי"),
    ("חנן ברנדס",                "other",                 "ניהול מוזמנים"),
    ("יהלי מעוז",                "other",                 "עוזרת ניהול מוזמנים"),
    # תוכן ואוצרות
    ("נבות ברנע",                "festival_programmer",   "לקטורה וייעוץ אמנותי"),
    ("תמר פרימן",                "other",                 "ניהול אתר האינטרנט"),
    ("שירה מאירסון",             "other",                 "ניהול אתר האינטרנט"),
    ('איתמר ב"ז',                "other",                 "ייעוץ לשוני"),
    ("רחל פרץ",                  "other",                 "ייעוץ לשוני"),
    ("אבי גרין",                 "other",                 "עוזר תחקיר"),
    # הנהלת חשבונות
    ("יערית אקוע",               "other",                 "מנהלת חשבונות"),
    ("אירית כחלון",              "other",                 "מנהלת חשבונות"),
    # ארכיון
    ("מאיר רוסו",                "other",                 "מנהל הארכיון"),
    ("הילה אברהם",               "other",                 "מנהלת פרויקט שימור דיגיטלי"),
    ("אופיר מסר",                "other",                 "מעבדת דיגיטציה"),
    ("יניב קוריס",               "other",                 "מעבדת דיגיטציה"),
    ("יגאל קליין",               "other",                 "מעבדת דיגיטציה"),
    ("יונתן רון",                "other",                 "מעבדת דיגיטציה"),
    ("מתוקה לב ארי פלשתי",       "other",                 "מעבדת דיגיטציה"),
    ("אבינועם לנד",              "other",                 "מעבדת דיגיטציה"),
    ("מעיין פורת",               "other",                 "מעבדת דיגיטציה"),
    ("ליהי הירשנבוים",           "other",                 "מעבדת דיגיטציה"),
    ("נעה כרם",                  "other",                 "מעבדת דיגיטציה"),
    # ניהול טכני
    ("אלי בן-זאב",               "other",                 "מנהל טכני"),
    ("עלי סידר",                 "other",                 "סגן מנהל טכני"),
    # מיון סרטים — קולנוע בינלאומי (ייעוץ)
    ("דן פיינרו",                "other",                 "יעוץ קולנוע בינלאומי"),
    ("עדנה פיינרו",              "other",                 "יעוץ קולנוע בינלאומי"),
    ("דליה קרפל",                "other",                 "יעוץ קולנוע בינלאומי"),
    ("טל מאירי",                 "other",                 "יעוץ קולנוע בינלאומי"),
    # מיון סרטים — קולנוע ישראלי
    ("סמירה סרייה",              "festival_programmer",   "מיון קולנוע עלילתי ישראלי"),
    ("אלעד קידן",                "festival_programmer",   "מיון קולנוע עלילתי ישראלי"),
    ("ג'ולי שלז",                "festival_programmer",   "מיון קולנוע תיעודי ישראלי"),
    ("קובי פרג'",                "festival_programmer",   "מיון קולנוע תיעודי ישראלי"),
    ("ענת אבן",                  "festival_programmer",   "מיון קולנוע תיעודי ישראלי"),
    ("מיה לנדסמן",               "festival_programmer",   "מיון סרטים קצרים"),
    ("יונתן דובק",               "festival_programmer",   "מיון סרטים קצרים"),
    ("ג'ניפר אבסירה",            "festival_programmer",   "מיון סרטים קצרים"),
    ("סוהא עראף",                "festival_programmer",   "מיון סרטים קצרים"),
    ("רובי אלמליח",              "festival_programmer",   "מיון סרטים קצרים"),
    ("יאן טיכי",                 "festival_programmer",   "מיון אמנות וידאו וקולנוע ניסיוני"),
    ("דביר שקד",                 "festival_programmer",   "מיון אמנות וידאו וקולנוע ניסיוני"),
    ("הדסה גולדויכט",            "festival_programmer",   "מיון אמנות וידאו וקולנוע ניסיוני"),
    ("רנא אבו פריחה",            "festival_programmer",   "פיצ'פוינט קצרים"),
    ("גבור גריינר",              "other",                 "פיצ'פוינט"),
    ("תרזה קבינה",               "other",                 "פיצ'פוינט"),
    ("עידן הובל",                "other",                 "פיצ'פוינט קצרים"),
    ("גיא עופרן",                "other",                 "פיצ'פוינט קצרים"),
]


def build_record(persons):
    people_ents = {}
    roles_list = []
    for i, (name, role_type, context) in enumerate(persons, 1):
        pid = f"person_{i:03d}"
        people_ents[pid] = {
            "name_he": name,
            "name_en": None,
            "aliases": [],
            "primary_roles": [role_type],
            "context_sentence": f"{context} – פסטיבל הקולנוע ירושלים {YEAR}",
            "sources": [URL],
        }
        roles_list.append({
            "id": f"role_{i:03d}_{role_type}",
            "person_id": pid,
            "organization_id": "org_001",
            "role_type": role_type,
            "start_year": YEAR,
            "end_year": YEAR,
            "notes": f"{context} – פסטיבל הקולנוע ירושלים {YEAR}",
            "sources": [URL],
        })

    return {
        "file": "jff__he_mamar_58098__manual.md",
        "url": URL,
        "source_name": SOURCE,
        "status": "ok",
        "content_hash": "manual",
        "content_length": 0,
        "filter_info": {"reason": "manual_import"},
        "truncated": False,
        "elapsed_sec": 0,
        "data": {
            "metadata": {
                "source_url": URL,
                "source_name": SOURCE,
                "extraction_date": TODAY,
                "language": "he",
                "canonical_source": "scraped_2026-06-03",
            },
            "entities": {
                "people": people_ents,
                "organizations": {
                    "org_001": {
                        "name_he": "פסטיבל הקולנוע ירושלים",
                        "name_en": "Jerusalem Film Festival",
                        "type": "festival",
                        "sources": [URL],
                    }
                },
                "films": {},
                "events": {},
            },
            "roles": roles_list,
            "relationships": [],
            "films": [],
        },
    }


def main():
    out_path = Path("out/jff/mentions.jsonl")
    record = build_record(people)
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"Added {len(people)} people from JFF {YEAR} staff (מאמר/58098) to {out_path}")


if __name__ == "__main__":
    main()
