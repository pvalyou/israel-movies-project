#!/usr/bin/env python3
"""
LLM Entity Extraction — per-source runner.

Per-source design:
  - One run = one source directory (e.g. filmfund, gesher, guidestar)
  - Output goes to <output_dir>/<source_name>/
  - Iterates *.md files (content); *.meta.json sidecars are scraping metadata,
    read only to pick up the URL when present, never iterated
  - Resumable: appends to mentions.jsonl, skips already-done .md filenames
  - Concurrent: 12 worker threads by default
  - Pre-filter: layered — generic film vocabulary OR specific named entities.
    Homepages and `__root__` files always pass the filter.
  - Live log file: tail -f <output>/<source>/run.log to monitor

Usage:
    export OPENROUTER_API_KEY=your_key
    python3 llm_extract.py <source_pages_dir> <output_dir> \\
        [--source-name NAME] [--max-pages N] [--workers N] [--max-chars N] [--no-filter]

Examples:
    # Run one source
    python3 llm_extract.py ./sources/filmfund/pages ./out --source-name filmfund

    # Test on first 100 pages
    python3 llm_extract.py ./sources/arava_film_fund/pages ./out --max-pages 100

    # Disable pre-filter (send every page to LLM)
    python3 llm_extract.py ./sources/gesher/pages ./out --no-filter

    # Tail the log from another terminal
    tail -f ./out/filmfund/run.log
"""

import argparse
import copy
import csv
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path

from openai import OpenAI

# ── Config ────────────────────────────────────────────────────────────────────

OPENROUTER_BASE = "https://openrouter.ai/api/v1"

MODEL_ID  = "google/gemini-2.5-flash-lite"
MODEL_KEY = "gemini25_lite"
PRICING   = {"input": 0.10, "output": 0.40}  # USD per 1M tokens

# Cap output size — runaway generations truncate mid-JSON and fail to parse.
MAX_OUTPUT_TOKENS = 4096
# Only echo malformed JSON back to the model when it's small enough to be useful.
JSON_RETRY_MAX_RAW = 8000

# Seed terms — layered. A page must hit AT LEAST ONE generic term to survive the filter.
# Generic terms are broad film-industry vocabulary — almost any relevant page hits these.
# Specific terms are signal-boosters: they don't change the filter decision but get logged
# so you can sort pages by "richness" later.
#
# Filter rule: page survives iff (generic_hits >= MIN_GENERIC_HITS) OR (specific_hits >= 1)
# This way a regional-fund homepage that says "קרן" + "סרט" passes, while a cooking blog
# that just happens to mention someone's name doesn't.

GENERIC_TERMS = [
    # --- Hebrew: core film vocabulary ---
    "סרט", "סרטים", "קולנוע", "במאי", "במאית", "מפיק", "מפיקה",
    "תסריט", "תסריטאי", "תסריטאית", "צילום", "עריכה", "שחקן", "שחקנית",
    "פסטיבל", "תיעודי", "עלילתי", "דוקומנטרי", "קצר",
    # --- Hebrew: funding / institutional ---
    "קרן", "תמיכה", "מימון", "מענק", "תקציב", "השקעה",
    "פרס", "תחרות", "הפקה", "דירקטוריון", "מועצה", "ועדה",
    "עמותה", "מלכ\"ר", "תקנון", "דוח", "פרוטוקול",
    # --- Hebrew: roles ---
    "מנכ\"ל", "מנכ\"לית", "יו\"ר", "מנהל", "מנהלת", "חבר", "חברת",
    "לקטור", "לקטורית", "לקטורים", "יועץ", "יועצת",
    # --- English: film vocabulary ---
    # These are case-insensitive matched below; values stored here are lowercase.
    "director", "producer", "screenwriter", "writers", "writer",
    "cinematography", "cinematographer", "editor", "editing",
    "actor", "actress", "actors", "cast", "starring",
    "film", "films", "movie", "movies", "cinema", "documentary",
    "feature", "short film", "screening", "festival",
    # --- English: funding / institutional ---
    "fund", "foundation", "grant", "funding", "support",
    "board", "committee", "council", "association", "members",
    "ceo", "chairman", "chairperson", "managing director",
    "executive director", "artistic director",
    # --- English: page-structure cues common on film-fund sites ---
    "about us", "our team", "leadership", "lectors", "evaluators",
    "supported films", "selected films", "recipients", "awards",
]

SPECIFIC_TERMS = [
    # Specific funds and orgs from the source report
    "קרן רבינוביץ", "קרן גשר", "יהושע רבינוביץ",
    "הקרן החדשה לקולנוע", "קרן הקולנוע", "הקרן הישראלית לקולנוע",
    "קרן מקור", "קרן ירושלים", "קרן הגליל", "קרן הערבה", "ערבה",
    "יונייטד קינג", "סינמה סיטי", "משרד התרבות",
    "התאחדות ענף הקולנוע", "איגוד התסריטאים", "מועצת הקולנוע",
    "פסטיבל ירושלים", "פסטיבל חיפה", "פסטיבל דוקאביב",
    # Known names from the source report
    "משה אדרי", "לאון אדרי", "גיורא עיני", "יואב אברמוביץ",
    "אתי כהן", "זיו נווה",
    # Hot terms
    "ניגוד עניינים", "בקשת תמיכה", "ערר", "הוראת שעה", "מבחני תמיכה",
]

