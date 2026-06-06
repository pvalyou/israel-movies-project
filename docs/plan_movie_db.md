# Plan: Comprehensive Israeli Movie Database (Multi-Source)

## The big picture

**Films are not the end goal — people are.**

The movie database exists to link person entities together. A film record is useful only insofar as it contains crew and cast that can be resolved back to people already in (or added to) `entity_registry.json`. Every name in a film's crew or cast is a potential:
- New person node in the network graph
- New `crew_credit` edge (person → film)
- New `co_credited` edge (person ↔ person, via shared film)
- New `fund_recipient` edge (film → fund, which connects the film's crew to that fund)

The richer the film data, the denser the people network. More crew roles → more co-credit pairs. More cast → more actor→director connections. More funds → more institutional conflict paths.

```
person ──crew_credit──▶ film ──fund_recipient──▶ fund
                         │
                  co_credited (all pairs of crew on the same film)
```

---

## Goal

Build `data/movies_db.json` — a unified, source-agnostic film store. It is:
1. The input to `build_network_graph()` (replaces `data/edb/edb_films.json`)
2. The backing store for film cards in the HTML report
3. Designed to absorb new sources without restructuring

---

## Source registry

Each source is a self-contained adapter. Adding a new source means:
1. Write a scraper → outputs `data/{source_key}/raw_films.json`
2. Write a parser → `parse_{source_key}(raw: dict) -> SourceFilmRecord`
3. Register it in `SOURCE_REGISTRY` in `scripts/build_movies_db.py`

No other file changes needed.

### Current sources

| Key | Site | Sitemap / Entry point | Confirmed fields |
|-----|------|-----------------------|-----------------|
| `edb` | `edb.co.il` | `/browse/b/c/israel/t/{type}/` | crew roles, funds (קרן), festivals, awards, is_short |
| `jfc` | `jfc.org.il` | `/movie-sitemap.xml` (~1,100 URLs) | director, cast, synopsis (HTML), topics/tags |
| `ci` | `cinemaofisrael.co.il` | sitemap index → 110 sub-sitemaps | full cast+character, 10 crew roles, English title, release date |

### Adding a future source
- Implement `scrape_{key}.py` → writes `data/{key}/raw_films.json`
- Each raw record must include at minimum: `title_he`, `year`, `crew[]`, and `url`
- Register in `SOURCE_REGISTRY` with a `parse` function and a `priority` int (lower = more trusted)

---

## Canonical film record schema

Scrape everything available — unknown fields stay `null`. More fields = richer graph edges and report cards.

```json
{
  "film_id":   "edb:t0016283",
  "sources":   ["edb", "jfc", "ci"],

  "title_he":       "עוד ניפגש",
  "title_en":       "We Will Meet Again",
  "title_alt":      ["Another Title Variant"],
  "title_original": null,

  "year":            2020,
  "release_date_il": "2021-03-04",
  "is_short":        false,
  "duration_min":    82,

  "genre":           "documentary",
  "genre_he":        "סרט תיעודי",
  "tags":            ["קונפליקט ישראלי-פלסטיני", "תיעודי"],
  "based_on":        null,

  "description_he":  "...",
  "description_en":  null,

  "country":         ["ישראל"],
  "language":        ["עברית"],
  "subtitles":       [],
  "color":           true,
  "format":          "HD",

  "funds":           ["nfct", "makor"],
  "production_companies": ["קמה פילמס"],
  "distribution_companies": ["לב זיסאפל הפצה"],
  "broadcaster":     null,

  "budget":          null,
  "box_office_il":   null,

  "crew": [
    {
      "name_he":     "שירה מרגלית",
      "name_en":     null,
      "role":        "director",
      "role_he":     "במאית",
      "edb_id":      "n0001234",
      "registry_id": "person::שירה מרגלית"
    }
  ],
  "cast": [
    {
      "name_he":     "דוד לוי",
      "name_en":     null,
      "character":   "עצמו",
      "edb_id":      null,
      "registry_id": null
    }
  ],

  "festivals": [
    {"name": "פסטיבל דוקאביב", "year": 2021, "award": "פרס הקהל", "section": null}
  ],
  "awards": [
    {"award": "אופיר", "year": 2021, "category": "סרט תיעודי מצטיין", "won": true}
  ],

  "poster_url":    "https://...",
  "trailer_url":   null,
  "watch_url":     null,

  "related_films": [],
  "related_interviews": [],

  "urls": {
    "edb": "https://www.edb.co.il/title/t0016283/",
    "jfc": "https://jfc.org.il/movie/45759-2/",
    "ci":  "https://cinemaofisrael.co.il/..."
  }
}
```

### Field source map

| Field | Best source | Notes |
|-------|------------|-------|
| `funds` | EDB only | תמיכה section |
| `festivals`, `awards` | EDB | פסטיבלים / פרסים sections |
| `edb_id` on crew | EDB | enables person-page cross-reference |
| `description_he` | JFC | longer editorial text |
| `tags` | JFC | topic links (`/topic/...`) |
| `watch_url` | JFC | if film available for streaming |
| `related_interviews` | JFC | ראיונות עם יוצרים links |
| `title_en` / `title_alt` | CI (cinemaofisrael) | "שם אחר/לועזי" label |
| `cast[].character` | CI | actor → character pairs |
| `release_date_il` | CI | "תאריך הפצה בישראל" |
| `based_on` | CI | "מבוסס על" |
| `format`, `color` | CI | from the `"YYYY / NNN דקות / עברית, צבע, HD"` line |
| `broadcaster` | future | hot, yes, kan |
| `budget`, `box_office_il` | future | if found |
| `poster_url` | any | og:image or dedicated poster element |

### Key field: `registry_id`
After building `movies_db.json`, a resolution pass matches each `crew[].name_he` and `cast[].name_he` against `entity_registry.json` (using the same `normalize_name()` already in `resolve_entities.py`). Matched entries get `registry_id` populated. This is what allows `build_network_graph()` to wire `crew_credit` edges to existing person nodes without an extra name-matching step.

### ID strategy
- Prefer EDB film_id as canonical: `"edb:t0016283"`
- Films not in EDB: `"jfc:{numeric-id}"` or `"ci:{hebrew-slug}"`
- IDs are stable once assigned — don't change when a new source matches later

---

## Per-source adapter

### Intermediate format (output of each scraper)
Each `data/{source_key}/raw_films.json` is a list of records in a **source-specific but consistent** shape:

```json
{
  "source_key":  "jfc",
  "source_id":   "44539-2",
  "url":         "https://jfc.org.il/movie/44539-2/",
  "title_he":    "ערב בלי נעמה",
  "title_en":    null,
  "title_alt":   [],
  "title_original": null,
  "year":        1992,
  "release_date_il": null,
  "is_short":    false,
  "duration_min": 94,
  "genre":       null,
  "genre_he":    null,
  "description_he": "...",
  "description_en": null,
  "country":     ["ישראל"],
  "language":    ["עברית"],
  "subtitles":   [],
  "color":       null,
  "format":      null,
  "based_on":    null,
  "funds":       [],
  "production_companies": ["צוף הפקות בע\"מ"],
  "distribution_companies": [],
  "broadcaster": null,
  "budget":      null,
  "box_office_il": null,
  "crew": [
    {"name_he": "משה צימרמן", "role": "director", "role_he": "בימוי", "edb_id": null}
  ],
  "cast": [
    {"name_he": "ערן איווניר", "character": null, "edb_id": null}
  ],
  "festivals":   [],
  "awards":      [],
  "tags":        ["דרמה", "מעמד חברתי"],
  "poster_url":  null,
  "trailer_url": null,
  "watch_url":   null,
  "related_films": [],
  "related_interviews": []
}
```

This is the same shape for all sources — scrapers normalize into it.

---

## Source 1 — EDB (`edb.co.il`)

**Unique value:** fund (קרן) support data, festivals, awards, `edb_id` for crew (links to `edb_persons.json`)

### Collection
- Existing: `data/edb/edb_film_ids.json` — 199 features + 98 shorts
- Expand: fetch browse pages for documentary / animation / TV categories
  - `https://www.edb.co.il/browse/b/c/israel/t/documentary/?p={N}`
  - `https://www.edb.co.il/browse/b/c/israel/t/animation/?p={N}`
  - Stop when page returns no new IDs

### Pages per film
1. `/title/{id}/` — title, year, description, funds (תמיכה section), festivals, awards, genre
2. `/title/{id}/cast/` — already done for 285 films; reuse existing data

### Key selectors (inspect live pages to confirm)
- Funds: `תמיכה` heading → adjacent links/text
- JSON-LD: `"genre"`, `"duration"`, `"dateCreated"`
- Festivals/awards: `פסטיבלים` / `פרסים` sections

### FUND_NAME_MAP
```python
FUND_NAME_MAP = {
    "הקרן החדשה לקולנוע וטלוויזיה": "nfct",
    "קרן מקור":                      "makor",
    "קרן רבינוביץ":                  "rabinovich_cinema",
    "קרן ירושלים":                   "jerusalem_film_fund",
    "קרן גשר":                       "gesher",
    "קרן קולנוע ישראל":              "filmfund",
    "קרן הסרט הישראלי":              "filmfund",
    "מסלול הפקות":                   "nfct",
    "הרשות לשידורי כבלים":           "cable_authority",
    "yes דוקו":                      "yes_doco",
    "hot8":                          "hot8",
}
```

### Script
`scripts/edb/enrich_edb_metadata.py` — reads `data/edb/edb_film_ids.json`, fetches main pages, writes enriched `data/edb/raw_films.json`

---

## Source 2 — JFC (`jfc.org.il`)

**Unique value:** editorial synopsis, thematic topic tags, historical archive films (pre-1990)

### Collection
- Sitemap: `https://jfc.org.il/movie-sitemap.xml` → ~1,100 URLs
- Pattern: `/movie/{numeric-id}-2/`

### Extraction (confirmed from live pages)
- `@type: Movie` JSON-LD block contains `actor[]`, `director[]`, `description` (HTML)
- HTML text: year + duration pattern `"NNN דקות, YYYY"` or `"YYYY, NNN דקות"`
- Topics: `<a href="/topic/...">` links
- No JS required — plain `requests` works

### Parser sketch
```python
def parse_jfc(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    ld = _extract_movie_ld(soup)   # find @type:Movie in JSON-LD graph

    title_he = _clean_title(soup.find("h1").get_text())
    year, duration = _parse_year_duration(soup.get_text())
    description = re.sub(r"<[^>]+>", " ", ld.get("description", "")).strip()
    directors = [p["name"] for p in ld.get("director", []) if isinstance(p, dict)]
    actors    = [p["name"] for p in ld.get("actor", []) if isinstance(p, dict)]
    tags = [a.get_text(strip=True) for a in soup.select("a[href*='/topic/']")]

    return {
        "source_key": "jfc",
        "source_id":  url.split("/movie/")[1].rstrip("/"),
        "url": url,
        "title_he": title_he,
        "year": year, "duration_min": duration,
        "description_he": description,
        "crew":  [{"name_he": d, "role": "director", "role_he": "בימוי"} for d in directors],
        "cast":  [{"name_he": a, "character": None} for a in actors],
        "tags": tags,
        **_empty_fields(),
    }
```

### Script
`scripts/jfc/scrape_jfc.py` → `data/jfc/raw_films.json`

---

## Source 3 — ספר הקולנוע (`cinemaofisrael.co.il`)

**Unique value:** full cast with character names, 10+ crew roles, English title, release date

### Collection
- Sitemap index: `https://cinemaofisrael.co.il/sitemap.xml` → 110 monthly sub-sitemaps
- Each sub-sitemap: ~56 URLs mixing film + person + company pages (all flat Hebrew-slug URLs)
- **Classification on fetch:** film page = has `בימוי` field AND year/duration line; return `None` for non-films

### Extraction (confirmed from live pages)
Film pages contain:
- `title_he` (`<h1>`), `title_en` ("שם אחר/לועזי" label)
- Year/duration/language from `"YYYY / NNN דקות / שפה"` line
- Crew fields each on a labeled line: בימוי, תסריט, הפקה, צילום, עריכה, מוזיקה, עיצוב פסקול, עיצוב אמנותי, עיצוב תלבושות
- Production companies ("חברת הפקה" label)
- Cast table under "משחק" section (actor → character pairs)
- Synopsis under "תקציר" label
- Release date ("תאריך הפצה בישראל" label)

### Script
`scripts/cinemaofisrael/scrape_cinemaofisrael.py` → `data/cinemaofisrael/raw_films.json`

---

## Build / Merge (`scripts/build_movies_db.py`)

### Source registry pattern
```python
SOURCE_REGISTRY = {
    "edb": {
        "raw_path":   "data/edb/raw_films.json",
        "priority":   1,   # lower = more authoritative
        "authoritative_for": ["film_id", "funds", "festivals", "awards", "is_short", "edb_id"],
    },
    "ci": {
        "raw_path":   "data/cinemaofisrael/raw_films.json",
        "priority":   2,
        "authoritative_for": ["title_en", "cast", "release_date_il"],
    },
    "jfc": {
        "raw_path":   "data/jfc/raw_films.json",
        "priority":   3,
        "authoritative_for": ["description_he", "tags"],
    },
    # Adding a new source: drop a new entry here + write its scraper
}
```

### Matching / deduplication
```
Primary key:   normalize(title_he) + str(year)
Fuzzy fallback: Levenshtein(normalize(title_he), normalize(candidate)) ≤ 2, same year
```

`normalize()`: strip niqqud, collapse whitespace, strip punctuation, NFKD.

When a match is found across sources, merge fields using each source's `authoritative_for` list. For non-authoritative fields, take the first non-empty value in priority order.

### People resolution pass
After merging, run a resolution pass over all `crew[].name_he` and `cast[].name_he`:

```python
def resolve_people(films: list, registry: dict) -> list:
    norm_to_id = {normalize_name(v["name"]): k for k, v in registry.items()}
    for film in films:
        for person in film.get("crew", []) + film.get("cast", []):
            key = normalize_name(person["name_he"])
            person["registry_id"] = norm_to_id.get(key)  # None if not yet in registry
    return films
```

`registry_id` is `None` for names not yet in the pipeline — that's fine. `build_network_graph()` skips them for existing edges but can optionally add new person nodes from film crew.

---

## Scripts to write

| Script | Input | Output |
|--------|-------|--------|
| `scripts/edb/enrich_edb_metadata.py` | `data/edb/edb_film_ids.json` | `data/edb/raw_films.json` |
| `scripts/jfc/scrape_jfc.py` | `jfc.org.il/movie-sitemap.xml` | `data/jfc/raw_films.json` |
| `scripts/cinemaofisrael/scrape_cinemaofisrael.py` | sitemap index | `data/cinemaofisrael/raw_films.json` |
| `scripts/build_movies_db.py` | `SOURCE_REGISTRY` entries + `entity_registry.json` | `data/movies_db.json` |

All scrapers: `--limit N` for testing, `--force` to re-scrape, checkpoint every 50 films.

---

## Integration into resolve_entities.py

Once `data/movies_db.json` exists, replace the EDB-only film loading in `build_network_graph()`:

```python
# Replace:
edb_films_path = Path("data/edb/edb_films.json")
# With:
edb_films_path = Path("data/movies_db.json") if Path("data/movies_db.json").exists() \
                 else Path("data/edb/edb_films.json")
```

Film nodes and `crew_credit` / `co_credited` / `fund_recipient` edges all flow from this file. With `registry_id` populated, matching to existing person nodes becomes a direct lookup instead of a name-normalize search.

---

## Execution order

1. **Inspect** 3 live pages per new source to confirm selectors (do this before writing code)
2. **Expand** `data/edb/edb_film_ids.json` with documentary/animation/TV categories
3. **Run scrapers** (independent — run in parallel):
   - `python3 scripts/edb/enrich_edb_metadata.py --limit 10`
   - `python3 scripts/jfc/scrape_jfc.py --limit 20`
   - `python3 scripts/cinemaofisrael/scrape_cinemaofisrael.py --limit 30`
4. **Verify** output on 10 sample records per source
5. **Full run** all three scrapers
6. **Build**: `python3 scripts/build_movies_db.py`
7. **Check resolution rate**: % of crew names matched to `registry_id`
8. **Update `resolve_entities.py`** to use `data/movies_db.json`
9. **Run QA agent**

---

## Expected coverage

| Metric | Estimate |
|--------|----------|
| Total unique films | 2,000–4,000 |
| Crew names resolved to existing registry entries | 30–50% (grows as more sources added) |
| Films with fund (קרן) data | ~500–800 |
| Films with synopsis | ~2,000+ |
| Films with full cast (incl. characters) | ~1,500+ |
| New person nodes from film crew (not yet in registry) | hundreds |
