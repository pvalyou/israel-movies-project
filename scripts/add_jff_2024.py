#!/usr/bin/env python3
"""Add JFF 2024 staff to out/jff/mentions.jsonl.
Extracted from https://jff.org.il/he/מאמר/77291 (צוות הפסטיבל 2024).
"""
import json, datetime
from pathlib import Path

URL = "https://jff.org.il/he/%D7%9E%D7%90%D7%9E%D7%A8/77291"
SOURCE = "jff"
YEAR = 2024
TODAY = datetime.date.today().isoformat()

people = [
    # הנהלה
    ("רוני מהדב-לוין", "ceo", "מנכ\"ל"),
    ("אלעד סמורזיק", "artistic_director", "מנהל אמנותי"),
    ("אור סיגולי", "artistic_director", "מנהל אמנותי"),
    ("אריאל רביבו", "fund_manager", "מנהל כספים וחשב"),
    ("ויויאן אוסטרובסקי", "artistic_director", "יעוץ אמנותי"),
    ("עינת סנפירי", "producer", "רכזת הנהלה והפקת קטלוג"),
    # הפקה
    ("אלה טל", "producer", "מפיקה ראשית"),
    ("הילה בר-חיים", "producer", "מפיקה בפועל"),
    ("יאן בירבריאר", "producer", "הפקה טכנית"),
    ("איליה שבתאי", "producer", "ניהול הפקה אירוע פתיחה"),
    ("יוחאי צמיר", "producer", "הפקה טכנית אירוע פתיחה"),
    ("בובי לקס", "director", "בימוי אירוע פתיחה"),
    ("רותם פז", "producer", "הפקת אירועי רסטורציה"),
    # מחלקת קשרי אורחים
    ("יפעת טובی", "producer", "מנהלת המחלקה"),
    ("יובל פרנס מדרא", "producer", "מפיק מחלקת אירוח ומתאם צוותי שיפוט"),
    ("טליה ביטון", "other", "קרדיטציה"),
    ("דוד כהן אלעזר", "other", "ליווי ג'ניפר ג'ייסון לי"),
    # קשרי חוץ
    ("דניאל כהן", "executive_producer", "מנהל קשרי חוץ והפצה"),
    ("דניאלה תורגמן-גלס", "other", "ניהול קשרי תורמים"),
    # קולנוע ישראלי
    ("גלי סמו", "festival_programmer", "מנהלת מסגרות הקולנוע הישראלי"),
    ("אוהד לטק", "producer", "מפיק מסגרות הקולנוע הישראלי"),
    ("איילה בנימין", "other", "מנהלת מחלקת חינוך ותחרות היצירה הצעירה"),
    ("אלעד חן", "other", "תאום והפקת תחרות היצירה הצעירה"),
    ("נוי סיה", "other", "תאום והפקת תחרות היצירה הצעירה"),
    # שיווק ומיתוג
    ("מירי קפילוטו פדהצור", "other", "מנהלת שיווק ופרסום"),
    ("דורין אליהו", "other", "עוזרת שיווק"),
    # יחסי ציבור
    ("רן רהב", "other", "ניהול יחסי ציבור"),
    ("יפעת רובינשטיין", "other", "תקשורת ויחצ\"צ"),
    ("לינור נוי", "other", "תקשורת ויחצ\"צ"),
    ("טל מסלטי", "other", "תקשורת ויחצ\"צ"),
    # עיצוב
    ("מתן שליטא", "other", "עיצוב גרפי ומיתוג"),
    ("מאיה בר יהודה", "other", "עיצוב גרפי ומיתוג"),
    ("עמית סטורלזי", "other", "מעצב פסלון הפרס"),
    ("תם וינטראוב", "other", "צילום"),
    # מנהלה
    ("קרול דרייפוס", "producer", "ניהול אורחי פרוטוקול ומפיקת הסינמטק"),
    ("קובי נעימי", "other", "ניהול מוזמנים"),
    ("דני סהר", "other", "עוזרת ניהול מוזמנים"),
    # תוכן ואוצרות
    ("נבות ברנע", "festival_programmer", "לקטורה וייעוץ אמנותי"),
    ("שירה מאירסון", "other", "ניהול אתר האינטרנט"),
    ("מתוקה לב ארי פלישתי", "other", "ניהול אתר האינטרנט"),
    ("יניב קוריס", "other", "ניהול אתר האינטרנט"),
    ("איתמר ב\"ז", "other", "ייעוץ לשוני"),
    ("אבי גרין", "other", "עוזר תחקיר"),
    # הנהלת חשבונות
    ("יערית אקוע", "other", "מנהלת חשבונות"),
    ("אירית כחלון", "other", "מנהלת חשבונות"),
    # ארכיון
    ("מאיר רוסו", "other", "מנהל הארכיון"),
    ("הילה אברהם", "other", "מנהלת פרויקט שימור דיגיטלי"),
    # קופות ואולמות
    ("דורון לוין", "other", "מנהל קופה"),
    # ניהול טכני
    ("יששכר פירוס", "other", "מנהל טכני"),
    ("עלי סידר", "other", "גן מנהל טכני"),
    # מיון סרטים
    ("שירי נבו פרידנטל", "festival_programmer", "קולנוע ישראלי עלילתי"),
    ("רנא אבו פריחה", "festival_programmer", "קולנוע ישראלי תיעודי"),
    ("עדה אושפיז", "festival_programmer", "קולנוע ישראלי תיעודי"),
    ("מאיה זינשטיין", "festival_programmer", "קולנוע ישראלי תיעודי"),
    ("ג'ניפר אבסירה", "festival_programmer", "סרטים ישראלים קצרים"),
    ("תמר גורן", "festival_programmer", "סרטים ישראלים קצרים"),
    ("חמד שרוף", "festival_programmer", "סרטים ישראלים קצרים"),
    ("דולב אמיתי", "festival_programmer", "סרטים ישראלים קצרים"),
    ("נעם גל", "festival_programmer", "אמנות וידאו וקולנוע ניסיוני"),
    ("ליאורה בלפורד", "festival_programmer", "אמנות וידאו וקולנוע ניסיוני"),
    ("דן רוברט להיאני", "festival_programmer", "אמנות וידאו וקולנוע ניסיוני"),
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
        "file": f"jff__he_mamar_77291__manual.md",
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
                "canonical_source": "agent_research_plan",
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
    print(f"Added {len(people)} people from JFF {YEAR} staff to {out_path}")

if __name__ == "__main__":
    main()