MIN_GENERIC_HITS = 2  # pages with strictly fewer generic hits AND zero specific hits get skipped

# Filename or URL-path patterns that ALWAYS pass the filter.
# Two groups because some words (film, movies) commonly appear inside source-name prefixes
# like 'arava_film_fund' and would false-trigger on every file there.
#
# Group A: terms uniquely indicating a content page — safe to match in filename OR URL.
# Group B: ambiguous terms — match ONLY in URL path (where `/movies/` clearly means
#          "page about a movie", unlike `arava_film_fund_*` filenames).

ALWAYS_PASS_PATTERNS_FILENAME_OR_URL = [
    re.compile(r'(?:^|[_\W/])root(?=[_\W/.]|$)',              re.IGNORECASE),
    re.compile(r'(?:^|[_\W/])about(?:[-_/]us)?(?=[_\W/.]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\W/])home(?=[_\W/.]|$)',              re.IGNORECASE),
    re.compile(r'(?:^|[_\W/])index(?=[_\W/.]|$)',             re.IGNORECASE),
    re.compile(r'(?:^|[_\W/])(?:our[-_])?team(?=[_\W/.]|$)',  re.IGNORECASE),
    re.compile(r'(?:^|[_\W/])leadership(?=[_\W/.]|$)',        re.IGNORECASE),
    re.compile(r'(?:^|[_\W/])members?(?=[_\W/.]|$)',          re.IGNORECASE),
    re.compile(r'(?:^|[_\W/])staff(?=[_\W/.]|$)',             re.IGNORECASE),
    re.compile(r'(?:^|[_\W/])(?:lectors?|evaluators?)(?=[_\W/.]|$)', re.IGNORECASE),
    re.compile(r'(?:^|[_\W/])catalog(?:ue)?(?=[_\W/.]|$)',    re.IGNORECASE),
    # Hebrew page-type cues
    re.compile(r'אודות'),       # about
    re.compile(r'צוות'),        # team
    re.compile(r'לקטורים'),     # lectors
    re.compile(r'חברי'),        # members of
    re.compile(r'מועצה'),       # council
    re.compile(r'דירקטוריון'),  # board of directors
]

# These match only in URL paths — too risky in filenames where the source name
# might contain the same word (e.g. 'arava_FILM_fund', 'JERUSALEM_film_fund').
ALWAYS_PASS_PATTERNS_URL_ONLY = [
    re.compile(r'/(?:movies?|films?)(?:/|$)',                 re.IGNORECASE),
    re.compile(r'/people(?:/|$)',                             re.IGNORECASE),
    re.compile(r'/(?:cast|crew)(?:/|$)',                      re.IGNORECASE),
    re.compile(r'/(?:director|producer|writer|editor)s?(?:/|$)', re.IGNORECASE),
    re.compile(r'/program(?:me)?(?:/|$)',                     re.IGNORECASE),
    re.compile(r'/(?:supported|selected|funded)[-_]?films?(?:/|$)', re.IGNORECASE),
    # Hebrew URL paths
    re.compile(r'/סרטים(?:/|$)'),
    re.compile(r'/בית(?:/|$)'),
]

