#!/usr/bin/env python3
"""Phase 3: Scrape EDB person pages → edb_persons.json

Fetches /name/<id>/ pages for each person in edb_films.json crew,
extracts filmography, collaborators, English name.
Then expands 1 hop to scrape collaborators.

Usage:
  python3 scripts/edb/scrape_edb_persons.py              # Full run (seed + expansion)
  python3 scripts/edb/scrape_edb_persons.py --seed-only   # Only seed persons
"""

import json
import os
import re
import sys
import time

import requests

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
BASE = "https://www.edb.co.il"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA})

CHECKPOINT = "data/edb/edb_persons.json"
SEED_INPUT = "data/edb/edb_films.json"

ROLE_MAP = {
    "בימוי": "director", "הפקה": "producer", "תסריט": "screenwriter",
    "עריכה": "editor", "צילום": "cinematographer",
    "מפיק/ה שותפ/ה": "co_producer", "מפיק/ה ראשי/ת": "executive_producer",
    "מפיק/ה אחראי/ת": "line_producer", "הפקה בפועל": "line_producer",
    "הפקת ליין": "line_producer", "מפיק שותף": "co_producer",
    "עיצוב אמנותי": "production_designer", "יצירה": "creator",
    "צלמ/ת ראשי/ת": "cinematographer", "תסריטאי/ת ראשי/ת": "screenwriter",
    "(עריכה)": "editor", "(צילום)": "cinematographer",
    "(עיצוב פסקול)": "sound_designer",
    "(עיצוב פסקול ועירבול)": "sound_designer",
    "(עיצוב אמנותי)": "production_designer",
    "(עיצוב תלבושות)": "costume_designer",
    "(ליהוק)": "casting_director", "(איפור)": "makeup_artist",
    "(מאפר/ת ראשי/ת)": "makeup_artist",
    "(עריכת תסריט)": "script_editor", "(עריכת פסקול)": "sound_editor",
    "(עריכת אונליין)": "online_editor",
    "(הקלטה)": "sound_recordist",
    "(מקליט/ה ראשי/ת)": "sound_recordist",
    "(עוזר/ת בימוי)": "assistant_director",
    "(עוזר/ת בימוי ראשונ/ה)": "first_ad",
    "(עיצוב תמונה)": "production_designer",
    "(הפקת פוסט)": "post_producer", "(תחקיר)": "researcher",
    "(צילום סטילס)": "still_photographer",
    "(תאורנ/ית ראשי/ת)": "gaffer", "(סט דרסר)": "set_decorator",
    "(ניהול הפקה)": "production_manager",
    "(ניהול אמנותי)": "art_manager",
    "(ניהול תסריט)": "script_supervisor",
    "(עורכ/ת ראשי/ת)": "editor",
    "(אפקטים ויזואלים)": "vfx_artist",
    "(צילום אירוע)": "cinematographer",
    "(צוות אנימציה)": "animator",
    "עצמו": "self", "עצמה": "self", "קול": "voice_actor",
    "מבצע/ת": "performer", "יוצר/ת שותפ/ה": "co_creator",
    "פיתוח תסריט": "script_developer",
    "עיצוב סאונד": "sound_designer",
    "(צוות אחר, מנהלת הפצה)": "distribution_manager",
    "(צוות אחר, ניהול הפצה)": "distribution_manager",
    "שחקן": "actor", "שחקנית": "actor", "משחק": "actor",
    "יוצרים": "actor",
}


def load_seed_ids(path: str) -> set:
    if not os.path.exists(path):
        print(f"ERROR: {path} not found")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        films = json.load(f)
    ids = set()
    for f in films:
        for c in f.get("crew", []):
            eid = c.get("edb_id", "")
            if eid:
                ids.add(eid)
    print(f"Seed person IDs from {path}: {len(ids)}")
    return ids


def load_checkpoint() -> dict:
    if not os.path.exists(CHECKPOINT):
        return {}
    with open(CHECKPOINT, encoding="utf-8") as f:
        items = json.load(f)
    return {p["edb_id"]: p for p in items}


def save_checkpoint(done: dict):
    items = list(done.values())
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def extract_role_he_from_td(td_text: str) -> str:
    """Extract the Hebrew role string from a <td> cell that may have sub-labels."""
    td_text = re.sub(r"<[^>]+>", " ", td_text)
    td_text = re.sub(r"\s+", " ", td_text).strip()
    # Often format: "בימוי (במאים)" or "מפיק/ה אחראי/ת (עורכים ומפיקים...)"
    # Take the part before the first (
    role_raw = td_text.split("(")[0].strip()
    return role_raw


def map_role(role_he: str) -> str:
    """Map Hebrew role string to English role key."""
    if not role_he:
        return "actor"
    role_he = role_he.strip()
    if role_he in ROLE_MAP:
        return ROLE_MAP[role_he]
    return "other"


