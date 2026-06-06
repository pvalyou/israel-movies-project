#!/usr/bin/env python3
"""
Enrich data/movies_db.json crew from EDB person pages (data/edb/edb_persons.json).

Why: build_movies_db.py only reads the raw *_films.json sources, whose crew is
director/producer-level (median 1 crew/film). The richer per-person filmographies
(sound, dop, editor, etc.) live in edb_persons.json (2,590 persons, ~33k credits),
which the pipeline never folded into movies_db. Without this, sourcing the
connections report's filmography from movies_db loses ~85%-real credits (see
docs/plan_pipeline_refactor.md, A/B finding 2026-06-04).

What it does (idempotent):
  1. Backs up movies_db.json → movies_db.json.bak
  2. PASS A — edb_persons.json: for each (person, film, role)
       - locate the movies_db film by EDB film_id, else by normalized title+year
       - append a crew row {name_he, name_en, role, role_he, edb_id, registry_id}
         if that (normalized-name, role) pair isn't already on the film
       - if the film isn't in movies_db, create a minimal record for it (D1: add
         everything — real EDB films missing from the DB)
  3. PASS B — mention /film/ pages (out/*/mentions.jsonl): fund & festival sites list
     full crew on dedicated film pages (director/producer/editor/dop/…). These real,
     conflict-relevant credits aren't in edb_persons or the thin raw crew. Extracted
     with the same guards the report uses (search-page skip + slug↔title match to
     reject sidebar/related films) and merged into the matching movies_db film.
  4. Re-resolves registry_id on every crew/cast row via entity_registry.json
  5. Writes movies_db.json and prints before/after stats

Run from project root, AFTER build_movies_db.py + enrich_movies_db_from_funds.py:
    python3 scripts/enrich_movies_db_crew.py
"""
import json, re, shutil, unicodedata
from pathlib import Path

MOVIES_DB    = Path("data/movies_db.json")
EDB_PERSONS  = Path("data/edb/edb_persons.json")
REGISTRY     = Path("entity_registry.json")

# ── Helpers (kept identical to build_movies_db.py so registry_id matches) ──────