EXTRACTION_PROMPT = """You are an investigative research assistant analyzing Israeli film industry data.

Extract entities and relationships from the following Hebrew web page into structured JSON for relationship-mapping.

Focus ONLY on REAL people (not fictional film characters). Prioritize by page type:
- FUND pages: evaluators/lectors (לקטורים), fund managers (מנכ"לים), board members (ועד מנהל), grant recipients
- FESTIVAL pages: jury members (חברי השופטים), artistic directors (מנהל/ת אמנותי/ת), programmers (מתכנת/ת), prize winners (זוכי פרסים), festival directors (מנהל/ת הפסטיבל)
- SCHOOL pages: faculty/teachers (מרצים, מורים), department heads (ראש מחלקה), school directors (מנהל/ת), notable alumni (בוגרים)
- GUILD pages: board members (ועד), guild chairs (יו"ר), prize committee members (ועדת הפרס)
- ALL pages: government officials related to film (משרד התרבות), founding figures

Return a JSON object with this EXACT structure:

{{
  "metadata": {{
    "source_url": "{url}",
    "source_name": "{source_name}",
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
        "context_sentence": "המשפט המדויק מהמקור שמנמק מדוע האדם נכלל — ציטוט עד 120 תווים",
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
      "sources": ["{url}"]
    }}
  ]
}}

Rules:
- IDs are zero-padded sequential WITHIN THIS PAGE ONLY (person_001, person_002 ...). Cross-page IDs will be resolved downstream.
- Omit name_en if not confident
- For organizations type use: fund | production_company | distribution_company | cinema_chain | government_body | council | festival | union | school | other
- For role_type use:
    FUND roles:      lector | appeal_lector | ceo | co_ceo | chairperson | director_general | council_member | board_member | fund_manager
    FESTIVAL roles:  jury_member | artistic_director | festival_director | festival_programmer | prize_committee_member | festival_staff
    SCHOOL roles:    faculty | department_head | academic_director | lab_mentor | alumni
    GUILD roles:     guild_board_member | guild_chair | guild_member
    CREATIVE roles:  filmmaker | director | producer | screenwriter | art_director | cinematographer | editor | actor
    GENERAL roles:   judge | owner | partner | mentor | event_speaker | event_participant | acknowledged_partner | other
  NOTE — do NOT use `lector` for school teachers; use `faculty`. `lector` = fund submission evaluator only.
- The same vocabulary applies to `primary_roles` on a person entity.
- For relationship type use: produced | directed | acted_in | edited | wrote_screenplay | cinematographer | funded | co_produced | served_as_lector | evaluated_application | owns | affiliated_with | screened_at | judged_at | won_award_at | teaches_at | graduated_from | selected_for | transferred_funds_to
- Skip fictional characters entirely
- Do NOT emit `flags` — conflict-of-interest judgments require cross-page context and will be generated downstream
- Keep output compact: at most ~15 people (institutional roles + key crew; skip minor/ensemble cast), ~10 orgs, ~5 films, ~20 relationships
- Add a `context_sentence` to each person: copy verbatim the shortest phrase or sentence from the page that most directly states their role. Max 120 characters. If no direct sentence exists, use the closest phrase.
- Keep `notes` on roles under 60 characters. Escape quotes in strings. URLs must not contain backslashes.
- Return valid JSON only, no other text

CRITICAL — Ignore sidebars and "related content" sections:
- If the page is about Film X, ignore any "related films" / "more like this" / sidebar listings
  of OTHER films and their directors (Hebrew: "עוד בעלילתי", "סרטים נוספים", "פוסטים קשורים",
  "ראה גם"; English: "Related films", "You may also like").
- People named ONLY in such sidebar listings are NOT crew or staff of the current page's subject.
  Do NOT extract their roles based on that proximity.
- Only extract a person's role when the page's MAIN content explicitly states it
  (e.g. "בימוי: X", "הפקה: Y", "לקטור: Z", or a clearly labeled staff/crew list).

CRITICAL — Attribute roles to the correct organization:
- The page belongs to ONE primary organization (usually inferable from the URL host or page
  title — e.g. kerenmakor.org.il = "קרן מקור"). Treat that as the page's "host org".
- Pages often mention OTHER organizations as partners, sponsors, co-funders, related bodies
  (e.g. "מפעל הפיס", "משרד התרבות", "קרן רבינוביץ׳", a foreign embassy, a film school).
- When you record a `role` linking a person to an organization, the `organization_id` MUST be
  the org the person actually serves in. If the page says "X from Mifal Hapais" or
  "Y, head of Council Z", do NOT attribute X or Y to the host org.
- If you cannot determine which org a person serves, omit the role entry rather than guess.

CRITICAL — Be strict about role labels:
- Use `lector` ONLY when the page literally states the person evaluated or read fund submissions
  ("לקטור", "לקטורים", "evaluated applications", "submission reviewer", "reader").
  EXCEPTION: if a section heading literally contains "לקטורים" / "Lectors" / "evaluators",
  treat ALL names directly under it as lectors — these are official institutional lists.
- Use `faculty` for school/university teachers and lecturers — NOT `lector`.
- Use `jury_member` for festival jury members (חברי השופטים, חבר/ת חבר השופטים).
  Use `judge` only when someone adjudicates at a fund or competition (not a festival).
- Use `board_member` / `council_member` ONLY when the page lists them under a clearly named
  governing body ("דירקטוריון", "ועדה מנהלת", "מועצה").
- Use `guild_board_member` / `guild_chair` for guild governing roles.
- For people who appear on an event/conference recap page:
  - Speakers, panelists → role `event_speaker` (set `notes` to the event title/year)
  - Attendees, thanked partners → `event_participant` or `acknowledged_partner`
  - Do NOT label them `lector` based on this alone.
- When in doubt between an institutional role and an event role, prefer the event role.
- Always use the `notes` field to capture specific context
  (e.g. "jury member DocAviv 2024", "faculty Sam Spiegel since 2018", "Ophir Prize committee 2023").

Page content:
{content}"""

MINIMAL_EXTRACTION_PROMPT = """Extract Israeli film industry entities from this page. Return valid JSON only.

{{
  "metadata": {{"source_url": "{url}", "source_name": "{source_name}", "extraction_date": "{today}", "language": "he"}},
  "entities": {{
    "people": {{"person_001": {{"name_he": "שם", "name_en": null, "aliases": [], "primary_roles": ["other"], "sources": ["{url}"]}}}},
    "organizations": {{}},
    "films": {{}},
    "events": {{}}
  }},
  "roles": [],
  "relationships": []
}}

HARD LIMITS: max 12 people, max 8 organizations, max 5 films, max 12 relationships.
Institutional roles only — skip minor cast and fictional characters. context_sentence max 80 chars. notes max 40 chars.
role_type: lector | jury_member | artistic_director | festival_director | festival_programmer | faculty | department_head | alumni | guild_board_member | guild_chair | board_member | council_member | ceo | chairperson | filmmaker | event_speaker | other
NOTE: use faculty (not lector) for school teachers. use jury_member (not judge) for festival juries.

Page:
{content}"""

