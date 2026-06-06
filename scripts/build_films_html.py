#!/usr/bin/env python3
"""Generate films.html — a searchable catalog of all films in movies_db.json.

Usage: python3 scripts/build_films_html.py
Output: films.html
"""

import json
import re
from collections import defaultdict
from datetime import date
from html import unescape
from pathlib import Path

MOVIES_DB = "data/movies_db.json"
OUTPUT = "films.html"

SOURCE_LABEL = {"edb": "EDB", "jfc": "JFC", "cinemaofisrael": "CI"}
SOURCE_PRIORITY = {"cinemaofisrael": 0, "jfc": 1, "edb": 2}  # lower = richer data
SOURCE_COLOR = {"edb": "#3b82f6", "jfc": "#10b981", "cinemaofisrael": "#f59e0b"}


def _norm_title(title: str) -> str:
    if not title:
        return ""
    t = unescape(title.strip())  # decode &#8230; and other HTML entities
    # Strip bracketed/parenthesised subtitles: [60 שעות לסואץ], (alt title)
    t = re.sub(r'\s*[\[\(][^\]\)]{1,60}[\]\)]', '', t)
    # Normalize ellipsis, en-dash, em-dash, and repeated dots to a single space
    t = re.sub(r'[…–—]|\.{2,}', ' ', t)
    # Strip trailing/leading punctuation that varies by source
    # (include curly single + double quotes: "The Ambassador’s Wife" == "...'s Wife")
    t = re.sub(r'["\'״׳""‘’“”\-?!:,.]', '', t)
    # Collapse all whitespace (including bidi markers)
    t = re.sub(r'[\s‏‎‪-‮]+', ' ', t)
    return t.strip().lower()


def _extract_urls(film: dict) -> dict:
    raw = film.get("urls") or {}
    if isinstance(raw, list):
        sources = film.get("sources", [])
        return {sources[i]: raw[i] for i in range(min(len(sources), len(raw)))}
    return dict(raw)


def _merge_group(group: list) -> dict:
    def _score(f):
        best_pri = min((SOURCE_PRIORITY.get(s, 99) for s in f.get("sources", [])), default=99)
        return (
            len(f.get("crew", [])) + len(f.get("cast", [])),
            bool(f.get("title_en")),
            bool(f.get("genre_he") or f.get("genre")),
            -best_pri,
        )

    best = max(group, key=_score)
    merged = dict(best)

    seen: set = set()
    all_sources: list = []
    for f in sorted(group, key=lambda x: min((SOURCE_PRIORITY.get(s, 99) for s in x.get("sources", [])), default=99)):
        for s in f.get("sources", []):
            if s not in seen:
                all_sources.append(s)
                seen.add(s)
    merged["sources"] = all_sources

    merged_urls: dict = {}
    for f in group:
        for s, u in _extract_urls(f).items():
            if s not in merged_urls and u:
                merged_urls[s] = u
    merged["urls"] = merged_urls
    return merged