def scrape_person(nid: str) -> dict | None:
    """Scrape a single person page. Returns dict or None on failure."""
    try:
        r = SESSION.get(f"{BASE}/name/{nid}/", timeout=15)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        html = r.text
    except Exception as e:
        print(f"    ERROR {nid}: {e}")
        return None

    # Name (Hebrew)
    name_he_m = re.search(r"<h1[^>]*>([^<]+)</h1>", html)
    name_he = name_he_m.group(1).strip() if name_he_m else ""

    # Name (English)
    name_en_m = re.search(r"<h2[^>]*>([^<]+)</h2>", html)
    name_en = name_en_m.group(1).strip() if name_en_m else ""

    # Collaborators
    collaborators = []
    collab_start = html.find("מרבה לעבוד")
    if collab_start > 0:
        section = html[collab_start:collab_start + 2000]
        collabs = re.findall(r"/name/(n\d+)/", section)
        collaborators = sorted(set(collabs))
        # Remove self-reference
        collaborators = [c for c in collaborators if c != nid]

    # Filmography — parse all <tr> rows in tables
    films = []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL)
    for row in rows:
        title_m = re.search(r'href="/title/(t\d+)/"[^>]*>([^<]+)</a>', row)
        if not title_m:
            continue

        film_id = title_m.group(1)
        title_he = title_m.group(2).strip()

        # Extract year from the row text
        year_m = re.search(r"\((\d{4})", row)
        year = int(year_m.group(1)) if year_m else None

        # Extract role from <td> cells
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        role_he = ""
        if len(tds) >= 2:
            role_he = extract_role_he_from_td(tds[-1])
        role = map_role(role_he)

        films.append({
            "film_id": film_id,
            "title": title_he,
            "year": year,
            "role_he": role_he,
            "role": role,
        })

    return {
        "edb_id": nid,
        "name_he": name_he,
        "name_en": name_en,
        "films": films,
        "collaborators": collaborators,
    }


def main():
    seed_only = "--seed-only" in sys.argv
    seed_ids = load_seed_ids(SEED_INPUT)

    done = load_checkpoint()
    print(f"Checkpoint: {len(done)} already scraped")

    todo_seed = sorted(seed_ids - set(done.keys()))
    print(f"Seed to scrape: {len(todo_seed)}")

    # ── Step 1: Scrape all seed persons ────────────────────────────────────
    started = time.time()
    for i, nid in enumerate(todo_seed):
        result = scrape_person(nid)
        if result:
            result["is_seed"] = True
            done[nid] = result

        if (i + 1) % 100 == 0:
            elapsed = time.time() - started
            rate = (i + 1) / elapsed * 60 if elapsed > 0 else 0
            save_checkpoint(done)
            print(f"  checkpoint: {len(done)} persons | {i+1}/{len(todo_seed)} "
                  f"({rate:.0f}/min)")

        time.sleep(0.4)

    save_checkpoint(done)
    elapsed = time.time() - started
    print(f"\nSeed complete: {len(done)} persons in {elapsed/60:.1f} min\n")

    if seed_only:
        print_stats(done)
        return

    # ── Step 2: Expand to collaborators (1 hop) ────────────────────────────
    all_collab_ids = set()
    for p in done.values():
        all_collab_ids.update(p.get("collaborators", []))

    new_ids = sorted(all_collab_ids - set(done.keys()))
    print(f"Collaborators to expand: {len(new_ids)}")

    started = time.time()
    for i, nid in enumerate(new_ids):
        result = scrape_person(nid)
        if result:
            result["is_seed"] = False
            done[nid] = result

        if (i + 1) % 100 == 0:
            elapsed = time.time() - started
            rate = (i + 1) / elapsed * 60 if elapsed > 0 else 0
            save_checkpoint(done)
            print(f"  expand checkpoint: {len(done)} persons | {i+1}/{len(new_ids)} "
                  f"({rate:.0f}/min)")

        time.sleep(0.4)

    save_checkpoint(done)
    elapsed = time.time() - started
    print(f"\nExpansion complete: {len(done)} persons in {elapsed/60:.1f} min")
    print_stats(done)


def print_stats(done: dict):
    seed = [p for p in done.values() if p.get("is_seed")]
    collab = [p for p in done.values() if not p.get("is_seed")]
    total_films = sum(len(p.get("films", [])) for p in done.values())
    total_collabs = sum(len(p.get("collaborators", [])) for p in done.values())
    print(f"Seed: {len(seed)}, Expanded: {len(collab)}, Total: {len(done)}")
    print(f"Total film credits: {total_films}")
    print(f"Total collaborator links: {total_collabs}")


if __name__ == "__main__":
    main()