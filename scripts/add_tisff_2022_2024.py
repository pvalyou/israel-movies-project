#!/usr/bin/env python3
"""Add TISFF 2022, 2023, 2024 results to out/festival_data/mentions.jsonl.
Only Israeli competition and short film competition winners.
Source: srita.net coverage of each year.
"""
import json, datetime
from pathlib import Path

TODAY = datetime.date.today().isoformat()
OUT = Path("out/festival_data/mentions.jsonl")

records = []

# ── TISFF 2022 ────────────────────────────────────────────────────────────────
URL_2022 = "https://srita.net/2022/06/20/student-film-fest-2022-winners/"
people_2022 = [
    # Israeli Competition
    ("בר כהן", "prize_winner", "best_film", "בין לבין", "אוניברסיטת תל אביב"),
    ("שרי אברג'ל", "prize_winner", "best_screenplay", "לשקר יש ארבע רגליים", "המכללה האקדמית ספיר"),
    ("נוי פריימן", "prize_winner", "best_screenplay", "לשקר יש ארבע רגליים", "המכללה האקדמית ספיר"),
    ("גא לבנת", "prize_winner", "best_screenplay", "לשקר יש ארבע רגליים", "המכללה האקדמית ספיר"),
    ("טל ניניו", "prize_winner", "best_cinematography", "המזמור החמישים", "תל-חי"),
    ("חמד שרוף", "prize_winner", "best_cinematography", "המזמור החמישים", "תל-חי"),
    ("פאדי קובטי", "prize_winner", "best_cinematography", "המזמור החמישים", "תל-חי"),
    ("גדעון טוקטלי", "prize_winner", "best_editing", "שמישהו יגיד לי מה להרגיש", "סם שפיגל"),
    ("מיכל הולנד", "prize_winner", "best_editing", "שמישהו יגיד לי מה להרגיש", "סם שפיגל"),
    ("נועם אימבר", "prize_winner", "best_actor", "חום", "סם שפיגל"),
    ("רועי משיח", "prize_winner", "best_actor", "חום", "סם שפיגל"),
    ("ברית לייבוביץ'", "prize_winner", "best_directing", "שיווי משקל", "ספיר"),
    ("ענת איזנברג", "prize_winner", "honorable_mention", "סולו", "אוניברסיטת תל אביב"),
    ("אור גץ", "prize_winner", "audience_choice", "משפט", "אוניברסיטת תל אביב"),
    # Independent Short Film
    ("הדר מורג", "prize_winner", "best_film_independent", "הגיע הזמן שתמותי כבר", ""),
    ("אתי ציקו", "prize_winner", "best_directing_independent", "רוסו", ""),
    ("סופי ארטוס", "prize_winner", "audience_choice_independent", "מחיקה מלאה", ""),
    ("מיכל קרני", "prize_winner", "audience_choice_independent", "מחיקה מלאה", ""),
]

# ── TISFF 2023 ────────────────────────────────────────────────────────────────
URL_2023 = "https://srita.net/2023/07/02/tisff_2023_winners/"
people_2023 = [
    # Israeli Competition
    ("דונה חוא", "prize_winner", "best_film", "סיבא", "סם שפיגל"),
    ("דנה וייל", "prize_winner", "best_screenplay", "הצילו! אני רוצה למות", "אוניברסיטת תל אביב"),
    ("בן פלד", "prize_winner", "best_cinematography", "הילד", "מנשר"),
    ("יהב וינר", "prize_winner", "best_cinematography", "הילד", "מנשר"),
    ("זוהר סלע", "prize_winner", "best_editing", "דודה דינה", "מנשר"),
    ("בנימין אסתיכנג'י", "prize_winner", "best_editing", "דודה דינה", "מנשר"),
    ("אבי סרוסי", "prize_winner", "best_actor", "ניפגש בסוף הבלוק", "אוניברסיטת תל אביב"),
    ("עומר פרלמן שטריקס", "prize_winner", "best_actor", "ניפגש בסוף הבלוק", "אוניברסיטת תל אביב"),
    ("דניאל גת", "prize_winner", "best_actor", "ניפגש בסוף הבלוק", "אוניברסיטת תל אביב"),
    ("אלמה בן זאב", "prize_winner", "honorable_mention", "מירה", "אוניברסיטת תל אביב"),
    # Independent Short Film
    ("איתמר אלקלעי", "prize_winner", "best_film_independent", "מים קרים", ""),
    ("הילה רויזנמן", "prize_winner", "best_directing_independent", "מחצבה", ""),
    ("טל קנטור", "prize_winner", "best_animation", "מכתב לחזיר", ""),
]

