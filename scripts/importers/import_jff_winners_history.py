#!/usr/bin/env python3
"""
import_jff_winners_history.py — Parse JFF year-by-year winner articles into
mentions.jsonl for the entity resolver.

Input  : sources/jff/pages/*.md whose title contains "הזוכים" or "זוכי"
         pages cover JFF 34 (2017) through JFF 42 (2025).
Output : out/jff_winners/mentions.jsonl

Emits, per person:
  - jury_member          (jurors and committee members)
  - prize_winner         (named individuals who won a prize)
  - director / producer / cinematographer / editor / composer / screenwriter /
    actor  (extracted from "בימוי:", "הפקה:" etc.)

This replaces the small hand-coded import_jff_winners.py — the 2025 winners
+ wiki historical lists are now superseded by the per-article extractions.
"""
from __future__ import annotations
import json, re
from datetime import date
from pathlib import Path

PAGES_DIR = Path("sources/jff/pages")
OUT_DIR   = Path("out/jff_winners")
OUT_JSONL = OUT_DIR / "mentions.jsonl"
SOURCE    = "jff_winners"
TODAY     = date.today().isoformat()
JFF_ORG   = "פסטיבל הקולנוע ירושלים"

# Article ID → festival year
YEAR_BY_ARTICLE_ID = {
    "11667": 2017, "23816": 2018, "34496": 2019, "41916": 2020,
    "58555": 2022, "68549": 2023, "77522": 2024, "87073": 2025,
}

# Heuristics
ROLE_PREFIX = {
    "בימוי":     "director",
    "במאי":      "director",
    "במאית":     "director",
    "במאיות":    "director",
    "במאים":     "director",
    "הפקה":      "producer",
    "מפיק":      "producer",
    "מפיקה":     "producer",
    "מפיקים":    "producer",
    "מפיקות":    "producer",
    "תסריט":     "screenwriter",
    "תסריטאי":   "screenwriter",
    "תסריטאית":  "screenwriter",
    "צילום":     "cinematographer",
    "עריכה":     "editor",
    "עורך":      "editor",
    "עורכת":     "editor",
    "מוזיקה":    "composer",
    "מלחין":     "composer",
    "מלחינה":    "composer",
    "ביה״ס":     None,   # film school — skip
    "ביה\"ס":    None,
    "בית הספר":  None,
}

# Inline-role detector for short cast prizes like "הופעתו של X"
ACTOR_MARKERS = ("שחקן", "שחקנית", "משחק", "הופעת", "ל**", "אנסמבל")