COMPACT_RETRY_USER = (
    "Your previous JSON was invalid or too large. Re-extract with STRICT limits: "
    "max 12 people, max 8 organizations, max 5 films, max 15 relationships. "
    "context_sentence max 80 chars. notes max 40 chars. Valid JSON only."
)


# ── Text preprocessing ────────────────────────────────────────────────────────

BOILERPLATE_PATTERNS = [
    re.compile(r'\[מעבר לתוכן[^\]]*\][^\n]*\n?'),
    re.compile(r'#{1,6}\s*תפריט לטלפון.*?(?=#{1,6}|\Z)', re.DOTALL),
    re.compile(r'#{1,6}\s*חיפוש\s*\nסגור\s*\nחיפוש\s*\n'),
    re.compile(r'## Links\n[\s\S]*', re.DOTALL),
    # additional common Hebrew web boilerplate
    re.compile(r'#{1,6}\s*תפריט\s*\n'),
    re.compile(r'דילוג לתוכן[^\n]*\n?'),
    re.compile(r'(שתף|שתפו|שיתוף ב)(פייסבוק|וואטסאפ|טוויטר|לינקדאין|מייל)[^\n]*\n?'),
    re.compile(r'©[^\n]*\n?'),
    re.compile(r'כל הזכויות שמורות[^\n]*\n?'),
    # "Related films" / sidebar sections — these list OTHER films with their directors
    # and cause the LLM to misattribute roles (e.g. directors of related films get
    # misread as lectors on the current film). Strip the heading and all subsequent
    # markdown-link list items (### [text](url)) that follow.
    re.compile(
        r'#{1,6}[ \t]*(?:'
        r'עוד ב[א-ת\'\"׳״]+|'               # Hebrew "more in <category>" (עוד בעלילתי, עוד בקטגוריה, …)
        r'סרטים (?:נוספים|קשורים|דומים)|'
        r'פוסטים (?:נוספים|קשורים|דומים)|'
        r'כתבות (?:נוספות|קשורות|דומות)|'
        r'ראה גם|באותו נושא|קרא עוד|לקריאה נוספת|אולי יעניין אותך|'
        r'more (?:in|from|by|like) [^\n]*|'  # "More in Fiction", "More from X", "More like this"
        r'more (?:films?|posts?|articles?)|'
        r'related (?:films?|posts?|articles?)|'
        r'see also|read more|you may also like'
        r')'
        r'[^\n]*\n'                                       # rest of heading line
        r'(?:[ \t]*#{1,6}[ \t]*\[[^\]]*\]\([^)]*\)[ \t]*\n?)*'  # ### [text](url) items
        r'(?:[ \t]*-[ \t]*\[[^\]]*\]\([^)]*\)[ \t]*\n?)*',      # - [text](url) bullets
        re.IGNORECASE | re.MULTILINE,
    ),
]

def clean_text(text):
    for p in BOILERPLATE_PATTERNS:
        text = p.sub('', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r' \1 ', text)
    text = re.sub(r'\*([^*]+)\*',     r' \1 ', text)
    text = re.sub(r'#{1,6}\s*',       ' ',     text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # markdown links
    text = re.sub(r' {2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def decode_filename(name):
    """
    Filenames from the scraper contain URL-percent-encoded Hebrew with `%` replaced by `-`.
    Example: 'arava_film_fund__movies-d7-a7-d7-95-d7-a7-d7-95-d7-94-d7-a8.md'
    decodes the percent-encoded portion to: 'arava_film_fund__movies/קוקוהר.md'.

    Strategy: only convert `-XX` sequences that appear in a *chain* of at least two pairs
    (so we don't accidentally decode random hex-looking fragments of hashes/IDs).
    Falls back to the original name on any decoding failure.
    """
    try:
        # Find runs of 2+ consecutive -XX pairs and decode each run.
        # A "run" looks like (-[0-9a-f]{2}){2,}
        def decode_run(match):
            run = match.group(0)  # e.g. "-d7-a7-d7-95"
            # Convert each -XX to %XX
            pct = re.sub(r'-([0-9a-f]{2})', r'%\1', run, flags=re.IGNORECASE)
            try:
                return urllib.parse.unquote(pct, encoding='utf-8', errors='replace')
            except Exception:
                return run

        result = re.sub(r'(?:-[0-9a-fA-F]{2}){2,}', decode_run, name)
        # Only return decoded form if it actually produced Hebrew text
        if result != name and any('\u0590' <= c <= '\u05ff' for c in result):
            return result
        return name
    except Exception:
        return name


def load_page(md_path):
    """Load content from a .md file. Look for an optional sibling .meta.json for the URL."""
    try:
        raw = md_path.read_text(encoding='utf-8')
        content = json.loads(raw).get('content', '') if raw.strip().startswith('{') else raw
        content = clean_text(content)
    except Exception as e:
        return '', f"__LOAD_ERROR__: {e}"

    # Optional metadata sibling — try a few naming conventions
    url = ''
    candidates = [
        md_path.with_suffix('.meta.json'),
        md_path.parent / (md_path.stem + '.meta.json'),
        md_path.parent / (md_path.name.replace('.md', '.meta.json')),
    ]
    for meta_path in candidates:
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding='utf-8'))
                url = meta.get('url', '') or meta.get('source_url', '')
                if url:
                    break
            except Exception:
                pass

    return url, content


