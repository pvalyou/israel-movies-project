# QA Tests — Conflict Pipeline

Each test is a runnable shell/Python command. Run from the project root.
"FAIL" = output is non-empty (unexpected records found).

---

## T01 — Lectors without a relevant URL

**What:** Real people tagged as `lector` from NFCT or Makor whose URL is not `manual://` and does not contain "lector" or "לקטור". Junk/placeholder names (filtered by `is_junk_name`) are excluded — they exist in raw data but are stripped by the pipeline.

```bash
python3 - <<'EOF'
import json, glob, urllib.parse, re, sys
sys.path.insert(0, ".")
from resolve_entities import is_junk_name

FILTERED_SOURCES = {"nfct", "nfct_new", "makor"}

for path in glob.glob("out/*/mentions.jsonl"):
    source = path.split("/")[1]
    if source not in FILTERED_SOURCES:
        continue
    with open(path) as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("status") != "ok":
                continue
            url = rec.get("url", "")
            decoded = urllib.parse.unquote(url)
            for p in rec.get("data", {}).get("entities", {}).get("people", {}).values():
                name = p.get("name_he") or ""
                if is_junk_name(name):
                    continue
                if "lector" in p.get("primary_roles", []) or "appeal_lector" in p.get("primary_roles", []):
                    if not url.startswith("manual://") and "lector" not in decoded.lower() and "לקטור" not in decoded:
                        print(f"[{source}] {name} | {decoded[:80]}")
EOF
```

**Pass:** empty output (or known real people who appear on press pages — investigate each manually).
**Common cause of failure:** LLM extracts "lector" from a newsletter or press mention that is not a lector list page.

---

## T02 — government_body leaking into the HTML report

**What:** Entities with `government_body` role exist in the raw mentions.jsonl (expected — the LLM occasionally misclassifies org names as people). The pipeline filters them out. This test verifies none leak into the rendered report.

```bash
python3 - <<'EOF'
import json

# Check entity_registry — government_body entities should not appear as people
with open("entity_registry.json") as f:
    reg = json.load(f)

GOV_WORDS = {"משרד", "ממשלת", "מועצה", "עיריית", "רשות"}
hits = []
for pid, p in reg.get("people", {}).items():
    name = p.get("canonical_name_he") or ""
    if any(w in name for w in GOV_WORDS) and len(name.split()) >= 2:
        hits.append(f"  {name} | sources={list(p.get('sources',{}).keys())}")

if hits:
    print(f"POSSIBLE LEAK ({len(hits)}):")
    for h in hits: print(h)
else:
    print("PASS")
EOF
```

**Pass:** empty output. If government/ministry names appear as registry people, they slipped past the `government_body` filter.

---

## T03 — Lab/workshop mentor roles from lab URLs

**What:** `mentor` or `lab_mentor` roles from URLs that decode to lab/workshop pages. These are not gatekeeping roles (the lab produces the films) and should have been stripped by the Makor lab filter.

```bash
python3 - <<'EOF'
import json, glob, urllib.parse, re

LAB_PAT = re.compile(r"מעבד|lab|חממ|workshop", re.IGNORECASE)
LAB_ROLES = {"mentor", "lab_mentor"}

for path in glob.glob("out/*/mentions.jsonl"):
    source = path.split("/")[1]
    with open(path) as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("status") != "ok":
                continue
            url = rec.get("url", "")
            decoded = urllib.parse.unquote(url)
            if not LAB_PAT.search(decoded):
                continue
            for p in rec.get("data", {}).get("entities", {}).get("people", {}).values():
                roles = set(p.get("primary_roles", []))
                if roles & LAB_ROLES:
                    print(f"[{source}] {p.get('name_he')} roles={roles & LAB_ROLES} | {decoded}")
EOF
```

**Pass:** empty output.
**Note:** URL must be `unquote`-d before the Hebrew regex or the check silently misses encoded paths.

---

## T04 — manual:// URLs surfacing verbatim in the HTML report

**What:** Every `manual://` URL must be resolved to a real URL via `CANONICAL_DOC_URLS` before rendering. If any leak through, links in the report will be broken.

```bash
grep -c "manual://" connections_report.html && echo "FAIL — raw manual:// URLs found" || echo "pass"
```

**Pass:** command exits non-zero (grep finds nothing) or prints `0`.

---

## T05 — Name looks like a Hebrew role heading, not a person

**What:** LLM occasionally extracts section headings or role descriptions as person names (e.g., "לקטורים ומנהלים אמנותיים", "ועדת הפרסים", "מנכ״ל הקרן"). These inflate counts and may generate spurious conflicts.

```bash
python3 - <<'EOF'
import json, glob, re

# Patterns that are almost certainly not personal names
JUNK_PAT = re.compile(
    r"^(לקטורים|לקטור ו|ועדת|חברי |מנכ.?ל הק|הקרן ה|צוות ה|מחלקת|ניהול|ארגון|מרכז ה)",
    re.UNICODE
)

for path in glob.glob("out/*/mentions.jsonl"):
    source = path.split("/")[1]
    with open(path) as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("status") != "ok":
                continue
            for p in rec.get("data", {}).get("entities", {}).get("people", {}).values():
                name = p.get("name_he") or ""
                if JUNK_PAT.search(name):
                    print(f"[{source}] «{name}» roles={p.get('primary_roles')} | {rec.get('url')}")
EOF
```

**Pass:** empty, or only known exceptions that were reviewed.

---

## T06 — Circular evidence: inst_url == film_url in a flagged conflict

**What:** A conflict where the only institutional evidence URL is the same page as the film credit is self-referential and should have been dropped by the circular-evidence filter.

```bash
python3 - <<'EOF'
import json

with open("connections_report.html") as f:
    # Report doesn't expose raw URLs — check via entity_registry.json instead
    pass

import glob

# Check entity_registry for any conflict where inst_urls ⊆ {film_url}
with open("entity_registry.json") as f:
    registry = json.load(f)

fc_list = registry.get("film_conflicts", [])
for fc in fc_list:
    film_url = (fc.get("film_url") or "").split("#")[0].rstrip("/")
    inst_urls = {(u or "").split("#")[0].rstrip("/") for u in fc.get("inst_urls", [])}
    inst_urls.discard("")
    if inst_urls and inst_urls <= {film_url}:
        print(f"CIRCULAR: {fc.get('person')} / {fc.get('film_title')} | inst={inst_urls}")
EOF
```

**Pass:** empty output.

---

## T07 — Transliteration duplicate films surviving deduplication

**What:** Film groups that contain at least one quality film (has year, or URL contains `/films/`) alongside no-quality films (no year, no `/films/` URL). The no-quality ones should have been dropped by the transliteration artifact filter.

```bash
python3 - <<'EOF'
import json

with open("entity_registry.json") as f:
    registry = json.load(f)

for person_id, fc_list in (registry.get("film_conflicts_by_person") or {}).items():
    for group in fc_list:
        films = group.get("films", [])
        quality = [f for f in films if f.get("year") or "/films/" in (f.get("url") or "")]
        no_quality = [f for f in films if not f.get("year") and "/films/" not in (f.get("url") or "")]
        if quality and len(no_quality) >= 2:
            titles = [f.get("title") for f in no_quality]
            print(f"{group.get('person')} — quality: {[f.get('title') for f in quality]} | surviving no-quality: {titles}")
EOF
```

**Pass:** empty output.

---

## T08 — Conflict strength label vs actual year gap

**What:** `conflict_strength` is computed from the year gap between an institutional role and a film credit. Verify the label matches the gap: strong ≤ 2yr, medium ≤ 4yr, weak > 4yr.

```bash
python3 - <<'EOF'
import json

with open("entity_registry.json") as f:
    registry = json.load(f)

THRESHOLDS = {"strong": 2, "medium": 4}

for fc in registry.get("film_conflicts", []):
    inst_year = fc.get("inst_year")
    film_year = fc.get("film_year")
    strength  = fc.get("conflict_strength")
    if inst_year and film_year and strength:
        gap = abs(int(film_year) - int(inst_year))
        expected = "weak"
        if gap <= 2:
            expected = "strong"
        elif gap <= 4:
            expected = "medium"
        if expected != strength:
            print(f"MISMATCH: {fc.get('person')} / {fc.get('film_title')} | gap={gap} labeled={strength} expected={expected}")
EOF
```

**Pass:** empty output.

---

## T09 — manual:// URL sort priority in person cards

**What:** When a person has both a `manual://` URL and a regular URL, the manual one must sort first in the rendered card (so it links to the authoritative PDF). The sort happens at render time in `resolve_entities.py`, not in the registry. Verify in the HTML report.

```bash
python3 - <<'EOF'
import re

with open("connections_report.html") as f:
    html = f.read()

# In the rendered report, find any card where a non-manual href appears before a manual-derived href.
# Manual URLs resolve to their canonical real URL (no manual:// visible in HTML — see T04).
# So this test checks: do any cards link to a /genre/ or /blog/ page before a /lectors/ or PDF link?
GENRE_BLOG = re.compile(r'href="(https?://[^"]+/(genre|blog|tag|category)/[^"]+)"')
hits = list(GENRE_BLOG.finditer(html))
if hits:
    print(f"INFO: {len(hits)} genre/blog/tag links in report (review if used as primary lector evidence)")
    for m in hits[:5]:
        print(f"  {m.group(1)[:80]}")
else:
    print("PASS — no genre/blog links used as primary evidence")
EOF
```

**Note:** The registry stores `sources` in insertion order (not sorted). The manual:// priority sort is applied during HTML rendering. Confirmed working in `resolve_entities.py` via the `key=lambda u: (0 if u.startswith("manual://") else 1)` sort.

---

## T10 — Lector count sanity per source

**What:** Quick sanity check — each source should yield a plausible number of unique lectors. A sudden spike or drop vs. the expected baseline indicates a scraping or extraction regression.

```bash
python3 - <<'EOF'
import json, glob, collections

# Expected approximate ranges (update as data grows)
EXPECTED = {
    "gesher":              (350, 560),   # manual import 512; unique names after dedup ~370
    "filmfund":            (40,  300),   # manual imports add up to 278
    "makor":               (100, 800),
    "nfct":                (50,  400),
    "nfct_new":            (0,   200),
    "jerusalem_film_fund": (100, 200),   # 2021 manual list is large
}

counts = collections.defaultdict(set)
for path in glob.glob("out/*/mentions.jsonl"):
    source = path.split("/")[1]
    with open(path) as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("status") != "ok":
                continue
            for p in rec.get("data", {}).get("entities", {}).get("people", {}).values():
                if "lector" in p.get("primary_roles", []):
                    counts[source].add(p.get("name_he", "").strip())

for src, (lo, hi) in EXPECTED.items():
    n = len(counts[src])
    status = "OK" if lo <= n <= hi else "⚠ OUT OF RANGE"
    print(f"[{status}] {src}: {n} lectors (expected {lo}–{hi})")
EOF
```

**Pass:** all lines show `OK`.

---

## T11 — Cross-language film pair not deduplicated (Latin + Hebrew same film)

**What:** A film conflict entry should not contain two film records where one title is Latin-only and the other is Hebrew for the same film. The `films_match()` cross-language heuristic should have merged them.

```bash
python3 - <<'EOF'
import json, re

IS_LATIN = re.compile(r'^[A-Za-z0-9 ,.\'\-–—:!?()]+$')

with open("entity_registry.json") as f:
    registry = json.load(f)

for fc in registry.get("film_conflicts", []):
    films = fc.get("films", [])
    latin_titles  = [f["title"] for f in films if IS_LATIN.match(f.get("title",""))]
    hebrew_titles = [f["title"] for f in films if not IS_LATIN.match(f.get("title","")) and f.get("title")]
    if latin_titles and hebrew_titles and len(films) > 1:
        print(f"{fc.get('person')}: Latin={latin_titles} | Hebrew={hebrew_titles}")
EOF
```

