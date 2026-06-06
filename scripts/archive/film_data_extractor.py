#!/usr/bin/env python3
"""
Film Governance Data Extractor
Extracts entities and relationships from scraped web data (meta.json + markdown pairs)
Uses DictaBERT + heBERT NER models for Hebrew person extraction.
No external API calls - runs entirely locally.
"""

import csv
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


# ── Text preprocessing ────────────────────────────────────────────────────────

BOILERPLATE_PATTERNS = [
    re.compile(r'\[מעבר לתוכן[^\]]*\][^\n]*\n?'),
    re.compile(r'#{1,6}\s*תפריט לטלפון.*?(?=#{1,6}|\Z)', re.DOTALL),
    re.compile(r'#{1,6}\s*חיפוש\s*\nסגור\s*\nחיפוש\s*\n'),
    re.compile(r'## Links\n[\s\S]*', re.DOTALL),
]


def clean_text(text):
    """Strip boilerplate and markdown formatting, preserving word spacing."""
    for p in BOILERPLATE_PATTERNS:
        text = p.sub('', text)
    # Markdown bold/italic → spaced tokens (prevents word concatenation)
    text = re.sub(r'\*\*([^*]+)\*\*', r' \1 ', text)
    text = re.sub(r'\*([^*]+)\*',     r' \1 ', text)
    text = re.sub(r'__([^_]+)__',     r' \1 ', text)
    text = re.sub(r'_([^_]+)_',       r' \1 ', text)
    text = re.sub(r'#{1,6}\s*',       ' ',     text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r' {2,}', ' ', text)
    return text


def normalize_name(name):
    """Normalize whitespace and apostrophe variants for consistent comparison."""
    name = name.strip()
    # Unify apostrophe variants
    name = re.sub(r"[\u2018\u2019\u201a\u201b\u02bc\u05f3]", "'", name)
    # Collapse tokenizer-spaced apostrophes: "ג ' ונתן" → "ג'ונתן"
    name = re.sub(r"([א-ת])\s+'\s*", r"\1'", name)
    name = re.sub(r'\s+', ' ', name)
    return name


# ── NER models ────────────────────────────────────────────────────────────────

class NERExtractor:
    def __init__(self):
        from transformers import pipeline
        print("Loading DictaBERT NER...", flush=True)
        self.dictabert = pipeline(
            'ner', model='dicta-il/dictabert-ner', aggregation_strategy='simple'
        )
        print("Loading heBERT NER...", flush=True)
        self.hebert = pipeline(
            'ner', model='avichr/heBERT_NER', aggregation_strategy='simple'
        )

    # Dropped-prefix: tokenizers split ג'ונתן → ג' + ונתן (no space between letter and apostrophe)
    _PREFIX_RE = re.compile(r"([א-ת]['\u05f3\u2019״׳])(?=\S)")

    def _recover_prefix(self, name, chunk):
        """If the tokenizer dropped a ג'/ז' prefix, recover it from the source text.
        Only matches when letter+apostrophe appear without whitespace before the name."""
        pattern = re.compile(self._PREFIX_RE.pattern + re.escape(name))
        m = pattern.search(chunk)
        return m.group(1) + name if m else name

    # Max chars a valid person name can have (filters heBERT over-aggregation)
    _MAX_NAME_CHARS = 40
    # Max words in a valid person name
    _MAX_NAME_WORDS = 5

    def _run_model(self, pipe, text, max_chars, per_label, min_score):
        names = set()
        chunks = [text[i:i+max_chars] for i in range(0, min(len(text), 12000), max_chars)]
        for chunk in chunks:
            try:
                for ent in pipe(chunk):
                    if ent['entity_group'] == per_label and ent['score'] >= min_score:
                        name = normalize_name(ent['word'])
                        # Skip over-aggregated multi-name strings
                        if len(name) > self._MAX_NAME_CHARS:
                            continue
                        if len(name.split()) > self._MAX_NAME_WORDS:
                            continue
                        name = self._recover_prefix(name, chunk)
                        if len(name) >= 3:
                            names.add(name)
            except Exception:
                pass
        return names

    def extract(self, text):
        """
        Run both models and return names with confidence level:
          'high'   — both models agree
          'medium' — only one model found it
        Returns: dict  name → {'confidence': str, 'models': list}
        """
        d = self._run_model(self.dictabert, text,
                            max_chars=2000, per_label='PER',   min_score=0.80)
        h = self._run_model(self.hebert,    text,
                            max_chars=500,  per_label='B_PERS', min_score=0.70)

        results = {}
        for name in d | h:
            in_d, in_h = name in d, name in h
            results[name] = {
                'confidence': 'high' if (in_d and in_h) else 'medium',
                'models': (['dictabert'] if in_d else []) + (['hebert'] if in_h else []),
            }
        return results