def filter_decision(filename, text, url=''):
    """
    Return (should_process, info_dict).

    Filter logic, in priority order:
      1. Always-pass: filename (raw or decoded) OR url path matches a known
         content-page pattern (root/about/team/movies/lectors/...).
      2. Specific seed term hit (Rabinovich, Edery, etc.) — any single hit passes.
      3. Generic film-vocabulary hits (Hebrew or English) — >= MIN_GENERIC_HITS passes.

    Generic and English terms are matched case-insensitively against the text.
    Specific (Hebrew) terms are matched as-is.
    """
    decoded = decode_filename(filename)

    # Step 1: always-pass on filename, decoded filename, or URL path
    for pat in ALWAYS_PASS_PATTERNS_FILENAME_OR_URL:
        if pat.search(filename) or pat.search(decoded) or (url and pat.search(url)):
            return True, {
                'reason': 'always_pass',
                'matched_pattern': pat.pattern,
                'decoded_name': decoded if decoded != filename else None,
                'generic_hits': None, 'specific_hits': None,
                'matched_generic': [], 'matched_specific': [],
            }
    # URL-only patterns: ambiguous words like /movies/ that we don't trust in filenames
    # (because source names like 'arava_film_fund' would false-match)
    if url:
        for pat in ALWAYS_PASS_PATTERNS_URL_ONLY:
            if pat.search(url):
                return True, {
                    'reason': 'always_pass',
                    'matched_pattern': pat.pattern,
                    'decoded_name': decoded if decoded != filename else None,
                    'generic_hits': None, 'specific_hits': None,
                    'matched_generic': [], 'matched_specific': [],
                }

    # Step 2 & 3: seed term matching
    text_lower = text.lower()  # for case-insensitive English matching
    generic_matched = []
    for t in GENERIC_TERMS:
        # If the term contains Hebrew chars, match as-is; otherwise lowercase compare
        if any('\u0590' <= c <= '\u05ff' for c in t):
            if t in text:
                generic_matched.append(t)
        else:
            if t.lower() in text_lower:
                generic_matched.append(t)
    specific_matched = [t for t in SPECIFIC_TERMS if t in text]
    g = len(generic_matched)
    s = len(specific_matched)

    keep = (g >= MIN_GENERIC_HITS) or (s >= 1)
    return keep, {
        'reason': 'pass' if keep else 'filter',
        'decoded_name': decoded if decoded != filename else None,
        'generic_hits':  g,
        'specific_hits': s,
        'matched_generic':  generic_matched[:5],
        'matched_specific': specific_matched[:5],
    }


# ── LLM caller ────────────────────────────────────────────────────────────────