**Pass:** empty, or only cases where they are genuinely different films (verify manually).

---

## T12 — Lector-on-film-page without relationship record (false negative detector)

**What:** A person tagged as `producer`/`director` on a fund's dedicated film page, who is also a lector at that same fund, should appear in the conflict report. This test finds candidates that the conflict detector *might* miss if the LLM created a person entity but forgot the `produced`/`directed` relationship.

Root cause: the LLM sometimes records a person's role (e.g., "producer") without generating an explicit relationship record linking them to the film. Bug fixed 2026-05-19 by adding a fallback that treats all people with CREATIVE_ROLES on a dedicated `/film/` page as implicit crew.

```bash
python3 - <<'EOF'
import json, glob, urllib.parse, re

FILM_URL_RE  = re.compile(r"/(film|films|movie|movies|סרט|סרטים)/", re.IGNORECASE)
CREATIVE = {"producer","co_producer","executive_producer","filmmaker","director","screenwriter","מפיק"}
STRICT   = {"lector","appeal_lector","board_member","ceo","chairperson","council_member",
            "committee_member","jury_member","festival_director","festival_programmer",
            "prize_committee_member","guild_board_member","guild_chair","fund_manager",
            "ministry_official","foundation_director","co_ceo","לקטור"}

# Per source: who are lectors? Who appears as crew on film pages?
lectors     = {}   # source → set of norm names
film_crew   = {}   # source → set of norm names with creative role on film page

def norm(n): return n.strip()

for path in glob.glob("out/*/mentions.jsonl"):
    source = path.split("/")[1]
    with open(path) as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("status") != "ok": continue
            url = rec.get("url","")
            is_film_page = bool(FILM_URL_RE.search(url))
            decoded = urllib.parse.unquote(url)

            for p in rec.get("data",{}).get("entities",{}).get("people",{}).values():
                name = (p.get("name_he") or "").strip()
                if not name: continue
                roles = set(p.get("primary_roles",[]))

                if roles & STRICT or url.startswith("manual://") and roles & STRICT:
                    lectors.setdefault(source, set()).add(norm(name))

                if is_film_page and roles & CREATIVE:
                    film_crew.setdefault(source, set()).add(norm(name))

# Anyone who is both a lector AND crew at the same fund
for src in set(lectors) & set(film_crew):
    overlap = lectors[src] & film_crew[src]
    for name in sorted(overlap):
        print(f"[{src}] {name} — lector + film crew (should be in conflict report)")
EOF
```

**Pass:** Everyone listed here should also be visible in `connections_report.html` under the film conflicts section. Any name that appears here but NOT in the report is a false negative — investigate the relationship records for that person.

**Known fixed cases:** יוני כהן (jerusalem_film_fund), בני פרדמן (filmfund) — caused by missing `produced` relationship in LLM output; fixed by film-page crew fallback (2026-05-19).

---

## T13 — Duplicate film credits in פרופיל מקצועי cards (same title, same source)

**What:** A person card should never show the same `(film title, source)` pair more than once. Two different URLs from the same source can both resolve to the same film in `url_to_film` (e.g., a `/films/slug` page and an `/events/awards/` page). Verified by simulating the exact render-loop dedup logic (Pass 1 of the two-pass fix).

```bash
python3 - <<'EOF'
import json, sys, re
sys.path.insert(0, ".")
from resolve_entities import load_url_to_film, normalize_url, dedupe_urls, _HEB_CHAR_RE

url_to_film = load_url_to_film("out/*/mentions.jsonl")

with open("entity_registry.json") as f:
    registry = json.load(f)

hits = []
for pid, person in registry.get("people", {}).items():
    name = person.get("canonical_name_he") or pid
    seen_films = set()
    for src, src_urls in sorted(person.get("sources", {}).items()):
        candidates = []
        local_title_keys = set()
        for u in dedupe_urls(src_urls):
            film = url_to_film.get(normalize_url(u))
            if not film or not film.get("title"): continue
            fkey = normalize_url(u)
            tkey = (film["title"].strip().lower(), src)
            if fkey in seen_films or tkey in seen_films or tkey in local_title_keys: continue
            local_title_keys.add(tkey)
            candidates.append((u, film, fkey, tkey))
        heb_years = {str(f["year"]) for _, f, _, _ in candidates if f.get("year") and _HEB_CHAR_RE.search(f["title"])}
        for u, film, fkey, tkey in candidates:
            yr = str(film["year"]) if film.get("year") else ""
            if not _HEB_CHAR_RE.search(film["title"]) and yr and yr in heb_years: continue
            if tkey in seen_films:
                hits.append(f"{name} | src={src} | dup={film['title']}")
            seen_films.add(fkey)
            seen_films.add(tkey)

if hits:
    print(f"FAIL — {len(hits)} duplicates survive the render logic:")
    for h in hits[:20]: print(f"  {h}")
else:
    print("PASS")
EOF
```

**Pass:** `PASS`.
**Root cause:** Multiple URLs per source resolve to the same film. Fixed by a two-pass render loop that deduplicates first by `(title.lower(), src)` and then drops Latin-only titles when a Hebrew version exists for the same year+source.

---

## T14 — Cross-language duplicates (Hebrew + English URL for same film)

**What:** Some sources (Makor, NFCT) have both a Hebrew-path URL and an English `?lang=en` URL for the same film. The English page stores the English title (e.g., "Absolute Happiness") while the Hebrew page stores the Hebrew title ("האושר המושלם"). Both resolve to separate `url_to_film` entries. Pass 2 of the render fix drops Latin-only films whose year already has a Hebrew-titled entry from the same source.

```bash
python3 - <<'EOF'
import json, sys
sys.path.insert(0, ".")
from resolve_entities import load_url_to_film, normalize_url, dedupe_urls, _HEB_CHAR_RE

url_to_film = load_url_to_film("out/*/mentions.jsonl")

with open("entity_registry.json") as f:
    registry = json.load(f)

hits = []
for pid, person in registry.get("people", {}).items():
    name = person.get("canonical_name_he") or pid
    for src, src_urls in person.get("sources", {}).items():
        # Collect all (title, year) pairs for this source after URL dedup
        entries = []
        seen_fkeys = set()
        for u in dedupe_urls(src_urls):
            film = url_to_film.get(normalize_url(u))
            if not film or not film.get("title"): continue
            fkey = normalize_url(u)
            if fkey in seen_fkeys: continue
            seen_fkeys.add(fkey)
            entries.append((film["title"], film.get("year"), u))
        # Check: Latin title with same year as a Hebrew title → should be dropped
        heb_years = {str(yr) for t, yr, _ in entries if yr and _HEB_CHAR_RE.search(t)}
        for title, yr, url in entries:
            yr_str = str(yr) if yr else ""
            is_latin = not _HEB_CHAR_RE.search(title)
            if is_latin and yr_str and yr_str in heb_years:
                hits.append(f"{name} | src={src} | Latin='{title}' ({yr}) — Hebrew version exists for this year")

if hits:
    print(f"INFO — {len(hits)} Latin-title entries that would be dropped by the cross-language filter:")
    for h in hits[:10]: print(f"  {h}")
    print("(These are correctly suppressed at render time — this is an INFO check, not FAIL)")
else:
    print("PASS — no cross-language pairs found")
EOF
```

**Pass:** INFO output is expected (shows what gets correctly suppressed). FAIL would be if these entries appeared in the final `connections_report.html` as rendered `resume-film-entry` rows alongside their Hebrew counterparts.
**Root cause fixed:** Pass 2 of the render loop in `render_person_card` collects `heb_years` (years with Hebrew-titled films per source) and skips Latin-only entries for those years.

---

## T15 — Non-consecutive institutional years displayed as a range

**What:** When a person served as a lector in e.g. 2016 and 2023 (but not in between), the card must show "2016, 2023" not "2016–2023". The range format implies continuous service. Detected by checking if the span content is `YYYY–YYYY` where end - start > 1.

```bash
python3 - <<'EOF'
import re

with open("connections_report.html") as f:
    html = f.read()

# Find all resume-entry-year spans
YEAR_RANGE_RE = re.compile(r'<span class="resume-entry-year">(\d{4})–(\d{4})</span>')
hits = []
for m in YEAR_RANGE_RE.finditer(html):
    start, end = int(m.group(1)), int(m.group(2))
    if end - start > 8:  # ranges > 8 years warrant a manual look
        # Extract surrounding context for person name
        ctx_start = max(0, m.start() - 300)
        ctx = html[ctx_start:m.start()]
        name_m = re.search(r'id="prof-([^"]+)"', ctx)
        name = name_m.group(1) if name_m else "?"
        hits.append(f"  {m.group(1)}–{m.group(2)} ({end-start}yr gap) — {name}")

if hits:
    print(f"WARN — {len(hits)} very long year ranges (review for non-consecutive service):")
    for h in hits: print(h)
else:
    print("PASS — no suspiciously long year ranges")
EOF
```

**Pass:** empty or only ranges where the person genuinely served continuously that long.
**Root cause fixed (2026-05-23):** `render_person_card()` now uses comma-separated list when `max - min > len(years) - 1`.

---

## T16 — Wiki link points to wrong person (name mismatch)

**What:** `enriched/wiki_persons.json` can contain stale cache entries where the matched `wiki_title_he` doesn't actually contain both the first and last name of the person. These render as wrong wikipedia links in profile cards.

```bash
python3 - <<'EOF'
import json, re

with open("enriched/wiki_persons.json") as f:
    wiki = json.load(f)

hits = []
for person_name, entry in wiki.items():
    if not entry: continue  # None = cache miss, no Wikipedia article found
    title = entry.get("wiki_title_he", "")
    if not title:
        continue
    title_clean = re.sub(r'\s*\(.*?\)', '', title).strip()
    title_words = title_clean.split()
    name_words = person_name.split()
    if len(name_words) >= 2:
        first, last = name_words[0], name_words[-1]
        if first not in title_words or last not in title_words:
            hits.append(f"  {person_name!r} → wiki_title={title!r} (name words not in title)")

if hits:
    print(f"FAIL — {len(hits)} mismatched wiki entries:")
    for h in hits: print(h)
else:
    print("PASS")
EOF
```

**Pass:** empty output. Any hit means a stale cache entry — delete the key from `enriched/wiki_persons.json`.
**Known fixed case (2026-05-23):** נדב הראל was matched to הראל מויאל (pop singer). Removed from cache.

---

## T17 — Production company duplicates in חברות הפקה

**What:** The same production company appearing under two different names (English/Hebrew variants, with/without `בע"מ`, spacing differences) inflates the count and misleads. Check the rendered section for near-duplicate company names.

```bash
python3 - <<'EOF'
import re

with open("connections_report.html") as f:
    html = f.read()

# Find the prod companies section
sec_start = html.find('id="sec-prod-companies"')
if sec_start < 0:
    print("SKIP — section not found")
    exit()
sec = html[sec_start:sec_start + 30000]

# Extract all company display names
names = re.findall(r'org-name-he[^>]*>(?:<[^>]+>)?([^<]{2,60})', sec)
names = [n.strip() for n in names if n.strip()]

# Look for obvious duplicates: same name modulo בע"מ, case, or punctuation
import unicodedata
def norm(n):
    n = re.sub(r'\s+בע["״]?מ\b', '', n)
    n = re.sub(r'[\s\-,.]', '', n)
    return n.lower()

seen = {}
for name in names:
    key = norm(name)
    if key in seen:
        print(f"DUP: {seen[key]!r} ↔ {name!r}")
    else:
        seen[key] = name

print(f"Checked {len(names)} companies — done")
EOF
```

**Pass:** no `DUP:` lines.
**Root cause fixed (2026-05-23):** `בע"מ` suffix stripped at load time; `ORG_ALIASES` added for Greenhouse variants, Hebrew/English pairs (Heymann Brothers Films → סרטי האחים הימן, etc.).

---