# ── TISFF 2024 ────────────────────────────────────────────────────────────────
URL_2024 = "https://srita.net/2024/08/20/tisff_2024_winners/"
people_2024 = [
    # Israeli Competition
    ("שמעון מכלוף", "prize_winner", "best_film", "אור, שמש, מפל", "מנשר"),
    ("בת-סער רביב", "prize_winner", "best_directing", "דברים שאני זוכרת מקיץ 2004", "אוניברסיטת תל אביב"),
    ("תמי ממיסטבלוב", "prize_winner", "best_screenplay", "עיניים של אבא", "קמרה אובסקורה"),
    ("שי אטר", "prize_winner", "best_cinematography", "תשובה", "ספיר"),
    ("רחל אלברט", "prize_winner", "best_cinematography", "תשובה", "ספיר"),
    ("ג'י לץ", "prize_winner", "best_cinematography", "תשובה", "ספיר"),
    ("אפק טסטה לאונר", "prize_winner", "best_cinematography", "תשובה", "ספיר"),
    ("איתמר גרוס", "prize_winner", "best_editing", "מים ודלק", "אוניברסיטת תל אביב"),
    ("יואב בירן", "prize_winner", "best_editing", "מים ודלק", "אוניברסיטת תל אביב"),
    ("אורלי אפל", "prize_winner", "honorable_mention_acting", "עוד חמצן בבקשה", "ספיר"),
    ("אלה דגן", "prize_winner", "honorable_mention_acting", "עוד חמצן בבקשה", "ספיר"),
    ("נעמה להב", "prize_winner", "audience_choice", "תמונת מראה", "סם שפיגל"),
    ("עמית אראל", "prize_winner", "honorable_mention", "משחק הכיסאות", "ספיר"),
    # Independent Short Film
    ("יואב בירן", "prize_winner", "best_film_independent", "לוט בערפל", ""),
    ("nikolai kolishov", "prize_winner", "best_directing_independent", "פרחי חורף", ""),
    ("בני שקלובסקי", "prize_winner", "best_directing_independent", "פרחי חורף", ""),
    ("אניה כספי שמאע", "prize_winner", "honorable_mention_independent", "חמוצים", ""),
    ("מירי דוחיקיאן", "prize_winner", "honorable_mention_independent", "חמוצים", ""),
    ("שימרית אילדיס", "prize_winner", "audience_choice_independent", "בתולת שפתיים", ""),
]


def make_record(year, url, people_list):
    people_ents = {}
    roles_list = []
    for i, (name, role_type, award, film, school) in enumerate(people_list, 1):
        pid = f"person_{i:03d}"
        ctx = f"זוכה פרס {award} על הסרט \"{film}\" – פסטיבל סרטי סטודנטים {year}"
        if school:
            ctx += f" ({school})"
        people_ents[pid] = {
            "name_he": name if all(ord(c) > 0x0590 for c in name if c.isalpha()) else "",
            "name_en": name if not all(ord(c) > 0x0590 for c in name if c.isalpha()) else None,
            "aliases": [],
            "primary_roles": [role_type],
            "context_sentence": ctx,
            "sources": [url],
        }
        roles_list.append({
            "id": f"role_{i:03d}_{award}",
            "person_id": pid,
            "organization_id": "org_001",
            "role_type": role_type,
            "start_year": year,
            "end_year": year,
            "notes": ctx,
            "sources": [url],
        })

    return {
        "file": f"festival_data__tisff_{year}__manual.md",
        "url": url,
        "source_name": "festival_data",
        "status": "ok",
        "content_hash": "manual",
        "content_length": 0,
        "filter_info": {"reason": "manual_import"},
        "truncated": False,
        "elapsed_sec": 0,
        "data": {
            "metadata": {
                "source_url": url,
                "source_name": "festival_data",
                "extraction_date": TODAY,
                "language": "he",
                "canonical_source": "agent_research_plan",
            },
            "entities": {
                "people": people_ents,
                "organizations": {
                    "org_001": {
                        "name_he": "פסטיבל סרטי סטודנטים",
                        "name_en": "Tel Aviv International Student Film Festival",
                        "type": "festival",
                        "sources": [url],
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
    with open(OUT, "a", encoding="utf-8") as f:
        for year, url, people in [
            (2022, URL_2022, people_2022),
            (2023, URL_2023, people_2023),
            (2024, URL_2024, people_2024),
        ]:
            rec = make_record(year, url, people)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"TISFF {year}: added {len(people)} people")


if __name__ == "__main__":
    main()
