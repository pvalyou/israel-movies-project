#!/usr/bin/env python3
"""
NER Comparison: Regex vs DictaBERT vs heBERT
Runs all three person-extraction methods on the same pages and compares results.
"""

import json
import os
import re
import sys
import csv
from pathlib import Path
from collections import defaultdict

# ── Boilerplate & disqualifiers (shared with film_data_extractor.py) ──────────

BOILERPLATE_PATTERNS = [
    re.compile(r'\[מעבר לתוכן[^\]]*\][^\n]*\n?'),
    re.compile(r'#{1,6}\s*תפריט לטלפון.*?(?=#{1,6}|\Z)', re.DOTALL),
    re.compile(r'#{1,6}\s*חיפוש\s*\nסגור\s*\nחיפוש\s*\n'),
    re.compile(r'## Links\n[\s\S]*', re.DOTALL),
]

NAME_DISQUALIFIERS = re.compile(
    r'ביותר|פסטיבל|הסרטים|הבינלאומי|הטוב|השנה|זוכה|פרס|'
    r'ינואר|פברואר|מרץ|אפריל|מאי|יוני|יולי|אוגוסט|ספטמבר|אוקטובר|נובמבר|דצמבר|'
    r'ישראל|ירושלים|תל.?אביב|חיפה|באר.?שבע|נגב|ערבה|מדבר|'
    r'הגרמני|הצרפתי|הישראלי|האיטלקי|האמריקאי|הבריטי|הספרדי|היפני|'
    r'הסיני|הרוסי|הטורקי|האיראני|הדנמרקי|ההונגרי|הרומני|'
    r'\bבין\b|\bכאן\b|\bשם\b|\bאחד\b|\bכמו\b|\bכבר\b|\bעוד\b|\bרק\b|'
    r'מחבר|מציג|מספר|מראה|מציאות|מנסה|מוצא|עוסק|מתמודד|מגלה'
)

NAME_STOPWORDS = {
    'מעבר לתוכן', 'תפריט לטלפון', 'ארכיון סרטים', 'חיפוש סגור',
    'קרא עוד', 'כל המדינות', 'כל הסרטים', 'כניסה לסרטים',
    'ארץ ערבה', 'ימי מדבר', 'נוף צוקים', 'קרן קולנוע',
    'סרטי קרן', 'סרטים בערבה', 'חבילות לינה', 'קצר במדבר',
}

def normalize_name(name):
    """Normalize name for comparison: strip whitespace, unify apostrophe variants."""
    name = name.strip()
    name = re.sub(r"[\u2018\u2019\u201a\u201b\u02bc\u05f3]", "'", name)
    # Collapse tokenizer-spaced apostrophes: "ג ' ונתן" → "ג'ונתן"
    name = re.sub(r"([א-ת])\s+'\s*", r"\1'", name)
    name = re.sub(r'\s+', ' ', name)
    return name

def preprocess_markdown(text):
    """Strip markdown formatting while preserving spaces between tokens."""
    text = re.sub(r'\*\*([^*]+)\*\*', r' \1 ', text)   # **bold**
    text = re.sub(r'\*([^*]+)\*',     r' \1 ', text)   # *italic*
    text = re.sub(r'__([^_]+)__',     r' \1 ', text)   # __bold__
    text = re.sub(r'_([^_]+)_',       r' \1 ', text)   # _italic_
    text = re.sub(r'#{1,6}\s*',       ' ',     text)   # headings
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # [text](url)
    text = re.sub(r' {2,}', ' ', text)
    return text

ROLE_PREFIXES = re.compile(
    r'(?:ה?במאי|ה?במאית|ה?מפיק|ה?מפיקה|ה?תסריטאי|ה?תסריטאית|'
    r'ה?צלם|ה?צלמת|ה?מוזיקאי|ה?מלחין|ה?עורך|ה?עורכת|'
    r'ה?מנהל|ה?מנהלת|מנכ"ל|מנכ״ל|ה?יוצר|ה?יוצרת|'
    r'ה?כוריאוגרף|ה?אמן|ה?אמנית|ה?שחקן|ה?שחקנית|'
    r'ה?מנהל האמנותי|ה?מנהלת האמנותית|ה?יו"ר|יו״ר|ה?לקטור|ה?לקטורית|'
    r'בימוי|בבימוי)'
)