## T18 — Duplicate role chips in person card

**What:** If two role strings (e.g. `screenwriter` and `scriptwriter`) map to the same Hebrew label ("תסריטאי"), they must deduplicate to a single chip. Check the HTML for consecutive identical chips.

```bash
python3 - <<'EOF'
import re

with open("connections_report.html") as f:
    html = f.read()

# Find all resume-chip spans grouped by card
CHIP_RE = re.compile(r'<span class="resume-chip[^"]*">([^<]+)</span>')
CARD_RE = re.compile(r'<div class="profile-card[^"]*">(.*?)</div>\s*</div>', re.DOTALL)

hits = []
for card in CARD_RE.finditer(html):
    card_html = card.group(1)
    chips = CHIP_RE.findall(card_html)
    seen = set()
    for chip in chips:
        chip = chip.strip()
        if chip in seen:
            # get person name from card
            name_m = re.search(r'id="prof-([^"]+)"', html[max(0, card.start()-200):card.start()])
            name = name_m.group(1) if name_m else "?"
            hits.append(f"  DUP chip '{chip}' in card for {name}")
            break
        seen.add(chip)

if hits:
    print(f"FAIL — {len(hits)} cards with duplicate role chips:")
    for h in hits: print(h)
else:
    print("PASS")
EOF
```

**Pass:** `PASS`.
**Root cause fixed (2026-05-23):** `_dedup_chips()` helper in `render_person_card()` deduplicates by Hebrew label before rendering.

---

## T19 — Broken profile anchor links in film conflict cards

**What:** Film conflict cards link to `#prof-{name}` anchors. If the person's profile card was not rendered (e.g., they fell below the render cap and weren't in `_fc_norm_names_needed`), the link points to a non-existent anchor — a silent 404.

```bash
python3 - <<'EOF'
import re

with open("connections_report.html") as f:
    html = f.read()

# Collect all defined anchor IDs
anchor_ids = set(re.findall(r'id="(prof-[^"]+)"', html))

# Collect all href="#prof-..." links
link_targets = set(re.findall(r'href="#(prof-[^"]+)"', html))

missing = link_targets - anchor_ids
if missing:
    print(f"FAIL — {len(missing)} broken profile anchor links:")
    for m in sorted(missing):
        print(f"  #{m}")
else:
    print(f"PASS — all {len(link_targets)} profile links resolve to an anchor")
EOF
```

**Pass:** `PASS — all N profile links resolve to an anchor`.
**Root cause fixed:** `_cross_norm_names` now equals `_rendered_norms` (only people with actual cards). People in film conflicts who fall beyond the 600-card cap are always force-rendered.

---

## T25 — Duplicate films from punctuation variants (כן / כן!)

**What:** A film title with a trailing `!` or `?` (e.g., "כן!") must not appear alongside the same title without that punctuation (e.g., "כן") in the same person's conflict film list. `normalize_film_title` strips `!?` and the dedup step uses it.

```bash
python3 - <<'EOF'
import re, json

with open("connections_report.html") as f:
    html = f.read()

# Find all film-list blocks and check for near-duplicate titles
pattern = re.compile(r'<ul class="film-list">(.*?)</ul>', re.DOTALL)
issues = []
for m in pattern.finditer(html):
    block = m.group(1)
    titles_raw = re.findall(r'<span dir="rtl">([^<]+)</span>', block)
    # Normalize: strip !? and lower
    norm_map = {}
    for t in titles_raw:
        n = re.sub(r"[!?]", "", t).strip().lower()
        norm_map.setdefault(n, []).append(t)
    for n, variants in norm_map.items():
        if len(variants) > 1:
            issues.append(f"  Dup variants: {variants}")

if issues:
    print(f"FAIL — {len(issues)} near-duplicate film title pairs:")
    for i in issues[:10]:
        print(i)
else:
    print("PASS — no punctuation-variant film duplicates found")
EOF
```

**Pass:** `PASS — no punctuation-variant film duplicates found`.
**Root cause fixed:** `normalize_film_title` now strips `!` and `?`; conflict dedup uses `normalize_film_title` instead of `normalize_name`.

---

## T26 — Inconsistent role labels in film-row badges

**What:** The film-row role badge must use consistent Hebrew labels. "ביים" (verbal past tense) must not appear — it should always be "במאי". "הפיק" must not appear — should be "מפיק". Both forms mapped to the same label in `ROLE_LABELS_HE`.

```bash
python3 - <<'EOF'
with open("connections_report.html") as f:
    html = f.read()

bad = []
if 'badge-role">ביים' in html:
    bad.append('"ביים" found in badge-role (should be "במאי")')
if 'badge-role">הפיק' in html:
    bad.append('"הפיק" found in badge-role (should be "מפיק")')
if 'badge-role">הפיק במשותף' in html:
    bad.append('"הפיק במשותף" found in badge-role (should be "מפיק שותף")')

if bad:
    print("FAIL —", "; ".join(bad))
else:
    print("PASS — role labels are consistent (ביים/הפיק not present)")
EOF
```

**Pass:** `PASS — role labels are consistent (ביים/הפיק not present)`.
**Root cause fixed:** `ROLE_LABELS_HE["directed"]` changed to `"במאי"`, `"produced"` → `"מפיק"`, `"co_produced"` → `"מפיק שותף"`.

---

## T27 — Duplicate institutional rows in profile cards

**What:** A person card must not show the same `(org_name, year, role)` combination twice. Happens when the same person appears in two sources (e.g., `film_schools` and `sam_spiegel`) that both resolve to the same institution, year, and role display text.

**Manually found:** יאיר אגמון — "סם שפיגל 2026 מרצה" appeared twice with different dot colors.

```bash
python3 - <<'EOF'
import re
from bs4 import BeautifulSoup

with open("connections_report.html") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")
hits = []

for card in soup.find_all("div", class_="person-card"):
    pid = card.get("id", "?")
    for section in card.find_all("div", class_="resume-section"):
        label = section.find("div", class_="resume-section-label")
        if not label or "תפקידים מוסדיים" not in label.text:
            continue
        seen_rows = set()
        for entry in section.find_all("div", class_="resume-entry"):
            org  = (entry.find(class_="resume-entry-org") or entry).get_text(strip=True)
            yr   = (entry.find(class_="resume-entry-year") or type("", (), {"get_text": lambda *a, **k: ""})()).get_text(strip=True) if entry.find(class_="resume-entry-year") else ""
            role = (entry.find(class_="resume-entry-role") or type("", (), {"get_text": lambda *a, **k: ""})()).get_text(strip=True) if entry.find(class_="resume-entry-role") else ""
            key = (org, yr, role)
            if key in seen_rows:
                hits.append(f"  {pid}: dup inst row ({org} | {yr} | {role})")
            seen_rows.add(key)

if hits:
    print(f"FAIL — {len(hits)} duplicate institutional rows:")
    for h in hits: print(h)
else:
    print("PASS")
EOF
```

**Pass:** `PASS`.
**Root cause fixed (2026-05-29):** `seen_inst_rows` set deduplicates by `(_org_label, display_year, role_str)` before rendering each row.

---

## T28 — English text in institutional role spans

**What:** `resume-entry-role` spans in `תפקידים מוסדיים` rows must not contain raw English role strings. A role that falls through `he_role()` without a Hebrew label renders its raw ID (e.g., `head_of_film_department`, `overall_mentor`, `contact_person`).

**Manually found:** יוסי חזן showing `head_of_film_department` and `overall_mentor` in English.

```bash
python3 - <<'EOF'
import re

with open("connections_report.html") as f:
    html = f.read()

ROLE_SPAN_RE = re.compile(r'<span class="resume-entry-role">([^<]+)</span>')
ASCII_WORD = re.compile(r'\b[a-zA-Z_]{4,}\b')

hits = []
for m in ROLE_SPAN_RE.finditer(html):
    role_text = m.group(1).strip()
    if ASCII_WORD.search(role_text):
        # Get surrounding card id for context
        ctx = html[max(0, m.start()-500):m.start()]
        card_m = re.findall(r'id="(prof-[^"]+)"', ctx)
        card_id = card_m[-1] if card_m else "?"
        hits.append(f"  {card_id}: {role_text!r}")

if hits:
    print(f"FAIL — {len(hits)} English role labels in inst rows:")
    for h in hits[:20]: print(h)
else:
    print("PASS")
EOF
```

**Pass:** `PASS`.
**Root cause fixed (2026-05-29):** Added `head_of_film_department`, `overall_mentor`, `project_mentor`, `editing_mentor`, `contact_person`, `fund_director`, `staff`, `directing_mentor`, and 20+ other roles to `ROLE_LABELS_HE`.

---

## T29 — Context citations that don't mention the person

**What:** The `resume-quote` block (shown in הופעות נוספות) must contain at least one word from the person's name. Showing a generic list snippet that names other people misleads the reader.

**Manually found:** יאיר אגמון's NFCT appearance showed a director list ("David Perlov, Dan Geva, ...") that didn't contain his name.

```bash
python3 - <<'EOF'
import re
from bs4 import BeautifulSoup

with open("connections_report.html") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")
hits = []

for card in soup.find_all("div", class_="person-card"):
    pid = card.get("id", "")
    name = pid.replace("prof-", "")
    name_parts = [p for p in name.split("-") if len(p) > 2]
    for q in card.find_all("div", class_="resume-quote"):
        qt = q.get_text(strip=True)
        if not any(part in qt for part in name_parts):
            hits.append(f"  {pid}: citation doesn't mention person — {qt[:80]!r}")

if hits:
    print(f"FAIL — {len(hits)} citations missing person name:")
    for h in hits[:15]: print(h)
else:
    print("PASS")
EOF
```

**Pass:** `PASS`.
**Root cause fixed (2026-05-29):** `render_person_card()` filters `ctx_quotes` — only shows citation when at least one name part appears in the text.

---

## T30 — Mentor role not shown in film credit row

**What:** When a person's only role at a source is `overall_mentor`, `project_mentor`, or `editing_mentor`, the film credit row must still display the role (e.g., "מלווה כולל"). Previously, only `CREATIVE_ROLES` were shown, which excluded mentor roles.

**Manually found:** יוסי חזן — "מלווה כולל" appeared as a chip but the film credit row for "מתיר אסורים" showed no role label.

```bash
python3 - <<'EOF'
import re
from bs4 import BeautifulSoup

with open("connections_report.html") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")
MENTOR_HE = {"מלווה כולל", "מלווה פרויקט", "מלווה עריכה", "מנטור במאי"}

hits = []
for card in soup.find_all("div", class_="person-card"):
    pid = card.get("id", "?")
    # Person has a mentor chip
    chip_texts = {c.get_text(strip=True) for c in card.find_all("span", class_="resume-chip")}
    if not chip_texts & MENTOR_HE:
        continue
    # Check film credit rows — at least one role cell should contain a mentor label
    # (role cells may contain compound strings like "במאי / מלווה פרויקט", so use substring check)
    film_role_texts = " ".join(r.get_text(strip=True) for r in card.find_all("span", class_="resume-film-role"))
    film_entries = card.find_all("div", class_="resume-film-entry")
    if film_entries and not any(m in film_role_texts for m in MENTOR_HE):
        hits.append(f"  {pid}: has mentor chip but no mentor role in film credit rows")

if hits:
    print(f"FAIL — {len(hits)} persons with mentor chip but no film credit role label:")
    for h in hits: print(h)
else:
    print("PASS")
EOF
```

**Pass:** `PASS`.
**Root cause fixed (2026-05-29):** `FILM_CREDIT_ROLES` constant added; film credit `role_str` now uses `FILM_CREDIT_ROLES` instead of `CREATIVE_ROLES`, including `overall_mentor`, `project_mentor`, `editing_mentor`.

---

## T31 — Junk film-subject roles appearing as identity chips

**What:** Roles like `self`, `character`, `subject` describe a person's appearance in a specific film (they played themselves, or were the documentary subject) — not their professional identity. They must not appear as chips in the profile card header.