# ── Main extractor ────────────────────────────────────────────────────────────

class FilmDataExtractor:
    def __init__(self, input_dir, output_dir):
        self.input_dir  = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        self.entities      = {"people": {}, "organizations": {}}
        self.relationships = []
        self.conflicts     = []
        self.processed_files = []

        self.ner = NERExtractor()

    # ── File I/O ──────────────────────────────────────────────────────────────

    def find_scraped_files(self):
        files = sorted(self.input_dir.glob("*.meta.json"))
        print(f"Found {len(files)} meta.json files")
        return files

    def load_file_pair(self, meta_file):
        md_path = meta_file.parent / meta_file.name.replace('.meta.json', '.md')
        try:
            meta    = json.loads(meta_file.read_text(encoding='utf-8'))
            raw_md  = md_path.read_text(encoding='utf-8')
            content = json.loads(raw_md).get('content', '') if raw_md.strip().startswith('{') else raw_md
            return meta, content
        except Exception as e:
            print(f"  ⚠ Error loading {meta_file.name}: {e}")
            return None, None

    # ── Extraction helpers ────────────────────────────────────────────────────

    # Known fund / org names — canonical forms
    KNOWN_ORGS = [
        'קרן קולנוע ערבה',
        'קרן הקולנוע ערבה',
        'קרן קולנוע נגב',
        'קרן קולנוע מדרום',
        'קרן רבינוביץ',
        'קרן גשר לקולנוע',
        'קרן גשר',
        'מועצה לקולנוע',
        'המועצה הישראלית לקולנוע',
        'קרן מדרום',
        'מכללת ספיר',
        'מרכז קהילה ערבה',
        'משרד התרבות',
        'המועצה האזורית ערבה תיכונה',
    ]

    def extract_organizations(self, text, meta):
        orgs = set()
        # Always tag aravaff pages with the festival's fund
        if 'aravaff' in meta.get('url', ''):
            orgs.add('קרן קולנוע ערבה')
        # Match known org names literally
        for org in self.KNOWN_ORGS:
            if org in text:
                orgs.add(org)
        return list(orgs)

    def extract_dates(self, text):
        years = sorted(set(re.findall(r'(202\d|201\d|199\d)', text)))
        return years

    # Role keywords mapped to canonical role labels
    ROLE_PATTERNS = [
        (re.compile(r'במאי|במאית|בימוי'),           'במאי'),
        (re.compile(r'מפיק|מפיקה|הפקה'),            'מפיק'),
        (re.compile(r'תסריטאי|תסריטאית'),           'תסריטאי'),
        (re.compile(r'צלם|צלמת'),                   'צלם'),
        (re.compile(r'מנהל אמנותי|מנהלת אמנותית'), 'מנהל אמנותי'),
        (re.compile(r'מנהל|מנהלת'),                 'מנהל'),
        (re.compile(r'מנכ"ל|מנכ״ל'),               'מנכ"ל'),
        (re.compile(r'יו"ר|יו״ר|יושב ראש'),         'יו"ר'),
        (re.compile(r'לקטור|לקטורית'),              'לקטור'),
        (re.compile(r'חבר ועדה|חברת ועדה'),         'חבר ועדה'),
        (re.compile(r'עורך|עורכת'),                 'עורך'),
        (re.compile(r'מלחין|מוזיקאי'),              'מלחין'),
        (re.compile(r'שחקן|שחקנית'),                'שחקן'),
        (re.compile(r'מייסד|מייסדת'),               'מייסד'),
    ]

    def extract_roles_for_name(self, name, text):
        """Find role keywords in a ±150-char window around each name occurrence.
        Snippet is centered on the name itself for readable evidence.
        Returns {role_label: context_snippet}."""
        seen = {}
        for m in re.finditer(re.escape(name), text):
            # Window centered on the name
            start = max(0, m.start() - 120)
            end   = min(len(text), m.end() + 120)
            window = text[start:end]
            for pattern, label in self.ROLE_PATTERNS:
                if label not in seen and pattern.search(window):
                    # Build a clean snippet: …before [NAME] after…
                    before = text[start:m.start()].replace('\n', ' ').strip()[-60:]
                    after  = text[m.end():end].replace('\n', ' ').strip()[:60:]
                    seen[label] = f"…{before} [{name}] {after}…"
        return seen  # {role_label: context_snippet}

    def detect_conflicts(self, person):
        conflicts = []
        if len(set(person.get('organizations', []))) > 1:
            conflicts.append({
                'type': 'multiple_organizations',
                'person': person['name'],
                'organizations': list(set(person['organizations'])),
            })
        roles = person.get('roles', [])
        evaluator_roles = {'מעריך', 'לקטור', 'לקטורית', 'ועדה'}
        beneficiary_roles = {'משקיע', 'מופקד', 'נתמך', 'מקבל מענק'}
        if any(r in roles for r in evaluator_roles) and \
           any(r in roles for r in beneficiary_roles):
            conflicts.append({
                'type': 'evaluator_and_beneficiary',
                'person': person['name'],
                'roles': roles,
            })
        return conflicts

    # ── Per-file processing ───────────────────────────────────────────────────

    def process_file(self, meta_file):
        meta, content = self.load_file_pair(meta_file)
        if not content:
            return

        text       = clean_text(content)
        source_url = meta.get('url', 'unknown')
        orgs       = self.extract_organizations(text, meta)
        years      = self.extract_dates(text)
        ner_names  = self.ner.extract(text)  # {name: {confidence, models}}

        for name, ner_info in ner_names.items():
            if name not in self.entities['people']:
                self.entities['people'][name] = {
                    'name':         name,
                    'confidence':   ner_info['confidence'],
                    'models':       ner_info['models'],
                    'sources':      [],
                    'organizations': [],
                    'roles':        [],
                    'dates':        [],
                }
            person = self.entities['people'][name]
            person['sources'].append(source_url)
            person['dates'].extend(years)
            # Upgrade confidence if a later page gives both-model agreement
            if ner_info['confidence'] == 'high':
                person['confidence'] = 'high'
            for m in ner_info['models']:
                if m not in person['models']:
                    person['models'].append(m)
            # Roles: keyword search in context window around name
            roles_found = self.extract_roles_for_name(name, text)
            for role, snippet in roles_found.items():
                if role not in person['roles']:
                    person['roles'].append(role)
                # Store role evidence for traceability
                person.setdefault('role_evidence', {})
                if role not in person['role_evidence']:
                    person['role_evidence'][role] = []
                person['role_evidence'][role].append({
                    'source_url': source_url,
                    'snippet': snippet,
                })
            # Organizations: link person to orgs found on this page
            for org in orgs:
                if org not in person['organizations']:
                    person['organizations'].append(org)

        for org in orgs:
            if org not in self.entities['organizations']:
                self.entities['organizations'][org] = {'name': org, 'sources': [], 'people': []}
            self.entities['organizations'][org]['sources'].append(source_url)
            # Link org back to people found on this page
            for name in ner_names:
                if name not in self.entities['organizations'][org]['people']:
                    self.entities['organizations'][org]['people'].append(name)

        for name in ner_names:
            roles_found = self.extract_roles_for_name(name, text)
            role_labels = list(roles_found.keys())
            # Pick the most specific snippet for evidence
            snippet = next(iter(roles_found.values()), '') if roles_found else ''
            for org in orgs:
                self.relationships.append({
                    'person':       name,
                    'confidence':   ner_names[name]['confidence'],
                    'organization': org,
                    'roles':        role_labels,          # how they relate
                    'context':      snippet,              # verbatim text evidence
                    'source_url':   source_url,
                    'source_file':  meta_file.name,
                })

        self.processed_files.append({
            'file':         meta_file.name,
            'url':          source_url,
            'people_found': len(ner_names),
            'orgs_found':   len(orgs),
            'years':        years,
        })

    # ── Pipeline ──────────────────────────────────────────────────────────────

    def run(self):
        print(f"\n{'='*60}")
        print("FILM DATA EXTRACTOR - Israeli Film Governance Analysis")
        print(f"{'='*60}\n")
        print(f"📂 Input:  {self.input_dir}")
        print(f"📁 Output: {self.output_dir}\n")

        meta_files = self.find_scraped_files()
        if not meta_files:
            print("❌ No meta.json files found!")
            return False

        print(f"\n🔄 Processing {len(meta_files)} files...\n")
        for i, mf in enumerate(meta_files, 1):
            print(f"  [{i}/{len(meta_files)}] {mf.name[:70]}", flush=True)
            self.process_file(mf)

        print("\n🔍 Detecting conflicts...")
        for person in self.entities['people'].values():
            self.conflicts.extend(self.detect_conflicts(person))

        self._print_summary()
        self._export_json()
        self._export_csv()
        return True

    # ── Output ────────────────────────────────────────────────────────────────

    def _print_summary(self):
        people  = self.entities['people']
        high    = [p for p in people.values() if p['confidence'] == 'high']
        medium  = [p for p in people.values() if p['confidence'] == 'medium']

        print(f"\n{'='*60}")
        print("📊 EXTRACTION SUMMARY")
        print(f"{'='*60}\n")
        print(f"✅ Files processed:       {len(self.processed_files)}")
        print(f"👥 People found:          {len(people)}")
        print(f"   • High confidence:     {len(high)}  (both models agree)")
        print(f"   • Medium confidence:   {len(medium)}  (one model only)")
        print(f"🏢 Organizations found:   {len(self.entities['organizations'])}")
        print(f"🔗 Relationships found:   {len(self.relationships)}")
        print(f"⚠️  Potential conflicts:  {len(self.conflicts)}\n")

        top = sorted(high, key=lambda p: len(p['sources']), reverse=True)[:10]
        if top:
            print("🌟 Most mentioned (high-confidence):")
            for p in top:
                print(f"  • {p['name']} ({len(p['sources'])} pages)")
        print(f"\n💾 Output: {self.output_dir}")

    def _export_json(self):
        out = {
            'extraction_metadata': {
                'extracted_at':    datetime.now().isoformat(),
                'models':          ['dicta-il/dictabert-ner', 'avichr/heBERT_NER'],
                'files_processed': len(self.processed_files),
                'entity_counts': {
                    'people':        len(self.entities['people']),
                    'high_confidence': sum(1 for p in self.entities['people'].values()
                                          if p['confidence'] == 'high'),
                    'organizations': len(self.entities['organizations']),
                    'relationships': len(self.relationships),
                    'conflicts':     len(self.conflicts),
                },
            },
            'entities':       self.entities,
            'relationships':  self.relationships,
            'conflicts':      self.conflicts,
        }
        path = self.output_dir / 'extracted_entities.json'
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"✅ JSON: {path}")

    def _export_csv(self):
        # Relationships
        rel_path = self.output_dir / 'relationships.csv'
        with open(rel_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=['person', 'confidence', 'roles',
                                              'organization', 'context',
                                              'source_url', 'source_file'])
            w.writeheader()
            for r in self.relationships:
                row = dict(r)
                row['roles'] = ', '.join(r.get('roles', []))
                w.writerow(row)
        print(f"✅ Relationships CSV: {rel_path}")

        # People
        people_path = self.output_dir / 'people.csv'
        with open(people_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=['name', 'confidence', 'models', 'roles',
                                              'organizations', 'source_count', 'years', 'sources'])
            w.writeheader()
            for p in sorted(self.entities['people'].values(),
                            key=lambda x: len(x['sources']), reverse=True):
                w.writerow({
                    'name':          p['name'],
                    'confidence':    p['confidence'],
                    'models':        '+'.join(p['models']),
                    'roles':         ', '.join(p.get('roles', [])),
                    'organizations': ', '.join(list(set(p.get('organizations', [])))),
                    'source_count':  len(p['sources']),
                    'years':         ','.join(sorted(set(p['dates']))),
                    'sources':       '; '.join(list(set(p['sources']))[:3]),
                })
        print(f"✅ People CSV: {people_path}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 film_data_extractor.py <input_dir> [output_dir]")
        sys.exit(1)

    input_dir  = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else './film_entities_output'

    if not os.path.exists(input_dir):
        print(f"❌ Input directory not found: {input_dir}")
        sys.exit(1)

    FilmDataExtractor(input_dir, output_dir).run()


if __name__ == '__main__':
    main()