def normalize_title(title: str) -> str:
    if not title:
        return ""
    t = unicodedata.normalize("NFKD", title)
    t = re.sub(r"[\"'״׳.,!?״׳:;()]", "", t)
    t = re.sub(r"[\-–—]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def normalize_name(name: str) -> str:
    if not name:
        return ""
    n = name.strip()
    n = re.sub(r"^ד[\"״״]ר|פרופ[''׳]?|מר|גב[''׳]|עו[\"״״]ד|רו[\"״״]ח\s+", "", n)
    n = re.sub(r"[\"'״׳׳״.,]", "", n)
    n = re.sub(r"[\-–—]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n

def build_registry_map() -> dict:
    if not REGISTRY.exists():
        print("  (warning) entity_registry.json missing — registry_id not resolved")
        return {}
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    m = {}
    for pid, info in reg.get("people", {}).items():
        canonical = info.get("canonical_name_he", "")
        if canonical:
            m[normalize_name(canonical)] = pid
    return m

def tid_of(film_id: str) -> str:
    """EDB t-id from a movies_db film_id ('edb:t0001' → 't0001')."""
    return film_id[4:] if film_id and film_id.startswith("edb:") else ""

# ── Pass B: crew from mention /film/ pages ─────────────────────────────────────

import glob

FILM_URL_RE   = re.compile(r"/(film|films|movie|movies|סרט|סרטים)/", re.IGNORECASE)
SEARCH_URL_RE = re.compile(r"[?&](keywords|search|q|s)=", re.IGNORECASE)
HEBREW_RE     = re.compile(r"[א-ת]")

# Roles that count as real film crew (mirrors the report's FALLBACK_CREW_ROLES;
# "filmmaker" excluded — too vague, means "appears in documentary"). role → role_he.
ROLE_HE = {
    "director": "בימוי", "producer": "הפקה", "co_producer": "הפקה",
    "screenwriter": "תסריט", "scriptwriter": "תסריט", "writer": "תסריט",
    "editor": "עריכה", "cinematographer": "צילום", "composer": "מוזיקה",
    "creator": "יוצר", "co_creator": "יוצר", "art_director": "עיצוב אמנותי",
    "production_designer": "עיצוב", "sound_designer": "פסקול",
}
CREW_ROLES = set(ROLE_HE)
REL_ROLE = {"produced": "producer", "co_produced": "co_producer", "directed": "director"}

def role_set(primary_roles) -> set:
    if not primary_roles:
        return set()
    if isinstance(primary_roles, str):
        primary_roles = re.split(r"[,/;]", primary_roles)
    return {r.strip().lower().replace(" ", "_") for r in primary_roles if r and r.strip()}

def slug_matches_title(url: str, title: str) -> bool:
    """Reject sidebar/related films on a /film/ page: the URL slug must share a
    word with the title (or have no usable slug)."""
    try:
        from urllib.parse import urlparse, unquote
        parts = [p for p in urlparse(url).path.split("/") if p]
        slug = unquote(parts[-1]) if parts else ""
    except Exception:
        return True
    slug_words  = {w.lower() for w in re.split(r"[-_\s]+", slug) if len(w) > 2}
    title_words = {w.lower() for w in re.split(r"[\s\-]+", title) if len(w) > 2}
    return bool(slug_words & title_words) or not slug_words

def _iter_jsonl(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except Exception:
                    continue

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=== Enrich movies_db.json crew from edb_persons.json ===\n")
    db = json.loads(MOVIES_DB.read_text(encoding="utf-8"))
    persons = json.loads(EDB_PERSONS.read_text(encoding="utf-8"))
    registry_map = build_registry_map()

    crew_before = sum(len(f.get("crew") or []) for f in db)
    films_before = len(db)

    # Indices into movies_db
    by_tid = {}
    by_ty = {}
    for f in db:
        t = tid_of(f.get("film_id") or "")
        if t:
            by_tid[t] = f
        key = normalize_title(f.get("title_he") or f.get("title_en") or "") + "|" + str(f.get("year") or "")
        by_ty.setdefault(key, f)

    def crew_signature(f):
        """Set of (normalized name, role) already on the film — for dedup."""
        sig = set()
        for c in (f.get("crew") or []):
            sig.add((normalize_name(c.get("name_he") or ""), c.get("role") or ""))
        return sig

    sigs = {id(f): crew_signature(f) for f in db}

    def new_film_record(tid, title, year):
        rec = {
            "film_id": f"edb:{tid}" if tid else None,
            "sources": ["edb_persons"],
            "title_he": title or "", "title_en": None, "title_alt": [], "title_original": None,
            "year": year, "release_date_il": None, "is_short": False, "duration_min": None,
            "genre": None, "genre_he": None, "tags": [], "based_on": None,
            "description_he": None, "description_en": None,
            "country": [], "language": [], "subtitles": [], "color": None, "format": None,
            "funds": [], "production_companies": [], "distribution_companies": [],
            "broadcaster": None, "budget": None, "box_office_il": None,
            "crew": [], "cast": [],
            "festivals": [], "awards": [], "related_films": [], "related_interviews": [],
            "poster_url": None, "trailer_url": None, "watch_url": None,
            "urls": {"edb": f"https://www.edb.co.il/title/{tid}/"} if tid else {},
        }
        db.append(rec)
        if tid:
            by_tid[tid] = rec
        by_ty.setdefault(normalize_title(title or "") + "|" + str(year or ""), rec)
        sigs[id(rec)] = set()
        return rec

    added_crew = 0
    added_films = 0
    for p in persons:
        name_he = (p.get("name_he") or "").strip()
        if not name_he:
            continue
        name_en = p.get("name_en")
        edb_id  = p.get("edb_id")
        rid     = registry_map.get(normalize_name(name_he))
        nn      = normalize_name(name_he)
        for film in (p.get("films") or []):
            tid   = film.get("film_id") or ""
            title = film.get("title") or ""
            year  = film.get("year")
            role    = film.get("role") or "other"
            role_he = film.get("role_he") or ""
            f = by_tid.get(tid)
            if f is None:
                f = by_ty.get(normalize_title(title) + "|" + str(year or ""))
            if f is None:
                f = new_film_record(tid, title, year)
                added_films += 1
            if (nn, role) in sigs[id(f)]:
                continue
            f.setdefault("crew", []).append({
                "name_he": name_he, "name_en": name_en,
                "role": role, "role_he": role_he,
                "edb_id": edb_id, "registry_id": rid,
            })
            sigs[id(f)].add((nn, role))
            added_crew += 1

    print(f"  PASS A (edb_persons): +{added_crew} crew rows, +{added_films} films")

    # ── PASS B: crew from mention /film/ pages ────────────────────────────────
    b_crew = 0
    b_films = 0
    for path in sorted(glob.glob("out/*/mentions.jsonl")):
        for r in _iter_jsonl(path):
            if r.get("status") != "ok":
                continue
            url = r.get("url") or ""
            # Only dedicated film pages; skip search/archive result pages.
            if not FILM_URL_RE.search(url) or SEARCH_URL_RE.search(url):
                continue
            data     = r.get("data") or {}
            entities = data.get("entities") or {}
            people   = entities.get("people") or {}
            films    = entities.get("films") or {}

            # local person id → (name, roles)
            local = {}
            for eid, p in people.items():
                if not p or not p.get("name_he"):
                    continue
                local[eid] = (p["name_he"].strip(), role_set(p.get("primary_roles")))

            for fid, film in films.items():
                if not film:
                    continue
                title = (film.get("title_he") or "").strip()
                if not title or not HEBREW_RE.search(title):
                    title = (film.get("title_en") or "").strip()
                if not title:
                    continue
                # The slug↔title guard only disambiguates sidebar/related films on
                # pages listing MANY films. On a dedicated single-film page (one film
                # entity) trust it — needed for English-slug + Hebrew-title pages
                # (e.g. arava /en/movies/a-burning-man/ → "איש בוער").
                if len(films) > 1 and not slug_matches_title(url, title):
                    continue
                try:
                    yr = int(film["year"]) if film.get("year") not in (None, "", "null") else None
                except (TypeError, ValueError):
                    yr = None

                # crew: director_ids + produced/directed relationships + fallback
                # creative-role people on this dedicated film page.
                crew = {}   # eid → role
                for did in (film.get("director_ids") or []):
                    if did in local:
                        crew[did] = "director"
                for rel in (data.get("relationships") or []):
                    if not rel:
                        continue
                    rt = REL_ROLE.get(rel.get("type", ""))
                    if not rt:
                        continue
                    sid, tid2 = rel.get("source_id", ""), rel.get("target_id", "")
                    pid_ = sid if tid2 == fid else (tid2 if sid == fid else None)
                    if pid_ in local:
                        crew.setdefault(pid_, rt)
                for eid, (pname, proles) in local.items():
                    hit = proles & CREW_ROLES
                    if hit:
                        crew.setdefault(eid, sorted(hit)[0])

                if not crew:
                    continue

                f = by_ty.get(normalize_title(title) + "|" + str(yr or ""))
                if f is None and yr is not None:
                    # try year-less match (fund pages often omit year)
                    f = by_ty.get(normalize_title(title) + "|")
                if f is None:
                    f = new_film_record("", title, yr)
                    b_films += 1
                for eid, role in crew.items():
                    pname = local[eid][0]
                    nn = normalize_name(pname)
                    if (nn, role) in sigs[id(f)]:
                        continue
                    f.setdefault("crew", []).append({
                        "name_he": pname, "name_en": None,
                        "role": role, "role_he": ROLE_HE.get(role, ""),
                        "edb_id": None, "registry_id": registry_map.get(nn),
                    })
                    sigs[id(f)].add((nn, role))
                    b_crew += 1
    print(f"  PASS B (mention film pages): +{b_crew} crew rows, +{b_films} films")
    added_crew  += b_crew
    added_films += b_films

    # ── Cleanup pass: drop junk + foreign noise ──────────────────────────────
    # (a) test/empty placeholder records (e.g. filmfund "TEST").
    # (b) edb_persons-ONLY films with no real crew role — these are foreign /
    #     international titles that entered only because an Israeli ACTOR appears in
    #     them (EDB lists an actor's full Hollywood filmography). Not Israeli-industry
    #     films. Kept only if some Israeli source also lists the film, or it has a
    #     director/producer/writer/etc. credit. See docs/plan_pipeline_refactor.md (D1).
    def _is_junk(f) -> bool:
        t = (f.get("title_he") or f.get("title_en") or "").strip()
        if not t or t.upper() == "TEST":
            return True
        if f.get("sources") == ["edb_persons"] and not any(
                c.get("role") in CREW_ROLES for c in (f.get("crew") or [])):
            return True
        return False

    before_clean = len(db)
    db = [f for f in db if not _is_junk(f)]
    dropped = before_clean - len(db)

    # Backfill missing year from edb_persons (which carries a year per credit),
    # matched by normalized title. Source pages (makor/fund) often omit the year.
    ep_year_by_title = {}
    for p in persons:
        for fl in (p.get("films") or []):
            if fl.get("year") and fl.get("title"):
                ep_year_by_title.setdefault(normalize_title(fl["title"]), fl["year"])
    yfix = 0
    for f in db:
        if not f.get("year"):
            y = ep_year_by_title.get(normalize_title(f.get("title_he") or f.get("title_en") or ""))
            if y:
                f["year"] = y
                yfix += 1
    # Strip EDB's "(ש.ל.ר)" title artifact from display titles on surviving films.
    _SLR = re.compile(r"\s*\(\s*ש\.?ל\.?ר\s*\)\s*")
    for f in db:
        for fld in ("title_he", "title_en"):
            if f.get(fld) and "ש.ל.ר" in f[fld]:
                f[fld] = _SLR.sub(" ", f[fld]).strip() or f[fld]
    print(f"  CLEANUP: dropped {dropped} junk/foreign films "
          f"(TEST/empty + actor-only edb_persons-only); stripped (ש.ל.ר) markers; "
          f"backfilled {yfix} years from edb_persons")

    # Re-resolve registry_id across all crew/cast (covers rows added by other steps too)
    resolved = total = 0
    for f in db:
        for person in (f.get("crew") or []) + (f.get("cast") or []):
            total += 1
            pid = registry_map.get(normalize_name(person.get("name_he") or ""))
            if pid:
                person["registry_id"] = pid
                resolved += 1

    # Backup + write
    shutil.copy2(MOVIES_DB, MOVIES_DB.with_suffix(".json.bak"))
    MOVIES_DB.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")

    crew_after = sum(len(f.get("crew") or []) for f in db)
    print(f"films:      {films_before} → {len(db)}  (+{added_films} new EDB films)")
    print(f"crew rows:  {crew_before} → {crew_after}  (+{added_crew} from edb_persons)")
    print(f"registry_id resolved: {resolved}/{total} ({100*resolved/max(1,total):.1f}%)")
    print(f"backup: {MOVIES_DB.with_suffix('.json.bak')}")
    print(f"→ {MOVIES_DB}")


if __name__ == "__main__":
    main()