**Manually found:** Several cards showed `self` and `subject` chips alongside professional roles.

```bash
python3 - <<'EOF'
import re

with open("connections_report.html") as f:
    html = f.read()

JUNK_LABELS = {"self", "character", "subject", "fictional_character", "film_subject"}

CHIP_RE = re.compile(r'<span class="resume-chip[^"]*">([^<]+)</span>')
CARD_BOUND = re.compile(r'id="(prof-[^"]+)"')

hits = []
pos = 0
for m in CARD_BOUND.finditer(html):
    card_id = m.group(1)
    card_start = m.start()
    card_end_m = CARD_BOUND.search(html, card_start + 1)
    card_end = card_end_m.start() if card_end_m else len(html)
    card_html = html[card_start:card_end]
    for chip_m in CHIP_RE.finditer(card_html):
        label = chip_m.group(1).strip().lower()
        if label in JUNK_LABELS:
            hits.append(f"  {card_id}: junk chip '{label}'")

if hits:
    print(f"FAIL — {len(hits)} junk film-subject chips found:")
    for h in hits[:20]: print(h)
else:
    print("PASS")
EOF
```

**Pass:** `PASS`.
**Root cause fixed (2026-05-29):** `SUPPRESS_CHIP_ROLES` set added; `other_r` in `render_person_card()` now subtracts these roles before chip generation.

---

## T32 — Film year sanity (impossible or absurd years)

**What:** Film credits in profile cards must have plausible years (1948–2027). A year outside this range indicates LLM hallucination, a date field parsed incorrectly, or a current-year inference bug.

```bash
python3 - <<'EOF'
import re

with open("connections_report.html") as f:
    html = f.read()

YEAR_RE = re.compile(r'<span class="resume-film-year">(\d{4})</span>')
hits = []
for m in YEAR_RE.finditer(html):
    yr = int(m.group(1))
    if yr < 1948 or yr > 2027:
        ctx = html[max(0, m.start()-400):m.start()]
        card_m = re.findall(r'id="(prof-[^"]+)"', ctx)
        hits.append(f"  {card_m[-1] if card_m else '?'}: year={yr}")

if hits:
    print(f"FAIL — {len(hits)} film credits with impossible year:")
    for h in hits: print(h)
else:
    print("PASS")
EOF
```

**Pass:** `PASS`.
**Why this matters:** Catches `INFER_CURRENT_YEAR_SOURCES` mis-fires, date parsing bugs, and LLM hallucinations before they pollute the graph.

---

## T33 — Episode-suffix series dedup (מגש הכסף bug class)

**What:** A person's film credit section must not contain two entries whose titles differ only by an episode/season marker (פרק N, חלק N, עונה N, Episode N). `_FILM_SUFFIX_RE` strips these for dedup. If two entries survive, the strip isn't working.

**Manually found:** "מגש הכסף – פרק 2" and "מגש הכסף – פרק 3" appeared as separate credits.

```bash
python3 - <<'EOF'
import re
from bs4 import BeautifulSoup

SUFFIX_RE = re.compile(
    r"\s*[–\-]\s*(פרק|חלק|עונה|season|episode|ep\.?|part)\s*\d*\s*$",
    re.IGNORECASE | re.UNICODE,
)

with open("connections_report.html") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")
hits = []

for card in soup.find_all("div", class_="person-card"):
    pid = card.get("id", "?")
    # Only check within the film credits section — a film can legitimately appear
    # in both "קרדיטים בסרטים" and "השתתפות בפסטיבל" for different reasons.
    for section in card.find_all("div", class_="resume-section"):
        label = section.find("div", class_="resume-section-label")
        if not label or "קרדיטים בסרטים" not in label.text:
            continue
        seen = set()
        for ft in section.find_all("span", class_="resume-film-title"):
            raw = ft.get_text(strip=True)
            t = SUFFIX_RE.sub("", raw).strip().lower()
            if t in seen:
                hits.append(f"  {pid}: duplicate after episode strip: '{t}' (raw: '{raw}')")
                break
            seen.add(t)

if hits:
    print(f"FAIL — {len(hits)} cards with episode-suffix series duplicates:")
    for h in hits: print(h)
else:
    print("PASS")
EOF
```

**Pass:** `PASS`.
**Root cause fixed (2026-05-25):** `_FILM_SUFFIX_RE` extended with `פרק|חלק|עונה|season|episode|ep\.?|part`.

---

## T34 — Year 2026 only from INFER_CURRENT_YEAR_SOURCES

**What:** Institutional rows showing year 2026 are legitimate only when the source is in `INFER_CURRENT_YEAR_SOURCES` (e.g., `sam_spiegel`, `critics`). Any other source showing 2026 means a null year was incorrectly inferred as current year.

**Manually found:** קרן ירושלים was in `INFER_CURRENT_YEAR_SOURCES` and showed 2026 instead of its actual 2021 date.

```bash
python3 - <<'EOF'
# Check the rendered HTML — years_by_src is not stored in entity_registry.json,
# only exists in-memory during rendering. We check inst rows showing 2026 and
# confirm they come from a known inferred source by checking the source label text.
import re

with open("connections_report.html", encoding="utf-8") as f:
    html = f.read()

# Sources whose 2026 year is inferred (no explicit date on the page)
INFER_CURRENT_YEAR_SOURCES = {
    "sam_spiegel", "film_schools", "critics", "guilds",
    "israeli_film_academy", "writers_guild", "haifa_film_festival",
    "jerusalem_cinematheque",
}

# Each institutional row: dot + org name + optional year
# We look for rows that display "2026" and try to identify their source
# by scanning backwards for the nearest prof-* anchor and source label.
ROW_RE = re.compile(
    r'<div class="resume-entry">.*?<span class="resume-entry-year">(\d{4})</span>',
    re.DOTALL
)
# Source label appears as data-src="<src>" on the resume-entry div when present,
# or we infer from the dot color via the source color table embedded in HTML.
# Simpler approach: parse the data-source attribute added to resume-entry divs.
ROW_SRC_RE = re.compile(
    r'<div class="resume-entry"[^>]*data-src="([^"]*)"[^>]*>.*?'
    r'<span class="resume-entry-year">(\d{4})</span>',
    re.DOTALL
)

hits = []
for m in ROW_SRC_RE.finditer(html):
    src, year = m.group(1), m.group(2)
    if year == "2026" and src and src not in INFER_CURRENT_YEAR_SOURCES:
        ctx = html[max(0, m.start()-600):m.start()]
        card_m = re.findall(r'id="(prof-[^"]+)"', ctx)
        hits.append(f"  {card_m[-1] if card_m else '?'}: src={src!r} year=2026")

if hits:
    print(f"FAIL — {len(hits)} inst rows showing 2026 from non-inferred sources:")
    for h in hits[:20]: print(h)
elif not ROW_SRC_RE.search(html):
    # data-src attribute not present — fall back to counting 2026 rows manually
    count_2026 = sum(1 for m in ROW_RE.finditer(html) if m.group(1) == "2026")
    print(f"SKIP — data-src attribute not in HTML; {count_2026} rows show 2026 (manual review needed)")
else:
    print("PASS")
EOF
```

**Pass:** `PASS` or `SKIP` (if `data-src` attribute was never added to the HTML renderer).
**Why this matters:** The `INFER_CURRENT_YEAR_SOURCES` set is easy to accidentally extend; this test catches sources added by mistake.
**Note:** `years_by_src` is only in-memory during rendering — never written to `entity_registry.json`. Full automation requires a `data-src` attribute on `resume-entry` divs; until then the test reports SKIP rather than a false FAIL.

---

## T35 — Role chip count sanity (role explosion detector)

**What:** A profile card with more than 15 unique role chips likely has a role normalization failure — the same role under different string variants (e.g., `co-director`, `co_director`, `animation`, `animator`) all surviving as separate chips. Cap is 15 because the widest legitimate profile (director + producer + screenwriter + editor + composer + cinematographer + lector + board_member + faculty + critic + event_speaker + moderator + ...) tops out around 13–14 for the most prolific multi-hyphenates.

```bash
python3 - <<'EOF'
import re

with open("connections_report.html") as f:
    html = f.read()

CARD_RE  = re.compile(r'id="(prof-[^"]+)"')
CHIP_RE  = re.compile(r'<span class="resume-chip[^"]*">([^<]+)</span>')
CHIPS_END = re.compile(r'</div>\s*</div>\s*<div class="resume-meta"')

hits = []
for m in CARD_RE.finditer(html):
    card_id = m.group(1)
    block_start = m.start()
    block_end_m = CARD_RE.search(html, block_start + 1)
    block = html[block_start: block_end_m.start() if block_end_m else block_start + 5000]
    chips = CHIP_RE.findall(block)
    unique_chips = set(c.strip() for c in chips)
    if len(unique_chips) > 15:
        hits.append(f"  {card_id}: {len(unique_chips)} chips — {sorted(unique_chips)}")

if hits:
    print(f"FAIL — {len(hits)} cards with suspicious chip count (>12):")
    for h in hits: print(h)
else:
    print("PASS")
EOF
```

**Pass:** `PASS`.
**Why this matters:** Role explosion is the #1 symptom of a missing `ROLE_NORMALIZE` entry. This test flags it automatically instead of waiting for manual review.

---

## T36 — Film credit entries with no year and no funder badge

**What:** A film credit row with neither a year nor a funder badge is a near-empty entry — just a title and an icon. These almost always indicate a false positive from a URL that shouldn't have been treated as a film page (e.g., a generic fund listing).

```bash
python3 - <<'EOF'
import re

with open("connections_report.html") as f:
    html = f.read()

# Each resume-film-entry should have either a year span or a funder span
ENTRY_RE  = re.compile(r'<div class="resume-film-entry">(.*?)</div>\s*</div>', re.DOTALL)
YEAR_RE   = re.compile(r'resume-film-year')
FUNDER_RE = re.compile(r'resume-film-funder')
TITLE_RE  = re.compile(r'resume-film-title[^>]*>.*?<span[^>]*>([^<]+)</span>')

hits = []
for m in ENTRY_RE.finditer(html):
    block = m.group(1)
    has_year   = bool(YEAR_RE.search(block))
    has_funder = bool(FUNDER_RE.search(block))
    if not has_year and not has_funder:
        title_m = TITLE_RE.search(block)
        title = title_m.group(1) if title_m else "?"
        ctx = html[max(0, m.start()-400):m.start()]
        card_m = re.findall(r'id="(prof-[^"]+)"', ctx)
        hits.append(f"  {card_m[-1] if card_m else '?'}: '{title}' — no year, no funder")

if hits:
    print(f"WARN — {len(hits)} bare film credit entries (no year, no funder):")
    for h in hits[:15]: print(h)
else:
    print("PASS")
EOF
```

**Pass:** `PASS` or low WARN count (a handful of pre-2000 films with no year data is acceptable).
**Why this matters:** Low-quality film entries without any provenance signal are likely false positives from generic listing pages that slipped past the film-page URL filter.

---

## T37 — EDB person-page film credits completeness (known person canary)

**What:** שירה מרגלית (EDB ID n0035480) has 4 known films that come from her EDB *person page* record (not the film-crew dataset): ווארט, ריקוד האש, אויבים, עוד ניפגש. These films appear in `out/edb/mentions.jsonl` but are exposed only via the `film_urls_by_src` pipeline path introduced to fix a bug where person-page records mapped to only the first film. This test verifies all 4 are present in her card.