def dedup_films(films: list) -> list:
    # Pass 1: exact (norm_title, year)
    by_key: dict = defaultdict(list)
    for f in films:
        key = (_norm_title(f.get("title_he", "")), str(f.get("year") or ""))
        by_key[key].append(f)
    merged1 = [_merge_group(g) for g in by_key.values()]

    # Pass 2: same norm_title, years differ by ≤1 (e.g. production vs release year)
    by_title: dict = defaultdict(list)
    for f in merged1:
        by_title[_norm_title(f.get("title_he", ""))].append(f)

    result = []
    for nt, group in by_title.items():
        if len(group) == 1:
            result.append(group[0])
            continue

        # Sort by year (None → 0)
        group.sort(key=lambda f: f.get("year") or 0)

        # Greedily merge entries whose years are within 1 of the previous merged entry
        chains: list = [[group[0]]]
        for f in group[1:]:
            last_year = chains[-1][-1].get("year") or 0
            this_year = f.get("year") or 0
            if abs(this_year - last_year) <= 1:
                chains[-1].append(f)
            else:
                chains.append([f])

        for chain in chains:
            result.append(_merge_group(chain))

    # Pass 3: EDB-thin entries (≤2 crew) whose title is a prefix of a richer entry's
    # title, with the same director and year — catches EDB truncation like "נדל" vs "נדל\"ן"
    def _directors(f: dict) -> set:
        return {re.sub(r'\s+', ' ', c["name_he"].strip().lower())
                for c in f.get("crew", [])
                if c.get("role") == "director" and c.get("name_he")}

    thin = {id(f): f for f in result
            if f.get("sources") == ["edb"] and len(f.get("crew", [])) <= 2}
    absorbed: set = set()

    for fid, te in thin.items():
        if fid in absorbed:
            continue
        tn = _norm_title(te.get("title_he", ""))
        td = _directors(te)
        te_yr = te.get("year") or 0
        for rf in result:
            if id(rf) in absorbed or id(rf) == fid:
                continue
            rn = _norm_title(rf.get("title_he", ""))
            if rn == tn:
                continue  # already handled
            if not (rn.startswith(tn) or tn.startswith(rn)):
                continue
            if abs((rf.get("year") or 0) - te_yr) > 1:
                continue
            rd = _directors(rf)
            if td and rd and not td & rd:
                continue  # different directors
            # Merge thin entry into richer entry in-place
            merged = _merge_group([te, rf])
            result[result.index(rf)] = merged
            absorbed.add(fid)
            break

    result = [f for f in result if id(f) not in absorbed]
    return result


def badge(src: str, url: str = None) -> str:
    color = SOURCE_COLOR.get(src, "#94a3b8")
    label = SOURCE_LABEL.get(src, src.upper())
    inner = f'<span class="badge badge-source" style="background:{color}" title="{src}">{label}</span>'
    if url:
        return f'<a href="{url}" target="_blank" rel="noopener" class="badge-link">{inner}</a>'
    return inner


def directors(film: dict) -> str:
    names = [c["name_he"] for c in film.get("crew", []) if c.get("role") == "director" and c.get("name_he")]
    return "، ".join(names) if names else ""


def build_row(film: dict, idx: int) -> str:
    year = film.get("year") or ""
    title_he = film.get("title_he") or ""
    title_en = film.get("title_en") or ""
    dir_names = directors(film)
    crew_count = len(film.get("crew", []))
    cast_count = len(film.get("cast", []))
    sources = film.get("sources", [])
    urls = _extract_urls(film)
    badges = "".join(badge(s, urls.get(s)) for s in sources)
    is_short = "קצר" if film.get("is_short") else ""
    genre = film.get("genre_he") or film.get("genre") or ""

    search_blob = " ".join(filter(None, [
        title_he, title_en, dir_names,
        str(year), genre,
        " ".join(SOURCE_LABEL.get(s, s) for s in sources),
    ])).lower()

    return (
        f'<tr data-search="{search_blob}" data-year="{year}" '
        f'data-sources="{",".join(sources)}">'
        f'<td class="col-year">{year}</td>'
        f'<td class="col-title" dir="rtl">'
        f'<span class="title-he">{title_he}</span>'
        + (f'<span class="title-en">{title_en}</span>' if title_en else "")
        + '</td>'
        f'<td class="col-dir" dir="rtl">{dir_names}</td>'
        f'<td class="col-genre" dir="rtl">{genre}</td>'
        f'<td class="col-crew">{crew_count or ""}</td>'
        f'<td class="col-cast">{cast_count or ""}</td>'
        f'<td class="col-src">{badges}</td>'
        f'</tr>\n'
    )


