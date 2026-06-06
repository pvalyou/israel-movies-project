#!/usr/bin/env python3
"""
enrich_movies_db_from_funds.py — Enrich data/movies_db.json with fund data
extracted from out/*/mentions.jsonl and data/funds/*.json.

For each fund-sourced film:
  - If already in movies_db → add fund key + fund URL
  - If missing → create new entry with title/year/director/fund

Run: python3 scripts/funds/enrich_movies_db_from_funds.py [--dry-run]

Sources processed:
  mentions.jsonl: makor, arava_film_fund, galilee_film_fund, gesher,
                  jerusalem_film_fund, nfct, filmfund, fdoc, rabinovich_cinema
  data/funds/nfct_films.json, filmfund_films.json (legacy flat lists)
"""

import glob
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

DB_PATH   = Path("data/movies_db.json")
TODAY     = date.today().isoformat()
DRY_RUN   = "--dry-run" in sys.argv

# Sources that represent fund support (not festivals, critics, etc.)
FUND_SOURCES = {
    "makor":              "קרן מקור",
    "arava_film_fund":    "קרן ערבה",
    "galilee_film_fund":  "קרן הגליל",
    "gesher":             "קרן גשר",
    "jerusalem_film_fund":"קרן ירושלים לקולנוע",
    "nfct":               "הקרן החדשה לקולנוע וטלוויזיה",
    "filmfund":           "הקרן הישראלית לקולנוע",
    "fdoc":               "הפורום הדוקומנטרי",
    "rabinovich_cinema":  "קרן רבינוביץ",
}