HEBREW_WORD = r'[א-ת][א-ת\'\-״׳]*'


def clean_boilerplate(text):
    for p in BOILERPLATE_PATTERNS:
        text = p.sub('', text)
    return text


def load_page(path):
    with open(path, encoding='utf-8') as f:
        raw = f.read()
    if raw.strip().startswith('{'):
        data = json.loads(raw)
        return data.get('url', ''), data.get('content', '')
    return '', raw


# ── Method 1: Regex (same logic as film_data_extractor.py) ───────────────────

def regex_extract(text):
    text = preprocess_markdown(clean_boilerplate(text))
    names = set()
    hw = HEBREW_WORD
    role_strip = re.compile(str(ROLE_PREFIXES.pattern) + r'\s+')

    # Strategy 1: role keyword → name
    pat1 = re.compile(str(ROLE_PREFIXES.pattern) + r'\s+((?:' + hw + r'\s+){1,3}' + hw + r')')
    for m in pat1.finditer(text):
        c = normalize_name(m.group(1))
        if not NAME_DISQUALIFIERS.search(c):
            names.add(c)

    # Strategy 2: bullet list items
    pat2 = re.compile(r'^\s*\*\s+((?:' + hw + r'\s+){1,4}' + hw + r')\s*$', re.MULTILINE)
    for m in pat2.finditer(text):
        c = normalize_name(role_strip.sub('', m.group(1).strip(), count=1))
        if c not in NAME_STOPWORDS and len(c) >= 4 and not NAME_DISQUALIFIERS.search(c):
            names.add(c)

    # Strategy 3: pipe-separated lists
    pat3 = re.compile(r'((?:' + hw + r'\s+){1,3}' + hw + r')\s*\|')
    for m in pat3.finditer(text):
        c = normalize_name(m.group(1))
        if c not in NAME_STOPWORDS and len(c) >= 4 and not NAME_DISQUALIFIERS.search(c):
            names.add(c)

    return names


# ── Method 2: DictaBERT NER ──────────────────────────────────────────────────

def load_dictabert():
    from transformers import pipeline
    print("Loading DictaBERT NER model...", flush=True)
    return pipeline('ner', model='dicta-il/dictabert-ner', aggregation_strategy='simple')


def dictabert_extract(text, pipe, max_chars=2000):
    text = preprocess_markdown(clean_boilerplate(text))
    names = set()
    chunks = [text[i:i+max_chars] for i in range(0, min(len(text), 10000), max_chars)]
    for chunk in chunks:
        try:
            for ent in pipe(chunk):
                if ent['entity_group'] == 'PER' and ent['score'] > 0.80:
                    name = normalize_name(ent['word'])
                    if len(name) >= 3:
                        names.add(name)
        except Exception:
            pass
    return names


# ── Method 3: heBERT NER ─────────────────────────────────────────────────────

def load_hebert():
    from transformers import pipeline
    print("Loading heBERT NER model...", flush=True)
    return pipeline('ner', model='avichr/heBERT_NER', aggregation_strategy='simple')


def hebert_extract(text, pipe, max_chars=500):  # heBERT has 512-token limit
    text = preprocess_markdown(clean_boilerplate(text))
    names = set()
    chunks = [text[i:i+max_chars] for i in range(0, min(len(text), 10000), max_chars)]
    for chunk in chunks:
        try:
            for ent in pipe(chunk):
                if 'PERS' in ent['entity_group'] and ent['score'] > 0.70:
                    name = normalize_name(ent['word'])
                    if len(name) >= 3:
                        names.add(name)
        except Exception:
            pass
    return names


# ── Comparison runner ─────────────────────────────────────────────────────────