class Usage:
    def __init__(self):
        self.lock = threading.Lock()
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0
        self.errors = 0
        self.json_retries = 0

    def add(self, in_tok, out_tok, error=False, retry=False):
        with self.lock:
            self.input_tokens += in_tok
            self.output_tokens += out_tok
            self.calls += 1
            if error: self.errors += 1
            if retry: self.json_retries += 1

    def cost(self):
        return (self.input_tokens / 1e6) * PRICING['input'] + \
               (self.output_tokens / 1e6) * PRICING['output']


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def adapt_cached_data(data: dict, url: str, source_name: str, today: str) -> dict:
    """Clone a prior extraction and point all source URLs at this page."""
    out = copy.deepcopy(data)
    meta = out.setdefault("metadata", {})
    meta["source_url"] = url
    meta["source_name"] = source_name
    meta["extraction_date"] = today

    def rewrite(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "sources" and isinstance(v, list):
                    obj[k] = [url]
                else:
                    rewrite(v)
        elif isinstance(obj, list):
            for item in obj:
                rewrite(item)

    rewrite(out)
    return out


def _normalize_json_raw(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw.strip())
    start = raw.find("{")
    if start > 0:
        raw = raw[start:]
    # LLMs sometimes emit invalid escapes in URLs, e.g. "\(" instead of "("
    return re.sub(r'\\([^"\\/bfnrtu])', r"\1", raw)


def parse_json_response(raw):
    """Parse LLM JSON; repair truncated or slightly malformed output when possible."""
    raw = _normalize_json_raw(raw)
    try:
        return json.JSONDecoder().raw_decode(raw)[0]
    except json.JSONDecodeError:
        pass

    chunk = raw
    suffixes = (
        "",
        "}",
        "]}",
        "}]",
        "}}",
        "}}]",
        "}}]}",
        "]}]}",
        "null}]}",
        '"}]}',
    )
    while chunk:
        trimmed = chunk.rstrip().rstrip(",")
        for suffix in suffixes:
            try:
                return json.loads(trimmed + suffix)
            except json.JSONDecodeError:
                continue
        pos = chunk.rfind("}")
        if pos <= 0:
            break
        chunk = chunk[:pos]

    return json.JSONDecoder().raw_decode(raw)[0]


def call_llm(client, prompt, usage, minimal_prompt=None):
    """LLM call with retries on malformed or oversized JSON. Thread-safe via usage lock."""
    kwargs = dict(
        model=MODEL_ID,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=MAX_OUTPUT_TOKENS,
        response_format={"type": "json_object"},
    )

    raw = ""
    resp = None
    max_attempts = 4 if minimal_prompt else 3
    for attempt in range(max_attempts):
        try:
            resp = client.chat.completions.create(**kwargs)
            raw = resp.choices[0].message.content or ""
            result = parse_json_response(raw)
            in_tok = resp.usage.prompt_tokens if resp.usage else 0
            out_tok = resp.usage.completion_tokens if resp.usage else 0
            usage.add(in_tok, out_tok, retry=(attempt > 0))
            return result, None
        except json.JSONDecodeError as e:
            in_tok = resp.usage.prompt_tokens if resp and resp.usage else 0
            out_tok = resp.usage.completion_tokens if resp and resp.usage else 0
            if attempt < max_attempts - 1:
                usage.add(in_tok, out_tok, retry=True)
                if attempt == 0 and len(raw) <= JSON_RETRY_MAX_RAW:
                    kwargs["messages"] = [
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": raw},
                        {
                            "role": "user",
                            "content": (
                                "Your JSON was malformed. Rewrite as valid JSON only. "
                                "context_sentence max 80 chars. Short notes only."
                            ),
                        },
                    ]
                elif attempt == max_attempts - 2 and minimal_prompt:
                    kwargs["messages"] = [{"role": "user", "content": minimal_prompt}]
                else:
                    kwargs["messages"] = [
                        {"role": "user", "content": f"{prompt}\n\n{COMPACT_RETRY_USER}"},
                    ]
                time.sleep(0.5)
            else:
                usage.add(in_tok, out_tok, error=True)
                return None, f"json_error: {e} | raw_len={len(raw)} | raw_head: {raw[:150]!r}"
        except Exception as e:
            if resp and resp.usage:
                usage.add(resp.usage.prompt_tokens, resp.usage.completion_tokens, error=True)
            else:
                usage.add(0, 0, error=True)
            return None, f"api_error: {e}"


def empty_result():
    return {"entities": {"people": {}, "organizations": {}, "films": {}, "events": {}},
            "roles": [], "relationships": []}


def count_records(data):
    e = data.get('entities', {})
    return (len(e.get('people', {})), len(e.get('organizations', {})),
            len(e.get('films', {})), len(data.get('relationships', [])),
            len(data.get('roles', [])))


# ── Per-page worker ───────────────────────────────────────────────────────────

def process_page(md_path, client, usage, source_name, max_chars, no_filter,
                 content_cache=None, cache_lock=None):
    """Process one page. Returns a dict ready to append to mentions.jsonl."""
    url, content = load_page(md_path)

    if content.startswith("__LOAD_ERROR__"):
        return {
            'file': md_path.name, 'url': url, 'source_name': source_name,
            'status': 'load_error', 'error': content,
            'data': empty_result(),
        }

    if not content or len(content) < 50:
        return {
            'file': md_path.name, 'url': url, 'source_name': source_name,
            'status': 'empty_content', 'content_length': len(content),
            'data': empty_result(),
        }

    original_length = len(content)
    keep, filter_info = filter_decision(md_path.name, content, url=url)

    if not no_filter and not keep:
        return {
            'file': md_path.name, 'url': url, 'source_name': source_name,
            'status': 'filtered',
            'content_length': original_length,
            'content_preview': content[:200],  # first 200 chars so you can audit without opening the file
            'filter_info': filter_info,
            'data': empty_result(),
        }

    truncated = original_length > max_chars
    content_to_send = content[:max_chars]
    chash = content_hash(content)

    if content_cache is not None and cache_lock is not None:
        with cache_lock:
            hit = content_cache.get(chash)
        if hit:
            data = adapt_cached_data(
                hit["data"], url, source_name, date.today().isoformat(),
            )
            return {
                "file": md_path.name,
                "url": url,
                "source_name": source_name,
                "status": "ok",
                "content_hash": chash,
                "deduped_from": hit["file"],
                "content_length": original_length,
                "filter_info": filter_info,
                "truncated": truncated,
                "elapsed_sec": 0,
                "data": data,
            }

    today = date.today().isoformat()
    prompt = EXTRACTION_PROMPT.format(
        url=url, source_name=source_name,
        content=content_to_send, today=today,
    )
    minimal_prompt = MINIMAL_EXTRACTION_PROMPT.format(
        url=url, source_name=source_name,
        content=content_to_send, today=today,
    )

    t0 = time.time()
    result, err = call_llm(client, prompt, usage, minimal_prompt=minimal_prompt)
    elapsed = time.time() - t0

    if err:
        return {
            'file': md_path.name, 'url': url, 'source_name': source_name,
            'status': 'llm_error', 'error': err,
            'content_length': original_length,
            'filter_info': filter_info,
            'truncated': truncated, 'elapsed_sec': round(elapsed, 2),
            'data': empty_result(),
        }

    rec = {
        "file": md_path.name,
        "url": url,
        "source_name": source_name,
        "status": "ok",
        "content_hash": chash,
        "content_length": original_length,
        "filter_info": filter_info,
        "truncated": truncated,
        "elapsed_sec": round(elapsed, 2),
        "data": result,
    }
    if content_cache is not None:
        lock = cache_lock or threading.Lock()
        with lock:
            content_cache.setdefault(chash, {"data": result, "file": md_path.name})
    return rec


# ── Resumability ──────────────────────────────────────────────────────────────

def load_done_keys(jsonl_path):
    """Build a set of already-processed page keys (using file name, not URL — URL may be empty on errors)."""
    done = set()
    if not jsonl_path.exists():
        return done
    with open(jsonl_path, encoding='utf-8') as f:
        for line in f:
            try:
                rec = json.loads(line)
                key = rec.get('file')
                if key:
                    done.add(key)
            except json.JSONDecodeError:
                continue
    return done


def load_content_cache(jsonl_path, pages_dir):
    """Map content_hash -> {data, file} from prior ok extractions in this source."""
    cache = {}
    if not jsonl_path.exists():
        return cache
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("status") != "ok":
                continue
            chash = rec.get("content_hash")
            if not chash:
                md = pages_dir / rec.get("file", "")
                if md.exists():
                    _, content = load_page(md)
                    chash = content_hash(content)
            if chash and chash not in cache:
                cache[chash] = {"data": rec["data"], "file": rec["file"]}
    return cache


# ── Logger ────────────────────────────────────────────────────────────────────

class Logger:
    """Thread-safe logger writing to both stdout and a log file (line-buffered)."""
    def __init__(self, log_path):
        self.lock = threading.Lock()
        self.file = open(log_path, 'a', encoding='utf-8', buffering=1)
        self.file.write(f"\n=== Run started {datetime.now().isoformat()} ===\n")

    def log(self, msg):
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        with self.lock:
            print(line, flush=True)
            self.file.write(line + "\n")

    def close(self):
        with self.lock:
            self.file.write(f"=== Run ended {datetime.now().isoformat()} ===\n")
            self.file.close()


# ── Runner ────────────────────────────────────────────────────────────────────

def run(args):
    api_key = os.environ.get('OPENROUTER_API_KEY')
    if not api_key:
        print("❌ OPENROUTER_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    pages_dir = Path(args.pages_dir)
    if not pages_dir.exists():
        print(f"❌ Pages dir not found: {pages_dir}", file=sys.stderr)
        sys.exit(1)

    source_name = args.source_name or pages_dir.name
    output_dir  = Path(args.output_dir) / source_name
    output_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = output_dir / 'mentions.jsonl'
    log_path   = output_dir / 'run.log'
    logger     = Logger(log_path)

    # Iterate .md files. Skip *.meta.json sidecars — they are scraping metadata, not content.
    md_files = sorted(p for p in pages_dir.glob('*.md') if not p.name.endswith('.meta.md'))
    if args.max_pages:
        md_files = md_files[:args.max_pages]

    if getattr(args, 'reprocess_truncated', False) and jsonl_path.exists():
        lines = jsonl_path.read_text(encoding='utf-8').splitlines()
        kept, removed = [], 0
        for line in lines:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                if rec.get('truncated') and not rec.get('url', '').startswith('manual://'):
                    removed += 1
                    continue
            except Exception:
                pass
            kept.append(line)
        jsonl_path.write_text('\n'.join(kept) + '\n', encoding='utf-8')
        print(f"  --reprocess-truncated: removed {removed} truncated entries, will re-extract")

    done = load_done_keys(jsonl_path)
    todo = [mf for mf in md_files if mf.name not in done]

    logger.log(f"Source: {source_name}")
    logger.log(f"Pages dir: {pages_dir}")
    logger.log(f"Output dir: {output_dir}")
    logger.log(f"Total .md pages found: {len(md_files)}  |  Already done: {len(done)}  |  To process: {len(todo)}")
    logger.log(f"Model: {MODEL_ID}  |  Workers: {args.workers}  |  Max chars: {args.max_chars}  |  Pre-filter: {'OFF' if args.no_filter else f'ON (min {MIN_GENERIC_HITS} generic OR >=1 specific)'}")

    if not todo:
        logger.log("Nothing to do — all pages already processed.")
        logger.close()
        return

    client = OpenAI(api_key=api_key, base_url=OPENROUTER_BASE)
    usage  = Usage()
    content_cache = load_content_cache(jsonl_path, pages_dir)
    cache_lock = threading.Lock()
    if content_cache:
        logger.log(f"Content dedup cache: {len(content_cache)} unique page bodies from prior ok runs")

    # Counters for live progress
    counts = {'ok': 0, 'filtered': 0, 'empty_content': 0, 'load_error': 0, 'llm_error': 0}
    counts_lock = threading.Lock()

    out_lock = threading.Lock()
    out_f = open(jsonl_path, 'a', encoding='utf-8', buffering=1)

    t_start = time.time()

    def worker(mf):
        return process_page(
            mf, client, usage, source_name, args.max_chars, args.no_filter,
            content_cache=content_cache, cache_lock=cache_lock,
        )

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(worker, mf): mf for mf in todo}
            for i, fut in enumerate(as_completed(futures), 1):
                try:
                    rec = fut.result()
                except Exception as e:
                    logger.log(f"  ⚠ worker crashed: {e}")
                    continue
                if rec is None:
                    continue

                with out_lock:
                    out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")

                with counts_lock:
                    counts[rec['status']] = counts.get(rec['status'], 0) + 1

                # Real filename always shown (copy-pasteable), decoded version as a hint when different
                real_name = rec['file']
                pretty_name = decode_filename(real_name)
                hint = f"  [{pretty_name}]" if pretty_name != real_name else ""
                url_short = rec.get('url', '')
                if len(url_short) > 80:
                    url_short = url_short[:77] + '...'

                if rec['status'] == 'ok':
                    p, o, fi, r, ro = count_records(rec['data'])
                    trunc = " [TRUNC]" if rec.get('truncated') else ""
                    dedup = f" [dedup←{rec['deduped_from']}]" if rec.get('deduped_from') else ""
                    logger.log(f"[{i}/{len(todo)}] OK   {p}p {o}o {fi}f {r}r {ro}ro  ({rec['elapsed_sec']}s){trunc}{dedup}")
                    logger.log(f"          file: {real_name}{hint}")
                    if url_short: logger.log(f"          url:  {url_short}")
                elif rec['status'] == 'filtered':
                    fi = rec.get('filter_info', {})
                    g = fi.get('generic_hits', '?')
                    s = fi.get('specific_hits', '?')
                    matched = (fi.get('matched_generic') or []) + (fi.get('matched_specific') or [])
                    matched_str = f" matched={matched}" if matched else ""
                    logger.log(f"[{i}/{len(todo)}] SKIP (g={g} s={s}){matched_str}")
                    logger.log(f"          file: {real_name}{hint}")
                    if url_short: logger.log(f"          url:  {url_short}")
                else:
                    err = str(rec.get('error', ''))[:120]
                    logger.log(f"[{i}/{len(todo)}] {rec['status'].upper()}: {err}")
                    logger.log(f"          file: {real_name}{hint}")
                    if url_short: logger.log(f"          url:  {url_short}")

                # Periodic running totals
                if i % 50 == 0:
                    elapsed_min = (time.time() - t_start) / 60
                    rate = i / elapsed_min if elapsed_min > 0 else 0
                    eta_min = (len(todo) - i) / rate if rate > 0 else 0
                    logger.log(f"  --- progress: {i}/{len(todo)} ({i/len(todo)*100:.1f}%)  rate: {rate:.1f}/min  eta: {eta_min:.1f}min  cost so far: ${usage.cost():.4f} ---")

    except KeyboardInterrupt:
        logger.log("⚠ interrupted by user — partial results saved to mentions.jsonl")
    finally:
        out_f.close()

    elapsed_min = (time.time() - t_start) / 60

    # ── Summary ───────────────────────────────────────────────────────────────
    logger.log("=" * 70)
    logger.log(f"DONE in {elapsed_min:.1f}min")
    logger.log(f"  ok:           {counts.get('ok', 0)}")
    logger.log(f"  filtered:     {counts.get('filtered', 0)}")
    logger.log(f"  empty:        {counts.get('empty_content', 0)}")
    logger.log(f"  load_error:   {counts.get('load_error', 0)}")
    logger.log(f"  llm_error:    {counts.get('llm_error', 0)}")
    logger.log(f"Tokens: {usage.input_tokens:,} in / {usage.output_tokens:,} out  |  Cost: ${usage.cost():.4f}")
    logger.log(f"Calls: {usage.calls}  |  Errors: {usage.errors}  |  JSON retries: {usage.json_retries}")
    logger.log(f"Output: {jsonl_path}")

    # Write a small summary JSON for orchestration scripts
    summary = {
        'source_name': source_name,
        'run_date': date.today().isoformat(),
        'elapsed_min': round(elapsed_min, 2),
        'pages_total': len(md_files),
        'pages_already_done': len(done),
        'pages_processed_this_run': len(todo),
        'status_counts': dict(counts),
        'tokens_input': usage.input_tokens,
        'tokens_output': usage.output_tokens,
        'cost_usd': round(usage.cost(), 4),
        'calls': usage.calls,
        'errors': usage.errors,
        'json_retries': usage.json_retries,
    }
    (output_dir / 'run_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    logger.log(f"Summary:  {output_dir / 'run_summary.json'}")
    logger.close()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Per-source LLM entity extractor (resumable, concurrent)")
    ap.add_argument('pages_dir', help='Directory containing *.meta.json + *.md pairs for one source')
    ap.add_argument('output_dir', help='Root output directory; a subdirectory named <source_name> will be created')
    ap.add_argument('--source-name', default=None,
                    help='Source label written into each mention (default: basename of pages_dir)')
    ap.add_argument('--max-pages', type=int, default=None,
                    help='Limit number of pages (for testing)')
    ap.add_argument('--workers', type=int, default=12,
                    help='Concurrent API calls (default 12)')
    ap.add_argument('--max-chars', type=int, default=32000,
                    help='Truncate page content to this many chars before LLM (default 32000)')
    ap.add_argument('--reprocess-truncated', action='store_true',
                    help='Re-extract pages previously truncated at a lower max-chars limit')
    ap.add_argument('--no-filter', action='store_true',
                    help='Disable seed-term pre-filter (send every page to LLM)')
    args = ap.parse_args()

    run(args)


if __name__ == '__main__':
    main()