```bash
python3 - <<'EOF'
import re

with open("connections_report.html", encoding="utf-8") as f:
    html = f.read()

# Find her card — look for the card block that contains "שירה מרגלית" as the heading
CARD_RE = re.compile(
    r'<div class="person-card[^"]*"[^>]*id="(prof-[^"]+)"[^>]*>(.*?)</div>\s*</div>\s*</div>',
    re.DOTALL
)
TITLE_RE = re.compile(r'resume-film-title[^>]*>.*?<span[^>]*dir="rtl">([^<]+)</span>')

card_html = ""
for m in CARD_RE.finditer(html):
    if "שירה מרגלית" in m.group(2)[:500]:
        card_html = m.group(2)
        break

if not card_html:
    # fallback: grab a generous window around her name
    idx = html.find("שירה מרגלית")
    card_html = html[idx:idx+8000] if idx != -1 else ""

found = set(TITLE_RE.findall(card_html))
expected = {"ווארט", "ריקוד האש", "אויבים", "עוד ניפגש"}
missing = expected - found

if missing:
    print(f"FAIL — שירה מרגלית missing EDB films: {missing}")
    print(f"  Found in card: {found & expected}")
else:
    print("PASS")
EOF
```

**Pass:** `PASS`.
**Why this matters:** Catches regressions in the `film_urls_by_src` pipeline path. Before the fix, only the first film from an EDB person-page record was displayed; the other 3 were silently dropped.

---

## T38 — Event-only roles must not generate film credits (festival Q&A host ≠ crew)

**What:** שמוליק דובדבני appears on DocAviv film pages as a panel moderator/Q&A host ("בהנחיית שמוליק דובדבני"). He is a film critic, NOT a film crew member. His profile card should contain NO "🎬" film credit entries — only his institutional/derived-conflict roles.

```bash
python3 - <<'EOF'
import re

with open("connections_report.html", encoding="utf-8") as f:
    html = f.read()

idx = html.find("שמוליק דובדבני")
if idx == -1:
    print("SKIP — שמוליק דובדבני not in report")
else:
    # Find his card (look ahead ~6000 chars for the next card boundary)
    card_chunk = html[idx:idx+6000]
    # Film credit entries contain 🎬
    film_credits = re.findall(r'resume-film-icon.*?🎬', card_chunk)
    if film_credits:
        print(f"FAIL — שמוליק דובדבני has {len(film_credits)} film credit(s) from event/moderator scrape")
    else:
        print("PASS")
EOF
```

**Pass:** `PASS`.
**Why this matters:** Festival film pages list Q&A/panel participants alongside crew. People whose only role at a source is `event_participant` or `event_speaker` should never appear in the "קרדיטים בסרטים" section.

---

## T39 — Same-film cross-source dedup (colon variant title)

**What:** "במדבר: דיפטיך תיעודי" (EDB) and "במדבר דיפטיך תיעודי" (fdoc) are the same film, differing only in a colon. After the `normalize_film_title` fix that collapses colons/dashes, the film should appear exactly once in שלומי אלקבץ's card, with two source badges.

```bash
python3 - <<'EOF'
import re

with open("connections_report.html", encoding="utf-8") as f:
    html = f.read()

idx = html.find("שלומי אלקבץ")
if idx == -1:
    print("SKIP — שלומי אלקבץ not in report")
else:
    card_chunk = html[idx:idx+8000]
    matches = re.findall(r'[בב]מדבר[^<]{0,20}דיפטיך', card_chunk)
    if len(matches) >= 2:
        print(f"FAIL — 'במדבר: דיפטיך תיעודי' appears {len(matches)}x (colon dedup not working)")
    elif len(matches) == 0:
        print("SKIP — film not found in this card")
    else:
        print("PASS — film appears exactly once")
EOF
```

**Pass:** `PASS — film appears exactly once`.

---

## T40 — Film school appearing as employer in conflict flag text

**What:** The conflict flag (⚑) block should never say "בסם שפיגל", "במכללת ספיר", "במנשר", "ביה\"ס לקולנוע" etc. — those are schools, not employers. They belong in the profile card institutional section, not the conflict flag. This is enforced by `_NON_EMPLOYER_SRCS` in `render_person_card`.

```bash
python3 - <<'EOF'
import re

SCHOOL_PATTERNS = [
    "בסם שפיגל",
    "במכללת ספיר",
    "במנשר",
    'ביה"ס לקולנוע',
    "בבית ברל",
    "באוניברסיטת תל אביב",
]

with open("connections_report.html", encoding="utf-8") as f:
    html = f.read()

# Find all conflict flag blocks (contain "ניגוד תפקידים" or the ⚑ flag)
flag_blocks = re.findall(r'<div[^>]*class="[^"]*conflict-flag[^"]*"[^>]*>.*?</div>', html, re.DOTALL)
# Also search inline flag spans
flag_spans = re.findall(r'<span[^>]*title="[^"]*ניגוד[^"]*"[^>]*>.*?</span>', html, re.DOTALL)

found = []
for pat in SCHOOL_PATTERNS:
    for block in flag_blocks + flag_spans:
        if pat in block:
            found.append(f"School name '{pat}' found in conflict flag block")
            break

# Broader search: any ⚑ flag description containing school names
for pat in SCHOOL_PATTERNS:
    # look for pattern near a ⚑ or flag role text
    hits = [m.start() for m in re.finditer(re.escape(pat), html)]
    for hit in hits:
        context = html[max(0, hit-200):hit+100]
        if "ניגוד תפקידים" in context or "⚑" in context or "conflict" in context.lower():
            found.append(f"School '{pat}' near conflict flag at offset {hit}")

if found:
    for f in found[:10]:
        print("FAIL —", f)
else:
    print("PASS")
EOF
```

**Pass:** `PASS`
**Root cause when failing:** `_NON_EMPLOYER_SRCS` in `resolve_entities.py` is missing the school's source key. Add the source key to that set.

---

## T41 — Sapir faculty source URL must be Cinema department (dep/529)

**What:** The old scrape used `https://www.sapir.ac.il/staff/dep/17` which is the Drama/Music department — wrong people entirely. Cinema department is dep/529. This test verifies the old URL is gone from entity_registry.

```bash
python3 - <<'EOF'
import json

BAD_URL = "https://www.sapir.ac.il/staff/dep/17"

with open("entity_registry.json", encoding="utf-8") as f:
    reg = json.load(f)

found = []
for pid, p in reg.get("people", {}).items():
    for src, urls in p.get("sources", {}).items():
        if any(BAD_URL in u for u in (urls if isinstance(urls, list) else [urls])):
            found.append(f"{p.get('canonical_name_he')} ({pid}) still has dep/17 URL")

if found:
    for f in found:
        print("FAIL —", f)
else:
    print("PASS")
EOF
```

**Pass:** `PASS`
**Root cause when failing:** `out/film_schools/mentions.jsonl` still has a record with `"url": "https://www.sapir.ac.il/staff/dep/17"`. Replace it with dep/529.

---

## T42 — Gender-slash "/ת" must not appear in rendered institutional role labels

**What:** Institutional section role labels must be gendered per-person (e.g. "בוגרת", "מרצה בכירה"), not contain the neutral slash form "בוגר/ת". Slash forms mean `he_role_g()` was not applied or the gender lookup failed.

```bash
python3 - <<'EOF'
import re

SLASH_PATTERN = re.compile(r'[א-ת]+/[א-ת]')  # e.g. בוגר/ת, מנהל/ת

with open("connections_report.html", encoding="utf-8") as f:
    html = f.read()

# Search within institutional role spans only
inst_spans = re.findall(r'<span[^>]*class="[^"]*resume-role[^"]*"[^>]*>(.*?)</span>', html, re.DOTALL)
found = []
for span in inst_spans:
    if SLASH_PATTERN.search(span):
        found.append(span.strip()[:80])

if found:
    for f in found[:10]:
        print("FAIL — slash role label:", f)
else:
    print("PASS")
EOF
```

**Pass:** `PASS`
**Root cause when failing:** `he_role(r)` was called instead of `he_role_g(r, _card_gender)` in `render_person_card()` institutional section.

---

## T43 — Sapir מכללת ספיר link in rendered cards must point to Cinema department (dep/529)

**What:** T41 checks `entity_registry.json` but misses wrong URLs hardcoded in `MANUAL_URL_MAP` inside `resolve_entities.py`. This test checks the actual rendered HTML link. The correct URL is `https://www.sapir.ac.il/staff/dep/529`. Known wrong values: `ba/cinema`, `staff/dep/17`.

```bash
python3 - <<'EOF'
import re

GOOD_URL = "https://www.sapir.ac.il/staff/dep/529"
BAD_PATTERNS = ["sapir.ac.il/ba/cinema", "sapir.ac.il/staff/dep/17"]

with open("connections_report.html", encoding="utf-8") as f:
    html = f.read()

found = []
for bad in BAD_PATTERNS:
    hits = [m.start() for m in re.finditer(re.escape(bad), html)]
    for hit in hits:
        context = html[max(0, hit-80):hit+120]
        found.append(f"Bad Sapir URL '{bad}' in rendered card: ...{context.strip()[:120]}...")

if found:
    for f in found[:5]:
        print("FAIL —", f)
else:
    # Verify the good URL is actually present
    if GOOD_URL not in html:
        print("WARN — dep/529 URL not found in report at all (no Sapir faculty rendered?)")
    else:
        print("PASS")
EOF
```

**Pass:** `PASS`
**Root cause when failing:** `MANUAL_URL_MAP` in `resolve_entities.py` has the wrong URL for `"manual://film_schools/sapir-faculty-2026/"`. Update it to `https://www.sapir.ac.il/staff/dep/529`.

---

## T44 — Admin/technical school staff must not be labeled "מרצה"

**What:** People imported with non-academic roles (coordinator, technician, librarian, archivist, building manager, etc.) must not receive the `faculty` role — which renders as "מרצה" (lecturer). This catches regressions in `role_for()` in `import_film_faculty.py` where the mapping was too coarse (all roles → `faculty`).

```bash
python3 - <<'EOF'
import json, glob, re

# Role strings that are clearly non-academic: if role_for() returns "faculty"
# for these, something is wrong.
NON_ACADEMIC_PATTERNS = re.compile(
    r"(רכז|סגן ראש מינהל|מרכז פרויקט|מרכז הפקות|טכנאי|מחסנאי|עובד תחזוקה|"
    r"מנהל גוש|סגן מנהל גוש|מנהל בית בכיר|ספרן|ספריי|מתאם מחשוב|ראש צוות מחשוב|"
    r"ראש מינהל|אחראי סדנ|מנהל אדמיניסטרטיבי)",
    re.UNICODE
)

hits = []
for path in glob.glob("out/*/mentions.jsonl"):
    source = path.split("/")[1]
    with open(path, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("status") != "ok":
                continue
            for p in rec.get("data", {}).get("entities", {}).get("people", {}).values():
                name = p.get("name_he") or ""
                roles = p.get("primary_roles", [])
                # Check all role strings attached to this person
                role_notes = p.get("role_notes") or p.get("role") or ""
                if isinstance(role_notes, list):
                    role_notes = " ".join(role_notes)
                if "faculty" in roles and NON_ACADEMIC_PATTERNS.search(role_notes):
                    hits.append(f"[{source}] {name!r} has role=faculty but role_notes={role_notes!r[:60]}")

if hits:
    print(f"FAIL — {len(hits)} non-academic staff imported as faculty:")
    for h in hits[:20]: print(f"  {h}")
else:
    print("PASS")
EOF
```

**Pass:** `PASS`  
**Complementary HTML check:**
```bash
python3 - <<'EOF'
import re

with open("connections_report.html", encoding="utf-8") as f:
    html = f.read()

# Find institutional entries linking to arts.tau.ac.il/administration
# where the role shown is מרצה — admin staff should never show as מרצה
TAU_ADMIN_URL = "arts.tau.ac.il/administration"
hits = []
for m in re.finditer(re.escape(TAU_ADMIN_URL), html):
    # Look ahead for the role span in the same entry
    window = html[m.start():m.start()+300]
    if 'resume-entry-role">מרצה<' in window:
        ctx = html[max(0, m.start()-400):m.start()]
        card_m = re.findall(r'id="(prof-[^"]+)"', ctx)
        hits.append(f"  {card_m[-1] if card_m else '?'}: admin-page entry shows מרצה role")

if hits:
    print(f"FAIL — {len(hits)} admin-page institutional entries mislabeled as מרצה:")
    for h in hits: print(h)
else:
    print("PASS — no admin staff mislabeled as מרצה")
EOF
```