def main():
    with open(MOVIES_DB, encoding="utf-8") as f:
        films = json.load(f)

    n_raw = len(films)
    films = dedup_films(films)
    n_deduped = n_raw - len(films)

    films.sort(key=lambda x: (-(x.get("year") or 0), x.get("title_he") or ""))

    n_total = len(films)
    years = sorted({f["year"] for f in films if f.get("year")})
    year_min, year_max = (years[0], years[-1]) if years else (0, 0)
    sources_seen = sorted({s for f in films for s in f.get("sources", [])})
    today = date.today().isoformat()

    rows_html = "".join(build_row(f, i) for i, f in enumerate(films))
    n_years_minus1 = max(len(years) - 1, 1)
    years_js = json.dumps(years)

    source_filter_btns = "".join(
        '<button class="src-btn active" data-src="{s}" style="--src-color:{c}">{label}</button>'.format(
            s=s, c=SOURCE_COLOR.get(s, "#94a3b8"), label=SOURCE_LABEL.get(s, s.upper())
        )
        for s in sources_seen
    )

    html = f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>קטלוג סרטים — תעשיית הקולנוע הישראלית</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
      background: #f1f5f9; color: #1e293b; font-size: 14px;
      line-height: 1.5; margin: 0;
    }}
    a {{ color: #3b82f6; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}

    .header {{
      background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%);
      color: white; padding: 28px 40px;
      display: flex; align-items: flex-start; justify-content: space-between;
      flex-wrap: wrap; gap: 12px;
    }}
    .header h1 {{ font-size: 20px; font-weight: 700; margin: 0 0 4px; }}
    .header .subtitle {{ color: #94a3b8; font-size: 13px; }}
    .header .back-link {{ color: #94a3b8; font-size: 12px; white-space: nowrap; }}
    .header .back-link:hover {{ color: #fff; }}

    .stats-bar {{
      display: flex; gap: 16px; padding: 18px 40px;
      background: #fff; border-bottom: 1px solid #e2e8f0; flex-wrap: wrap;
    }}
    .stat {{ text-align: center; min-width: 90px; }}
    .stat .value {{ font-size: 26px; font-weight: 700; color: #0f172a; }}
    .stat .label {{ font-size: 11px; color: #64748b; text-transform: uppercase;
                   letter-spacing: 0.5px; margin-top: 2px; }}

    .controls {{
      padding: 16px 40px; background: #fff; border-bottom: 1px solid #e2e8f0;
      display: flex; gap: 16px; align-items: center; flex-wrap: wrap;
    }}
    .search-box {{
      flex: 1; min-width: 220px; padding: 8px 14px;
      border: 1px solid #cbd5e1; border-radius: 8px;
      font-size: 13px; outline: none; direction: rtl;
    }}
    .search-box:focus {{ border-color: #3b82f6; box-shadow: 0 0 0 2px #bfdbfe; }}
    .year-filter {{ display: flex; flex-direction: column; gap: 4px; min-width: 220px; }}
    .year-filter-label {{
      font-size: 11px; color: #64748b; display: flex; justify-content: space-between;
      align-items: center;
    }}
    .year-range-val {{ font-weight: 700; color: #0f172a; font-size: 12px; letter-spacing: -.3px; }}
    .year-reset {{ font-size: 10px; color: #94a3b8; cursor: pointer; padding: 1px 6px;
                  border: 1px solid #e2e8f0; border-radius: 8px; background: #f8fafc; }}
    .year-reset:hover {{ color: #3b82f6; border-color: #3b82f6; }}
    .year-slider-wrap {{
      position: relative; height: 20px; display: flex; align-items: center;
    }}
    .year-track {{
      position: absolute; left: 0; right: 0; height: 4px;
      background: #e2e8f0; border-radius: 2px; pointer-events: none;
    }}
    .year-fill {{
      position: absolute; height: 4px; background: #3b82f6;
      border-radius: 2px; pointer-events: none;
    }}
    .year-slider {{
      position: absolute; width: 100%; height: 4px;
      -webkit-appearance: none; appearance: none;
      background: transparent; pointer-events: none; outline: none;
    }}
    .year-slider::-webkit-slider-thumb {{
      -webkit-appearance: none; appearance: none;
      width: 16px; height: 16px; border-radius: 50%;
      background: #fff; border: 2px solid #3b82f6;
      box-shadow: 0 1px 4px rgba(0,0,0,.15);
      pointer-events: auto; cursor: pointer;
    }}
    .year-slider::-moz-range-thumb {{
      width: 16px; height: 16px; border-radius: 50%;
      background: #fff; border: 2px solid #3b82f6;
      box-shadow: 0 1px 4px rgba(0,0,0,.15);
      pointer-events: auto; cursor: pointer;
    }}
    .year-slider::-webkit-slider-thumb:hover {{ border-color: #1d4ed8; background: #eff6ff; }}
    .year-slider::-moz-range-thumb:hover {{ border-color: #1d4ed8; background: #eff6ff; }}
    .src-filters {{ display: flex; gap: 6px; flex-wrap: wrap; }}
    .src-btn {{
      padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600;
      border: 2px solid var(--src-color); background: var(--src-color); color: #fff;
      cursor: pointer; transition: opacity .15s;
    }}
    .src-btn:not(.active) {{ background: transparent; color: var(--src-color); opacity: .6; }}
    .count-line {{
      font-size: 12px; color: #64748b; white-space: nowrap; align-self: center;
    }}

    .table-wrap {{
      max-width: 1400px; margin: 24px auto; padding: 0 40px;
    }}
    table {{
      width: 100%; border-collapse: collapse; background: #fff;
      border-radius: 10px; border: 1px solid #e2e8f0; overflow: hidden;
    }}
    thead tr {{ background: #0f172a; }}
    th {{
      color: #f8fafc; text-align: right; padding: 10px 14px;
      font-size: 11px; letter-spacing: 0.4px; font-weight: 600;
      border-bottom: 2px solid #1e293b; white-space: nowrap; cursor: pointer;
      user-select: none;
    }}
    th:hover {{ background: #1e3a5f; }}
    th.sort-asc::after  {{ content: " ▲"; font-size: 9px; }}
    th.sort-desc::after {{ content: " ▼"; font-size: 9px; }}
    td {{
      padding: 9px 14px; border-bottom: 1px solid #f1f5f9;
      vertical-align: middle;
    }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover td {{ background: #f8fafc; }}
    tr.hidden {{ display: none; }}

    .col-year  {{ width: 60px; color: #64748b; font-size: 12px; text-align: center; }}
    .col-title {{ min-width: 200px; }}
    .col-dir   {{ min-width: 140px; font-size: 12px; color: #374151; }}
    .col-genre {{ min-width: 90px; font-size: 12px; color: #64748b; }}
    .col-crew  {{ width: 55px; text-align: center; font-size: 12px; color: #64748b; }}
    .col-cast  {{ width: 55px; text-align: center; font-size: 12px; color: #64748b; }}
    .col-src   {{ width: 100px; text-align: center; }}

    .title-he {{ font-weight: 600; font-size: 13px; display: block; }}
    .title-en {{ font-size: 11px; color: #64748b; direction: ltr; display: block;
                 text-align: right; }}

    .badge {{
      display: inline-flex; align-items: center; padding: 2px 7px;
      border-radius: 10px; font-size: 10px; font-weight: 700;
      white-space: nowrap; color: #fff; margin: 1px;
    }}
    .badge-source {{ color: #fff; }}

    .no-results {{
      text-align: center; padding: 48px; color: #94a3b8; font-size: 14px;
      display: none;
    }}

    /* site nav */
    .site-nav {{ background:#0f172a; padding:6px 40px; display:flex; gap:4px; direction:rtl;
                position:sticky; top:0; z-index:1000; border-bottom:1px solid rgba(255,255,255,.05); }}
    .site-nav a {{ color:#94a3b8; text-decoration:none; font-size:12px; font-weight:500;
                  padding:5px 12px; border-radius:6px; transition:background .15s, color .15s; white-space:nowrap; }}
    .site-nav a:hover {{ background:#1e293b; color:#e2e8f0; text-decoration:none; }}
    .site-nav a.active {{ background:#1e3a5f; color:#fff; font-weight:600; }}
  </style>
</head>
<body>

<nav class="site-nav">
  <a href="graph.html">🔗 גרף ניגודי עניינים</a>
  <a href="connections_report.html">📋 דוח חיבורים</a>
  <a href="films.html" class="active">🎬 קטלוג סרטים</a>
</nav>

<div class="header">
  <div>
    <h1>קטלוג סרטים ישראליים</h1>
    <div class="subtitle">נגזר מ-EDB · JFC · Cinema of Israel</div>
  </div>
</div>

<div class="stats-bar">
  <div class="stat"><div class="value">{n_total:,}</div><div class="label">סרטים</div></div>
  <div class="stat"><div class="value">{year_min}–{year_max}</div><div class="label">בין השנים</div></div>
  <div class="stat"><div class="value">{len(sources_seen)}</div><div class="label">מקורות</div></div>
</div>

<div class="controls">
  <input class="search-box" type="text" id="search" placeholder="חיפוש לפי שם, במאי, ז'אנר..." />
  <div class="year-filter">
    <div class="year-filter-label">
      <span>שנה</span>
      <span>
        <span class="year-range-val" id="year-range-label" dir="ltr">{year_min} – {year_max}</span>
        &nbsp;<span class="year-reset" id="year-reset">איפוס</span>
      </span>
    </div>
    <div class="year-slider-wrap" dir="ltr">
      <div class="year-track"></div>
      <div class="year-fill" id="year-fill"></div>
      <input class="year-slider" type="range" id="year-from"
             min="0" max="{n_years_minus1}" value="0" step="1">
      <input class="year-slider" type="range" id="year-to"
             min="0" max="{n_years_minus1}" value="{n_years_minus1}" step="1">
    </div>
  </div>
  <div class="src-filters" id="src-filters">
    {source_filter_btns}
  </div>
  <div class="count-line" id="count-line">{n_total:,} סרטים</div>
</div>

<div class="table-wrap">
  <table id="films-table">
    <thead>
      <tr>
        <th data-col="year" class="sort-desc">שנה</th>
        <th data-col="title">שם הסרט</th>
        <th data-col="dir">במאי/ת</th>
        <th data-col="genre">ז'אנר</th>
        <th data-col="crew">צוות</th>
        <th data-col="cast">שחקנים</th>
        <th data-col="src">מקור</th>
      </tr>
    </thead>
    <tbody id="films-body">
{rows_html}
    </tbody>
  </table>
  <div class="no-results" id="no-results">לא נמצאו סרטים תואמים</div>
</div>

<script>
(function() {{
  var YEARS = {years_js};
  var rows = Array.from(document.querySelectorAll('#films-body tr'));
  var searchInput  = document.getElementById('search');
  var sliderFrom   = document.getElementById('year-from');
  var sliderTo     = document.getElementById('year-to');
  var yearLabel    = document.getElementById('year-range-label');
  var yearFill     = document.getElementById('year-fill');
  var yearReset    = document.getElementById('year-reset');
  var countLine    = document.getElementById('count-line');
  var noResults    = document.getElementById('no-results');
  var srcBtns      = Array.from(document.querySelectorAll('.src-btn'));

  var activeSources = new Set({json.dumps(sources_seen)});

  function updateSliderFill() {{
    var a = parseInt(sliderFrom.value);
    var b = parseInt(sliderTo.value);
    var lo = Math.min(a, b);
    var hi = Math.max(a, b);
    var max = parseInt(sliderFrom.max);
    yearFill.style.left  = (lo / max * 100) + '%';
    yearFill.style.width = ((hi - lo) / max * 100) + '%';
    yearLabel.textContent = YEARS[lo] + ' – ' + YEARS[hi];
  }}

  function getYearRange() {{
    var lo = Math.min(parseInt(sliderFrom.value), parseInt(sliderTo.value));
    var hi = Math.max(parseInt(sliderFrom.value), parseInt(sliderTo.value));
    return [YEARS[lo], YEARS[hi]];
  }}

  sliderFrom.addEventListener('input', function() {{ updateSliderFill(); filter(); }});
  sliderTo.addEventListener('input',   function() {{ updateSliderFill(); filter(); }});
  yearReset.addEventListener('click',  function() {{
    sliderFrom.value = 0;
    sliderTo.value   = sliderFrom.max;
    updateSliderFill(); filter();
  }});
  updateSliderFill();

  srcBtns.forEach(function(btn) {{
    btn.addEventListener('click', function() {{
      var src = btn.dataset.src;
      if (activeSources.has(src)) {{ activeSources.delete(src); btn.classList.remove('active'); }}
      else                         {{ activeSources.add(src);    btn.classList.add('active');    }}
      filter();
    }});
  }});

  function filter() {{
    var q = searchInput.value.trim().toLowerCase();
    var yr = getYearRange();
    var yFrom = yr[0], yTo = yr[1];
    var visible = 0;

    rows.forEach(function(row) {{
      var blob    = row.dataset.search || '';
      var year    = parseInt(row.dataset.year) || null;
      var sources = (row.dataset.sources || '').split(',');

      var matchQ = !q || blob.includes(q);
      var matchY = year === null || (year >= yFrom && year <= yTo);
      var matchS = sources.some(function(s) {{ return activeSources.has(s); }});

      if (matchQ && matchY && matchS) {{
        row.classList.remove('hidden'); visible++;
      }} else {{
        row.classList.add('hidden');
      }}
    }});

    countLine.textContent = visible.toLocaleString() + ' סרטים';
    noResults.style.display = visible === 0 ? 'block' : 'none';
  }}

  searchInput.addEventListener('input', filter);

  // Sorting
  var sortCol = 'year', sortDir = -1;
  var tbody = document.getElementById('films-body');
  var headers = Array.from(document.querySelectorAll('th[data-col]'));

  function sortRows(col, dir) {{
    var sorted = rows.slice().sort(function(a, b) {{
      var av, bv;
      if (col === 'year') {{
        av = parseInt(a.dataset.year) || 0;
        bv = parseInt(b.dataset.year) || 0;
        return dir * (bv - av);
      }} else if (col === 'title') {{
        av = a.querySelector('.title-he') ? a.querySelector('.title-he').textContent : '';
        bv = b.querySelector('.title-he') ? b.querySelector('.title-he').textContent : '';
      }} else if (col === 'dir') {{
        av = a.querySelector('.col-dir') ? a.querySelector('.col-dir').textContent : '';
        bv = b.querySelector('.col-dir') ? b.querySelector('.col-dir').textContent : '';
      }} else if (col === 'crew') {{
        av = parseInt(a.querySelector('.col-crew').textContent) || 0;
        bv = parseInt(b.querySelector('.col-crew').textContent) || 0;
        return dir * (bv - av);
      }} else if (col === 'cast') {{
        av = parseInt(a.querySelector('.col-cast').textContent) || 0;
        bv = parseInt(b.querySelector('.col-cast').textContent) || 0;
        return dir * (bv - av);
      }} else {{
        av = ''; bv = '';
      }}
      return dir * av.localeCompare(bv, 'he');
    }});
    sorted.forEach(function(r) {{ tbody.appendChild(r); }});
    // Re-sync rows order for filter
    rows.splice(0, rows.length);
    Array.from(tbody.querySelectorAll('tr')).forEach(function(r) {{ rows.push(r); }});
  }}

  headers.forEach(function(th) {{
    th.addEventListener('click', function() {{
      var col = th.dataset.col;
      if (col === sortCol) {{ sortDir *= -1; }}
      else {{ sortCol = col; sortDir = -1; }}
      headers.forEach(function(h) {{ h.classList.remove('sort-asc', 'sort-desc'); }});
      th.classList.add(sortDir === -1 ? 'sort-desc' : 'sort-asc');
      sortRows(sortCol, sortDir);
    }});
  }});
}})();
</script>
</body>
</html>
"""

    Path(OUTPUT).write_text(html, encoding="utf-8")
    print(f"Wrote {OUTPUT} — {n_total} films ({n_deduped} dupes merged), {Path(OUTPUT).stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
