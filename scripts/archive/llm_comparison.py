#!/usr/bin/env python3
"""
LLM Entity Extraction — Israeli film industry graph schema.
Uses OpenRouter as the API gateway (OpenAI-compatible interface).

Usage:
    export OPENROUTER_API_KEY=your_key
    python3 llm_comparison.py <pages_dir> <output_dir> [--pages N]
"""

import csv
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

from openai import OpenAI

# ── Config ────────────────────────────────────────────────────────────────────

OPENROUTER_BASE = "https://openrouter.ai/api/v1"

MODELS = {
    "gemini25_lite": "google/gemini-2.5-flash-lite",
}

EXTRACTION_PROMPT = """You are an investigative research assistant analyzing Israeli film industry data.

Extract entities and relationships from the following Hebrew web page into a structured JSON format for relationship-mapping visualization.

Focus ONLY on REAL people (not fictional film characters). Prioritize:
- Fund evaluators / committee members (לקטורים, חברי ועדה)
- Fund managers / directors (מנהלים, מנכ"לים)
- Grant recipients / supported filmmakers (מקבלי מענקים, במאים נתמכים)
- Board members / chairpersons (יו"ר, דירקטוריון)
- Government officials related to film funding (משרד התרבות)

Return a JSON object with this EXACT structure:

{{
  "metadata": {{
    "source_url": "{url}",
    "extraction_date": "{today}",
    "language": "he"
  }},
  "entities": {{
    "people": {{
      "person_001": {{
        "name_he": "שם מלא בעברית",
        "name_en": "English name if known",
        "aliases": [],
        "primary_roles": ["director", "producer"],
        "sources": ["{url}"]
      }}
    }},
    "organizations": {{
      "org_001": {{
        "name_he": "שם הארגון",
        "name_en": "English name if known",
        "type": "fund",
        "subtype": "public_film_fund",
        "active_years": [null, null],
        "sources": ["{url}"]
      }}
    }},
    "films": {{
      "film_001": {{
        "title_he": "שם הסרט",
        "title_en": "English title if known",
        "director_ids": ["person_001"],
        "year": null,
        "funded_by_org_ids": [],
        "sources": ["{url}"]
      }}
    }},
    "events": {{}}
  }},
  "roles": [
    {{
      "id": "role_001",
      "person_id": "person_001",
      "organization_id": "org_001",
      "role_type": "lector",
      "start_year": null,
      "end_year": null,
      "notes": "",
      "sources": ["{url}"]
    }}
  ],
  "relationships": [
    {{
      "id": "rel_001",
      "type": "directed",
      "source_id": "person_001",
      "target_id": "film_001",
      "year": null,
      "amount_nis": null,
      "via_person_id": null,
      "notes": "",
      "evidence_strength": "documented",
      "evidence": "Hebrew sentence supporting this",
      "sources": ["{url}"]
    }}
  ],
  "flags": []
}}

Rules:
- IDs are zero-padded sequential within this page (person_001, person_002 ...)
- Omit name_en if not confident
- For organizations type use: fund | production_company | distribution_company | cinema_chain | government_body | council | festival | union | school | other
- For role_type use: lector | appeal_lector | art_director | ceo | co_ceo | chairman | director_general | council_member | board_member | judge | mentor | festival_staff | owner | partner | filmmaker | other
- For relationship type use: produced | directed | acted_in | edited | wrote_screenplay | cinematographer | funded | co_produced | served_as_lector | evaluated_application | owns | affiliated_with | screened_at | judged_at | transferred_funds_to
- evidence_strength: documented (has clear source) | reported (secondary source) | alleged (unverified)
- Skip fictional characters entirely — do not include them even with is_fictional flag
- Only create a flag if there is a clear conflict of interest or governance issue visible on this page
- Return valid JSON only, no other text

Page content:
{content}"""


# ── Text preprocessing ────────────────────────────────────────────────────────