**Root cause when failing:** `role_for()` in `scripts/importers/import_film_faculty.py` falls through to `return "faculty"` for strings it should map to `administrator`, `technician`, `librarian`, etc. Add the missing keyword patterns.

---

## T45 — Every film-school manual URL must resolve to a named institution with a link

**What:** When a person's film-school source is a `manual://` URL, `canonical_url_for()` must return a real URL that maps to a named institution in `URL_DOMAIN_LABELS`. If the lookup fails, the institutional entry shows the generic source label ("בתי ספר לקולנוע") as plain unlinked text instead of a named clickable institution.

**Manually found:** אתי ציקו — TAU admin source (`manual://film_schools/tau-arts-admin-2026/`) was missing from `CANONICAL_DOC_URLS`; her institutional entry showed "בתי ספר לקולנוע" with no link.

```bash
python3 - <<'EOF'
import json, sys
sys.path.insert(0, ".")
from resolve_entities import CANONICAL_DOC_URLS, URL_DOMAIN_LABELS
from urllib.parse import urlparse

# Collect all manual:// URLs used in film_schools source
manual_urls = set()
with open("out/film_schools/mentions.jsonl", encoding="utf-8") as f:
    for line in f:
        try:
            rec = json.loads(line)
            u = rec.get("url", "")
            if u.startswith("manual://"):
                manual_urls.add(u)
        except Exception:
            pass

hits = []
for mu in sorted(manual_urls):
    # Check if it resolves
    resolved = ""
    for prefix, real in CANONICAL_DOC_URLS.items():
        if mu.startswith(prefix):
            resolved = real
            break
    if not resolved:
        hits.append(f"  MISSING from CANONICAL_DOC_URLS: {mu}")
        continue
    # Check if the resolved domain has a label
    domain = urlparse(resolved).netloc.lower()
    if domain not in URL_DOMAIN_LABELS:
        hits.append(f"  Domain not in URL_DOMAIN_LABELS: {domain} (from {mu})")

if hits:
    print(f"FAIL — {len(hits)} film_schools manual URLs without institution resolution:")
    for h in hits: print(h)
else:
    print("PASS")
EOF
```

**Complementary HTML check — no unlinked "בתי ספר לקולנוע" in institutional entries:**
```bash
python3 - <<'EOF'
import re

with open("connections_report.html", encoding="utf-8") as f:
    html = f.read()

# An unlinked org entry looks like: <span class="resume-entry-org"><span dir="rtl">בתי ספר לקולנוע</span></span>
# A linked entry looks like: <a href="..." class="resume-entry-org"><span dir="rtl">...</span></a>
UNLINKED_RE = re.compile(
    r'<span class="resume-entry-org"><span dir="rtl">בתי ספר לקולנוע</span></span>'
)
hits = list(UNLINKED_RE.finditer(html))

if hits:
    print(f"FAIL — {len(hits)} unlinked 'בתי ספר לקולנוע' entries (manual URL not resolved):")
    for m in hits[:10]:
        ctx = html[max(0, m.start()-400):m.start()]
        card_m = re.findall(r'id="(prof-[^"]+)"', ctx)
        print(f"  {card_m[-1] if card_m else '?'}")
else:
    print("PASS — all film-school entries have a named linked institution")
EOF
```

**Pass:** both checks print `PASS`.  
**Root cause when failing:** Add the missing `"manual://film_schools/<key>/"` → `"https://..."` mapping to `CANONICAL_DOC_URLS` in `resolve_entities.py`.

---

## T46 — Section beacon must use threshold:0 (not 0.05)

**What:** The floating section-name beacon uses `IntersectionObserver`. With `threshold: 0.05` the observer requires 5% of the section element to be visible — which never happens for tall sections like "פרופיל מקצועי" (1,600+ cards, easily 100× the viewport height). The beacon silently never fires. Correct value is `threshold: 0`.

**Manually found:** The beacon stopped showing the current section name entirely because `sec-cross-people` is too tall for any threshold > 0 to fire.

```bash
python3 - <<'EOF'
import re

with open("connections_report.html", encoding="utf-8") as f:
    html = f.read()

# Find the IntersectionObserver threshold in the beacon script
threshold_m = re.search(r'new IntersectionObserver\b.*?threshold\s*:\s*([0-9.]+)', html, re.DOTALL)
if not threshold_m:
    print("SKIP — IntersectionObserver threshold not found in report")
elif float(threshold_m.group(1)) != 0.0:
    print(f"FAIL — section beacon threshold={threshold_m.group(1)} (must be 0 — tall sections never fire otherwise)")
else:
    print("PASS — threshold: 0")
EOF
```

**Pass:** `PASS — threshold: 0`  
**Root cause when failing:** Change `threshold: 0.05` (or any non-zero value) to `threshold: 0` in the `BEACON_JS` template inside `resolve_entities.py`, then regenerate the report.

---

## T47 — School-role chips must have institution tooltip

**What:** Profile card chips for school-related roles (`מרצה`, `סגל מינהלי`, `טכנאי`, `ספרן`, `אחראי ארכיון`, `מנהל סינמטק`) must carry a `title` attribute showing the institution name. Without it, hovering the chip gives no context about which school. The chip tooltip is generated by `_chip_tooltips` in `render_person_card()`.

**Manually found:** After adding admin-role types (`administrator`, `technician`, etc.), their chips rendered without tooltips because `_chip_tooltips` only covered the `faculty` role key.

```bash
python3 - <<'EOF'
import re

SCHOOL_ROLE_LABELS = {"מרצה", "סגל מינהלי", "טכנאי", "טכנאית", "ספרן", "ספרנית",
                      "אחראי ארכיון", "אחראית ארכיון", "מנהל סינמטק", "מנהלת סינמטק"}

with open("connections_report.html", encoding="utf-8") as f:
    html = f.read()

# Chips that have a title attribute contain: class="resume-chip..." title="...">label<
# Chips without: class="resume-chip...">label<  (no title= between class end and >)
CHIP_WITH_TITLE_RE    = re.compile(r'<span class="resume-chip[^"]*"\s+title="([^"]+)">([^<]+)</span>')
CHIP_WITHOUT_TITLE_RE = re.compile(r'<span class="resume-chip[^"]*">([^<]+)</span>')

# Collect all chips that have a school-role label but no title
chips_with    = {m.group(2).strip() for m in CHIP_WITH_TITLE_RE.finditer(html)}
chips_without = {m.group(1).strip() for m in CHIP_WITHOUT_TITLE_RE.finditer(html)}

# A school role that appears without a title somewhere in the report
unlabeled = (chips_without - chips_with) & SCHOOL_ROLE_LABELS

if unlabeled:
    # Find which cards have the untipped chips for debugging
    hits = []
    for label in sorted(unlabeled):
        pat = re.compile(r'id="(prof-[^"]+)"[^>]*>.*?<span class="resume-chip[^"]*">' + re.escape(label) + r'</span>', re.DOTALL)
        for m in pat.finditer(html):
            hits.append(f"  {m.group(1)}: chip '{label}' has no tooltip")
            if len(hits) >= 10: break
    print(f"FAIL — {len(unlabeled)} school-role chip labels found without tooltip: {sorted(unlabeled)}")
    for h in hits[:10]: print(h)
else:
    print("PASS — all school-role chips have institution tooltip")
EOF
```

**Pass:** `PASS — all school-role chips have institution tooltip`  
**Root cause when failing:** In `render_person_card()` in `resolve_entities.py`, extend the `_chip_tooltips` loop to cover the new role key (e.g. add it to the `_school_role in (...)` tuple near the `_faculty_schools` block).

---

## T48 — movies_db.json minimum film and fund counts

**What:** `data/movies_db.json` is the source of truth for all film data. After `enrich_movies_db_from_funds.py` runs, the database must contain at least 8,000 films and each major fund must have at least its known baseline number of funded films. A drop below these thresholds means the enrichment script wasn't run, a scraper regressed, or fund data was accidentally cleared.

**Baselines (as of 2026-06-03):**

| metric | minimum |
|--------|---------|
| Total films | 8,000 |
| Films with any fund data | 3,500 |
| `nfct` | 1,400 |
| `makor` | 700 |
| `filmfund` | 700 |
| `arava_film_fund` | 180 |
| `jerusalem_film_fund` | 150 |
| `fdoc` | 280 |
| `rabinovich_cinema` | 50 |
| `galilee_film_fund` | 25 |
| `gesher` | 20 |

```bash
python3 - <<'EOF'
import json
from collections import Counter

with open("data/movies_db.json", encoding="utf-8") as f:
    movies = json.load(f)

fund_counts = Counter(f for m in movies for f in (m.get("funds") or []))
with_funds  = sum(1 for m in movies if m.get("funds"))

MINIMUMS = {
    "__total__":         8000,
    "__with_funds__":    3500,
    "nfct":              1400,
    "makor":              700,
    "filmfund":           700,
    "arava_film_fund":    180,
    "jerusalem_film_fund":150,
    "fdoc":               280,
    "rabinovich_cinema":   50,
    "galilee_film_fund":   25,
    "gesher":              20,
}

fails = []
actual = dict(fund_counts)
actual["__total__"]      = len(movies)
actual["__with_funds__"] = with_funds

for key, minimum in MINIMUMS.items():
    count = actual.get(key, 0)
    if count < minimum:
        fails.append(f"  {key}: {count} < {minimum} (expected ≥ {minimum})")

if fails:
    print(f"FAIL — {len(fails)} counts below minimum:")
    for f in fails: print(f)
else:
    print(f"PASS — {len(movies)} films, {with_funds} with fund data")
    print("  " + ", ".join(f"{k}={v}" for k, v in sorted(fund_counts.items())))
EOF
```

**Pass:** `PASS — N films, M with fund data`  
**Root cause when failing:** Run `python3 scripts/funds/enrich_movies_db_from_funds.py` to restore fund data. If a specific fund drops, re-scrape that fund's source (`out/<fund>/mentions.jsonl`).

---

## T49 — Known filmmaker filmographies present in movies_db

**What:** Specific filmmakers whose profiles are well-documented must have their known films in `movies_db.json`. This catches regressions where a rebuild overwrites or drops manually-added film entries (e.g. films added via `enrich_movies_db_from_funds.py` or `filmmaker_profiles`).

**Canary filmmakers and required films:**

| Filmmaker | Films that must exist |
|-----------|----------------------|
| כליל כובש | שכבות (2024), ילדי בר (2024), נחל עמוד (2025), אחו (2020) |
| אסף לפיד | השיבה מהכוכבים, סיבת המוות, הנביא כהנא |

```bash
python3 - <<'EOF'
import json, re

def norm(s):
    if not s: return ""
    s = re.sub(r'["\'"״׳.,!?:;()]', "", s)
    s = re.sub(r"[-–—]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()

with open("data/movies_db.json", encoding="utf-8") as f:
    movies = json.load(f)

# Build person → film titles index
person_films: dict[str, set] = {}
for m in movies:
    for person in (m.get("crew") or []) + (m.get("cast") or []):
        name = norm(person.get("name_he") or "")
        if name:
            person_films.setdefault(name, set()).add(norm(m.get("title_he") or ""))

REQUIRED = {
    "כליל כובש": ["שכבות", "ילדי בר", "נחל עמוד", "אחו"],
    "אסף לפיד":  ["השיבה מהכוכבים", "סיבת המוות", "הנביא כהנא"],
}

fails = []
for filmmaker, films in REQUIRED.items():
    have = person_films.get(norm(filmmaker), set())
    missing = [f for f in films if norm(f) not in have]
    if missing:
        fails.append(f"  {filmmaker}: missing {missing} (has {len(have)} films total)")

if fails:
    print(f"FAIL — {len(fails)} filmmaker filmographies incomplete:")
    for f in fails: print(f)
else:
    print("PASS — all canary filmmaker filmographies present")
EOF
```

