#!/usr/bin/env python3
"""
import_guilds_boards.py — Import guild board members (Directors Guild + Producers Guild)
into out/guilds/mentions.jsonl as synthetic manual entries.

Run: python3 import_guilds_boards.py [--dry-run]

Sources:
  Directors Guild: https://directorsguild.org.il/הנהלה-וצוות/  (accessed 2026-05-26)
  Producers Guild: https://producers.org.il/about              (accessed 2026-05-26)
"""

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

OUT_JSONL = Path("out/guilds/mentions.jsonl")
SOURCE_NAME = "guilds"
TODAY = date.today().isoformat()

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

DIRECTORS_GUILD = {
    "manual_url":   "manual://guilds/directors-guild/board-2026",
    "canonical_url": "https://directorsguild.org.il/%D7%94%D7%A0%D7%94%D7%9C%D7%94-%D7%95%D7%A6%D7%95%D7%95%D7%AA/",
    "org_name_he":  "איגוד הבמאיות והבמאים בישראל",
    "org_name_en":  "Israeli Directors Guild",
    "members": [
        # (name_he, role, year)
        ("עלירן אליה",      "chairperson",    2026),
        ("יונתן גורפינקל", "board_member",   2026),
        ("אביגיל שפרבר",   "board_member",   2026),
        ("רוני סאר",        "board_member",   2026),
        ("דני רוזנברג",     "board_member",   2026),
        ("טל גרניט",        "board_member",   2026),
        ("יוחאי חדד",       "board_member",   2026),
        ("אלית זקצור",     "board_member",   2026),
        ("יסמין קיני",     "board_member",   2026),
        ("עידן חובל",       "board_member",   2026),
        ("סופי ארטוס",     "board_member",   2026),
        ("חליל קובש",      "board_member",   2026),
    ],
}

PRODUCERS_GUILD = {
    "manual_url":   "manual://guilds/producers-guild/board-2026",
    "canonical_url": "https://producers.org.il/about",
    "org_name_he":  "איגוד יוצרי הסרט הישראלים — המפיקים",
    "org_name_en":  "Israeli Television and Film Producers Union",
    "members": [
        ("אדר שפרן",         "chairperson",  2026),
        ("שי אינס",           "board_member", 2026),
        ("ליאת בנאסולי",     "board_member", 2026),
        ("אריק ברנשטיין",    "board_member", 2026),
        ("אביתר מונצ'ז",     "board_member", 2026),
        ("קובי מזרחי",       "board_member", 2026),
        ("רוני מנור",         "board_member", 2026),
        ("איתן מנצורי",      "board_member", 2026),
        ("שירה מרגלית",      "board_member", 2026),
        ("עדי נבון",           "board_member", 2026),
        ("אסנת סרגה",        "board_member", 2026),
        ("יפעת פרסטלניק",   "board_member", 2026),
        ("לי קופרמן",         "board_member", 2026),
        ("מרק רוזנבאום",     "board_member", 2026),
        ("שולה שפיגל",       "board_member", 2026),
    ],
}


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_entry(guild: dict) -> dict:
    manual_url = guild["manual_url"]
    people, roles = {}, []
    for idx, (name_he, role, year) in enumerate(guild["members"], 1):
        pid = f"person_{idx:03d}"
        people[pid] = {
            "name_he":       name_he,
            "name_en":       None,
            "aliases":       [],
            "primary_roles": [role],
            "sources":       [manual_url],
        }
        roles.append({
            "id":              f"role_{idx:03d}",
            "person_id":       pid,
            "organization_id": "org_001",
            "role_type":       role,
            "start_year":      year,
            "end_year":        year,
            "notes":           "",
            "sources":         [manual_url],
        })

    chash = hashlib.md5(manual_url.encode()).hexdigest()
    return {
        "file":           f"guilds__{guild['org_name_en'].lower().replace(' ', '-')}__manual.md",
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
                "canonical_source": guild["canonical_url"],
            },
            "entities": {
                "people": people,
                "organizations": {
                    "org_001": {
                        "name_he": guild["org_name_he"],
                        "name_en": guild["org_name_en"],
                        "type":    "guild",
                        "subtype": "professional_guild",
                        "sources": [manual_url],
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


def main():
    dry_run = "--dry-run" in sys.argv

    guilds = [DIRECTORS_GUILD, PRODUCERS_GUILD]
    entries = [build_entry(g) for g in guilds]

    if dry_run:
        for g, e in zip(guilds, entries):
            print(f"\n=== {g['org_name_he']} ({g['manual_url']}) ===")
            for _, (name, role, year) in enumerate(g["members"]):
                print(f"  {name:20s}  {role}")
        print("\n(dry run — nothing written)")
        return

    # Preserve existing lines that aren't our board entries
    BOARD_PREFIXES = {g["manual_url"] for g in guilds}
    existing = []
    if OUT_JSONL.exists():
        for line in OUT_JSONL.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                if rec.get("url", "") in BOARD_PREFIXES:
                    continue
            except Exception:
                pass
            existing.append(line)

    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for line in existing:
            f.write(line + "\n")
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    total = sum(len(g["members"]) for g in guilds)
    print(f"Wrote {len(entries)} entries ({total} people) to {OUT_JSONL}")


if __name__ == "__main__":
    main()