# Strip bold/italic markdown and link syntax from a snippet
def clean(s: str) -> str:
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)   # [text](url) → text
    s = re.sub(r"\*+", "", s)                         # **bold** → bold
    s = re.sub(r"[״׳]", '"', s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

NAME_SPLIT = re.compile(r"\s*(?:,|;| ו| ו-|/|\bו\b)\s*")  # name list separator

def split_names(blob: str) -> list[str]:
    blob = clean(blob)
    # Drop trailing parentheticals like "(אנגליה)" or "(2024)"
    blob = re.sub(r"\([^)]*\)\s*$", "", blob).strip()
    raw = re.split(r"[,،;]| ו(?=[א-ת])", blob)
    out = []
    for tok in raw:
        n = tok.strip(" .-: ״\"'")
        # Drop empties + obvious country codes / single-letter
        if not n or len(n) < 2 or len(n) > 60:
            continue
        # Skip if it's all latin or all digits (likely english title)
        if re.fullmatch(r"[A-Za-z .,'\-]+", n):
            continue
        # Skip headings & filler words
        if n in ("יו\"ר", "יו״ר", "השופטים", "השופטות", "השופטת", "מפיק",
                 "מפיקים", "במאי", "במאית", "במאיות", "במאים"):
            continue
        out.append(n)
    return out

# Quote-like film title detector: "..." or ״...״ or **...** or [...]
FILM_PATTERNS = [
    re.compile(r"\[\*\*([^*\]]+)\*\*\]\(([^)]+)\)"),    # [**title**](url)
    re.compile(r"\*\*\[([^\]]+)\]\(([^)]+)\)\*\*"),     # **[title](url)**
    re.compile(r"\[([^\]]+)\]\(([^)]+)\)"),             # [title](url)
    re.compile(r"\*\*[\"״]([^\"״*]+)[\"״]\*\*"),       # **"title"**
    re.compile(r"[\"״]([^\"״]{2,40})[\"״]"),            # "title"
]

def find_film(blob: str) -> tuple[str | None, str | None]:
    """Return (title, url) for first film mention in the blob, else (None,None)."""
    for pat in FILM_PATTERNS:
        m = pat.search(blob)
        if m:
            title = clean(m.group(1))
            url = m.group(2) if m.lastindex and m.lastindex >= 2 else None
            if title and 1 < len(title) < 80:
                return title, url
    return None, None


def extract_prize_blocks(md: str) -> list[dict]:
    """
    Split the markdown into blocks. Each block is a paragraph (separated by
    blank lines).  Returns a list of {text, has_prize} dicts.
    """
    paras = re.split(r"\n\s*\n+", md)
    return [{"text": p.strip()} for p in paras if p.strip()]


def parse_page(md_path: Path):
    """
    Yield records for one JFF winners page:
        {kind: "jury"|"winner", name, role, film?, film_url?, year, prize_label}
    """
    text = md_path.read_text(encoding="utf-8")
    # Determine year
    year = None
    # Match the article ID embedded in the source URL inside the file's meta.
    # As fallback, parse from title.
    meta_path = md_path.with_suffix(".meta.json")
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        for aid, y in YEAR_BY_ARTICLE_ID.items():
            if aid in meta.get("url", ""):
                year = y; break
    if not year:
        m = re.search(r"ה[\- ]?(\d{2})", text[:200])
        if m:
            year = 1984 + int(m.group(1)) - 1
        else:
            m = re.search(r"20\d\d", text[:300])
            if m: year = int(m.group(0))
    if not year:
        return

    blocks = extract_prize_blocks(text)

    # Track "current prize label" — when we see a bold header like
    # "**פרס X**" we tag subsequent crew lines until the next header.
    last_prize = ""
    last_film  = ""
    last_film_url = None
    is_competition_header = re.compile(r"\*\*(תחרות|התחרות|פרסים)\b")
    # Prize header: a line that names a prize AND announces a winner — either
    # "<פרס X> מוענק לסרט <Y>", "ציון לשבח מוענק לסרט <Y>", or
    # "<פרס X> לסרט <Y>".  We also accept "זכה <Y>" / "זוכה <Y>".
    prize_award_re = re.compile(
        r"(?:^|\n)\s*\*?\*?\s*((?:פרס|ציון לשבח|מענק)[^\n]*?)"
        r"\s*(?:מוענק|זכה|זוכה|מוענקת)\s+(?:לסרט\s+|ל)?"
    )

    for blk in blocks:
        txt = blk["text"]

        # Competition section header — reset prize/film context
        if is_competition_header.search(txt) and "מוענק" not in txt:
            last_prize = ""
            last_film  = ""
            last_film_url = None

        # Jury line
        jurom = re.search(
            r"(?:חבר ה?שופט(?:ים|ות)?|השופטת|חבר השופטים כלל)[ :]+([^\n]+)",
            txt
        )
        if jurom:
            for n in split_names(jurom.group(1)):
                # Strip "(יו\"ר)" annotation but record chair role
                role_type = "jury_member"
                if "יו\"ר" in jurom.group(0) or "(יו" in jurom.group(0):
                    if n == split_names(jurom.group(1))[0]:
                        role_type = "prize_committee_member"
                yield {
                    "kind": "jury", "name": n, "role": role_type,
                    "year": year, "prize_label": last_prize,
                    "film": None, "film_url": None,
                }

        # Prize header — capture label and film
        ph = prize_award_re.search(txt)
        if ph:
            last_prize = clean(ph.group(1))
            film, url = find_film(txt[ph.end():])  # film appears AFTER "מוענק לסרט"
            if not film:
                film, url = find_film(txt)
            if film:
                last_film = film
                last_film_url = url

        # Is this block inside a "prize awarded" section?  Look at the current
        # block PLUS the most recent prize header — if a prize was just
        # declared, this block's directors/producers are the winners.
        prize_active = (
            ("מוענק" in txt or "זכה" in txt or "זוכה" in txt) or
            (last_prize and last_film)   # carried over from previous header block
        )

        # Whole block — find all "role: names" patterns and emit
        # crew records bound to last_film (when present).
        for pref, role in ROLE_PREFIX.items():
            if not role:
                continue
            # Match "פרפיקס: name1, name2 ..." up to newline or sentence end.
            # Use non-greedy stop at next role-prefix or paragraph.
            for m in re.finditer(rf"{re.escape(pref)}\s*[:：]\s*([^\n]+?)(?=  |$|\n)", txt):
                blob = m.group(1)
                # Stop at next "ROLE:" pattern within same line
                cut = re.search(r"(?:בימוי|הפקה|תסריט|צילום|עריכה|מוזיקה|מלחין|במאי|מפיק|תסריטאי|עורך)\s*:", blob)
                if cut:
                    blob = blob[:cut.start()]
                for n in split_names(blob):
                    yield {
                        "kind":"winner", "name": n, "role": role,
                        "year": year,
                        "prize_label": last_prize or "פרס",
                        "film": last_film or None,
                        "film_url": last_film_url,
                    }
                    # Director / producer of a freshly-awarded film → prize winner.
                    if prize_active and role in ("director", "producer"):
                        yield {
                            "kind":"winner", "name": n, "role":"prize_winner",
                            "year": year,
                            "prize_label": last_prize or "פרס",
                            "film": last_film or None,
                            "film_url": last_film_url,
                        }

        # Actor / acting prizes — look for the pattern "מוענק ל**NAME**, על הופעת"
        if any(mk in txt for mk in ACTOR_MARKERS):
            for m in re.finditer(r"מוענק\s+ל\s*\*\*([^*]+)\*\*", txt):
                n = clean(m.group(1))
                if n and 2 <= len(n) <= 40 and re.search(r"[א-ת]", n):
                    f, u = find_film(txt)
                    yield {
                        "kind":"winner", "name": n, "role":"actor",
                        "year": year, "prize_label": last_prize,
                        "film": f or last_film, "film_url": u or last_film_url,
                    }
                    # Also stamp prize_winner role for the named recipient
                    yield {
                        "kind":"winner", "name": n, "role":"prize_winner",
                        "year": year, "prize_label": last_prize,
                        "film": f or last_film, "film_url": u or last_film_url,
                    }

        # Directors of prize-winning films also get prize_winner
        if "מוענק לסרט" in txt or "זכה" in txt or "זוכה" in txt:
            for m in re.finditer(r"בימוי\s*[:：]\s*([^\n,]+)", txt):
                for n in split_names(m.group(1)):
                    yield {
                        "kind":"winner", "name": n, "role":"prize_winner",
                        "year": year, "prize_label": last_prize,
                        "film": last_film, "film_url": last_film_url,
                    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    md_files = sorted(PAGES_DIR.glob("jff__*.md"))
    targets = []
    for p in md_files:
        meta = p.with_suffix(".meta.json")
        if not meta.exists(): continue
        try:
            m = json.loads(meta.read_text())
        except Exception:
            continue
        title = m.get("title", "")
        if not ("הזוכים" in title or "זוכי " in title):
            continue
        targets.append(p)

    print(f"Found {len(targets)} JFF winner pages")

    # Dedup
    seen_role = set()      # (name, role, year, source_url)
    people = {}            # name → person record
    roles_out = []
    films = {}             # title → film record
    rels = []

    for p in targets:
        meta = json.loads(p.with_suffix(".meta.json").read_text())
        url = meta["url"]
        n_before = len(roles_out)
        for rec in parse_page(p):
            n = rec["name"]
            if n not in people:
                people[n] = {
                    "name_he": n, "name_en": None, "aliases": [],
                    "primary_roles": [], "sources": [],
                }
            entry = people[n]
            if rec["role"] not in entry["primary_roles"]:
                entry["primary_roles"].append(rec["role"])
            if url not in entry["sources"]:
                entry["sources"].append(url)

            key = (n, rec["role"], rec["year"], url)
            if key in seen_role: continue
            seen_role.add(key)

            if rec.get("film"):
                ftitle = rec["film"]
                if ftitle not in films:
                    films[ftitle] = {
                        "name_he": ftitle, "name_en": None,
                        "year": rec["year"], "sources": [url],
                        "url": rec.get("film_url"),
                    }
                elif url not in films[ftitle]["sources"]:
                    films[ftitle]["sources"].append(url)

            note = rec.get("prize_label", "") or ""
            if rec.get("film"): note = f"{note} — {rec['film']} ({rec['year']})".strip(" —")
            roles_out.append({
                "id": f"role_{len(roles_out)+1:04d}",
                "person_id": n, "organization_id": "org_001",
                "role_type": rec["role"],
                "start_year": rec["year"], "end_year": rec["year"],
                "notes": note,
                "sources": [url],
            })
        print(f"  {p.name[:60]:60s}  +{len(roles_out)-n_before} roles")

    # Assign stable IDs
    pid_map = {}
    for i, n in enumerate(sorted(people), start=1):
        pid_map[n] = f"person_{i:04d}"
    fid_map = {}
    for i, t in enumerate(sorted(films), start=1):
        fid_map[t] = f"film_{i:04d}"

    # Replace person/film references with IDs
    people_out = {pid_map[n]: people[n] for n in people}
    films_out  = {fid_map[t]: films[t]   for t in films}
    for r in roles_out:
        r["person_id"] = pid_map[r["person_id"]]
    for r in roles_out:
        pass

    rec = {
        "file": "jff_winners_history__manual.md",
        "url": "manual://jff_winners/all_years/",
        "source_name": SOURCE,
        "status": "ok",
        "content_hash": "manual_jff_winners_history",
        "content_length": 0,
        "filter_info": {"reason": "manual_canonical_source"},
        "truncated": False, "elapsed_sec": 0,
        "data": {
            "metadata": {
                "source_url": "manual://jff_winners/all_years/",
                "source_name": SOURCE,
                "extraction_date": TODAY,
                "language": "he",
                "canonical_source": "https://jff.org.il/he/",
            },
            "entities": {
                "people": people_out,
                "organizations": {
                    "org_001": {
                        "name_he": JFF_ORG,
                        "name_en": "Jerusalem Film Festival",
                        "type": "festival", "subtype": "film_festival",
                        "sources": ["https://jff.org.il/he/"],
                    }
                },
                "films": films_out,
                "events": {},
            },
            "roles": roles_out,
            "relationships": rels,
            "films": [],
        },
    }

    with OUT_JSONL.open("w", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"\nWrote {OUT_JSONL}: {len(people)} people, {len(films)} films, "
          f"{len(roles_out)} roles")


if __name__ == "__main__":
    main()