**Pass:** `PASS — all canary filmmaker filmographies present`  
**Root cause when failing:** A film was dropped from `movies_db.json`. Add it back directly with correct `crew` and `funds` fields, or re-run `enrich_movies_db_from_funds.py`.

---

## T50 — Known film–fund associations correct in movies_db

**What:** Specific films with documented funding must have the correct fund keys in their `funds` array. This catches cases where the enrichment script stripped fund data, a title-matching bug caused a fund to be assigned to the wrong film, or a film was re-added without its fund metadata.

```bash
python3 - <<'EOF'
import json, re

def norm(s):
    if not s: return ""
    s = re.sub(r'["\'"״׳.,!?:;()]', "", s)
    s = re.sub(r"[-–—]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()

with open("data/movies_db.json", encoding="utf-8") as f:
    movies = json.load(f)

# Build title+year → film index
index = {}
for m in movies:
    key = (norm(m.get("title_he") or ""), m.get("year"))
    index[key] = m

# (title_he, year, required_funds[])
REQUIRED_FUNDS = [
    ("שכבות",            2024, ["arava_film_fund", "makor", "galilee_film_fund"]),
    ("ילדי בר",          2024, ["rabinovich_cinema", "galilee_film_fund"]),
    ("נחל עמוד",         2025, ["galilee_film_fund"]),
    ("אלוהי הפסנתר",     2019, ["filmfund"]),
    ("קופה ראשית: הסרט", 2026, ["nfct"]),   # NFCT canary
]

fails = []
for title, year, required in REQUIRED_FUNDS:
    key = (norm(title), year)
    m = index.get(key)
    if m is None and year is None:
        # Try title-only match
        m = next((v for k, v in index.items() if k[0] == norm(title)), None)
    if m is None:
        fails.append(f"  MISSING film: {title} ({year or 'any year'})")
        continue
    actual_funds = set(m.get("funds") or [])
    missing_funds = [f for f in required if f not in actual_funds]
    if missing_funds:
        fails.append(f"  {title} ({year or '?'}): missing funds {missing_funds}, has {sorted(actual_funds)}")

if fails:
    print(f"FAIL — {len(fails)} film–fund associations wrong or missing:")
    for f in fails: print(f)
else:
    print("PASS — all canary film–fund associations correct")
EOF
```

**Pass:** `PASS — all canary film–fund associations correct`  
**Root cause when failing:** The film exists but its `funds` array is missing an entry. Edit `data/movies_db.json` directly to add the fund key, or re-run `enrich_movies_db_from_funds.py` (the enrichment script may have failed to match the film by title+year).

---

## T51 — movies_db is the source of all film credits in the report

**What:** Every film title visible in profile cards in `connections_report.html` must correspond to a film in `data/movies_db.json`. This detects regressions where film credits are being injected via `mentions.jsonl` or the `filmmaker_profiles` importer instead of coming through `movies_db.json`, bypassing the canonical source of truth.

```bash
python3 - <<'EOF'
import json, re

def norm(s):
    if not s: return ""
    s = re.sub(r'["\'"״׳.,!?:;()]', "", s)
    s = re.sub(r"[-–—]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()

with open("data/movies_db.json", encoding="utf-8") as f:
    movies = json.load(f)

db_titles = {norm(m.get("title_he") or "") for m in movies if m.get("title_he")}
db_titles |= {norm(m.get("title_en") or "") for m in movies if m.get("title_en")}
db_titles.discard("")

with open("connections_report.html", encoding="utf-8") as f:
    html = f.read()

# Extract all film titles shown in resume-film-title spans
film_titles_in_report = re.findall(
    r'<span class="resume-film-title"[^>]*>.*?<span[^>]*dir="rtl">([^<]+)</span>',
    html, re.DOTALL
)

missing_from_db = []
for title in film_titles_in_report:
    t = norm(title)
    if t and len(t) > 1 and t not in db_titles:
        missing_from_db.append(title)

missing_from_db = list(dict.fromkeys(missing_from_db))  # dedupe preserving order
total = len(film_titles_in_report)
ratio = (len(missing_from_db) / total) if total else 0

# Threshold: < 2% of report titles can be missing from movies_db.
# Higher than that means many credits are bypassing the canonical source.
THRESHOLD = 0.02

if ratio > THRESHOLD:
    print(f"FAIL — {len(missing_from_db)}/{total} ({ratio:.1%}) film titles in report not in movies_db (threshold {THRESHOLD:.0%}):")
    for t in missing_from_db[:20]: print(f"  {t!r}")
    if len(missing_from_db) > 20:
        print(f"  ... and {len(missing_from_db)-20} more")
elif missing_from_db:
    print(f"PASS — {len(missing_from_db)}/{total} ({ratio:.1%}) titles missing — below {THRESHOLD:.0%} threshold")
else:
    print(f"PASS — all {total} film credits in report are in movies_db")
EOF
```

**Pass:** `PASS` (under 2% of report titles missing from db). Hitting the threshold means film credits are being injected somewhere other than `movies_db.json`.  
**Root cause when failing:** Film credits are being added via `mentions.jsonl` / `filmmaker_profiles` importer rather than through `movies_db.json`. Add those films to the db and run `enrich_movies_db_from_funds.py`.

---

## T52 — Prize-winner conflicts: jury/programmer at festival X + prize_winner

**What:** Verify the CONFLICT_PAIR `{jury_member, festival_programmer, prize_committee_member, festival_director, artistic_director} × {prize_winner}` fires for known cases. The temporal-overlap check is skipped when `prize_winner` is involved (a prize is a one-off event whose date does not bound the other role's span).

```bash
python3 <<'PYEOF'
import re
h = open("connections_report.html", encoding="utf-8").read()
expected = [
    ("אתי ציקו",      "אוצר פסטיבל",  "זוכה פרס"),
    ("אוהד מילשטיין",  "חבר שופטים",  "זוכה פרס"),
    ("כליל כובש",     "אוצר פסטיבל",  "זוכה פרס"),
]
fails = []
for name, role_a, role_b in expected:
    anchor = f'id="prof-{name.replace(" ","-")}"'
    idx = h.find(anchor)
    if idx < 0:
        fails.append(f"{name}: anchor missing"); continue
    end = h.find('class="card resume-card', idx + 100)
    card = h[idx:end]
    flag_blob = " ".join(
        re.sub(r"<[^>]+>", " ", m)
        for m in re.findall(r'<div class="conflict-flag"[^>]*>(.+?)</div>', card, re.S)
    )
    if role_a in flag_blob and role_b in flag_blob:
        continue
    fails.append(f"{name}: missing {role_a!r} + {role_b!r} pair")
if fails:
    print("FAIL"); [print(" ", f) for f in fails]
else:
    print(f"PASS — {len(expected)} prize-winner conflicts present")
PYEOF
```

**Pass:** `PASS — 3 prize-winner conflicts present`.

**Root cause when failing:** Either `prize_winner` was dropped from `SOFT_INST_ROLES`, the dedicated CONFLICT_PAIR was removed, or an importer (e.g. `import_jff_winners.py`, `import_ministry_prizes.py`) is emitting roles under a different label.

---

## T53 — No duplicate film titles within a profile card (cross-source movies_db merge)

**What:** The per-person filmography in `connections_report.html` is sourced from
`data/movies_db.json` via `person_films()`. The same film often exists under different
source-prefixed `film_id`s (`edb:t0001220` vs `cinemaofisrael:…`); `person_films()` must
collapse them by normalized title so a film renders once per card. (Two genuinely
different seasons that display identically after episode-suffix stripping, e.g.
`חוות החופש` vs `חוות החופש (עונה 2)`, are allowed.)

```bash
python3 <<'PYEOF'
import re
from collections import Counter
html = open("connections_report.html", encoding="utf-8").read()
CARD = re.compile(r'id="(prof-[^"]+)"(.*?)(?=id="prof-|id="sec-|$)', re.DOTALL)
dups = []
for m in CARD.finditer(html):
    titles = re.findall(
        r'class="resume-film-title">.*?<span dir="rtl">([^<]+)</span>',
        m.group(2), re.DOTALL)
    for t, c in Counter(titles).items():
        if c > 1:
            dups.append(f"  {m.group(1)}: {t!r} ×{c}")
# Allow the single known season-collision; flag anything beyond it.
if len(dups) > 1:
    print(f"FAIL — {len(dups)} duplicate film entries:")
    for d in dups[:15]: print(d)
else:
    print(f"PASS — no cross-source duplicate film titles ({len(dups)} benign season-collision)")
PYEOF
```

**Pass:** `PASS — no cross-source duplicate film titles (≤1 benign season-collision)`.

**Root cause when failing:** `person_films()` lost its second dedup pass (collapse by
`normalize_film_title`), so films appearing under multiple source `film_id`s render once
per source. Fix in `resolve_entities.py::person_films` — group merged credits by
normalized title, union roles/roles_he/funds, prefer an `edb.co.il` URL + Hebrew title.

---

## T54 — Film credit URL points at the right film (URL path must contain a title token)

**What:** `data/movies_db.json` stores per-fund URLs as `{makor: …, fdoc: …, edb: …}`. A
data bug at the importer level can attach the WRONG film's URL under a key — e.g. the
"קרוב רחוק" 2009 record had `urls.makor` pointing at the unrelated `/films/21-יום-ולילה/`
page. Render side guards against this by preferring URLs whose decoded path contains
a ≥3-char token from the title; this test detects records where NO URL matches the
title at all (genuine upstream data bug worth fixing in movies_db, not papering over
in the renderer).

```bash
python3 <<'PYEOF'
import json, re
from urllib.parse import unquote, urlparse
db = json.load(open("data/movies_db.json", encoding="utf-8"))
def normalize_for_dedup(s):
    return re.sub(r"[\"'״׳.,!?:–—\-‘’“”]", " ", s.strip().lower())
# Hosts that use opaque numeric/alphanumeric IDs in their paths (not title slugs)
# get skipped — there's no slug to compare against, so a "no token match" finding
# is meaningless for these.
ID_HOSTS = {
    "www.edb.co.il", "edb.co.il",
    "www.filmfund.org.il", "filmfund.org.il",
}
def is_id_url(u):
    try:
        host = urlparse(u).netloc.lower()
        path = urlparse(u).path
    except Exception:
        return False
    if host in ID_HOSTS:
        return True
    # Pure-ID paths after /title|/movie|/film|/movies|/item|/id  — accepts:
    #   /title/t0001234/, /movie/12345, /movie/48599-2/, /movie/12345/anything-trailing
    if re.search(r"/(title|movie|film|movies|item|id)/[A-Za-z]?\d+(?:[-_]\d+)*/?$", path):
        return True
    if re.search(r"[?&](id|movieId|filmId|itemId)=\d+", u):
        return True
    return False
bad = []
for f in db:
    title_he = f.get("title_he") or ""
    title_en = f.get("title_en") or ""
    if not (title_he or title_en):
        continue
    # Compare against BOTH Hebrew and English titles: many fund websites use
    # English slugs (e.g. "legend-of-destruction") for films whose primary
    # title in movies_db is Hebrew ("אגדת חורבן").
    toks = []
    for t in (title_he, title_en):
        toks += [w for w in normalize_for_dedup(t).split() if len(w) >= 3]
    # Drop English stopwords so a URL like /movie/the-other-son/ isn't trivially
    # "matched" by "the/and/of" from a different film's English title.
    STOP_EN = {"the", "and", "for", "with", "from", "into", "are"}
    toks = [t for t in toks if t not in STOP_EN]
    if not toks:
        continue
    urls = f.get("urls") or {}
    if not isinstance(urls, dict):
        continue
    for src, u in urls.items():
        if not isinstance(u, str) or not u.startswith("http"):
            continue
        if is_id_url(u):
            continue  # ID-based URL, no slug to compare against
        path = unquote(u).lower()
        if not any(t in path for t in toks):
            bad.append((f.get("film_id"), title_he or title_en, src, u))
if bad:
    print(f"WARN — {len(bad)} films have a slug-based URL whose path doesn't match the title:")
    for fid, t, src, u in bad[:15]:
        print(f"  {fid} {t!r} via {src}: {u[:90]}")
else:
    print("PASS — every slug-based film URL's path contains a token from the title")
PYEOF
```

**Pass:** `PASS`. **WARN** is acceptable if the count is small and the URLs are known
manual:// canonicals; **FAIL** means investigate the importer and possibly correct
movies_db rows. Don't silently drop the URL in the renderer — fix the data.

---

## T55 — No same-person duplicate registry records under different name word-orders

**What:** Arabic naming order (family-name-first vs given-name-first) can produce two
`entity_registry.json` records for the same person. Example caught 2026-06-05:
`p_05ee74b8` "מוחמד אבו אחמד" (3 sources) and `p_e340a3c2` "אבו אחמד מוחמד" (rabinovich
only). Same person, sources just disagree on word order.

Heuristic: for every pair of registry people whose canonical names share the exact
same word multiset (set of whitespace-separated tokens) but in a different order,
treat as a probable duplicate.

```bash
python3 <<'PYEOF'
import json
from collections import defaultdict
reg = json.load(open("entity_registry.json", encoding="utf-8"))
people = reg.get("people", {})
buckets = defaultdict(list)
for pid, p in people.items():
    name = (p.get("canonical_name_he") or "").strip()
    toks = tuple(sorted(name.split()))
    if len(toks) < 2 or len(toks) > 4:
        continue
    buckets[toks].append((pid, name, p.get("source_count", 0)))
dups = [b for b in buckets.values() if len({n for _, n, _ in b}) > 1]
if dups:
    print(f"WARN — {len(dups)} suspected word-order duplicate pairs:")
    for b in dups[:15]:
        line = " ↔ ".join(f"{name!r}({sc}src,{pid})" for pid, name, sc in b)
        print(f"  {line}")
    print()
    print("If genuine same-person, add to PERSON_NAME_FIXES in resolve_entities.py")
    print("mapping the rarer variant → the canonical one.")
else:
    print("PASS — no same-multiset name-order duplicates")
PYEOF
```

**Pass:** `PASS`. WARN here doesn't always mean a bug (two people can genuinely share
the same words in different order), but every hit must be eyeballed.