# Titles that are category headings, not real films — skip them
_SKIP_TITLE_RE = re.compile(
    r"^(סרטים|short|long|feature|documentary|animation|קצר|ארוך|עלילת|תיעוד"
    r"|פרויקט|project|אפיזוד|episode|ראיון|interview|פאנל|panel|אירוע|event"
    r"|season|עונה|גלרי|gallery|clip|קליפ|trailer|טריילר|making|מאחורי|הקרנ"
    r"|about|אודות)",
    re.IGNORECASE | re.UNICODE,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def norm_title(t: str) -> str:
    if not t:
        return ""
    t = unicodedata.normalize("NFKD", t)
    t = re.sub(r'["\'"״׳.,!?:;()\[\]]', "", t)
    t = re.sub(r"[-–—]", " ", t)
    return re.sub(r"\s+", " ", t).strip().lower()


def url_slug_matches_title(url: str, title_he: str, title_en: str = "") -> bool:
    """Return True iff the URL's last path slug plausibly belongs to this film.

    Pages like kerenmakor.org.il/films/<slug>/ have one canonical film per slug.
    Films listed in a "related films" sidebar appear in the page's extracted
    entities but DO NOT belong to that page's slug. We refuse to attach a page
    URL to a film unless at least one significant title token appears in the
    decoded slug.
    """
    from urllib.parse import unquote, urlparse
    if not url or not title_he:
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    # URLs that identify films via query-string IDs (e.g. ?movieId=123) or
    # numeric path IDs are trusted as-is — they don't carry a title slug.
    if parsed.query and re.search(r"(movieid|filmid|id)=\d+", parsed.query, re.I):
        return True
    segs = [s for s in parsed.path.split("/") if s]
    if not segs:
        return False
    slug = unquote(segs[-1]).lower()
    # Purely numeric / very short last segment → can't slug-check; trust it.
    if re.fullmatch(r"\d+", slug) or len(slug) < 3:
        return True
    # accept any title token of length >= 3 (Hebrew/Arabic or latin)
    tokens = []
    for src in (title_he, title_en or ""):
        for tok in re.split(r"\s+", src.strip().lower()):
            tok = re.sub(r'["\'"״׳.,!?:;()\[\]\-–—]', "", tok)
            if len(tok) >= 3:
                tokens.append(tok)
    if not tokens:
        # No usable title tokens → can't check; default to accept.
        return True
    return any(tok in slug for tok in tokens)


def is_real_film(title_he: str, title_en: str = "") -> bool:
    """Return False for generic category headings and junk titles."""
    t = (title_he or "").strip()
    if not t or len(t) < 2:
        return False
    if _SKIP_TITLE_RE.match(t):
        return False
    # Too many words = likely a sentence description, not a film title
    if len(t.split()) > 10:
        return False
    return True


def make_film_id(source: str, slug: str) -> str:
    import hashlib
    h = hashlib.md5(slug.encode()).hexdigest()[:8]
    return f"{source}:{h}"


# ── Load current DB ───────────────────────────────────────────────────────────

def load_db() -> tuple[list, dict, dict, dict]:
    with open(DB_PATH, encoding="utf-8") as f:
        movies = json.load(f)
    # Index by (norm_title, str_year)
    by_title_year: dict[tuple, int] = {}
    # Index by norm_title only (for no-year fallback)
    by_title: dict[str, list[int]] = defaultdict(list)
    # Index by normalized English title — used to merge fund rows into
    # existing EDB rows when the Hebrew title disagrees (often because
    # upstream LLM extractors hallucinated Hebrew translations).
    by_title_en: dict[str, list[int]] = defaultdict(list)
    for idx, m in enumerate(movies):
        nt = norm_title(m.get("title_he", ""))
        yr = str(m.get("year") or "")
        by_title_year[(nt, yr)] = idx
        by_title[nt].append(idx)
        ne = norm_title(m.get("title_en") or "")
        if len(ne) >= 3:
            by_title_en[ne].append(idx)
    return movies, by_title_year, by_title, by_title_en


def find_match(title_he, title_en, year, movies,
               by_title_year, by_title, by_title_en) -> int | None:
    """Return index into movies list, or None.

    Tries Hebrew title first (with/without year), then falls back to English
    title when the Hebrew didn't match — this catches fund rows whose Hebrew
    title was hallucinated upstream but whose English title still aligns with
    the canonical EDB record.
    """
    nt  = norm_title(title_he)
    yr  = str(year or "")
    if nt:
        # Exact match with year
        if yr and (nt, yr) in by_title_year:
            return by_title_year[(nt, yr)]
        # Year-less match (if only one film has that title)
        if nt in by_title:
            hits = by_title[nt]
            if len(hits) == 1:
                return hits[0]
            # If caller supplied year, try matching within 1 year
            if yr:
                for i in hits:
                    db_yr = str(movies[i].get("year") or "")
                    if db_yr and abs(int(yr) - int(db_yr)) <= 1:
                        return i
    # Fallback: English-title match
    ne = norm_title(title_en or "")
    if len(ne) >= 3 and ne in by_title_en:
        hits = by_title_en[ne]
        if len(hits) == 1:
            return hits[0]
        if yr:
            for i in hits:
                db_yr = str(movies[i].get("year") or "")
                if db_yr and abs(int(yr) - int(db_yr)) <= 1:
                    return i
    return None


def add_fund(film_record: dict, fund_key: str, fund_url: str = "") -> bool:
    """Add fund_key to film's funds list. Return True if added."""
    funds = film_record.setdefault("funds", [])
    if isinstance(funds, list) and fund_key not in funds:
        funds.append(fund_key)
        # Add fund URL — urls may be dict or list; only update if dict
        if fund_url:
            urls = film_record.get("urls")
            if isinstance(urls, dict) and fund_key not in urls:
                urls[fund_key] = fund_url
            elif urls is None:
                film_record["urls"] = {fund_key: fund_url}
        return True
    return False


# ── Extract from mentions.jsonl ───────────────────────────────────────────────

def extract_from_mentions(source: str) -> list[dict]:
    """Return list of {title_he, title_en, year, director_he, director_en, url, fund}."""
    path = f"out/{source}/mentions.jsonl"
    if not Path(path).exists():
        return []

    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
                if rec.get("status") != "ok":
                    continue
                url = rec.get("url", "")
                # Skip search/listing pages
                if re.search(r"[?&](keywords|search|q|s)=", url, re.I):
                    continue
                entities = (rec.get("data") or {}).get("entities", {}) or {}
                films   = entities.get("films", {}) or {}
                people  = entities.get("people", {}) or {}

                # Build person_id → name map
                pid_to_name: dict[str, tuple[str, str]] = {}
                for pid, p in (people or {}).items():
                    if p:
                        pid_to_name[pid] = (
                            (p.get("name_he") or "").strip(),
                            (p.get("name_en") or "").strip(),
                        )

                for film in (films or {}).values():
                    if not film:
                        continue
                    title_he = (film.get("title_he") or "").strip()
                    title_en = (film.get("title_en") or "").strip()
                    if not is_real_film(title_he, title_en):
                        continue

                    year = film.get("year")
                    if isinstance(year, str):
                        try:
                            year = int(year) if year.strip() else None
                        except ValueError:
                            year = None

                    # Get director from director_ids → people map
                    director_he, director_en = "", ""
                    for did in (film.get("director_ids") or []):
                        name_he, name_en = pid_to_name.get(did, ("", ""))
                        if name_he:
                            director_he = name_he
                            director_en = name_en
                            break

                    # Fallback: if only one person on the page has a creative role
                    if not director_he and len(people) == 1:
                        p = list(people.values())[0]
                        if p and set(p.get("primary_roles") or []) & {
                            "director", "filmmaker", "screenwriter"
                        }:
                            director_he = (p.get("name_he") or "").strip()
                            director_en = (p.get("name_en") or "").strip()

                    # Fund URL = page URL if it looks like a film page AND the
                    # URL slug actually matches the film's title (else we'd be
                    # attaching the host page's URL to a sidebar/"related" film).
                    is_film_url = bool(re.search(
                        r"/(film|films|movie|movies|title|סרט|סרטים)/",
                        url, re.I
                    ))
                    fund_url = url if (is_film_url and url_slug_matches_title(
                        url, title_he, title_en
                    )) else ""

                    records.append({
                        "title_he":    title_he,
                        "title_en":    title_en or None,
                        "year":        year,
                        "director_he": director_he or None,
                        "director_en": director_en or None,
                        "fund":        source,
                        "url":         url,
                        "fund_url":    fund_url,
                    })
            except Exception:
                pass

    return records


# ── Extract from flat fund JSON files ─────────────────────────────────────────

def extract_from_fund_json(path: str, fund_key: str) -> list[dict]:
    if not Path(path).exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    records = []
    for item in data:
        if not isinstance(item, dict):
            continue
        title_he = (item.get("title_he") or "").strip()
        if not is_real_film(title_he):
            continue
        year = item.get("year")
        try:
            year = int(year) if year else None
        except (TypeError, ValueError):
            year = None
        raw_url = item.get("url", "") or ""
        # Same sanity check as for mentions.jsonl: drop the URL if its slug
        # doesn't plausibly match the film title.
        safe_url = raw_url if url_slug_matches_title(raw_url, title_he) else ""
        records.append({
            "title_he":    title_he,
            "title_en":    None,
            "year":        year,
            "director_he": (item.get("director") or "").strip() or None,
            "director_en": None,
            "fund":        fund_key,
            "url":         raw_url,
            "fund_url":    safe_url,
        })
    return records


# ── Collapse hallucinated-Hebrew duplicates ──────────────────────────────────

def collapse_by_title_en(records: list[dict]) -> list[dict]:
    """Records sharing the same (norm_title_en, year, fund) describe the same
    film. Upstream LLM extractors often produced many different Hebrew titles
    for the same English title (e.g. "Legend of destruction" → "אגדת חורבן",
    "אגדת ההרס", "אגדת ההשמדה", "הנביא", …). Collapse them into one record,
    keeping the most common Hebrew title as canonical. Records without both
    title_en and year are left alone — too risky to collapse without that
    anchor (a generic English title plus no year may cover different films).
    """
    groups: dict[tuple, list[dict]] = defaultdict(list)
    out: list[dict] = []
    for r in records:
        te = norm_title(r.get("title_en") or "")
        yr = r.get("year")
        if len(te) < 3 or not yr:
            out.append(r)
            continue
        groups[(te, str(yr), r["fund"])].append(r)
    collapsed = 0
    for rs in groups.values():
        if len(rs) == 1:
            out.append(rs[0])
            continue
        titles = [r["title_he"] for r in rs if r.get("title_he")]
        best_he = Counter(titles).most_common(1)[0][0] if titles else rs[0]["title_he"]
        merged = dict(rs[0])
        merged["title_he"] = best_he
        for r in rs:
            if not merged.get("director_he") and r.get("director_he"):
                merged["director_he"] = r.get("director_he")
                merged["director_en"] = r.get("director_en")
            if not merged.get("fund_url") and r.get("fund_url"):
                merged["fund_url"] = r["fund_url"]
        out.append(merged)
        collapsed += len(rs) - 1
    if collapsed:
        print(f"  Collapsed {collapsed} fund records by matching English title + year")
    return out


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=== Enrich movies_db from fund sources ===\n")

    movies, by_title_year, by_title, by_title_en = load_db()
    initial_count = len(movies)
    print(f"Loaded movies_db: {initial_count} films\n")

    # Collect all fund film records
    all_records: list[dict] = []
    for src in FUND_SOURCES:
        recs = extract_from_mentions(src)
        print(f"  {src:25s}: {len(recs)} film records from mentions")
        all_records.extend(recs)

    # Add from flat JSON files
    for path, fund_key in [
        ("data/funds/nfct_films.json",     "nfct"),
        ("data/funds/filmfund_films.json",  "filmfund"),
    ]:
        recs = extract_from_fund_json(path, fund_key)
        print(f"  {fund_key:25s}: +{len(recs)} from {path}")
        all_records.extend(recs)

    print(f"\nTotal raw fund records: {len(all_records)}")

    # Collapse hallucinated-Hebrew duplicates that share (title_en, year, fund)
    all_records = collapse_by_title_en(all_records)

    # Deduplicate records by (title_he, year, fund) before applying
    seen_fund_titles: set[tuple] = set()
    deduped: list[dict] = []
    for r in all_records:
        key = (norm_title(r["title_he"]), str(r.get("year") or ""), r["fund"])
        if key not in seen_fund_titles:
            seen_fund_titles.add(key)
            deduped.append(r)
    print(f"After dedup: {len(deduped)} unique (title, year, fund) combinations\n")

    # Process
    stats = {"enriched": 0, "added": 0, "skipped": 0}
    new_films: list[dict] = []
    _new_film_index:    dict[tuple, dict] = {}   # (nt,yr) → new_entry
    _new_film_by_title: dict[str, dict]   = {}   # nt only → new_entry
    _new_film_by_en_yr: dict[tuple, dict] = {}   # (ne,yr) → new_entry

    for r in deduped:
        title_he    = r["title_he"]
        title_en    = r.get("title_en")
        year        = r.get("year")
        director_he = r.get("director_he")
        director_en = r.get("director_en")
        fund        = r["fund"]
        fund_url    = r.get("fund_url", "")

        idx = find_match(title_he, title_en, year, movies,
                         by_title_year, by_title, by_title_en)

        # Also check if it's already in the new-films queue
        nt_key = norm_title(title_he)
        yr_key = str(year or "")
        ne_key = norm_title(title_en or "")
        existing_new = (
            _new_film_index.get((nt_key, yr_key))
            or _new_film_by_title.get(nt_key)
            or (_new_film_by_en_yr.get((ne_key, yr_key)) if len(ne_key) >= 3 else None)
        )

        if idx is not None:
            # Enrich existing film
            if add_fund(movies[idx], fund, fund_url):
                if title_en and not movies[idx].get("title_en"):
                    movies[idx]["title_en"] = title_en
                stats["enriched"] += 1
        elif existing_new is not None:
            # Add fund to the already-queued new entry
            if add_fund(existing_new, fund, fund_url):
                stats["enriched"] += 1
        else:
            # New film — create entry
            crew = []
            if director_he:
                crew.append({
                    "name_he":     director_he,
                    "name_en":     director_en,
                    "role":        "director",
                    "role_he":     "בימוי",
                    "edb_id":      None,
                    "registry_id": None,
                })

            film_id = make_film_id(fund, f"{title_he}|{year or ''}")
            new_entry = {
                "film_id":             film_id,
                "sources":             [fund],
                "title_he":            title_he,
                "title_en":            title_en,
                "title_alt":           [],
                "title_original":      None,
                "year":                year,
                "release_date_il":     None,
                "is_short":            True,   # fund-only films are typically shorts
                "duration_min":        None,
                "genre":               None,
                "genre_he":            None,
                "tags":                [],
                "based_on":            None,
                "description_he":      None,
                "description_en":      None,
                "country":             ["ישראל"],
                "language":            [],
                "subtitles":           [],
                "color":               None,
                "format":              None,
                "funds":               [fund],
                "production_companies":[],
                "distribution_companies": [],
                "broadcaster":         None,
                "budget":              None,
                "box_office_il":       None,
                "crew":                crew,
                "cast":                [],
                "festivals":           [],
                "awards":              [],
                "related_films":       [],
                "related_interviews":  [],
                "poster_url":          None,
                "trailer_url":         None,
                "watch_url":           None,
                "urls":                {fund: fund_url} if fund_url else {},
            }
            new_films.append(new_entry)
            # Register in a separate new-films index so subsequent records
            # for the same new film can add extra funds without creating duplicates.
            nt = norm_title(title_he)
            yr = str(year or "")
            # Use a sentinel large index; find_match won't hit movies[idx] for these
            # because we only use the sentinel to signal "already queued as new film".
            # We track them in a dedicated dict instead.
            if (nt, yr) not in _new_film_index:
                _new_film_index[(nt, yr)] = new_entry
            if nt not in _new_film_by_title:
                _new_film_by_title[nt] = new_entry
            ne = norm_title(title_en or "")
            if len(ne) >= 3 and (ne, yr) not in _new_film_by_en_yr:
                _new_film_by_en_yr[(ne, yr)] = new_entry
            stats["added"] += 1

    movies.extend(new_films)
    print(f"Results:")
    print(f"  Enriched existing films: {stats['enriched']}")
    print(f"  New films added:         {stats['added']}")
    print(f"  Final total:             {len(movies)}")

    if DRY_RUN:
        print("\n(dry run — nothing written)")
        # Show sample new films
        print("\nSample new films that would be added:")
        for nf in new_films[:20]:
            director = nf['crew'][0]['name_he'] if nf['crew'] else '—'
            print(f"  {nf['title_he']:35s}  {str(nf['year'] or '?'):6s}  "
                  f"fund={nf['funds']}  director={director}")
        return

    # Resolve crew registry IDs against entity_registry
    print("\nResolving crew registry IDs...")
    reg_path = Path("entity_registry.json")
    if reg_path.exists():
        with open(reg_path, encoding="utf-8") as f:
            reg = json.load(f)
        import unicodedata as _ud
        def _norm_name(n):
            if not n: return ""
            n = _ud.normalize("NFKC", n.strip())
            n = re.sub(r'["\'"״׳.,]', "", n)
            n = re.sub(r'[-–—]', " ", n)
            return re.sub(r'\s+', " ", n).strip()
        reg_map = {_norm_name(v.get("canonical_name_he", "")): pid
                   for pid, v in reg.get("people", {}).items()
                   if v.get("canonical_name_he")}
        resolved = 0
        for nf in new_films:
            for person in nf.get("crew", []):
                key = _norm_name(person.get("name_he", ""))
                pid = reg_map.get(key)
                if pid:
                    person["registry_id"] = pid
                    resolved += 1
        print(f"  Resolved {resolved} crew → registry IDs on new films")

    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(movies, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {len(movies)} films to {DB_PATH}")


if __name__ == "__main__":
    main()