BOILERPLATE_PATTERNS = [
    re.compile(r'\[מעבר לתוכן[^\]]*\][^\n]*\n?'),
    re.compile(r'#{1,6}\s*תפריט לטלפון.*?(?=#{1,6}|\Z)', re.DOTALL),
    re.compile(r'#{1,6}\s*חיפוש\s*\nסגור\s*\nחיפוש\s*\n'),
    re.compile(r'## Links\n[\s\S]*', re.DOTALL),
]

def clean_text(text):
    for p in BOILERPLATE_PATTERNS:
        text = p.sub('', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r' \1 ', text)
    text = re.sub(r'\*([^*]+)\*',     r' \1 ', text)
    text = re.sub(r'#{1,6}\s*',       ' ',     text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()

def load_page(meta_path):
    md_path = meta_path.parent / meta_path.name.replace('.meta.json', '.md')
    try:
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        raw  = md_path.read_text(encoding='utf-8')
        content = json.loads(raw).get('content', '') if raw.strip().startswith('{') else raw
        return meta.get('url', ''), clean_text(content)
    except Exception:
        return '', ''


# ── LLM caller ────────────────────────────────────────────────────────────────

class LLMExtractor:
    def __init__(self, api_key):
        self.client = OpenAI(api_key=api_key, base_url=OPENROUTER_BASE)
        self.usage = {m: {'input_tokens': 0, 'output_tokens': 0, 'calls': 0, 'errors': 0}
                      for m in MODELS}

    def _parse_json(self, raw):
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r'^```[a-z]*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw.strip())
        start = raw.find('{')
        if start > 0:
            raw = raw[start:]
        return json.JSONDecoder().raw_decode(raw)

    def extract(self, model_key, url, content, max_chars=6000):
        model_id = MODELS[model_key]
        content  = content[:max_chars]
        prompt   = EXTRACTION_PROMPT.format(url=url, content=content, today=date.today().isoformat())

        kwargs = dict(
            model=model_id,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )

        raw = ""
        for attempt in range(2):
            try:
                resp = self.client.chat.completions.create(**kwargs)
                raw  = resp.choices[0].message.content or ""
                result, _ = self._parse_json(raw)
                if resp.usage:
                    self.usage[model_key]['input_tokens']  += resp.usage.prompt_tokens
                    self.usage[model_key]['output_tokens'] += resp.usage.completion_tokens
                self.usage[model_key]['calls'] += 1
                return result
            except json.JSONDecodeError as e:
                if attempt == 0:
                    kwargs['messages'] = [
                        {"role": "user",      "content": prompt},
                        {"role": "assistant", "content": raw},
                        {"role": "user",      "content": "Your JSON was malformed. Rewrite it as valid JSON only. Shorten evidence fields to avoid special characters that break JSON."},
                    ]
                    time.sleep(1)
                else:
                    self.usage[model_key]['errors'] += 1
                    print(f"    ⚠ {model_key} JSON error: {e} | raw: {repr(raw[:200])}")
                    return _empty_result()
            except Exception as e:
                self.usage[model_key]['errors'] += 1
                print(f"    ⚠ {model_key} error: {e} | raw: {repr(raw[:200]) if raw else '(no response)'}")
                return _empty_result()

    def cost_summary(self):
        pricing = {
            'gemini25_lite':  {'input': 0.10, 'output': 0.40},
            'gemini25_flash': {'input': 0.30, 'output': 2.50},
        }
        print("\n💰 Cost Summary:")
        for m in MODELS:
            p = pricing.get(m, {'input': 0, 'output': 0})
            u = self.usage[m]
            cost = u['input_tokens'] / 1e6 * p['input'] + u['output_tokens'] / 1e6 * p['output']
            print(f"  {m:16s}: {u['input_tokens']:,} in + {u['output_tokens']:,} out  →  ${cost:.4f}"
                  f"  ({u['calls']} calls, {u['errors']} errors)")


def _empty_result():
    return {"metadata": {}, "entities": {"people": {}, "organizations": {}, "films": {}, "events": {}},
            "roles": [], "relationships": [], "flags": []}

def _count(data):
    e = data.get('entities', {})
    people = len(e.get('people', {}))
    orgs   = len(e.get('organizations', {}))
    films  = len(e.get('films', {}))
    rels   = len(data.get('relationships', []))
    roles  = len(data.get('roles', []))
    flags  = len(data.get('flags', []))
    return people, orgs, films, rels, roles, flags


# ── Report writer ────────────────────────────────────────────────────────────

def _write_report(output_dir, results, all_pages, usage):
    run_date = date.today().isoformat()
    pricing  = {'gemini25_lite': {'input': 0.10, 'output': 0.40},
                'gemini25_flash': {'input': 0.30, 'output': 2.50}}

    # ── Per-model stats ───────────────────────────────────────────────────────
    stats = {}
    for model_key in results:
        totals = {'people': 0, 'orgs': 0, 'films': 0, 'rels': 0, 'roles': 0, 'flags': 0}
        unique_people, unique_orgs, unique_films = set(), set(), set()
        rel_types, role_types = {}, {}
        errors, elapsed_list = 0, []
        for d in results[model_key]:
            p, o, f, r, ro, fl = _count(d)
            totals['people'] += p; totals['orgs'] += o; totals['films'] += f
            totals['rels'] += r;   totals['roles'] += ro; totals['flags'] += fl
            for person in d.get('entities', {}).get('people', {}).values():
                n = person.get('name_he') or person.get('name_en', '')
                if n: unique_people.add(n)
            for org in d.get('entities', {}).get('organizations', {}).values():
                n = org.get('name_he', '')
                if n: unique_orgs.add(n)
            for film in d.get('entities', {}).get('films', {}).values():
                n = film.get('title_he', '')
                if n: unique_films.add(n)
            for rel in d.get('relationships', []):
                t = rel.get('type', 'unknown')
                rel_types[t] = rel_types.get(t, 0) + 1
            for role in d.get('roles', []):
                t = role.get('role_type', 'unknown')
                role_types[t] = role_types.get(t, 0) + 1
            if '_elapsed_sec' in d:
                elapsed_list.append(d['_elapsed_sec'])

        u   = usage.get(model_key, {})
        p   = pricing.get(model_key, {'input': 0, 'output': 0})
        cost = u.get('input_tokens', 0) / 1e6 * p['input'] + u.get('output_tokens', 0) / 1e6 * p['output']
        avg_elapsed = sum(elapsed_list) / len(elapsed_list) if elapsed_list else 0

        stats[model_key] = {
            'totals': totals,
            'unique_people': sorted(unique_people),
            'unique_orgs':   sorted(unique_orgs),
            'unique_films':  sorted(unique_films),
            'rel_types':     dict(sorted(rel_types.items(), key=lambda x: -x[1])),
            'role_types':    dict(sorted(role_types.items(), key=lambda x: -x[1])),
            'cost':          cost,
            'avg_elapsed':   avg_elapsed,
            'calls':         u.get('calls', 0),
            'errors':        u.get('errors', 0),
            'input_tokens':  u.get('input_tokens', 0),
            'output_tokens': u.get('output_tokens', 0),
        }

    # ── Markdown report ───────────────────────────────────────────────────────
    md_lines = [
        f"# Extraction Run Report — {run_date}",
        f"\n**Pages processed:** {len(all_pages)}  ",
        f"**Models:** {', '.join(results.keys())}  ",
        f"**Run date:** {run_date}\n",
    ]

    for model_key, s in stats.items():
        t = s['totals']
        md_lines += [
            f"## {model_key} (`{MODELS[model_key]}`)",
            f"\n### Counts",
            f"| Metric | Value |",
            f"|---|---|",
            f"| Unique people (deduplicated) | {len(s['unique_people'])} |",
            f"| Total people extractions | {t['people']} |",
            f"| Unique organizations | {len(s['unique_orgs'])} |",
            f"| Unique films | {len(s['unique_films'])} |",
            f"| Relationships | {t['rels']} |",
            f"| Roles | {t['roles']} |",
            f"| Flags | {t['flags']} |",
            f"\n### Performance & Cost",
            f"| Metric | Value |",
            f"|---|---|",
            f"| API calls | {s['calls']} ({s['errors']} errors) |",
            f"| Avg response time | {s['avg_elapsed']:.1f}s |",
            f"| Tokens | {s['input_tokens']:,} in / {s['output_tokens']:,} out |",
            f"| Estimated cost | ${s['cost']:.4f} |",
            f"\n### Relationship Types",
            "| Type | Count |", "|---|---|",
        ]
        for rt, cnt in s['rel_types'].items():
            md_lines.append(f"| `{rt}` | {cnt} |")

        md_lines += [f"\n### Role Types", "| Type | Count |", "|---|---|"]
        for rt, cnt in s['role_types'].items():
            md_lines.append(f"| `{rt}` | {cnt} |")

        md_lines += [f"\n### People Found ({len(s['unique_people'])})"]
        md_lines.append(", ".join(f"`{n}`" for n in s['unique_people'][:50]))
        if len(s['unique_people']) > 50:
            md_lines.append(f"_(and {len(s['unique_people'])-50} more)_")

        md_lines += [f"\n### Organizations Found ({len(s['unique_orgs'])})"]
        md_lines.append(", ".join(f"`{n}`" for n in s['unique_orgs'][:30]))

        md_lines.append("\n---\n")

    md_path = output_dir / f'run_report_{run_date}.md'
    md_path.write_text('\n'.join(md_lines), encoding='utf-8')
    print(f"✅ MD report:    {md_path}")

    # ── HTML report ───────────────────────────────────────────────────────────
    def md_table_to_html(lines):
        rows = [l for l in lines if l.startswith('|') and '---' not in l]
        html = ['<table>']
        for i, row in enumerate(rows):
            cells = [c.strip() for c in row.strip('|').split('|')]
            tag = 'th' if i == 0 else 'td'
            html.append('<tr>' + ''.join(f'<{tag}>{c}</{tag}>' for c in cells) + '</tr>')
        html.append('</table>')
        return '\n'.join(html)

    html_sections = []
    for model_key, s in stats.items():
        t = s['totals']
        rt_rows = ''.join(f'<tr><td><code>{k}</code></td><td>{v}</td></tr>'
                          for k, v in s['rel_types'].items())
        role_rows = ''.join(f'<tr><td><code>{k}</code></td><td>{v}</td></tr>'
                             for k, v in s['role_types'].items())
        people_tags = ' '.join(f'<span class="tag">{n}</span>' for n in s['unique_people'])
        org_tags    = ' '.join(f'<span class="tag org">{n}</span>' for n in s['unique_orgs'])

        html_sections.append(f"""
<section>
  <h2>{model_key} <small>({MODELS[model_key]})</small></h2>
  <div class="stats-grid">
    <div class="stat"><div class="num">{len(s['unique_people'])}</div><div>Unique people</div></div>
    <div class="stat"><div class="num">{len(s['unique_orgs'])}</div><div>Organizations</div></div>
    <div class="stat"><div class="num">{len(s['unique_films'])}</div><div>Films</div></div>
    <div class="stat"><div class="num">{t['rels']}</div><div>Relationships</div></div>
    <div class="stat"><div class="num">{t['roles']}</div><div>Roles</div></div>
    <div class="stat"><div class="num">{t['flags']}</div><div>Flags</div></div>
    <div class="stat"><div class="num">${s['cost']:.4f}</div><div>Est. cost</div></div>
    <div class="stat"><div class="num">{s['avg_elapsed']:.1f}s</div><div>Avg response</div></div>
  </div>
  <div class="tables">
    <div>
      <h3>Relationship Types</h3>
      <table><tr><th>Type</th><th>Count</th></tr>{rt_rows}</table>
    </div>
    <div>
      <h3>Role Types</h3>
      <table><tr><th>Type</th><th>Count</th></tr>{role_rows}</table>
    </div>
  </div>
  <h3>People ({len(s['unique_people'])})</h3>
  <div class="tags">{people_tags}</div>
  <h3>Organizations ({len(s['unique_orgs'])})</h3>
  <div class="tags">{org_tags}</div>
</section>""")

    html = f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<title>Extraction Report — {run_date}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 1100px; margin: 2rem auto; padding: 0 1rem; color: #222; }}
  h1 {{ border-bottom: 2px solid #333; }}
  h2 {{ margin-top: 2rem; color: #1a5276; }}
  small {{ font-weight: normal; color: #666; font-size: .75em; }}
  .stats-grid {{ display: flex; flex-wrap: wrap; gap: .75rem; margin: 1rem 0; }}
  .stat {{ background: #f0f4f8; border-radius: 8px; padding: .75rem 1.25rem; text-align: center; min-width: 100px; }}
  .stat .num {{ font-size: 1.6rem; font-weight: 700; color: #1a5276; }}
  .tables {{ display: flex; gap: 2rem; flex-wrap: wrap; margin: 1rem 0; }}
  table {{ border-collapse: collapse; font-size: .9em; }}
  th, td {{ padding: .3rem .7rem; border: 1px solid #ddd; text-align: right; }}
  th {{ background: #eaf0fb; }}
  .tags {{ display: flex; flex-wrap: wrap; gap: .4rem; margin: .5rem 0 1.5rem; }}
  .tag {{ background: #d6eaf8; border-radius: 4px; padding: .2rem .5rem; font-size: .85em; }}
  .tag.org {{ background: #d5f5e3; }}
  section {{ border-bottom: 1px solid #eee; padding-bottom: 2rem; }}
</style>
</head>
<body>
<h1>Extraction Run Report — {run_date}</h1>
<p><strong>Pages processed:</strong> {len(all_pages)} &nbsp;|&nbsp;
   <strong>Models:</strong> {', '.join(results.keys())} &nbsp;|&nbsp;
   <strong>Run date:</strong> {run_date}</p>
{''.join(html_sections)}
</body>
</html>"""

    html_path = output_dir / f'run_report_{run_date}.html'
    html_path.write_text(html, encoding='utf-8')
    print(f"✅ HTML report:  {html_path}")


# ── Runner ────────────────────────────────────────────────────────────────────

def run_extraction(pages_dir, output_dir, max_pages=30):
    api_key = os.environ.get('OPENROUTER_API_KEY')
    if not api_key:
        print("❌ OPENROUTER_API_KEY not set")
        sys.exit(1)

    pages_dir  = Path(pages_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    meta_files = sorted(pages_dir.glob('*.meta.json'))[:max_pages]
    model_list = ', '.join(MODELS.keys())
    print(f"\nProcessing {len(meta_files)} pages with {model_list}...\n")

    extractor = LLMExtractor(api_key)
    results   = {m: [] for m in MODELS}
    all_pages = []

    for i, mf in enumerate(meta_files, 1):
        url, content = load_page(mf)
        if not content:
            continue

        print(f"[{i}/{len(meta_files)}] {mf.name[:65]}", flush=True)
        page_results = {'file': mf.name, 'url': url}

        for model_key in MODELS:
            print(f"  → {model_key}...", end=' ', flush=True)
            t0      = time.time()
            data    = extractor.extract(model_key, url, content)
            elapsed = time.time() - t0
            people, orgs, films, rels, roles, flags = _count(data)
            print(f"{people}p {orgs}o {films}f {rels}r {roles}roles {flags}flags ({elapsed:.1f}s)")
            data['_elapsed_sec'] = round(elapsed, 2)
            page_results[model_key] = data
            results[model_key].append(data)

        all_pages.append(page_results)
        time.sleep(0.3)

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("EXTRACTION SUMMARY")
    print("="*60)

    for model_key in MODELS:
        totals = {'people': 0, 'orgs': 0, 'films': 0, 'rels': 0, 'roles': 0, 'flags': 0}
        all_people_names = set()
        for d in results[model_key]:
            p, o, f, r, ro, fl = _count(d)
            totals['people'] += p
            totals['orgs']   += o
            totals['films']  += f
            totals['rels']   += r
            totals['roles']  += ro
            totals['flags']  += fl
            for person in d.get('entities', {}).get('people', {}).values():
                name = person.get('name_he') or person.get('name_en', '')
                if name:
                    all_people_names.add(name)

        print(f"\n{model_key} ({MODELS[model_key]}):")
        print(f"  Unique people (across pages): {len(all_people_names)}")
        print(f"  Total people extractions:     {totals['people']}")
        print(f"  Organizations:                {totals['orgs']}")
        print(f"  Films:                        {totals['films']}")
        print(f"  Relationships:                {totals['rels']}")
        print(f"  Roles:                        {totals['roles']}")
        print(f"  Flags:                        {totals['flags']}")

    extractor.cost_summary()

    # ── Export ────────────────────────────────────────────────────────────────
    json_path = output_dir / 'llm_extraction.json'
    json_path.write_text(
        json.dumps({'pages': all_pages, 'model_names': MODELS}, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )
    print(f"\n✅ Full results: {json_path}")

    _write_report(output_dir, results, all_pages, extractor.usage)

    # CSV: all people across all pages for quick review
    if results:
        first_model = list(MODELS.keys())[0]
        csv_path = output_dir / 'extracted_people.csv'
        rows = []
        for page in all_pages:
            url = page.get('url', '')
            data = page.get(first_model, {})
            for pid, person in data.get('entities', {}).get('people', {}).items():
                rows.append({
                    'url':           url,
                    'person_id':     pid,
                    'name_he':       person.get('name_he', ''),
                    'name_en':       person.get('name_en', ''),
                    'primary_roles': ', '.join(person.get('primary_roles', [])),
                })
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=['url', 'person_id', 'name_he', 'name_en', 'primary_roles'])
            w.writeheader()
            w.writerows(rows)
        print(f"✅ People CSV:   {csv_path}")


# ── Entry point ───────────────────────────────────────────────────────────────

class Tee:
    """Write to both stdout and a log file simultaneously."""
    def __init__(self, path):
        self.file = open(path, 'w', encoding='utf-8', buffering=1)
        self.stdout = sys.stdout
    def write(self, data):
        self.stdout.write(data)
        self.file.write(data)
    def flush(self):
        self.stdout.flush()
        self.file.flush()
    def close(self):
        self.file.close()


if __name__ == '__main__':
    pages   = sys.argv[1] if len(sys.argv) > 1 else './arava_film_fund/pages'
    out     = sys.argv[2] if len(sys.argv) > 2 else './arava_film_fund/output'
    pages_n = int(sys.argv[3]) if len(sys.argv) > 3 else 30

    if not os.path.exists(pages):
        print(f"❌ Pages dir not found: {pages}")
        sys.exit(1)

    os.makedirs(out, exist_ok=True)
    log_path = Path(out) / f'run_{date.today().isoformat()}.log'
    tee = Tee(log_path)
    sys.stdout = tee
    print(f"Logging to {log_path}")

    try:
        run_extraction(pages, out, max_pages=pages_n)
    finally:
        sys.stdout = tee.stdout
        tee.close()