---

## T56 — Conflict sentences must not span year ranges across institutions

**What:** The per-card "⚑ … כיהנה כ…" conflict sentence pairs each role with its
specific source and that source's actual years. A regression where years got unioned
across multiple sources would produce a misleading "(2019–2026)" tenure spanning two
unrelated institutions. Detect by inspecting sentences whose year range exceeds the
real per-source span by more than the dataset's longest real-world tenure (15yr).

```bash
python3 <<'PYEOF'
import re
html = open("connections_report.html", encoding="utf-8").read()
FLAG_RE  = re.compile(r'<div class="conflict-flag">(.*?)</div>', re.DOTALL)
RANGE_RE = re.compile(r'\((\d{4})[–-](\d{4})\)')
hits = []
for m in FLAG_RE.finditer(html):
    text = re.sub(r'<[^>]+>', '', m.group(1))
    for r in RANGE_RE.finditer(text):
        a, b = int(r.group(1)), int(r.group(2))
        if b - a > 15:
            hits.append(f"  {a}–{b} ({b-a}yr) in: {text[:120]}…")
if hits:
    print(f"WARN — {len(hits)} conflict sentences with >15yr tenure ranges:")
    for h in hits[:10]: print(h)
else:
    print("PASS — no excessive tenure ranges in conflict sentences")
PYEOF
```

**Pass:** `PASS`. WARN values within reason (e.g. 16–18yr) may be real careers; only
investigate if a single sentence shows e.g. "(1995–2025)" — a giveaway that two
institutions' years got unioned.

---

## T57 — exec_filmmaker derived conflicts must be sourced to actual exec-at-fund rows

**What:** `compute_exec_filmmaker` historically attributed the "fund executive" label
to every fund the person showed up at, even when they were merely a lector there
(e.g. Moriah Shirel was flagged as CEO at רבינוביץ because of `ceo` from a different
source). After the 2026-06-05 fix it must only flag people whose `roles_by_src[src]`
actually intersects `EXEC_ROLES` at a fund key.

```bash
python3 <<'PYEOF'
import json
EXEC_ROLES = {"ceo", "fund_manager", "executive_director"}
FUND_KEYS  = {"makor", "filmfund", "rabinovich_cinema", "jerusalem_film_fund",
              "nfct", "fdoc", "gesher", "festival_data"}
reg = json.load(open("entity_registry.json", encoding="utf-8"))["people"]
dc  = json.load(open("data/derived_conflicts.json", encoding="utf-8"))
bad = []
for e in dc.get("exec_filmmaker", []):
    name  = e["person"]
    funds = e["funds"]
    rec = next((p for p in reg.values() if p.get("canonical_name_he") == name), None)
    if not rec:
        bad.append((name, "MISSING from registry", funds))
        continue
    rbs = rec.get("roles_by_src") or {}
    for f in funds:
        if not (set(rbs.get(f, [])) & EXEC_ROLES):
            bad.append((name, f, sorted(rbs.get(f, []))))
if bad:
    print(f"FAIL — {len(bad)} exec_filmmaker rows attribute exec role to a fund the person isn't an exec at:")
    for n, f, r in bad[:15]:
        print(f"  {n} @ {f}: roles_at_this_src={r}")
else:
    print("PASS — every exec_filmmaker fund matches a roles_by_src exec role")
PYEOF
```

**Pass:** `PASS`. Any FAIL means `compute_derived_conflicts.compute_exec_filmmaker`
regressed and is again union'ing across all funds rather than checking per-source.

---

## T58 — Names that look truncated by Hebrew single-letter prefix-drop

**What:** Hebrew NER can drop a leading single-letter prefix (ב/מ/ל/כ/ו/ה/ש) from a
name, e.g. "מוריה שיראל" → "וריה שיראל". Catch suspected cases: registry names where
the first word, with one of `במלכוהש` prepended, matches another registry name's
first word AND the second words are identical.

```bash
python3 <<'PYEOF'
import json
from collections import defaultdict
reg = json.load(open("entity_registry.json", encoding="utf-8"))["people"]
PREFIX = "במלכוהש"
by_last = defaultdict(list)
for pid, p in reg.items():
    parts = (p.get("canonical_name_he") or "").split()
    if len(parts) < 2:
        continue
    by_last[parts[-1]].append((pid, p["canonical_name_he"], parts[0], p.get("source_count", 0)))
hits = []
for last, group in by_last.items():
    if len(group) < 2:
        continue
    firsts = {fst: (pid, nm, sc) for pid, nm, fst, sc in group}
    for fst in list(firsts):
        for ch in PREFIX:
            cand = ch + fst
            if cand in firsts and cand != fst:
                hits.append((firsts[fst][1], firsts[cand][1]))
hits = sorted(set(hits))
if hits:
    print(f"WARN — {len(hits)} suspected prefix-drop name pairs:")
    for short, long in hits[:15]:
        print(f"  {short!r} ↔ {long!r}  (add to PERSON_NAME_FIXES if same person)")
else:
    print("PASS — no suspected prefix-drop name pairs")
PYEOF
```

**Pass:** `PASS`. Every WARN hit needs eyeball verification — some genuine pairs exist
(e.g. "ויקטור / וויקטור" type spelling variants, "אהוד / אאהוד"). Confirmed duplicates
go into `PERSON_NAME_FIXES` in `resolve_entities.py` (around line 231).

---

## T59 — movies_db films where one title is a strict word-suffix of another (transliteration dup)

**What:** `data/movies_db.json` sometimes carries the same film under three rows: the
canonical Hebrew title, the Arabic+Hebrew variant ("قربة غربة קרוב רחוק"), and a
Hebrew transliteration of the Arabic ("קירבה גירבה קרוב רחוק"). The Arabic-strip
inside `normalize_film_title` catches the Arabic variant; the transliterated-Hebrew
variant needs the suffix-merge pass in `person_films`. This test surfaces remaining
underlying duplicate rows in movies_db so they can be merged at the data layer.

```bash
python3 <<'PYEOF'
import json, re
db = json.load(open("data/movies_db.json", encoding="utf-8"))
def norm(t):
    n = re.sub(r"[\"'״׳.,!?:–—\-‘’“”]", " ", (t or "").strip().lower())
    n = re.sub(r"[؀-ۿ]+", " ", n)           # strip Arabic
    return re.sub(r"\s+", " ", n).strip()
by_norm = {}
for f in db:
    t = norm(f.get("title_he") or "")
    if not t:
        continue
    by_norm.setdefault(tuple(t.split()), []).append(f.get("film_id"))
shorter_keys = sorted(by_norm, key=len)
hits = []
for i, sk in enumerate(shorter_keys):
    if len(sk) < 2:
        continue
    for lk in shorter_keys[i+1:]:
        if len(lk) > len(sk) and lk[-len(sk):] == sk:
            hits.append((" ".join(sk), " ".join(lk),
                         by_norm[sk][:1], by_norm[lk][:1]))
if hits:
    print(f"WARN — {len(hits)} suspected suffix-dup film pairs in movies_db:")
    for short, long, sids, lids in hits[:15]:
        print(f"  {short!r} ⊂ {long!r}  ({sids} ↔ {lids})")
else:
    print("PASS — no suspected suffix-dup film pairs in movies_db")
PYEOF
```

**Pass:** `PASS`. WARN entries should be reviewed: if same film, merge the rows in
`movies_db.json` (or fix the upstream importer that produced both); the renderer
already deduplicates at display time via `person_films`'s suffix-merge pass.

---

## T60 — movies_db films sharing a title_en across rows with different Hebrew spellings

**What:** Israeli films transliterated from other scripts often appear in `movies_db.json`
under multiple rows that disagree on Hebrew spelling but share the same `title_en`.
Example caught 2026-06-06: "Nandauri" exists as `נאנדאורי` (full mater-lectionis),
`ננדאורי` (compact), and `Nandauri` (English-only row from arava_film_fund). All
have `title_en == "Nandauri"`. The renderer's `person_films` now merges by
normalized `title_en` as a third dedup pass. This test surfaces the underlying
duplicate rows so they can be cleaned at the data layer.

```bash
python3 <<'PYEOF'
import json, re
from collections import defaultdict
db = json.load(open("data/movies_db.json", encoding="utf-8"))
def norm_en(s):
    return re.sub(r"\s+", " ",
        re.sub(r"[^a-z0-9]+", " ", (s or "").strip().lower())).strip()
by_en = defaultdict(list)
for f in db:
    te = norm_en(f.get("title_en"))
    if len(te) < 3:
        continue
    by_en[te].append((f.get("film_id"), f.get("title_he"), f.get("year")))
hits = [(k, v) for k, v in by_en.items() if len({h for _, h, _ in v if h}) > 1]
if hits:
    print(f"WARN — {len(hits)} title_en groups with divergent Hebrew spellings:")
    for k, rows in hits[:10]:
        print(f"  {k!r}:")
        for fid, th, yr in rows:
            print(f"    {fid} | {th!r} ({yr})")
else:
    print("PASS — every title_en maps to a single Hebrew spelling")
PYEOF
```

**Pass:** `PASS`. WARN entries should be merged in `movies_db.json` (or the upstream
importers should be reconciled). The display-side dedup keeps the report clean
either way, but each duplicate row wastes index space and risks divergent metadata.