def run_comparison(pages_dir, output_dir, max_pages=None):
    pages_dir = Path(pages_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    meta_files = sorted(pages_dir.glob('*.meta.json'))
    if max_pages:
        meta_files = meta_files[:max_pages]

    print(f"\nProcessing {len(meta_files)} pages with 3 methods...\n")

    # Load NER models once
    dictabert = load_dictabert()
    hebert = load_hebert()

    # Per-method aggregate name → source URLs
    results = {
        'regex':     defaultdict(set),
        'dictabert': defaultdict(set),
        'hebert':    defaultdict(set),
    }

    for i, meta_file in enumerate(meta_files, 1):
        md_path = meta_file.parent / meta_file.name.replace('.meta.json', '.md')
        if not md_path.exists():
            continue
        url, text = load_page(md_path)
        print(f"  [{i}/{len(meta_files)}] {meta_file.name[:60]}", flush=True)

        for name in regex_extract(text):
            results['regex'][name].add(url)
        for name in dictabert_extract(text, dictabert):
            results['dictabert'][name].add(url)
        for name in hebert_extract(text, hebert):
            results['hebert'][name].add(url)

    # ── Build comparison sets ─────────────────────────────────────────────────
    r = set(results['regex'])
    d = set(results['dictabert'])
    h = set(results['hebert'])

    all_names = r | d | h
    in_all    = r & d & h
    ner_only  = (d & h) - r       # both NER agree but regex missed
    regex_only = r - d - h        # only regex found it (likely noise)
    d_only    = d - r - h
    h_only    = h - r - d

    print(f"\n{'='*60}")
    print("COMPARISON SUMMARY")
    print(f"{'='*60}")
    print(f"  Regex:      {len(r)} names")
    print(f"  DictaBERT:  {len(d)} names")
    print(f"  heBERT:     {len(h)} names")
    print(f"  All unique: {len(all_names)}")
    print(f"\n  Found by all 3:          {len(in_all)}")
    print(f"  Both NER, not regex:     {len(ner_only)}  ← regex missed these")
    print(f"  Only regex (likely noise): {len(regex_only)}")
    print(f"  Only DictaBERT:          {len(d_only)}")
    print(f"  Only heBERT:             {len(h_only)}")

    if in_all:
        print(f"\nTop names found by ALL 3 methods:")
        by_sources = sorted(in_all, key=lambda n: len(results['dictabert'][n]), reverse=True)
        for name in by_sources[:20]:
            print(f"  • {name} ({len(results['dictabert'][name])} pages)")

    if ner_only:
        print(f"\nNames both NER models found but regex MISSED (worth adding):")
        for name in sorted(ner_only, key=lambda n: len(results['dictabert'][n]), reverse=True)[:20]:
            print(f"  • {name}")

    if regex_only:
        print(f"\nNames ONLY regex found (likely noise — review):")
        for name in sorted(regex_only, key=lambda n: len(results['regex'][n]), reverse=True)[:20]:
            print(f"  • {name}")

    # ── Export CSV ────────────────────────────────────────────────────────────
    csv_path = output_dir / 'ner_comparison.csv'
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['name', 'regex', 'dictabert', 'hebert',
                         'regex_sources', 'dictabert_sources', 'hebert_sources'])
        for name in sorted(all_names):
            writer.writerow([
                name,
                '✓' if name in r else '',
                '✓' if name in d else '',
                '✓' if name in h else '',
                len(results['regex'][name]),
                len(results['dictabert'][name]),
                len(results['hebert'][name]),
            ])
    print(f"\n✅ Comparison CSV: {csv_path}")

    # ── Export JSON ───────────────────────────────────────────────────────────
    json_path = output_dir / 'ner_comparison.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            'summary': {
                'regex_count': len(r),
                'dictabert_count': len(d),
                'hebert_count': len(h),
                'all_count': len(all_names),
                'found_by_all_3': len(in_all),
                'ner_only_missed_by_regex': len(ner_only),
                'regex_only_noise': len(regex_only),
            },
            'found_by_all_3': sorted(in_all),
            'ner_only_missed_by_regex': sorted(ner_only),
            'regex_only': sorted(regex_only),
            'dictabert_only': sorted(d_only),
            'hebert_only': sorted(h_only),
        }, f, ensure_ascii=False, indent=2)
    print(f"✅ Comparison JSON: {json_path}")


if __name__ == '__main__':
    pages = sys.argv[1] if len(sys.argv) > 1 else './arava_film_fund/pages'
    out   = sys.argv[2] if len(sys.argv) > 2 else './arava_film_fund/output'
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else None

    if not os.path.exists(pages):
        print(f"❌ Pages directory not found: {pages}")
        sys.exit(1)

    run_comparison(pages, out, max_pages=limit)
