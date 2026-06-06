#!/usr/bin/env python3
"""Add DocAviv 2025 lectors committee and Haifa 2025 jury to mentions.jsonl.
"""
import json, datetime
from pathlib import Path

TODAY = datetime.date.today().isoformat()
OUT_DIR = Path("out")

def make_record(source_name, url, people_list, org_name, org_type, year, context_prefix):
    people_ents = {}
    roles_list = []
    for i, (name, role_type, context) in enumerate(people_list, 1):
        pid = f"person_{i:03d}"
        people_ents[pid] = {
            "name_he": name,
            "name_en": None,
            "aliases": [],
            "primary_roles": [role_type],
            "context_sentence": f"{context} – {context_prefix} {year}",
            "sources": [url],
        }
        roles_list.append({
            "id": f"role_{i:03d}_{role_type}",
            "person_id": pid,
            "organization_id": "org_001",
            "role_type": role_type,
            "start_year": year,
            "end_year": year,
            "notes": f"{context} – {context_prefix} {year}",
            "sources": [url],
        })

    return {
        "file": f"{source_name}__{year}__manual.md",
        "url": url,
        "source_name": source_name,
        "status": "ok",
        "content_hash": "manual",
        "content_length": 0,
        "filter_info": {"reason": "manual_import"},
        "truncated": False,
        "elapsed_sec": 0,
        "data": {
            "metadata": {
                "source_url": url,
                "source_name": source_name,
                "extraction_date": TODAY,
                "language": "he",
                "canonical_source": "agent_research_plan",
            },
            "entities": {
                "people": people_ents,
                "organizations": {
                    "org_001": {
                        "name_he": org_name,
                        "name_en": None,
                        "type": org_type,
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
    # ── DocAviv 2025 lectors committee ──────────────────────────────────────
    docaviv_url = "https://www.docaviv.co.il/2025/03-30-israeli_lineup/"
    docaviv_people = [
        ("קרין ריבקינד סגל", "festival_programmer", "מנהלת אמנותית, ועדת לקטורים בתחרות הישראלית"),
        ("גדעון לצמן", "festival_programmer", "יוצר ועורך סרטים, ועדת לקטורים בתחרות הישראלית"),
        ("איילת אלבנדה", "festival_programmer", "במאית ויוצרת קולנוע דוקומנטרי, ועדת לקטורים בתחרות הישראלית"),
        ("טל ענבר", "festival_programmer", "במאית, ועדת לקטורים בתחרות הסטודנטים"),
        ("אדם ויינגרוד", "festival_programmer", "ממאי, יוצר דוקומנטרי ומוזיקאי, ועדת לקטורים בתחרות הסטודנטים"),
        ("ענת נטל", "festival_programmer", "מנהלת התוכנית של פסטיבל דוקאביב, ועדת לקטורים בתחרות הסטודנטים"),
    ]
    docaviv_rec = make_record(
        source_name="docaviv_festivals",
        url=docaviv_url,
        people_list=docaviv_people,
        org_name="פסטיבל דוקאביב",
        org_type="festival",
        year=2025,
        context_prefix="פסטיבל דוקאביב",
    )
    out_path = OUT_DIR / "docaviv_festivals" / "mentions.jsonl"
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(docaviv_rec, ensure_ascii=False) + "\n")
    print(f"DocAviv 2025: added {len(docaviv_people)} people")

    # ── Haifa 2025 juries ───────────────────────────────────────────────────
    haifa_url = "https://www.haifaff.co.il/%D7%A9%D7%95%D7%A4%D7%98%D7%99%D7%9D"
    haifa_people = [
        # Carmel Competition
        ("אריק להב-לבוביץ'", "jury_member", "חבר שופטים – תחרות כרמל"),
        ("אסי לוי", "jury_member", "חבר שופטים – תחרות כרמל"),
        ("ליעד הרמן", "jury_member", "חבר שופטים – תחרות כרמל"),
        ("סופי ארטוס", "jury_member", "חברת שופטים – תחרות כרמל"),
        ("לירון בן שלוש", "jury_member", "חברת שופטים – תחרות כרמל"),
        # Golden Anchor
        # Israeli Film
        ("ברנד בודר", "jury_member", "חבר שופטים – קולנוע ישראלי"),
        ("שמוליק דובדבני", "jury_member", "חבר שופטים – קולנוע ישראלי"),
        ("ליזה שלוח-אзорאד", "jury_member", "חברת שופטים – קולנוע ישראלי"),
        ("ניר ברגמן", "jury_member", "חבר שופטים – קולנוע ישראלי"),
        # Israeli Short Films
        ("אוהד מילשטיין", "jury_member", "חבר שופטים – קולנוע ישראלי קצר"),
        ("גן דה לנגה", "jury_member", "חברת שופטים – קולנוע ישראלי קצר"),
        ("עדה רימון", "jury_member", "חברת שופטים – קולנוע ישראלי קצר"),
    ]
    haifa_rec = make_record(
        source_name="haifa_film_festival",
        url=haifa_url,
        people_list=haifa_people,
        org_name="פסטיבל הסרטים הבינלאומי חיפה",
        org_type="festival",
        year=2025,
        context_prefix="פסטיבל חיפה",
    )
    out_path = OUT_DIR / "haifa_film_festival" / "mentions.jsonl"
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(haifa_rec, ensure_ascii=False) + "\n")
    print(f"Haifa 2025: added {len(haifa_people)} people")


if __name__ == "__main__":
    main()
