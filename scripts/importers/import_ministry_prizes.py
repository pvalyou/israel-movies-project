#!/usr/bin/env python3
"""
import_ministry_prizes.py — Ministry of Culture Cinema Arts Prizes 2024.

Source: https://www.gov.il/he/pages/praasim_2024_7
        ("שר התרבות והספורט מיקי זוהר הכריז על הזוכים בפרסי אמנות הקולנוע לשנת 2024")

Categories (total ₪210K):
  - מפעל חיים (₪40K)               → prize_winner_lifetime
  - עידוד היצירה (₪120K split by 3) → prize_winner_encouragement
  - יוצרים בראשית דרכם (₪50K /2)    → prize_winner_emerging

Plus the 8-member jury (jury_member) and 1 observer (event_participant).

Roles emitted are mapped to existing taxonomy:
  - jury_member            (STRICT_INST_ROLE — gatekeeping)
  - prize_committee_member (STRICT — used for jury chair)
  - prize_winner           (label only — credit, not a conflict)
"""
import json
from datetime import date
from pathlib import Path

OUT_DIR     = Path("out/ministry_of_culture_prizes")
OUT_JSONL   = OUT_DIR / "mentions.jsonl"
SOURCE_NAME = "ministry_of_culture_prizes"
CANONICAL   = "https://www.gov.il/he/pages/praasim_2024_7"
TODAY       = date.today().isoformat()

# (name_he, role) — role uses the canonical taxonomy
WINNERS = [
    ("רנן שור",       "prize_winner"),   # מפעל חיים
    ("קובי פרג'",     "prize_winner"),   # עידוד היצירה
    ("אוהד מילשטיין", "prize_winner"),   # עידוד היצירה
    ("רועי אסף",      "prize_winner"),   # עידוד היצירה
    ("רוני בהט",      "prize_winner"),   # יוצרים בראשית דרכם
    ("כליל כובש",     "prize_winner"),   # יוצרים בראשית דרכם
]

JURY = [
    ("יעל פרלוב",          "prize_committee_member"),  # יו"ר ועדה
    ("אלירן מלכה",         "jury_member"),
    ("יצחק צחייק",         "jury_member"),
    ("שמוליק דובדבני",     "jury_member"),
    ("נועה ברגמן-הרצברג",  "jury_member"),
    ("יוסי מדמוני",        "jury_member"),
    ("גליה בדור",          "jury_member"),
]

OBSERVER = [
    ("רמי שלמור", "event_participant"),  # משקיף — יו"ר ועד הנאמנים
]

ORG_HE = "משרד התרבות והספורט - פרסי אמנות הקולנוע"
ORG_EN = "Ministry of Culture & Sport — Cinema Arts Prizes"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    people = {}
    roles  = []
    pid = 0
    for (name, role) in WINNERS + JURY + OBSERVER:
        pid += 1
        key = f"person_{pid:03d}"
        people[key] = {
            "name_he": name,
            "name_en": None,
            "aliases": [],
            "primary_roles": [role],
            "sources": [CANONICAL],
        }
        roles.append({
            "id": f"role_{pid:03d}",
            "person_id": key,
            "organization_id": "org_001",
            "role_type": role,
            "start_year": 2024,
            "end_year": 2024,
            "notes": "פרסי אמנות הקולנוע 2024" if role == "prize_winner" else
                     "ועדת פרסי אמנות הקולנוע 2024",
            "sources": [CANONICAL],
        })

    record = {
        "file": "ministry_of_culture_prizes__praasim_2024_7__manual.md",
        "url": CANONICAL,
        "source_name": SOURCE_NAME,
        "status": "ok",
        "content_hash": "manual_praasim_2024_7",
        "content_length": 0,
        "filter_info": {"reason": "manual_canonical_source"},
        "truncated": False,
        "elapsed_sec": 0,
        "data": {
            "metadata": {
                "source_url": CANONICAL,
                "source_name": SOURCE_NAME,
                "extraction_date": TODAY,
                "language": "he",
                "canonical_source": CANONICAL,
            },
            "entities": {
                "people": people,
                "organizations": {
                    "org_001": {
                        "name_he": ORG_HE,
                        "name_en": ORG_EN,
                        "type": "government",
                        "subtype": "ministry_prize",
                        "sources": [CANONICAL],
                    }
                },
                "films": {},
                "events": {},
            },
            "roles": roles,
            "relationships": [],
            "films": [],
        },
    }

    with OUT_JSONL.open("w", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Wrote {OUT_JSONL}: {len(people)} people, {len(roles)} roles")


if __name__ == "__main__":
    main()
