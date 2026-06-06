#!/usr/bin/env python3
"""
resolve_entities.py — Entity resolution + HTML connections report.

Reads:   out/*/mentions.jsonl
Writes:  entity_registry.json      — canonical entities with stable IDs
         ambiguous_pairs.json      — fuzzy candidate pairs for review
         connections_report.html   — human-readable investigation report

Re-runnable: always rebuilds from scratch. Safe to run after adding new sources.

Usage:
  python3 resolve_entities.py
  python3 resolve_entities.py --out-dir ./reports   # write outputs elsewhere
  python3 resolve_entities.py --no-fuzzy            # skip fuzzy matching (faster)
"""

import argparse
import glob
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

try:
    from rapidfuzz import fuzz as rfuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

# ── Configuration ──────────────────────────────────────────────────────────────

MENTIONS_GLOB   = "out/*/mentions.jsonl"

# Map synthetic URL prefix → real canonical document URL. When the resolver sees
# a `manual://` URL in the institutional evidence, it links to the URL below.
# More specific prefixes MUST come before broader ones (longest-prefix-first matching).
CANONICAL_DOC_URLS = {
    # filmfund: historical May-2023 PDF must be checked before the general 2026-05 entry
    "manual://filmfund/lectors-list-2026-05/supplemental-2023":
        "https://d18hmyzxupgbf8.cloudfront.net/wp-content/uploads/2023/06/"
        "%D7%A8%D7%A9%D7%99%D7%9E%D7%AA-%D7%94%D7%9C%D7%A7%D7%98%D7%95%D7%A8%D7%99%D7%9D-"
        "%D7%94%D7%9E%D7%90%D7%95%D7%A9%D7%A8%D7%99%D7%9D-%D7%A0%D7%9B%D7%95%D7%9F"
        "_%D7%9C%D7%9E%D7%90%D7%99_2023.pdf",
    "manual://makor/lectors-list-2026-04/":
        "https://kerenmakor.org.il/wp-content/uploads/2026/04/"
        "%D7%A8%D7%A9%D7%99%D7%9E%D7%AA-%D7%9C%D7%A7%D7%98%D7%95%D7%A8%D7%99%D7%9D-"
        "%D7%A7%D7%A8%D7%9F-%D7%9E%D7%A7%D7%95%D7%A8-%D7%9C%D7%90%D7%AA%D7%A8-04.2026.pdf",
    "manual://gesher/lectors-list-2026-05/":
        "https://gesherfilmfund.org.il/Page/45/",
    "manual://filmfund/lectors-list-2026-05/":
        "https://www.filmfund.org.il/ContentPage?id=49",
    "manual://nfct/lectors-list/":
        "https://nfct.org.il/lectors/",
    "manual://jerusalem_film_fund/lectors-list-2021/":
        "https://www.jda.gov.il/en/wp-content/uploads/2021/03/"
        "%D7%9E%D7%90%D7%92%D7%A8-%D7%9C%D7%A7%D7%98%D7%95%D7%A8%D7%99%D7%9D.pdf",
    "manual://rabinovich_cinema/lectors-list/":
        "https://www.cinemaproject.org.il/ns/index.php"
        "?option=com_phocadownload&view=category&download=29",
    "manual://guilds/directors-guild/board-2026":
        "https://directorsguild.org.il/%D7%94%D7%A0%D7%94%D7%9C%D7%94-%D7%95%D7%A6%D7%95%D7%95%D7%AA/",
    "manual://guilds/producers-guild/board-2026":
        "https://producers.org.il/about",
    "manual://haifa_film_festival/staff-2026/":
        "https://www.haifaff.co.il/%D7%A6%D7%95%D7%95%D7%AA_%D7%94%D7%A4%D7%A1%D7%98%D7%99%D7%91%D7%9C",
    "manual://jerusalem_cinematheque/staff-2026/":
        "https://jer-cin.org.il/he/%D7%9E%D7%90%D7%9E%D7%A8/4202",
    "manual://jerusalem_cinematheque/board-2026/":
        "https://jer-cin.org.il/he/%D7%9E%D7%90%D7%9E%D7%A8/4204",
    "manual://jff/selectors-2022/":
        "https://jer-cin.org.il/he/%D7%9E%D7%90%D7%9E%D7%A8/58098",
    "manual://fdoc/board-2024-2026/":
        "https://www.fdoc.org.il/%D7%94%D7%A0%D7%94%D7%9C%D7%94/",
    "manual://israeli_film_academy/board-2026/":
        "https://israelfilmacademy.co.il/?section=590",
    "manual://israeli_film_academy/ceo-2026/":
        "https://israelfilmacademy.co.il/?section=590",
    "manual://film_schools/sam-spiegel-faculty-2026/":
        "https://www.jsfs.co.il/teaching-staff",
    "manual://film_schools/sapir-faculty-2026/":
        "https://www.sapir.ac.il/staff/dep/529",
    "manual://film_schools/tau-faculty-2026/":
        "https://arts.tau.ac.il/filmTV/stf",
    "manual://film_schools/tau-arts-admin-2026/":
        "https://arts.tau.ac.il/administration",
    "manual://film_schools/minshar-faculty-2026/":
        "https://minshar.org.il/film-studies/faculty-members",
    "manual://film_schools/beit-berl-faculty-2026/":
        "https://www.beitberl.ac.il/colleges/arts",
    "manual://film_schools/bezalel-faculty-2026/":
        "https://www.bezalel.ac.il",
    "manual://film_schools/seminar-hakibbutzim-faculty-2026/":
        "https://www.smkb.ac.il",
    "manual://film_schools/ariel-university-faculty-2026/":
        "https://www.ariel.ac.il",
    "manual://film_schools/open-university-faculty-2026/":
        "https://www.openu.ac.il",
    "manual://film_schools/high-school-cinema-teachers-2026/":
        "https://meyda.education.gov.il",
    "manual://jff_staff/selectors-2019/":
        "https://jff.org.il/he/article/6145",
    "manual://jff_staff/selectors-2022/":
        "https://jff.org.il/he/%D7%9E%D7%90%D7%9E%D7%A8/58098",
    "manual://jff_staff/selectors-2023/":
        "https://jff.org.il/he/%D7%9E%D7%90%D7%9E%D7%A8/68273",
    "manual://jff_staff/selectors-2025/":
        "https://jff.org.il/he/%D7%9E%D7%90%D7%9E%D7%A8/86793",
    "manual://writers_guild/board-2025/":
        "https://writersguild.org.il/",
    "manual://writers_guild/ceo-2025/":
        "https://writersguild.org.il/",
    "manual://sam_spiegel/teaching-staff":
        "https://www.jsfs.co.il/teaching-staff",
}

# Date label shown on the person card for each lectors-list source.
# Used to distinguish e.g. "לקטור (מאי 2023)" from "לקטור (מאי 2026)".
LIST_DATE_LABELS: dict[str, str] = {
    "manual://filmfund/lectors-list-2026-05/supplemental-2023": "מאי 2023",
    "manual://makor/lectors-list-2026-04/":                     "אפריל 2026",
    "manual://gesher/lectors-list-2026-05/":                    "מאי 2026",
    "manual://filmfund/lectors-list-2026-05/":                  "מאי 2026",
    "manual://nfct/lectors-list/":                              "",
    "manual://jerusalem_film_fund/lectors-list-2021/":          "2021",
    "manual://rabinovich_cinema/lectors-list/":                 "",
}


def canonical_url_for(manual_url: str) -> str:
    for prefix, real in CANONICAL_DOC_URLS.items():
        if manual_url.startswith(prefix):
            return real
    return ""


def list_date_label_for(manual_url: str) -> str:
    """Return the year/date label for a manual:// lectors-list URL, or ''."""
    for prefix, label in LIST_DATE_LABELS.items():
        if manual_url.startswith(prefix):
            return label
    return ""
REGISTRY_FILE   = "entity_registry.json"
PAIRS_FILE      = "ambiguous_pairs.json"

# Reusable methodology + disclaimer block — embed in every generated report.
DISCLAIMER_HTML = """
<div style="
  background:#fefce8;border:1px solid #fde047;border-radius:8px;
  padding:12px 20px;margin:18px 0;font-size:12px;color:#713f12;
  line-height:1.7;direction:rtl;text-align:right">
  <div style="font-weight:700;font-size:13px;margin-bottom:6px">מתודולוגיה וגילוי נאות</div>
  <div style="margin-bottom:6px">
    <strong>אופן ההצגה:</strong>
    הדוח מציג רק אנשים שמופיעים ב־<strong>שני מקורות נתונים או יותר</strong> (cross-source).
    אנשים שמוזכרים במקור יחיד נמצאים <strong>בבסיס הנתונים</strong> אך אינם מקבלים כרטיס פרופיל כאן.
  </div>
  <div>
    <strong>מקורות ושימוש:</strong>
    המידע נאסף ממקורות פתוחים בלבד (OSINT) — אתרי אינטרנט, מסמכים פומביים ופרסומים רשמיים.
    הדוח מיועד <strong>למחקר בלבד</strong> ואינו מהווה מסמך משפטי, ממצא חקירתי מאומת, או קביעה בדבר אחריות כלשהי.
    כל ממצא המופיע כאן מצריך אימות עצמאי לפני שימוש פומבי.
  </div>
  <div style="color:#92400e;font-size:11px;margin-top:6px">
    Cross-source filter (≥2 sources per profile) · Data sourced from public records only · For research use only · Not a legal document · Requires independent verification before publication
  </div>
</div>"""
HTML_FILE       = "connections_report.html"

FUZZY_THRESHOLD = 82   # token_sort_ratio; below this → not a candidate
MIN_NAME_LEN    = 4    # don't fuzzy-match very short names

# Org name aliases: variant → canonical (applied before resolve)
ORG_ALIASES: dict[str, str] = {
    "משרד התרבות":            "משרד התרבות והספורט",
    "משרד התרבות, המדע והספורט": "משרד התרבות והספורט",
    "המשרד לתרבות ולספורט":  "משרד התרבות והספורט",
    "סינמטק תל-אביב":         "סינמטק תל אביב",
    "סינמטק ת\"א":             "סינמטק תל אביב",
    "הקרן החדשה לקולנוע וטלויזיה":   "הקרן החדשה לקולנוע וטלוויזיה",
    "הקרן החדשה לקולנוע ולטלוויזיה": "הקרן החדשה לקולנוע וטלוויזיה",
    "הקרן החדשה לקולנוע ולטלויזיה":  "הקרן החדשה לקולנוע וטלוויזיה",
    # Greenhouse — English/Hebrew variants of the NFCT development lab
    "GREENHOUSE":              "גרינהאוס",
    "Greenhouse":              "גרינהאוס",
    "Greenhouse Films":        "גרינהאוס",
    "Greenhouse Film Center":  "גרינהאוס",
    "Greenhouse Program":      "גרינהאוס",
    "Greenhouse Programme":    "גרינהאוס",
    "GreenProductions":        "גרין פרודקשנס",
    "גרינהאוס פילמס":          "גרינהאוס",
    "גרינהאוס פראגרם":         "גרינהאוס",
    "גרינהאוס - הקרן החדשה לקולנוע וטלוויזיה": "גרינהאוס",
    "תוכנית גרינהאוס":         "גרינהאוס",
    "תכנית גרינהאוס":          "גרינהאוס",
    "תכנית גרינהאוס הבינלאומית": "גרינהאוס",
    "פרויקט גרינהאוס":         "גרינהאוס",
    "גרינהאוס מזרח תיכון":     "גרינהאוס",
    # Production companies — Hebrew/English pairs
    "Heymann Brothers Films":  "סרטי האחים הימן",
    "The Hive Studio":         "סטודיו הייב",
    # Production companies — spacing/abbreviation variants
    "דרומהפקות":               "דרומה הפקות",
    "דנה ושולה סטודיו":        "שולה ודנה הפקות",
}

# Known placeholder / junk strings to discard entirely
JUNK_NAMES_EXACT = {
    # Form placeholders the LLM mistakes for person names
    "שם מלא בעברית", "שם פרטי", "שם משפחה", "שם מלא",
    "full name", "first name", "last name", "name",
    # "Name not provided" variants
    "לא צוין שם", "לא מצוין שם", "שם לא ידוע", "שם לא צוין",
    "לא ידוע", "unknown",
    # Role-category labels (not person names)
    "לקטורים", "לקטור", "יועצים אמנותיים", "יועצים מקצועיים",
    "מנכל הקרן", "מנהל הקרן", "מנהלת הקרן", 'מנכ"ל הקרן', "חברי הועדה", "חבר הנהלה",
    "המנהלת האמנותית", "מנהלת ההפקות", "מנהל האמנותי של הקרן", "מנהלי הקרן החדשה לקולנוע וטלוויזיה",
    "יועצים אמנותיים חיצוניים", "יועצים אמנותיים (לקטורים)",
    "יור ועדת התכניות", "הקרן",
    "לקטורים ומנהלים אמנותיים", "צוות לקטורים",
    # Org names mistaken for people
    "הקרן החדשה לקולנוע וטלוויזיה", "צוות הקרן", "צוות הקרן החדשה לקולנוע וטלוויזיה",
    "הקרן הישראלית לקולנוע", "קרן רבינוביץ",
}

# LLM OCR/extraction errors: wrong Hebrew spelling → correct name
PERSON_NAME_FIXES: dict[str, str] = {
    "טוה אשר": "טובה אשר",
    "וריה שיראל": "מוריה שיראל",
    # Arik Lahav-Leibovitch — editor/screenwriter (EDB n0004600).
    # Sources spell the surname 7 different ways: ליבוביץ / לייבוביץ / לבוביץ,
    # hyphenated or spaced, with straight or curly apostrophe. Canonical = EDB form.
    "אריק להב ליבוביץ":      "אריק להב-לייבוביץ'",
    "אריק להב ליבוביץ'":     "אריק להב-לייבוביץ'",
    "אריק להב ליבוביץ׳":     "אריק להב-לייבוביץ'",
    "אריק להב-ליבוביץ":      "אריק להב-לייבוביץ'",
    "אריק להב-ליבוביץ'":     "אריק להב-לייבוביץ'",
    "אריק להב לייבוביץ'":    "אריק להב-לייבוביץ'",
    "אריק להב לייבוביץ׳":    "אריק להב-לייבוביץ'",
    "אריק להב-לבוביץ'":      "אריק להב-לייבוביץ'",
    # NFCT credits him as just "אריק ליבוביץ" (editor, הזירה 2001) — confirmed
    # same person via he.wikipedia.org/wiki/אריק_להב_ליבוביץ.
    "אריק ליבוביץ":          "אריק להב-לייבוביץ'",
}

# Hebrew words that indicate a description/group rather than a person name
JUNK_WORDS = {"יוצרים", "יוצרות", "תושבי", "תושבות", "חבל", "עצמאיים", "עצמאיות",
              "לקטורים", "יועצים", "חברי", "הועדה"}

# Government/institution names that get misclassified as people
_GOV_LEADING = {"משרד", "ממשלת", "עיריית"}
_GOV_ROLE_LEADING = {"היועץ", "המבקר", "המנהל", "המפקח", "יועץ", "מבקר", "מנהל",
                     "מפקח", "יושב", 'סמנכ"ל', "רואה", "ראש"}
_DELEGATION_LEADING = {"נציג", "נציגי", "נציגים"}


def is_junk_name(name: str) -> bool:
    if not name:
        return True
    low = name.strip().lower()
    if low in JUNK_NAMES_EXACT or name in JUNK_NAMES_EXACT:
        return True
    if name.startswith("http") or name.startswith("שם "):
        return True
    # Role-title phrases: מנהל/ת/י + definite noun (e.g. "מנהלת הקרן", "מנהלי ההפקות")
    if re.match(r'^מנהל(?:ת|י|ים)?\s+ה', name):
        return True
    if re.match(r'^המנהל(?:ת|י|ים)?\s+ה', name):
        return True
    words = name.split()
    if len(words) > 6:         # too many words to be a single person
        return True
    if len(words) == 1:        # single-word "name" — first name only, can't identify a person
        return True
    if any(w in JUNK_WORDS for w in words):
        return True
    # Government entities and institutional role descriptions misclassified as people
    # Check each word, stripping one optional Hebrew prefix letter (ב/מ/ל/כ/ו/ה/ש)
    _GOV_KEYWORDS = {"משרד", "ממשלת", "עיריית", "הרשות"}
    for w in words:
        bare = w[1:] if w and w[0] in "במלכוהש" else w
        if bare in _GOV_KEYWORDS or w in _GOV_KEYWORDS:
            return True
    if words[0] in _DELEGATION_LEADING and len(words) > 2:
        return True
    if "הרשות" in name and words[0] in _GOV_ROLE_LEADING:
        return True
    if words[0] == "ראש" and len(words) > 1 and words[1] == "עיריית":
        return True
    return False


# Titles stripped during normalization
TITLE_RE = re.compile(
    r"^(ד[\"״״]ר|פרופ['’׳]?|מר|גב['’׳]|"
    r"הרב|עו[\"״״]ד|רו[\"״״]ח|ח[\"״״]כ|"
    r"dr\.?|prof\.?|mr\.?|ms\.?|mrs\.?)\s+",
    re.IGNORECASE
)

# Roles that suggest institutional power (investigative relevance)
POWER_ROLES = {
    # Fund roles
    "lector", "appeal_lector", "fund_manager", "ceo", "co_ceo", "director_general",
    "executive_director", "foundation_director", "board_member", "chairperson",
    "council_member", "committee_member", "ministry_official",
    # Festival roles
    "jury_member", "artistic_director", "festival_director", "festival_programmer",
    "prize_committee_member",
    # School roles
    "academic_director", "department_head",
    # Guild roles
    "guild_board_member", "guild_chair",
    # Hebrew variants
    "מנהל", 'מנכ"ל', "לקטור",
}

# Strictly institutional roles — unambiguous conflict-of-interest signals.
# These are GATEKEEPING roles: people who decide which projects get funded/selected.
STRICT_INST_ROLES = {
    "lector", "appeal_lector", "fund_manager", "ceo", "co_ceo", "foundation_director",
    "board_member", "chairperson", "council_member", "committee_member", "committee_chair",
    "ministry_official",
    # Festival gatekeepers — they decide which films screen / win prizes
    "jury_member", "festival_director", "festival_programmer", "prize_committee_member",
    # Guild roles
    "guild_board_member", "guild_chair",
    "לקטור",
}

# Soft ties — institutional presence without direct gatekeeping power.
# Worth surfacing as context but NOT treated as conflict-of-interest triggers.
SOFT_INST_ROLES = {
    # Creative/program leadership — not submission evaluators
    "artistic_director", "art_director", "academic_director", "department_head",
    "lab_mentor", "mentor", "faculty", "alumni",
    # Event roles
    "event_speaker", "event_participant", "acknowledged_partner",
    "guest_speaker", "panelist", "festival_staff",
    # Guild membership (not board)
    "guild_member",
    # Critics — institutional presence in discourse but no gatekeeping power
    "critic",
    # School admin & operational staff
    "administrator", "cinematheque_director", "archivist",
    # Prize recipient — a recorded relationship with the awarding body
    # (institutional context for the person; gatekeeping pairs with this in
    #  CONFLICT_PAIRS below trigger an explicit conflict flag).
    "prize_winner",
}

# Creative roles (less investigative, but relevant for cross-source conflicts)
CREATIVE_ROLES = {
    "producer", "co_producer", "executive_producer", "filmmaker",
    "screenwriter", "director", "מפיק",
}

# Roles safe to use in the film-page fallback crew detection.
# "filmmaker" is excluded: the LLM uses it for "person who is a filmmaker
# and appears in/is interviewed for this documentary" — too ambiguous to
# treat as direct authorship of the film on that page.
FALLBACK_CREW_ROLES = CREATIVE_ROLES - {"filmmaker"}

# Roles that indicate festival/event participation (speaker, moderator, juror)
EVENT_ROLES = {"event_speaker", "event_participant", "jury_member", "panelist", "guest_speaker"}

# Conflict pairs: holding role from set A and set B simultaneously = flag
CONFLICT_PAIRS = [
    # Fund lector + creative credit at same fund = classic conflict
    ({"lector", "appeal_lector"}, {"fund_manager", "ceo", "co_ceo", "executive_director",
                                    "foundation_director", "board_member", "chairperson"}),
    ({"lector", "appeal_lector"}, {"producer", "co_producer", "executive_producer", "director", "filmmaker"}),
    ({"board_member", "council_member", "committee_member", "chairperson"}, {"producer", "filmmaker"}),
    ({"fund_manager", "ceo", "co_ceo", "executive_director"}, {"producer", "co_producer"}),
    # Festival jury / programmer + film in competition = conflict
    ({"jury_member", "festival_programmer", "prize_committee_member"},
     {"producer", "filmmaker", "director"}),
    # Festival/prize gatekeeper at institution X + winner of prize at X (or any).
    # Trips when the SAME person both selected/judged for one festival and won
    # a prize at another (or the same) festival — the cross-source conflict
    # pair logic excludes self-source matches automatically.
    ({"jury_member", "festival_programmer", "prize_committee_member",
      "festival_director", "artistic_director"},
     {"prize_winner"}),
    # Guild prize committee + prize recipient
    ({"prize_committee_member", "guild_board_member"}, {"producer", "filmmaker"}),
]

# Hebrew display labels for source IDs
SOURCE_LABELS_HE = {
    "makor":                "קרן מקור",
    "rabinovich_cinema":    "קרן רבינוביץ",
    "rabinovich_foundation": "קרן רבינוביץ (קרן)",
    "arava_film_fund":      "קרן ערבה",
    "jerusalem_film_fund":  "קרן ירושלים לקולנוע",
    "filmfund":             "הקרן הישראלית לקולנוע",
    "gesher":               "קרן גשר",
    "galilee_film_project": "פרויקט הקולנוע הגלילי",
    "galilee_film_fund":    "קרן הגליל",
    "guidestar":            "גיידסטאר",
    "cash_rebate":          "החזר מס",
    "ministry_of_culture":  "משרד התרבות",
    "film_council":         "מועצת הקולנוע",
    "council_protocols":    "פרוטוקולי המועצה",
    "lectors_database":     "מאגר לקטורים",
    "docaviv_festivals":    "פסטיבלים",
    "film_schools":         "בתי ספר לקולנוע",
    "guilds":               "איגוד מפיקי הטלוויזיה והקולנוע בישראל",
    "archives":             "ארכיונים",
    "recanati_foundation":  "קרן רקנאטי",
    "nfct":                 "הקרן החדשה לקולנוע וטלוויזיה",
    "nfct_new":             "הקרן החדשה לקולנוע וטלוויזיה",
    "jff":                  "פסטיבל הסרטים בירושלים",
    "fdoc":                 "הפורום הדוקומנטרי",
    "festival_data":        "פסטיבלים",
    "haifa_film_festival":      "פסטיבל חיפה",
    "jerusalem_cinematheque":   "סינמטק ירושלים",
    "israeli_film_academy":     "האקדמיה הישראלית לקולנוע וטלוויזיה",
    "writers_guild":            "איגוד התסריטאים הישראלי",
    "sam_spiegel":              "סם שפיגל",
    "critics":                  "מבקרי קולנוע",
    "jff_staff":                "פסטיבל הקולנוע ירושלים",
    "filmmaker_profiles":       "פרופיל יוצר/ת",
}

# Domain → specific display name (overrides generic source label when URL is known)
URL_DOMAIN_LABELS: dict[str, str] = {
    "www.docaviv.co.il":           "DocAviv",
    "docaviv.co.il":               "DocAviv",
    "www.haifaff.co.il":           "פסטיבל חיפה",
    "haifaff.co.il":               "פסטיבל חיפה",
    "tlvfest.com":                 "פסטיבל תל אביב לסטודנטים",
    "www.tlvfest.com":             "פסטיבל תל אביב לסטודנטים",
    "www.animixfest.co.il":        "Animix",
    "animixfest.co.il":            "Animix",
    "jff.org.il":                  "פסטיבל הסרטים בירושלים",
    "www.jff.org.il":              "פסטיבל הסרטים בירושלים",
    "www.israelfilmacademy.co.il": "האקדמיה הישראלית לקולנוע",
    "israelfilmacademy.co.il":     "האקדמיה הישראלית לקולנוע",
    "www.aiff.co.il":              "פסטיבל אילת",
    "aiff.co.il":                  "פסטיבל אילת",
    "www.jsfs.co.il":              "סם שפיגל",
    "jsfs.co.il":                  "סם שפיגל",
    "www.sapir.ac.il":             "מכללת ספיר",
    "sapir.ac.il":                 "מכללת ספיר",
    "arts.tau.ac.il":              "אוניברסיטת תל אביב",
    "www.beitberl.ac.il":          "מכללת בית ברל",
    "beitberl.ac.il":              "מכללת בית ברל",
    "minshar.org.il":              "מנשר לאמנות",
    "www.minshar.org.il":          "מנשר לאמנות",
    "www.bezalel.ac.il":           "בצלאל",
    "bezalel.ac.il":               "בצלאל",
    "www.smkb.ac.il":              "סמינר הקיבוצים",
    "smkb.ac.il":                  "סמינר הקיבוצים",
    "www.ariel.ac.il":             "אוניברסיטת אריאל",
    "ariel.ac.il":                 "אוניברסיטת אריאל",
    "www.openu.ac.il":             "האוניברסיטה הפתוחה",
    "openu.ac.il":                 "האוניברסיטה הפתוחה",
    "meyda.education.gov.il":      "משרד החינוך — מורי קולנוע",
    "www.maale.co.il":             "מעלה",
    "maale.co.il":                 "מעלה",
    "jff.org.il":                  "פסטיבל הקולנוע ירושלים",
    "www.jff.org.il":              "פסטיבל הקולנוע ירושלים",
    "directorsguild.org.il":       "גילדת הבמאים",
    "www.directorsguild.org.il":   "גילדת הבמאים",
    "niveshetcohen.com":           "סוכנות עשת כהן",
    "www.niveshetcohen.com":       "סוכנות עשת כהן",
}

# Sources that should be merged into a canonical source name at load time
SOURCE_ALIASES: dict[str, str] = {
    "nfct_new": "nfct",
    "ministry_of_culture_prizes": "ministry_of_culture",
    "jff_winners":                "jff",
}

CURRENT_YEAR = 2026

# Sources where a null/missing year on an institutional role means "current" —
# i.e. the page shows current staff, not a historical list.
INFER_CURRENT_YEAR_SOURCES: set = {
    "rabinovich_foundation",
    "rabinovich_cinema",
    "filmfund",
    "gesher",
    "makor",
    "galilee_film_fund",
    "arava_film_fund",
    "ministry_of_culture",
    "film_council",
    "film_schools",
    "guilds",
    "haifa_film_festival",
    "jerusalem_cinematheque",
    "recanati_foundation",
    "israeli_film_academy",
    "writers_guild",
    "sam_spiegel",
    "critics",
}


def normalize_source(src: str) -> str:
    return SOURCE_ALIASES.get(src, src)


def he_source(src: str) -> str:
    return SOURCE_LABELS_HE.get(src, src.replace("_", " "))


# ── movies_db.json as the single source of truth for a person's films ───────
# The connections report used to re-derive each person's filmography from raw
# mention URLs (url_to_film + a pile of search-page / transliteration filters).
# That produced a film list that disagreed with films.html and the graph, both
# of which read data/movies_db.json. These helpers make the report read the same
# canonical DB: a person's films are looked up by registry_id (exact, matches
# stable_id("p", name)) with a normalized-name fallback for crew rows that
# movies_db could not resolve to a registry_id (~47% of rows).
_MOVIES_INDEX: dict | None = None

def _build_movies_index() -> dict:
    """Index data/movies_db.json -> {"by_pid": {pid: {film_id: credit}},
    "by_norm": {norm_name: {film_id: credit}}}.
    credit = {film_id, title, year, roles, roles_he, funds, url}."""
    by_pid: dict = defaultdict(dict)
    by_norm: dict = defaultdict(dict)
    path = Path("data/movies_db.json")
    if not path.exists():
        return {"by_pid": {}, "by_norm": {}}
    try:
        db = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"by_pid": {}, "by_norm": {}}

    def _stash(bucket: dict, key: str, fid: str, credit: dict) -> None:
        d = bucket[key]
        if fid in d:
            d[fid]["roles"] |= credit["roles"]
            d[fid]["roles_he"] |= credit["roles_he"]
        else:
            d[fid] = credit

    for f in db:
        title = (f.get("title_he") or f.get("title_en") or "").strip()
        if not title:
            continue
        year  = f.get("year")
        # ~20% of movies_db records have no film_id; fall back to a title|year key
        # so their crew (≈9k rows) is still indexed and deduped.
        fid   = f.get("film_id") or f"t|{normalize_film_title(title)}|{year or ''}"
        funds = f.get("funds") or []
        urls  = f.get("urls") or {}
        # `urls` is normally {source_key: url} but some records store a bare list.
        if isinstance(urls, dict):
            _url_vals = [urls.get("edb")] + list(urls.values())
        elif isinstance(urls, list):
            _url_vals = urls
        else:
            _url_vals = []
        # Prefer URLs whose decoded path contains a significant token from the
        # title — guards against data bugs in movies_db where a fund's URL
        # points to the wrong film (e.g. makor:e97a1f04 "קרוב רחוק" has its
        # `urls.makor` pointing at the "21 יום ולילה" page).
        _candidates = [v for v in _url_vals if isinstance(v, str) and v.startswith("http")]
        from urllib.parse import unquote
        _title_norm = normalize_film_title(title)
        _title_toks = [t for t in _title_norm.split() if len(t) >= 3]
        def _url_matches_title(u: str) -> bool:
            if not _title_toks:
                return True  # nothing to compare against; accept anything
            path = unquote(u).lower()
            return any(t in path for t in _title_toks)
        url = next((v for v in _candidates if _url_matches_title(v)), "")
        if not url and _candidates:
            url = _candidates[0]  # fall back to first if none match (better than nothing)
        title_en = (f.get("title_en") or "").strip()
        for c in (f.get("crew") or []):
            nm = (c.get("name_he") or "").strip()
            if not nm:
                continue
            credit = {
                "film_id": fid, "title": title, "title_en": title_en,
                "year": year, "funds": funds,
                "url": url,
                "roles":    {c.get("role")} if c.get("role") else set(),
                "roles_he": {c.get("role_he")} if c.get("role_he") else set(),
            }
            rid = c.get("registry_id")
            if rid:
                _stash(by_pid, rid, fid, dict(credit, roles=set(credit["roles"]),
                                              roles_he=set(credit["roles_he"])))
            _stash(by_norm, normalize_name(nm), fid,
                   dict(credit, roles=set(credit["roles"]), roles_he=set(credit["roles_he"])))
    return {"by_pid": dict(by_pid), "by_norm": dict(by_norm)}

def person_films(name: str) -> list:
    """All films for a person from movies_db.json, merged by registry_id (exact)
    + normalized name (fallback). Deduped first by film_id, then by normalized
    TITLE — the same film often appears under different source-prefixed film_ids
    (edb:t0001220 vs cinemaofisrael:…), which would otherwise render twice (T26)."""
    global _MOVIES_INDEX
    if _MOVIES_INDEX is None:
        _MOVIES_INDEX = _build_movies_index()
    pid = stable_id("p", name)
    nn  = normalize_name(name)
    out: dict = {}
    for bucket in (_MOVIES_INDEX["by_pid"].get(pid, {}),
                   _MOVIES_INDEX["by_norm"].get(nn, {})):
        for fid, c in bucket.items():
            if fid in out:
                out[fid]["roles"]    |= c["roles"]
                out[fid]["roles_he"] |= c["roles_he"]
            else:
                out[fid] = {**c, "roles": set(c["roles"]), "roles_he": set(c["roles_he"])}

    # Collapse cross-source duplicates of the same film (different film_id, same title).
    by_title: dict = {}
    for c in out.values():
        tkey = normalize_film_title(c["title"]) or c["film_id"]
        m = by_title.get(tkey)
        if m is None:
            by_title[tkey] = c
            continue
        m["roles"]    |= c["roles"]
        m["roles_he"] |= c["roles_he"]
        if not m.get("year") and c.get("year"):
            m["year"] = c["year"]
        # prefer an EDB film page as the canonical link
        if "edb.co.il" not in (m.get("url") or "") and "edb.co.il" in (c.get("url") or ""):
            m["url"] = c["url"]
        elif not m.get("url") and c.get("url"):
            m["url"] = c["url"]
        # prefer a Hebrew title for display
        if not _HEB_CHAR_RE.search(m["title"]) and _HEB_CHAR_RE.search(c["title"]):
            m["title"] = c["title"]
        m["funds"] = list(dict.fromkeys((m.get("funds") or []) + (c.get("funds") or [])))

    # Second pass: merge titles where one is a strict word-suffix of the other.
    # Catches transliterated Arabic prefixes the Arabic-strip can't reach,
    # e.g. "קרוב רחוק" ↔ "קירבה גירבה קרוב רחוק" (Hebrew transliteration of
    # the Arabic "قربة غربة" still glued onto the canonical Hebrew title).
    # Only safe when the shorter title has ≥2 words (avoid merging "מלך" into
    # everything that ends "… מלך").
    items = list(by_title.items())
    items.sort(key=lambda kv: len(kv[0].split()))  # shortest first → canonical base
    merged_by: dict = {}
    final: dict = {}
    for tkey, c in items:
        toks = tkey.split()
        absorbed_into = None
        if len(toks) >= 2:
            for ktkey, kc in final.items():
                ktoks = ktkey.split()
                # other title ends with ours, and is longer → ours is the base
                if len(ktoks) > len(toks) and ktoks[-len(toks):] == toks:
                    absorbed_into = ktkey  # keep the long key as the bucket
                    break
                # we end with theirs, theirs is shorter → they're the base; absorb us into them
                if len(toks) > len(ktoks) and toks[-len(ktoks):] == ktoks:
                    absorbed_into = ktkey
                    break
        if absorbed_into is None:
            final[tkey] = c
            continue
        m = final[absorbed_into]
        m["roles"]    |= c["roles"]
        m["roles_he"] |= c["roles_he"]
        if not m.get("year") and c.get("year"):
            m["year"] = c["year"]
        if "edb.co.il" not in (m.get("url") or "") and "edb.co.il" in (c.get("url") or ""):
            m["url"] = c["url"]
        elif not m.get("url") and c.get("url"):
            m["url"] = c["url"]
        # Prefer the SHORTER canonical title for display (drop the transliteration prefix).
        if len(c["title"].split()) < len(m["title"].split()):
            m["title"] = c["title"]
        m["funds"] = list(dict.fromkeys((m.get("funds") or []) + (c.get("funds") or [])))

    # Third pass: dedup by English title. Two records with the same normalized
    # title_en (e.g. "Nandauri") are the same film even when Hebrew spellings
    # diverge ("נאנדאורי" vs "ננדאורי") — different mater-lectionis choices in
    # transliteration. Only films with title_en participate; films without
    # title_en fall through unchanged.
    by_en: dict = {}
    out_list = []
    for c in final.values():
        ten = normalize_film_title(c.get("title_en") or "")
        # Don't merge unless title_en is a real Latin-script transliteration
        # (≥3 letters, contains alpha) — avoid bucketing all "" together.
        if ten and len(ten) >= 3 and any(ch.isalpha() and ord(ch) < 0x590 for ch in ten):
            if ten in by_en:
                m = by_en[ten]
                m["roles"]    |= c["roles"]
                m["roles_he"] |= c["roles_he"]
                if not m.get("year") and c.get("year"):
                    m["year"] = c["year"]
                if "edb.co.il" not in (m.get("url") or "") and "edb.co.il" in (c.get("url") or ""):
                    m["url"] = c["url"]
                elif not m.get("url") and c.get("url"):
                    m["url"] = c["url"]
                # Prefer Hebrew title for display; if both Hebrew, prefer shorter
                m_is_he = bool(_HEB_CHAR_RE.search(m["title"]))
                c_is_he = bool(_HEB_CHAR_RE.search(c["title"]))
                if c_is_he and not m_is_he:
                    m["title"] = c["title"]
                elif c_is_he and m_is_he and len(c["title"]) < len(m["title"]):
                    m["title"] = c["title"]
                m["funds"] = list(dict.fromkeys((m.get("funds") or []) + (c.get("funds") or [])))
                continue
            by_en[ten] = c
        out_list.append(c)
    return out_list


def he_source_for_url(src: str, url: str) -> str:
    """Return a specific label derived from the URL domain when available,
    falling back to the generic source label. Used for multi-org sources
    like docaviv_festivals where one source covers multiple organizations."""
    if url and not url.startswith("manual://"):
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.lower()
            if domain in URL_DOMAIN_LABELS:
                return URL_DOMAIN_LABELS[domain]
        except Exception:
            pass
    return he_source(src)


# One color per source (cycles if > len)
SOURCE_PALETTE = [
    "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
    "#06b6d4", "#f97316", "#84cc16", "#ec4899", "#6366f1",
    "#14b8a6", "#a855f7", "#0ea5e9", "#d946ef", "#22c55e",
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def stable_id(prefix: str, name: str) -> str:
    h = hashlib.md5(name.strip().encode("utf-8")).hexdigest()[:8]
    return f"{prefix}_{h}"


import urllib.parse as _urlparse_mod


def normalize_url(url: str) -> str:
    """Decode percent-encoding and lowercase the host so URLs that differ only in
    encoding case collapse to one. The same WordPress page is scraped as both
    `%D7%90...` and `%d7%90...` and as native Hebrew — all should dedupe.
    Also normalizes query-string space encoding (%20 vs +) so search-page URLs
    that differ only in space encoding collapse to the same key."""
    if not url: return ""
    # NFCT LLM extractions sometimes concatenate the URL with the markdown link
    # title (e.g. `https://… "title"`). Strip anything from the first whitespace
    # or quote so the URL is usable as an href (T22 fix).
    url = re.split(r'[\s"\']', url, maxsplit=1)[0]
    try:
        decoded = _urlparse_mod.unquote_plus(url)
    except Exception:
        decoded = url
    p = _urlparse_mod.urlsplit(decoded)
    return _urlparse_mod.urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip("/"),
                                     p.query, ""))


_COMMENT_FRAG_RE = re.compile(r"^#U[A-Za-z0-9]{4,}$")  # Disqus / WP comment anchors


_BAD_URL_CHARS_RE = re.compile(r'[\s"\'\\]')  # spaces, quotes, backslashes in URL = malformed


def is_valid_url(url: str) -> bool:
    """Return True only for URLs safe to use as href attributes (http/https only)."""
    if not url or url.startswith("manual://"):
        return False
    return not bool(_BAD_URL_CHARS_RE.search(url))


def strip_comment_fragment(url: str) -> str:
    """Remove Disqus/comment-system fragment anchors (e.g. #UAmlxHHRM4) from URLs.
    These anchors point to dynamic comment threads that no longer resolve."""
    if "#" not in url:
        return url
    base, frag = url.rsplit("#", 1)
    if _COMMENT_FRAG_RE.match("#" + frag):
        return base
    return url


def dedupe_urls(urls: list) -> list:
    """Return URLs in original order, removing variants that normalize to the same URL."""
    seen, out = set(), []
    for u in urls:
        n = normalize_url(u)
        if n in seen: continue
        seen.add(n)
        out.append(u)
    return out


_FILM_SUFFIX_RE = re.compile(
    r"\s*[–\-]\s*(הגרסה|גרסה|הנוסחה|גרסאות|director.s cut|extended|full version"
    r"|פרק|חלק|עונה|season|episode|ep\.?|part)\s*\d*\s*$",
    re.IGNORECASE,
)

def normalize_film_title(title: str) -> str:
    """Normalize a film title for cross-source deduplication."""
    n = title.strip().lower()
    n = re.sub(r"\(\s*ש\.?ל\.?ר\s*\)", " ", n)   # EDB "(ש.ל.ר)" title marker
    n = re.sub(r"\[[^\]]*\]", " ", n)             # [קצר]/[תיעודי] genre-format tags
    # Fold straight + curly quotes/apostrophes; colon/dash → space
    # (handles "The Ambassador’s Wife" == "The Ambassador's Wife").
    n = re.sub(r"[\"'״׳.,!?:–—\-‘’“”]", " ", n)
    n = _FILM_SUFFIX_RE.sub("", n).strip()
    # Collapse mater lectionis: וי → ו at word boundary (e.g. דויד→דוד)
    n = re.sub(r"וי(?=\s|$|[^א-ת])", "ו", n)
    # Strip Arabic-script characters and diacritics — Israeli films often appear
    # with the Arabic translation prepended to the Hebrew title (e.g.
    # "قربة غربة קרוב רחוק" should match "קרוב רחוק" for dedup).
    n = re.sub(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]+", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def normalize_name(name: str) -> str:
    if not name:
        return ""
    n = name.strip()
    n = TITLE_RE.sub("", n)                        # strip honorifics
    n = re.sub(r"[\"'״׳׳״.,]", "", n)       # strip punctuation
    n = re.sub(r"[\-–—]", " ", n)           # dashes → space (preserves word boundaries)
    n = re.sub(r"\s+", " ", n).strip()      # collapse whitespace
    return n


# Normalize verbose/English LLM role strings to canonical IDs
ROLE_NORMALIZE: dict[str, str] = {
    "head of documentary department":                   "department_head",
    "head of documentaries":                            "department_head",
    "head_of_documentary_and_investigative_department": "department_head",
    "head of drama":                                    "department_head",
    "head of content":                                  "department_head",
    "artistic director":                                "artistic_director",
    "art director":                                     "art_director",
    "executive director":                               "executive_director",
    "creative director":                                "artistic_director",
    "musician":                                         "composer",
    # Hyphenated / spaced variants that the LLM emits inconsistently
    "co-director":          "co_director",
    "co-producer":          "co_producer",
    "co director":          "co_director",
    "co producer":          "co_producer",
    "music composer":       "composer",
    "sound editor":         "sound_editor",
    "voice actor":          "actor",
    "animation director":   "animation_director",
    "online editor":        "online_editor",
    "script editor":        "editor",
    "soundtrack composer":  "composer",
    "original soundtrack":  "composer",
    "executive producer":   "executive_producer",
    "visual effects":       "visual_effects_supervisor",
    "visual_effects":       "visual_effects_supervisor",
    "visual_effects_designer": "visual_effects_supervisor",
    "original_music":       "composer",
    "original_soundtrack_composer": "composer",
    "script":               "screenwriter",
    "designer":             "production_designer",
    "animation":            "animator",
    "presenter":            "moderator",
    "color_corrector":      "colorist",
    "vfx_artist":           "visual_effects_supervisor",
    "visual_effects_artist": "visual_effects_supervisor",
    "chair of the film and new media committee":    "committee_chair",
    "chairman of the film and new media committee": "committee_chair",
    "soundtrack":           "composer",
    "sound_composer":       "composer",
    "soundtrack_composer":  "composer",
    "additional cinematographer": "cinematographer",
    "production_company":   "other",
    "system":               "other",
}

# Roles that describe a person's appearance in a film, not their profession —
# suppress from profile chip row entirely.
SUPPRESS_CHIP_ROLES: set[str] = {
    "self", "character", "subject", "fictional_character",
    "film_subject", "subject_of_film", "subject_of_documentary",
}

# Roles shown in film credit rows (extends CREATIVE_ROLES with on-set/mentor roles)
FILM_CREDIT_ROLES: set[str] = {
    "producer", "co_producer", "executive_producer", "filmmaker",
    "screenwriter", "director", "co_director", "מפיק",
    "creator", "co_creator", "xr_creator",
    "overall_mentor", "project_mentor", "editing_mentor", "directing_mentor",
    "editor", "cinematographer", "composer", "sound_designer",
    "casting_director", "line_producer", "production_designer",
    "actor",
}


def role_set(roles) -> set:
    return {ROLE_NORMALIZE.get(r.strip().lower(), r.strip().lower())
            for r in (roles or []) if r}


# ── Gender detection ───────────────────────────────────────────────────────────

# Unambiguously female Israeli first names
FEMALE_NAMES: set = {
    "שרה", "רבקה", "לאה", "רחל", "מרים", "דבורה", "חנה", "תמר", "נעמי", "רות",
    "אסתר", "נועה", "מיכל", "אביגיל", "דינה", "ענת", "יעל", "גלית", "אורית", "מיה",
    "לי", "אילנה", "יפית", "ציפי", "ריקי", "ורד", "דפנה", "רונית", "אפרת", "טלי",
    "שיר", "עינב", "כרמית", "ליאת", "ניצן", "שירה", "עדי", "הילה", "ענבל",
    "תמי", "שולמית", "פנינה", "שושנה", "עליזה", "רינה", "ניצה", "אסנת", "אורנה",
    "לירון", "מיטל", "אהובה", "נירית", "אמירה", "גאולה", "אדוה",
    "יונית", "רחלי", "נעמה", "שרון", "נגה", "אורה", "ברכה", "גילה", "זהבה",
    "טובה", "יהודית", "כוכבה", "מרגלית", "נחמה", "ציפורה", "תרצה", "בתיה", "חיה",
    "מינה", "עדינה", "פרידה", "צביה", "קלרה", "רוזה", "שיינדל", "ויקטוריה",
    "ג׳ניפר", "סוזן", "פאולה", "אירית", "גנית", "מאיה", "נירה", "עינת", "צליל",
    "קטי", "רינת", "שנית", "תהילה", "יפה", "חגית", "רחמה", "זוהרה", "רוני",
    "אגם", "דנה", "לירי", "נטע", "איילת", "אביטל", "שושי", "חנית", "ורדית",
    "הדסה", "יעלי", "ציונה", "אורלי", "בלה", "לילך", "אלמה", "נורית",
    "נאוה", "ליהי", "רותם", "ספיר",
    # Common names missing from original list
    "מעיין", "מירי", "שני", "צמרת", "לי-אור", "מור", "זהר",
    "אביה", "שילה", "שחרית", "לינור", "ירדנה",
    "דליה", "ציפה", "ריטה", "מרב", "שירן", "רוית", "כלנית",
    "מיכאלה", "נטלי", "גבריאלה", "אנה", "יוליה", "נינה", "מרינה",
    "אלנה", "קסניה", "איריס", "ליבי", "סיגל", "רותי",
    "עדנה", "ופא", "מייסם", "נדאא", "אמל", "רים", "חנאן", "מרוה",
    "סנא", "לובנה", "אסמאא", "שרין", "מאיסם", "ראמה", "ולאא", "בתל",
    # Western female names used in Israel
    "ג'ולי", "שירלי", "סופי", "ג'ין", "קארן", "לינדה", "מוניקה",
    "ג'ני", "אנה", "לורה", "סנדרה", "רחל", "קתרין", "ג'סיקה",
    # More Israeli female names
    "רויטל", "לימור", "אסתי", "מיטל", "הדר", "שלי", "אילת",
    "קציעה", "טובית", "זמירה", "פנינית", "יפעת", "חמוטל",
    "מורן", "שי", "יפה",
    # Arabic female names common in Israeli film
    "נוף", "למיס", "מאיסם", "ספאא", "לינא", "סואר", "נדאל",
    "אסיל", "דימה", "ניבין", "אמאל", "הלא", "ריהאם",
}

# Unambiguously male Israeli first names
MALE_NAMES: set = {
    "דוד", "משה", "אברהם", "יצחק", "יעקב", "יוסף", "שלמה", "אהרון", "לוי", "שמעון",
    "דניאל", "גבריאל", "מיכאל", "רפאל", "אורי", "רון", "יואב", "איתן", "עמיר", "גיל",
    "אבי", "נתן", "ניר", "אייל", "אלון", "אמיר", "ארז", "ברק", "גד",
    "דרור", "הראל", "זיו", "חגי", "יואל", "כפיר", "לירן", "מורן",
    "פיני", "צור", "קובי", "רועי", "שחר", "תום", "אדם", "בן", "דן",
    "הדר", "חן", "ידין", "יניב", "כרם", "לב", "מאור", "נמרוד", "ענר", "פז", "צבי",
    "ראם", "אבנר", "בועז", "גדעון", "דב", "הלל", "ויקטור", "זאב",
    "חיים", "טוביה", "יהודה", "כלב", "מנחם", "נחום", "עזרא", "פינחס", "צדוק", "קיש",
    "ראובן", "שמואל", "ישי", "אביב", "אופיר", "אליאב", "בנימין", "גרשון", "הרצל",
    "ויצמן", "זכריה", "חנוך", "יורם", "כדורי", "לאור", "מרדכי", "נסים", "עמוס",
    "פרץ", "ציון", "קלמן", "רמי", "שלו", "תמיר", "אסף", "אורן", "ירון", "יריב",
    "שלומי", "יאיר", "עידו", "גיורא", "אמנון", "נחמן", "יהושע", "פנחס",
    "שמשון", "גדליה", "מתתיהו", "אלחנן", "ירמיהו", "יחזקאל", "חבקוק",
    # Common names missing from original list
    "גיא", "יונתן", "יהונתן", "איתי", "ערן", "יוסי", "דני", "תומר", "נדב",
    "אריאל", "עידן", "דורון", "יותם", "עמרי", "רונן", "אילן", "גלעד",
    "אריק", "אלכס", "איתמר", "אוהד", "עומרי", "רוי", "מתן", "עופר",
    "עודד", "אלעד", "אמרי", "אודי", "מאיר", "אסי", "מוטי", "עמנואל",
    "ניב", "שגיא", "יגאל", "בנצי", "מיכי", "צחי", "אלדד", "נעם",
    "אלי", "ג'ונתן", "ג'וני", "ג'ק", "ג'אד", "אנדרה", "מרסל", "פייר",
    # Arabic male names common in Israeli film industry
    "חליל", "ואיל", "ראמי", "נאדר", "בשיר", "פאדי", "מחמוד", "זיאד",
    "יאסר", "ח'אלד", "ג'מאל", "פואד", "סאמי", "חנא", "ואליד", "נדאל",
    "רפיק", "בסאם", "נאיף", "כמאל", "עאדל", "טארק", "מאזן", "האני",
    # More Israeli male names
    "רובי", "בני", "עמיקם", "רם", "ארי", "פלג", "בוריס", "רן",
    "יוחנן", "אשר", "דולב", "ארקדי", "דידי", "עמי", "ספי", "ביבי",
    "רוברט", "מוריס", "ג'ק", "לאוניד", "בוריס", "אנדריי", "ולדי",
    "שאול", "מנחם", "גדי", "שמעיה", "בנצי", "פייסל", "חמד", "בדר",
}

# Unisex names — do NOT classify these (return unknown)
_UNISEX_NAMES: set = {
    "טל", "עמית", "שי", "גל", "קרן", "עומר", "נועם", "אביב", "עדן", "שחר",
    "ליאור", "ניצן", "רון", "דן", "אור", "נוי", "ים", "רום", "שקד",
}

# Male names that end with ה (exception to the female heuristic)
_MALE_HE_ENDINGS: set = {
    "משה", "יהודה", "אליהו", "נחמיה", "זכריה", "ירמיה", "ישעיה", "עובדיה", "מנשה",
    "יוסה", "נטעה", "לביה", "ראובנה",
}


def infer_gender(name_he: str) -> str:
    """Infer gender from a Hebrew first name. Returns 'f', 'm', or 'unknown'."""
    if not name_he:
        return "unknown"
    first = name_he.strip().split()[0]
    if first in _UNISEX_NAMES:
        return "unknown"
    if first in FEMALE_NAMES:
        return "f"
    if first in MALE_NAMES:
        return "m"
    # Heuristic fallback
    if first.endswith("ית"):
        return "f"
    if len(first) > 2 and first.endswith("ה") and first not in _MALE_HE_ENDINGS:
        return "f"
    return "unknown"


# Hebrew grammatical gender markers found in context sentences.
# Past-tense verbs and role nouns are grammatically gendered in Hebrew,
# so "טל הייתה מפיקה" unambiguously signals female.
_CTX_FEMININE = {
    # Pa'al past tense feminine (ה ending — unambiguous for these roots)
    "כתבה", "עבדה", "למדה", "שיחקה", "עמדה", "ישבה", "קמה", "הלכה", "באה",
    "פעלה", "ניסתה", "הצליחה", "חיה", "עסקה", "נשאה",
    # Pi'el past tense feminine
    "ניהלה", "פרסמה", "ייסדה", "לימדה", "ייצגה", "גייסה", "השתתפה",
    "ביימה", "הפיקה", "קיימה", "שיתפה", "הציגה", "ליוותה",
    "כיהנה", "שימשה", "עיצבה", "צילמה", "ביצעה",
    # Hiph'il past tense feminine
    "הובילה", "הקימה", "השלימה", "סיימה", "הופיעה", "הגישה",
    # Common auxiliaries / verbs feminine
    "הייתה", "היתה", "זכתה", "קיבלה", "נבחרה", "מונתה", "הוכרה",
    "חיברה", "השתתפה", "פנתה", "כתבה",
    # Feminine role / title nouns
    "מפיקה", "במאית", "שחקנית", "עורכת", "לקטורית", "יועצת", "מנהלת",
    'מנכ"לית', "רכזת", "מתאמת", "מייסדת", "תסריטאית", "צלמת",
    "כותבת", "אמנית", "חוקרת", "סופרת", "מגישה", "נשיאה", "מפקחת",
    "מקדמת", "עורכת-דין", "פסלת", "ציירת", "מוסיקאית",
    # Feminine role words in credit-list format (e.g. "בימוי: [name]" → not useful,
    # but "מפיקה: [name]" IS useful — however we need to handle "הפקה:" separately)
    "יוצרת", "מחברת", "מחזאית",
}

_CTX_MASCULINE = {
    # Pa'al past tense masculine (no ה ending)
    "כתב", "עבד", "למד", "שיחק", "עמד", "ישב", "הלך", "בא",
    "פעל", "ניסה", "הצליח", "עסק", "נשא",
    # Pi'el past tense masculine
    "ניהל", "פרסם", "ייסד", "לימד", "ייצג", "גייס", "השתתף",
    "ביים", "הפיק", "קיים", "שיתף", "הציג",
    "כיהן", "שימש", "עיצב", "צילם", "ביצע",
    # Hiph'il past tense masculine
    "הוביל", "הקים", "השלים", "סיים", "הופיע", "הגיש",
    # Common auxiliaries / verbs masculine
    "היה", "זכה", "קיבל", "נבחר", "הוכר", "חיבר", "פנה",
    # Masculine role / title nouns
    "מפיק", "במאי", "שחקן", "עורך", "לקטור", "יועץ", "מנהל",
    'מנכ"ל', "רכז", "מתאם", "מייסד", "תסריטאי", "צלם",
    "כותב", "אמן", "חוקר", "סופר", "מגיש", "נשיא", "מפקח",
    "יזם", "יוצר", "מחבר", "מחזאי", "עורך-דין", "פסל", "צייר",
}

# ה-ending words that are MASCULINE (Hiph'il/Pi'el from ו/י/ה roots) — exclude from
# naive feminine heuristic inside context scanning
_MASC_HE_VERBS = {"ליווה", "ראה", "הראה", "עשה", "רצה", "בנה", "קנה", "שתה"}

_CTX_SPLIT_RE = re.compile(r'[\s,\.;:!\?\-–—״"\'()\[\]/]+')
# Hebrew preposition/conjunction prefixes that attach to words
_HE_PREFIXES = ("בה", "וה", "כה", "שה", "לה", "מה", "ב", "ו", "ל", "כ", "ש", "ה")
_HEB_CHAR_RE  = re.compile(r"[א-ת]")   # any Hebrew letter


def _ctx_word_variants(word: str) -> list:
    """Return a word and its prefix-stripped variant."""
    for p in _HE_PREFIXES:
        if word.startswith(p) and len(word) > len(p) + 1:
            return [word, word[len(p):]]
    return [word]


def infer_gender_from_context(contexts: list) -> str:
    """
    Scan Hebrew context sentences for grammatical gender markers.
    Handles Hebrew prefixes (ו/ב/ל/כ/ש/ה) attached to role words.
    Returns 'f', 'm', or 'unknown'.
    """
    f_score = 0
    m_score = 0
    for ctx in contexts:
        if not ctx:
            continue
        for raw_word in _CTX_SPLIT_RE.split(ctx):
            if not raw_word:
                continue
            for word in _ctx_word_variants(raw_word):
                if word in _CTX_FEMININE:
                    f_score += 1
                    break
                if word in _CTX_MASCULINE:
                    m_score += 1
                    break
    if f_score > m_score:
        return "f"
    if m_score > f_score:
        return "m"
    return "unknown"


def resolve_gender(members: list) -> str:
    """
    Determine gender for a group of person mentions.
    Priority: context-sentence grammar > name-lookup voting > morphology.
    """
    contexts = [m.get("context", "") for m in members if m.get("context")]
    g = infer_gender_from_context(contexts)
    if g != "unknown":
        return g
    votes: dict = {"f": 0, "m": 0, "unknown": 0}
    for m in members:
        votes[infer_gender(m["name_he"])] += 1
    if votes["f"] > votes["m"] and votes["f"] > votes["unknown"]:
        return "f"
    if votes["m"] > votes["f"] and votes["m"] > votes["unknown"]:
        return "m"
    return "unknown"


# ── Loading ────────────────────────────────────────────────────────────────────

def _iter_jsonl(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except Exception:
        return


def _load_raw_records(mentions_glob: str) -> list:
    """Parse all JSONL files once; returns list of (path, record) pairs.
    Call this in main() and pass the result to the three loaders to avoid
    reading the same files three times."""
    result = []
    for path in sorted(glob.glob(mentions_glob)):
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    try:
                        result.append((path, json.loads(line)))
                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue
    return result


def load_url_to_film(mentions_glob: str, _cache: list = None) -> dict:
    """Build a {normalized_url: {title, year}} map for every film across all sources,
    so we can show 'Movie Title (year)' instead of raw URLs in the people cards."""
    url_to_film: dict = {}
    IS_HEBREW = re.compile(r'[א-ת]')
    pairs = _cache if _cache is not None else [
        (path, r)
        for path in sorted(glob.glob(mentions_glob))
        for r in _iter_jsonl(path)
    ]
    for _path, r in pairs:
        if r.get("status") != "ok":
            continue
        url = r.get("url") or r.get("file") or ""
        if not url:
            continue
        # Skip search-result pages — they list many films out of context
        if re.search(r"[?&](keywords|search|q|s)=", url, re.IGNORECASE):
            continue
        films = (r.get("data") or {}).get("entities", {}).get("films", {}) or {}
        if not films:
            continue
        best_title, best_year = "", None
        for film in films.values():
            if not film:
                continue
            t_he = (film.get("title_he") or "").strip()
            t_en = (film.get("title_en") or "").strip()
            title = t_he if (t_he and IS_HEBREW.search(t_he)) else (t_en or t_he)
            if not title:
                continue
            if not best_title or (IS_HEBREW.search(title) and not IS_HEBREW.search(best_title)):
                best_title = title
                try:
                    best_year = int(film.get("year")) if film.get("year") else None
                except (TypeError, ValueError):
                    best_year = None
        if best_title:
            nurl = normalize_url(url)
            url_to_film.setdefault(nurl, {"title": best_title, "year": best_year})
        # Also index each film entity's own URL (e.g. EDB person-page records
        # embed per-film URLs that differ from the record URL).
        for film in films.values():
            if not film:
                continue
            fu = (film.get("url") or "").strip()
            if not fu or fu == url:
                continue
            t_he = (film.get("title_he") or "").strip()
            t_en = (film.get("title_en") or "").strip()
            title = t_he if (t_he and IS_HEBREW.search(t_he)) else (t_en or t_he)
            if not title:
                continue
            try:
                yr = int(film.get("year")) if film.get("year") else None
            except (TypeError, ValueError):
                yr = None
            url_to_film.setdefault(normalize_url(fu), {"title": title, "year": yr})
    # Build secondary index: normalized film title → best external URL
    # (used to upgrade manual:// URLs at render time)
    title_to_url: dict = {}
    for nurl, film in url_to_film.items():
        if not nurl.startswith("manual://") and film.get("title"):
            norm = normalize_film_title(film["title"])
            title_to_url.setdefault(norm, nurl)
    url_to_film["__title_to_url__"] = title_to_url  # piggyback to avoid API change
    return url_to_film


def load_mentions(mentions_glob: str, _cache: list = None):
    """Return flat lists of person and org mentions with full provenance."""
    people_raw = []   # list of dicts
    orgs_raw   = []

    if _cache is None:
        paths = sorted(glob.glob(mentions_glob))
        if not paths:
            print(f"ERROR: no files matching {mentions_glob}", file=sys.stderr)
            sys.exit(1)
        pairs = [(path, r) for path in paths for r in _iter_jsonl(path)]
    else:
        pairs = _cache

    total = 0
    for _path, r in pairs:
        if r.get("status") != "ok":
            continue
        total += 1
        src   = normalize_source(r.get("source_name", "unknown"))
        file_ = r.get("file", "")
        url   = r.get("url", "")
        # NFCT LLM extractions sometimes concatenate the URL with the markdown
        # link title — strip anything from the first whitespace/quote (T22).
        if url:
            url = re.split(r'[\s"\']', url, maxsplit=1)[0]
        data  = r.get("data") or {}
        entities = data.get("entities") or {}

        # Build year lookup from roles array: entity_id → set of years
        role_year_map: dict = defaultdict(set)
        for rrec in (data.get("roles") or []):
            pid_r = rrec.get("person_id")
            if not pid_r:
                continue
            for ykey in ("start_year", "end_year"):
                y = rrec.get(ykey)
                try:
                    y = int(y) if y not in (None, "", "null") else None
                except (TypeError, ValueError):
                    y = None
                if y and 1980 <= y <= 2030:
                    role_year_map[pid_r].add(y)

        for eid, p in (entities.get("people") or {}).items():
            if not p or not p.get("name_he"):
                continue
            if is_junk_name(p["name_he"]):
                continue
            p_roles = role_set(p.get("primary_roles"))
            if "government_body" in p_roles:
                continue  # organization misclassified as person
            # For NFCT (and nfct_new), "lector" role is only trustworthy from the
            # official /lectors/ page or linked PDFs. Blog posts, film pages, and
            # archive search pages mention lectors in passing → false positives.
            if src in ("nfct", "nfct_new") and "lector" in p_roles:
                u = (url or "")
                if "/lectors" not in u and "lectors" not in u:
                    p_roles = p_roles - {"lector"}
                    if not p_roles:
                        continue
            # For Makor, lector role is only valid from the canonical import or
            # lector-specific pages (lab/workshop pages produce false positives).
            if src == "makor" and "lector" in p_roles:
                u = (url or "")
                if not u.startswith("manual://") and "lector" not in u and "לקטור" not in u:
                    p_roles = p_roles - {"lector"}
                    if not p_roles:
                        continue
            raw_name = p["name_he"].strip()
            raw_name = PERSON_NAME_FIXES.get(raw_name, raw_name)
            # Collect per-film URLs embedded in the record (e.g. EDB person-page
            # records embed each film's canonical /title/ URL in the film entity).
            _film_urls = [
                strip_comment_fragment(re.split(r'[\s"\']', f["url"], maxsplit=1)[0])
                for f in (entities.get("films") or {}).values()
                if f and (f.get("url") or "").strip() and f["url"] != url
            ]
            people_raw.append({
                "name_he":   raw_name,
                "name_en":   (p.get("name_en") or "").strip(),
                "roles":     p_roles,
                "source":    src,
                "file":      file_,
                "url":       strip_comment_fragment(url),
                "page_id":   eid,
                "years":     sorted(role_year_map.get(eid, set())),
                "context":   (p.get("context_sentence") or "").strip()[:150],
                "notes":     (p.get("notes") or "").strip(),
                "film_urls": _film_urls,
            })

        for eid, o in (entities.get("organizations") or {}).items():
            if not o or not o.get("name_he"):
                continue
            _raw = o["name_he"].strip()
            # Strip legal suffix בע"מ / בעמ (Ltd.) before alias lookup
            _raw = re.sub(r'\s+בע["״]?מ\b', '', _raw).strip()
            org_name_he = ORG_ALIASES.get(_raw, _raw)
            orgs_raw.append({
                "name_he": org_name_he,
                "name_en": (o.get("name_en") or "").strip(),
                "type":    o.get("type", ""),
                "source":  src,
                "file":    file_,
                "url":     url,
                "page_id": eid,
            })

    print(f"Loaded {total} ok records → {len(people_raw)} person mentions, "
          f"{len(orgs_raw)} org mentions")
    return people_raw, orgs_raw


# ── Resolution ─────────────────────────────────────────────────────────────────

def resolve(mentions: list, id_prefix: str, use_fuzzy: bool):
    """
    Resolve mentions into canonical groups.
    Returns:
      groups        — dict {canonical_name_he: [mention, ...]}
      norm_map      — dict {normalized_name: canonical_name}
      ambiguous     — list of (name_a, name_b, score) candidate pairs
    """
    # Pass 1: exact grouping by name_he
    exact: dict[str, list] = defaultdict(list)
    for m in mentions:
        exact[m["name_he"]].append(m)

    # Pass 2: normalized grouping
    norm_map: dict[str, str] = {}   # normalized → canonical (first seen)
    groups:   dict[str, list] = defaultdict(list)

    for name_he, members in exact.items():
        norm = normalize_name(name_he)
        if norm in norm_map:
            canonical = norm_map[norm]
        else:
            canonical = name_he
            norm_map[norm] = canonical
        groups[canonical].extend(members)

    # Pass 3: fuzzy candidates (rapidfuzz)
    ambiguous = []
    if use_fuzzy and HAS_RAPIDFUZZ:
        canonical_names = [n for n in groups if len(n) >= MIN_NAME_LEN]
        norms = {n: normalize_name(n) for n in canonical_names}
        checked = set()
        for i, a in enumerate(canonical_names):
            for b in canonical_names[i + 1:]:
                pair = (min(a, b), max(a, b))
                if pair in checked:
                    continue
                checked.add(pair)
                score = rfuzz.token_sort_ratio(norms[a], norms[b])
                if score >= FUZZY_THRESHOLD:
                    ambiguous.append({
                        "name_a": a, "name_b": b, "score": score,
                        "norm_a": norms[a], "norm_b": norms[b],
                        "count_a": len(groups[a]), "count_b": len(groups[b]),
                    })
        ambiguous.sort(key=lambda x: -x["score"])

    return dict(groups), norm_map, ambiguous


# ── Registry building ──────────────────────────────────────────────────────────

def build_registry(people_groups: dict, org_groups: dict) -> dict:
    registry = {"people": {}, "organizations": {}, "generated_at": datetime.now().isoformat()}

    for canonical, members in people_groups.items():
        pid = stable_id("p", canonical)
        aliases = sorted({m["name_he"] for m in members} - {canonical})
        en_names = sorted({m["name_en"] for m in members if m["name_en"]})
        all_roles: set = set()
        sources_by_src: dict[str, set] = defaultdict(set)
        roles_by_src:   dict[str, set] = defaultdict(set)
        for m in members:
            all_roles |= m["roles"]
            sources_by_src[m["source"]].add(m["url"] or m["file"])
            roles_by_src[m["source"]] |= m["roles"]

        registry["people"][pid] = {
            "canonical_name_he": canonical,
            "canonical_name_en": en_names[0] if en_names else None,
            "aliases":           aliases,
            "all_roles":         sorted(all_roles),
            "mention_count":     len(members),
            "source_count":      len(sources_by_src),
            "sources":           {s: sorted(urls) for s, urls in sources_by_src.items()},
            "roles_by_src":      {s: sorted(r) for s, r in roles_by_src.items()},
            "gender":            resolve_gender(members),
        }

    for canonical, members in org_groups.items():
        oid = stable_id("o", canonical)
        en_names = sorted({m["name_en"] for m in members if m["name_en"]})
        types    = sorted({m["type"] for m in members if m["type"]})
        sources_by_src: dict[str, set] = defaultdict(set)
        for m in members:
            sources_by_src[m["source"]].add(m["url"] or m["file"])

        registry["organizations"][oid] = {
            "canonical_name_he": canonical,
            "canonical_name_en": en_names[0] if en_names else None,
            "types":             types,
            "mention_count":     len(members),
            "source_count":      len(sources_by_src),
            "sources":           {s: sorted(urls) for s, urls in sources_by_src.items()},
        }

    return registry


# ── Connection analysis ────────────────────────────────────────────────────────

def analyze_connections(people_groups: dict) -> dict:
    """Find cross-source people and flag potential conflicts."""
    cross_source = []
    conflicts    = []

    for canonical, members in people_groups.items():
        src_roles:      dict[str, set] = defaultdict(set)
        src_urls:       dict[str, set] = defaultdict(set)
        src_film_urls:  dict[str, set] = defaultdict(set)  # per-film URLs (uncapped)
        src_event_urls: dict[str, set] = defaultdict(set)  # uncapped, event roles only
        src_years:      dict[str, set] = defaultdict(set)
        src_contexts:   dict[str, set] = defaultdict(set)
        notes_set:      set = set()
        _inst_role_set = STRICT_INST_ROLES | SOFT_INST_ROLES
        for m in members:
            m_roles = m["roles"]
            src_roles[m["source"]] |= m_roles
            if m.get("url"):
                src_urls[m["source"]].add(m["url"])
                if m_roles & EVENT_ROLES:
                    src_event_urls[m["source"]].add(m["url"])
                # Track film-path URLs uncapped in src_film_urls so they bypass
                # the 3-URL cap and reach the renderer even when pushed out by
                # manual:// lector URLs sorting first.
                if (m_roles & FILM_CREDIT_ROLES
                        and not m["url"].startswith("manual://")
                        and re.search(
                            r"/(film|films|movie|movies|title|סרט|סרטים)/|edb\.co\.il",
                            m["url"], re.IGNORECASE)):
                    src_film_urls[m["source"]].add(m["url"])
            for fu in m.get("film_urls", []):
                src_film_urls[m["source"]].add(fu)
            # Only count years toward the source year-range when this page
            # gave the person an institutional role — prevents film-credit
            # years (e.g. producer 2010) from contaminating the lector range.
            if m_roles & _inst_role_set:
                m_years = m.get("years", [])
                if not m_years and m["source"] in INFER_CURRENT_YEAR_SOURCES:
                    m_years = [CURRENT_YEAR]
                for y in m_years:
                    src_years[m["source"]].add(y)
            if m.get("context"):
                src_contexts[m["source"]].add(m["context"])
            if m.get("notes"):
                notes_set.add(m["notes"])

        if len(src_roles) < 2:
            continue

        all_roles: set = set()
        for roles in src_roles.values():
            all_roles |= roles

        gender = resolve_gender(members)

        entry = {
            "name":              canonical,
            "sources":           len(src_roles),
            "mentions":          len(members),
            "roles_by_src":      {s: sorted(r) for s, r in src_roles.items()},
            "urls_by_src":       {s: sorted(urls, key=lambda u: (0 if u.startswith("manual://") else 1))[:3] for s, urls in src_urls.items()},
            "film_urls_by_src":  {s: sorted(urls) for s, urls in src_film_urls.items() if urls},
            "event_urls_by_src": {s: sorted(urls) for s, urls in src_event_urls.items()},
            "years_by_src":      {s: sorted(y) for s, y in src_years.items()},
            "contexts_by_src":   {s: sorted(ctx)[:2] for s, ctx in src_contexts.items() if ctx},
            "notes":             sorted(notes_set),
            "all_roles":         sorted(all_roles),
            "is_power":          bool(all_roles & POWER_ROLES),
            "gender":            gender,
        }
        cross_source.append(entry)

        # Conflict detection — deduplicate by (src_a, src_b) pair
        flags = []
        seen_pairs: set = set()
        for set_a, set_b in CONFLICT_PAIRS:
            roles_with_a = {s for s, r in src_roles.items() if r & set_a}
            roles_with_b = {s for s, r in src_roles.items() if r & set_b}
            if not roles_with_a or not roles_with_b or roles_with_a == roles_with_b:
                continue
            # Require year ranges to overlap — if role A ended before role B started
            # (or vice versa), the periods don't overlap and it's not a real conflict.
            # Exception: prize_winner is a one-off event whose dated mentions
            # under-represent the years the b-side role actually spans (the
            # person was a director long before/after the prize). Skip the
            # temporal check for prize_winner so e.g. festival_programmer
            # 2019 + prize_winner 2025 at the same festival still flags.
            years_a = set().union(*(src_years.get(s, set()) for s in roles_with_a))
            years_b = set().union(*(src_years.get(s, set()) for s in roles_with_b))
            _skip_temporal = "prize_winner" in (set_a | set_b)
            if years_a and years_b and not _skip_temporal:
                if max(years_b) < min(years_a) or max(years_a) < min(years_b):
                    continue  # no temporal overlap → skip
            pair_key = (frozenset(roles_with_a), frozenset(roles_with_b))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            flags.append({
                "role_a": sorted(all_roles & set_a),   # only the matching roles from set_a
                "role_b": sorted(all_roles & set_b),   # only the matching roles from set_b
                "src_a":  sorted(roles_with_a),
                "src_b":  sorted(roles_with_b),
            })
        if flags:
            conflicts.append({**entry, "flags": flags})

    cross_source.sort(key=lambda x: (-x["sources"], -x["mentions"], -int(x["is_power"])))
    conflicts.sort(key=lambda x: (-len(x["flags"]), -x["sources"]))

    return {"cross_source": cross_source, "conflicts": conflicts}


# ── Film-level conflict extraction ─────────────────────────────────────────────

def extract_film_conflicts(mentions_glob: str, _cache: list = None) -> list:
    """
    Within each source (= each fund's website), find cases where a person:
      1. Has an institutional role (lector, board_member, ceo, fund_manager…)
      2. Is also crew (producer, director…) on a film that same source funded

    This is the solid conflict: the fund paid for a film while an insider
    (lector / board member) was on the production.

    Returns a deduplicated list of conflict dicts, sorted by source then person.
    """
    FILM_URL_RE      = re.compile(r"/(film|films|movie|movies|סרט|סרטים)/", re.IGNORECASE)
    SEARCH_RESULT_RE = re.compile(r"[?&](keywords|search|q|s)=", re.IGNORECASE)
    IS_HEBREW   = re.compile(r'[א-ת]')

    try:
        import urllib.parse as _urlparse
    except ImportError:
        _urlparse = None

    def slug_matches_title(url: str, title: str) -> bool:
        """Return True if the URL slug plausibly refers to this film.
        On a /films/some-slug/ page, the LLM sometimes extracts OTHER films from
        sidebars/related sections. We reject those by checking slug↔title overlap."""
        if not _urlparse:
            return True
        parsed = _urlparse.urlparse(url)
        # Take the last non-empty path segment (the film slug)
        path_parts = [p for p in parsed.path.split("/") if p]
        slug = _urlparse.unquote(path_parts[-1]) if path_parts else ""
        slug_words = {w.lower() for w in re.split(r"[-_\s]+", slug) if len(w) > 2}
        # Check both Hebrew and romanized words in the title
        title_words = {w.lower() for w in re.split(r"[\s\-]+", title) if len(w) > 2}
        return bool(slug_words & title_words) or not slug_words

    # Per source: {norm_name: {"actual": str, "inst_roles": set, "soft_roles": set,
    #                          "urls": list, "page_count": int, "notes_by_url": dict}}
    source_inst: dict[str, dict] = defaultdict(dict)
    # Per source: {norm_title: {"title": str, "crew": dict, "film_url": str, "has_canon_url": bool}}
    # Using a dict keyed by norm_title deduplicates the same film across listing/event pages,
    # and upgrades film_url to the canonical /films/ page when found.
    source_films: dict[str, dict] = defaultdict(dict)

    pairs = _cache if _cache is not None else [
        (path, r)
        for path in sorted(glob.glob(mentions_glob))
        for r in _iter_jsonl(path)
    ]
    for path, r in pairs:
        src = normalize_source(Path(path).parts[1])  # out/<source>/mentions.jsonl
        if r.get("status") != "ok":
            continue

        data     = r.get("data") or {}
        entities = data.get("entities") or {}
        people   = entities.get("people") or {}
        films    = entities.get("films") or {}
        url      = r.get("url") or r.get("file") or ""
        # Search-result pages (e.g. /movies-archive?keywords=...) are not
        # proper film pages — skip them as film evidence
        is_search_page = bool(SEARCH_RESULT_RE.search(url))
        is_film_page = bool(FILM_URL_RE.search(url)) and not is_search_page

        # Local ID → (name, roles)
        local_people: dict[str, tuple] = {}
        for eid, p in people.items():
            if not p or not p.get("name_he"):
                continue
            name = p["name_he"].strip()
            name = PERSON_NAME_FIXES.get(name, name)
            if is_junk_name(name):
                continue
            roles = role_set(p.get("primary_roles"))
            if "government_body" in roles:
                continue  # organization misclassified as person
            # NFCT (and nfct_new) lector role is only valid from /lectors/ pages/PDFs
            if src in ("nfct", "nfct_new") and "lector" in roles and "lectors" not in url:
                roles = roles - {"lector"}
                if not roles:
                    continue
            # Makor lector role is only valid from the canonical import or lector-specific pages
            if src == "makor" and "lector" in roles and not url.startswith("manual://") \
                    and "lector" not in url and "לקטור" not in url:
                roles = roles - {"lector"}
                if not roles:
                    continue
            # Lab/workshop pages list mentors who co-created films through the lab —
            # that's the lab's purpose, not a gatekeeping conflict. Strip soft roles.
            if not url.startswith("manual://"):
                _url_decoded = _urlparse_mod.unquote(url)
                if re.search(r"מעבד|lab|חממ|workshop", _url_decoded, re.IGNORECASE):
                    roles = roles - {"mentor", "lab_mentor"}
                    if not roles:
                        continue
            # Strip CEO role when context indicates a city/municipality executive
            if "ceo" in roles:
                _ctx = (p.get("context_sentence") or "").lower()
                if any(kw in _ctx for kw in ["עירייה", "מועצה מקומית", "ראש עיר", 'מנכ"ל העיר', "עיריית"]):
                    roles = roles - {"ceo"}
                    if not roles:
                        continue
            local_people[eid] = (name, roles)

        # Build per-person role context: notes + years from the roles array
        role_notes: dict[str, str] = {}
        role_years: dict[str, set] = {}    # person_id → set of int years
        for rrec in (data.get("roles") or []):
            if not rrec: continue
            pid = rrec.get("person_id")
            if not pid: continue
            note = (rrec.get("notes") or "").strip()
            if note:
                role_notes[pid] = note
            for ykey in ("start_year", "end_year"):
                y = rrec.get(ykey)
                try:
                    y = int(y) if y not in (None, "", "null") else None
                except (TypeError, ValueError):
                    y = None
                if y and 1980 <= y <= 2030:
                    role_years.setdefault(pid, set()).add(y)

        # Collect institutional + soft-tie people from this page
        for eid, (name, roles) in local_people.items():
            strict = roles & STRICT_INST_ROLES
            soft   = roles & SOFT_INST_ROLES
            if not strict and not soft:
                continue
            norm = normalize_name(name)
            if norm not in source_inst[src]:
                source_inst[src][norm] = {
                    "actual": name, "inst_roles": set(), "soft_roles": set(),
                    "urls": [], "page_count": 0, "notes_by_url": {},
                    "years": set(), "_url_set": set(),
                }
            entry = source_inst[src][norm]
            entry["inst_roles"] |= strict
            entry["soft_roles"] |= soft
            if url:
                clean_url = strip_comment_fragment(url)
                norm_u = normalize_url(clean_url)
                if norm_u not in entry["_url_set"]:
                    entry["page_count"] += 1
                    entry["_url_set"].add(norm_u)
                entry["urls"].append(clean_url)
                if eid in role_notes:
                    entry["notes_by_url"][clean_url] = role_notes[eid]
            if eid in role_years:
                entry["years"] |= role_years[eid]

        # Collect film crew from this page
        for fid, film in films.items():
            if not film:
                continue
            # Prefer Hebrew title; fall back to English
            title_he = (film.get("title_he") or "").strip()
            title_en = (film.get("title_en") or "").strip()
            # If title_he has no Hebrew chars (LLM put English there), treat as English
            if title_he and not IS_HEBREW.search(title_he):
                title_en = title_he
                title_he = ""
            title = title_he or title_en
            if not title:
                continue

            crew: dict[str, tuple] = {}  # norm_name → (actual, role)

            # Directors listed on the film entity
            for did in (film.get("director_ids") or []):
                if did in local_people:
                    name, _ = local_people[did]
                    crew[normalize_name(name)] = (name, "director")

            # Producers/directors from relationships
            for rel in (data.get("relationships") or []):
                if not rel:
                    continue
                rtype = rel.get("type", "")
                if rtype not in ("produced", "co_produced", "directed"):
                    continue
                sid, tid = rel.get("source_id", ""), rel.get("target_id", "")
                person_id = sid if tid == fid else (tid if sid == fid else None)
                if person_id and person_id in local_people:
                    name, _ = local_people[person_id]
                    crew[normalize_name(name)] = (name, rtype)

            # Fallback: on a dedicated film page the LLM sometimes records a person's
            # role (e.g. "producer") without generating a relationship record.
            # Uses FALLBACK_CREW_ROLES (excludes "filmmaker" — too vague).
            if is_film_page:
                for eid2, (pname, proles) in local_people.items():
                    if proles & FALLBACK_CREW_ROLES:
                        pnorm = normalize_name(pname)
                        if pnorm not in crew:
                            role_label = next(iter(proles & FALLBACK_CREW_ROLES))
                            crew[pnorm] = (pname, role_label)

            if not crew:
                continue

            # Search/archive result pages list many films out of context —
            # the LLM associates crew from sidebars with wrong films. Skip them.
            if is_search_page:
                continue
            # On a dedicated /films/ page, only trust the film whose title
            # matches the page slug — others are sidebar/related extractions.
            if is_film_page and not slug_matches_title(url, title):
                continue

            # Year (may be int, str, or None)
            raw_year = film.get("year")
            try:
                year = int(raw_year) if raw_year not in (None, "", "null") else None
            except (TypeError, ValueError):
                year = None

            norm_title = normalize_name(title)
            if norm_title not in source_films[src]:
                source_films[src][norm_title] = {
                    "title": title,
                    "crew": {},
                    "film_url": url,
                    "has_canon_url": is_film_page,
                    "year": year,
                }
            else:
                entry = source_films[src][norm_title]
                # Upgrade to canonical /films/ URL if we've found one
                if is_film_page and not entry["has_canon_url"]:
                    entry["film_url"] = url
                    entry["has_canon_url"] = True
                # Prefer Hebrew title if we previously stored English
                if title_he and not IS_HEBREW.search(entry["title"]):
                    entry["title"] = title_he
                # Year: keep first non-null seen
                if entry.get("year") is None and year is not None:
                    entry["year"] = year
            # Merge crew across pages (union — more appearances = more certain)
            source_films[src][norm_title]["crew"].update(crew)

    # Cross-reference: institutional person + film crew → conflict
    seen: set = set()
    conflicts: list = []

    for src in sorted(set(list(source_inst.keys()) + list(source_films.keys()))):
        inst    = source_inst.get(src, {})
        films_d = source_films.get(src, {})
        if not inst or not films_d:
            continue

        for norm_title, film_data in films_d.items():
            film_url   = film_data["film_url"]
            film_title = film_data["title"]
            film_year  = film_data.get("year")
            for norm, (crew_actual, crew_role) in film_data["crew"].items():
                if norm not in inst:
                    continue
                info = inst[norm]
                key  = (src, norm, norm_title)
                if key in seen:
                    continue
                seen.add(key)
                # Separate institutional URLs from film page URLs (dedupe URL variants)
                all_inst_urls = dedupe_urls(sorted(set(info["urls"])))
                # Prefer non-film-page URLs as the institutional evidence link
                staff_urls = [u for u in all_inst_urls
                              if not re.search(r"/(film|films|movie|movies|סרט|סרטים)/",
                                               u, re.IGNORECASE)
                              and not _SEARCH_URL_RE.search(u)]
                inst_display_urls = staff_urls[:2]
                # Detect circular evidence: all institutional URLs are the same page
                # as the film credit (e.g. mentor mentioned on the same workshop recap
                # that lists the film they directed).
                film_url_norm = normalize_url(film_url)
                inst_url_norms = {normalize_url(u) for u in all_inst_urls}
                same_page = inst_url_norms <= {film_url_norm}  # all inst URLs == film URL
                # Tie type: strict (insider) takes priority; soft ties are surfaced separately
                strict_roles = sorted(info.get("inst_roles", set()))
                soft_roles   = sorted(info.get("soft_roles", set()))
                tie_type     = "strict" if strict_roles else "soft"
                # Skip soft-tie conflicts with circular (same-page) evidence — there is
                # no independent signal that the person holds an institutional role.
                if tie_type == "soft" and same_page:
                    continue
                # Carry one representative note (the first one we have) for soft-tie display
                notes = info.get("notes_by_url", {}) or {}
                tie_note = ""
                for u in inst_display_urls:
                    if u in notes:
                        tie_note = notes[u]; break
                if not tie_note and notes:
                    tie_note = next(iter(notes.values()))
                conflicts.append({
                    "source":          src,
                    "fund_label":      src.replace("_", " ").title(),
                    "person":          info["actual"],     # name from institutional context
                    "crew_name":       crew_actual,        # name from film credits (may differ)
                    "film":            film_title,
                    "film_year":       film_year,
                    "inst_roles":      strict_roles,
                    "soft_roles":      soft_roles,
                    "inst_years":      sorted(info.get("years", set())),
                    "tie_type":        tie_type,
                    "tie_note":        tie_note,
                    "crew_role":       crew_role,
                    "film_url":        film_url,
                    "inst_urls":       inst_display_urls,
                    "same_page":       same_page,
                    "inst_page_count": info["page_count"],
                })

    # Post-dedup: if same (source, person, role) has both a Hebrew-titled and English-titled
    # conflict, keep only the Hebrew one. English-only titles come from listing/English pages
    # where the LLM put the translated title; the Hebrew version is canonical.
    def _has_hebrew(s: str) -> bool:
        return bool(IS_HEBREW.search(s))

    by_group: dict = defaultdict(list)
    for c in conflicts:
        key = (c["source"], normalize_name(c["person"]), c["crew_role"])
        by_group[key].append(c)

    final_conflicts = []
    for group in by_group.values():
        hebrew = [c for c in group if _has_hebrew(c["film"])]
        english_only = [c for c in group if not _has_hebrew(c["film"])]
        if hebrew and english_only:
            final_conflicts.extend(hebrew)   # drop English duplicates
        else:
            final_conflicts.extend(group)

    # Group by (source, person) so one person gets one card with their films listed inside.
    # Keep tie_type=strict over soft if the person has both (strict role plus event speaking).
    groups: dict = {}
    for c in final_conflicts:
        key = (c["source"], normalize_name(c["person"]))
        if key not in groups:
            groups[key] = {
                "source":          c["source"],
                "fund_label":      c["fund_label"],
                "person":          c["person"],
                "crew_name":       c["crew_name"],
                "tie_type":        c["tie_type"],
                "inst_roles":      list(c["inst_roles"]),
                "soft_roles":      list(c.get("soft_roles", [])),
                "inst_years":      list(c.get("inst_years", [])),
                "tie_note":        c.get("tie_note", ""),
                "inst_urls":       list(c["inst_urls"]),
                "same_page":       c["same_page"],
                "inst_page_count": c["inst_page_count"],
                "films": [],
            }
        g = groups[key]
        # Upgrade tie_type to strict if any contributing record is strict
        if c["tie_type"] == "strict":
            g["tie_type"] = "strict"
        # Merge roles (any record contributes its role to the group)
        g["inst_roles"] = sorted(set(g["inst_roles"]) | set(c["inst_roles"]))
        g["soft_roles"] = sorted(set(g["soft_roles"]) | set(c.get("soft_roles", [])))
        g["inst_years"] = sorted(set(g["inst_years"]) | set(c.get("inst_years", [])))
        if c.get("tie_note") and not g["tie_note"]:
            g["tie_note"] = c["tie_note"]
        # Take the max page_count seen (the per-person institutional evidence)
        g["inst_page_count"] = max(g["inst_page_count"], c["inst_page_count"])
        # Add film entry
        g["films"].append({
            "title":     c["film"],
            "url":       c["film_url"],
            "crew_role": c["crew_role"],
            "year":      c.get("film_year"),
        })

    # Within each group, dedupe films:
    #   1. exact normalized title
    #   2. fuzzy match — Hebrew-aware: strip prefix letters (ה,ב,ל,מ,ש,ו) before
    #      comparing tokens. Two titles merge if ≥1 shared 3+char stem AND
    #      rapidfuzz token_set_ratio ≥ 60 on the stem-normalized text.
    #   When merging, keep the variant with (a) a year, then (b) a canonical /films/ URL.
    FILM_PATH_RE = re.compile(r"/(film|films|movie|movies|סרט|סרטים)/", re.IGNORECASE)
    HEBREW_PREFIXES = ("ה", "ב", "ל", "מ", "ש", "ו", "כ")  # ה=the, ב=in, ל=to, מ=from, ש=that, ו=and, כ=as

    def hebrew_stems(title: str) -> set:
        """Tokenize Hebrew title, strip 1-2 prefix letters, return stems ≥3 chars."""
        stems = set()
        for w in re.split(r"[\s\-]+", normalize_name(title)):
            if len(w) < 3:
                continue
            # Try stripping 1 prefix letter if it's a known prefix and word is long enough
            for n_strip in (0, 1, 2):
                if n_strip <= len(w) - 3 and (n_strip == 0 or w[:n_strip][-1] in HEBREW_PREFIXES):
                    s = w[n_strip:]
                    if len(s) >= 3:
                        stems.add(s)
        return stems

    def film_priority(f):
        has_year = 0 if f.get("year") else 1
        has_canon = 0 if (f.get("url") and FILM_PATH_RE.search(f["url"])) else 1
        # Prefer Hebrew titles over non-Hebrew (0 = Hebrew, 1 = no Hebrew)
        is_hebrew = 0 if HAS_HEBREW_RE.search(f.get("title") or "") else 1
        return (has_year, has_canon, is_hebrew, -len(f.get("title") or ""))

    HAS_HEBREW_RE = re.compile(r"[א-ת]")

    def _is_no_hebrew(title: str) -> bool:
        """True if title contains no Hebrew characters (English/transliteration)."""
        return not HAS_HEBREW_RE.search(title or "")

    def films_match(a: dict, b: dict) -> bool:
        # Same URL → definitely the same film (regardless of language of title stored)
        ua, ub = a.get("url", ""), b.get("url", "")
        if ua and ub and normalize_url(ua) == normalize_url(ub):
            return True
        # Same year required if both have years (different years = different films)
        ya, yb = a.get("year"), b.get("year")
        if ya and yb and ya != yb:
            return False
        # Cross-language pair: one title has no Hebrew (English/transliteration), the other does
        ta_noheb = _is_no_hebrew(a.get("title", ""))
        tb_noheb = _is_no_hebrew(b.get("title", ""))
        if ta_noheb != tb_noheb:
            # Different scripts — can't compare by stem; rely on URL/year match only.
            # If we reach here, same year (or no year) with different scripts: treat as same.
            return True
        sa, sb = hebrew_stems(a["title"]), hebrew_stems(b["title"])
        if not sa or not sb:
            return False
        # Need at least one shared stem
        shared = sa & sb
        # Also accept "almost-shared" stems where one is a prefix of the other (≥4 chars)
        if not shared:
            for x in sa:
                for y in sb:
                    if len(x) >= 4 and len(y) >= 4 and (x.startswith(y[:4]) or y.startswith(x[:4])):
                        shared = {x}
                        break
                if shared: break
        if not shared:
            return False
        # And rapidfuzz score on stem-joined text ≥ 60
        if HAS_RAPIDFUZZ:
            ta = " ".join(sorted(sa)); tb = " ".join(sorted(sb))
            if rfuzz.token_set_ratio(ta, tb) < 60:
                return False
        return True

    for g in groups.values():
        # First: exact dedupe by normalized title
        by_norm: dict[str, list] = {}
        for f in g["films"]:
            by_norm.setdefault(normalize_film_title(f["title"]), []).append(f)
        exact_deduped = [sorted(grp, key=film_priority)[0] for grp in by_norm.values()]

        # Second: fuzzy union-find using Hebrew-aware matching
        if len(exact_deduped) > 1:
            parent = list(range(len(exact_deduped)))
            def find(i):
                while parent[i] != i:
                    parent[i] = parent[parent[i]]; i = parent[i]
                return i
            for i in range(len(exact_deduped)):
                for j in range(i+1, len(exact_deduped)):
                    if films_match(exact_deduped[i], exact_deduped[j]):
                        ri, rj = find(i), find(j)
                        if ri != rj: parent[ri] = rj
            clusters: dict[int, list] = {}
            for i, f in enumerate(exact_deduped):
                clusters.setdefault(find(i), []).append(f)
            fuzzy_deduped = [sorted(c, key=film_priority)[0] for c in clusters.values()]
        else:
            fuzzy_deduped = exact_deduped

        # Transliteration artifact filter: if a person has ≥1 quality film (year OR
        # canonical /films/ URL) AND ≥2 low-quality films (no year, no /films/ URL),
        # the low-quality ones are likely transliteration duplicates from news pages.
        # A single low-quality film is kept — it may be a real film without year data.
        _has_quality = [f for f in fuzzy_deduped
                        if f.get("year") or FILM_PATH_RE.search(f.get("url", ""))]
        _no_quality  = [f for f in fuzzy_deduped
                        if not f.get("year") and not FILM_PATH_RE.search(f.get("url", ""))]
        if _has_quality and len(_no_quality) >= 2:
            fuzzy_deduped = _has_quality

        g["films"] = sorted(fuzzy_deduped, key=lambda f: f["title"])
        g["inst_urls"] = dedupe_urls(g["inst_urls"])

        # Compute conflict strength: min gap between lector year and film year,
        # but only count gaps where lector year <= film year (served before/during film release).
        # If a person became a lector AFTER the film was made (by >1 year), it is not a conflict.
        iy_list = [y for y in g.get("inst_years", []) if y]
        fy_list = [f.get("year") for f in g["films"] if f.get("year")]
        if iy_list and fy_list:
            valid_gaps = [fy - iy for iy in iy_list for fy in fy_list if fy >= iy - 1]
            min_gap = min(valid_gaps) if valid_gaps else None
        else:
            min_gap = None
        g["conflict_gap"]      = min_gap
        g["conflict_strength"] = (
            "strong" if min_gap is not None and min_gap <= 2 else
            "medium" if min_gap is not None and min_gap <= 4 else
            "weak"
        )
        g["revolving_door_type"] = classify_revolving_door(iy_list, fy_list)

    grouped = list(groups.values())
    # Sort: strict first, then by film_count (more films = more material), then page_count
    grouped.sort(
        key=lambda g: (
            0 if g["tie_type"] == "strict" else 1,
            -len(g["films"]),
            -g["inst_page_count"],
            g["source"], g["person"],
        )
    )
    n_strict = sum(1 for g in grouped if g["tie_type"] == "strict")
    n_soft   = len(grouped) - n_strict
    n_films  = sum(len(g["films"]) for g in grouped)
    print(f"Film-level conflicts: {len(grouped)} people, {n_films} films  "
          f"(strict={n_strict}, soft={n_soft})")
    return grouped


# ── Repeat winners ────────────────────────────────────────────────────────────

def compute_repeat_winners(film_conflicts: list) -> list:
    """
    Find people who appear as film crew across 3+ unique funded films.

    Groups film_conflicts by canonical person name, deduplicates films by title,
    and returns people with 3+ unique films sorted by film_count descending.
    """
    from collections import defaultdict as _dd

    by_person: dict = _dd(lambda: {
        "films": {},           # norm_title → film dict
        "sources": set(),
        "inst_roles": set(),
    })

    for entry in film_conflicts:
        person = entry["person"]
        rec = by_person[person]
        rec["sources"].add(entry["source"])
        rec["inst_roles"].update(entry.get("inst_roles", []))
        rec["inst_roles"].update(entry.get("soft_roles", []))
        for film in entry.get("films", []):
            title = film.get("title", "")
            if not title:
                continue
            norm = normalize_name(title)
            if norm not in rec["films"]:
                rec["films"][norm] = {
                    "title":  title,
                    "year":   film.get("year"),
                    "source": entry["source"],
                    "url":    film.get("url", ""),
                }
            else:
                # Upgrade: prefer entry with a year
                existing = rec["films"][norm]
                if existing.get("year") is None and film.get("year") is not None:
                    existing["year"] = film["year"]
                if not existing.get("url") and film.get("url"):
                    existing["url"] = film["url"]

    result = []
    for person, rec in by_person.items():
        unique_films = list(rec["films"].values())
        if len(unique_films) < 3:
            continue
        unique_films.sort(key=lambda f: (f.get("year") or 9999, f["title"]))
        result.append({
            "person":      person,
            "film_count":  len(unique_films),
            "films":       unique_films,
            "sources":     sorted(rec["sources"]),
            "inst_roles":  sorted(rec["inst_roles"]),
        })

    result.sort(key=lambda x: -x["film_count"])
    return result


# ── Power map ──────────────────────────────────────────────────────────────────

def compute_power_map(cross: list, film_conflicts: list) -> list:
    """
    Build the 'heart of the network': people who held gatekeeper roles
    (STRICT_INST_ROLES) across multiple funding institutions.

    Returns a list sorted by:
      1. revolving_door (# distinct sources with gatekeeper roles) DESC
      2. total sources DESC
    Each entry: name, gender, power_sources, power_roles, revolving_door,
                total_sources, years_range, has_film_conflict, funded_film_count.
    """
    # Build a lookup of who appears in film conflicts and how many funded films they have
    film_cf_by_name: dict = {}
    for fc in film_conflicts:
        norm = normalize_name(fc["person"])
        if norm not in film_cf_by_name:
            film_cf_by_name[norm] = 0
        film_cf_by_name[norm] += len(fc.get("films", []))

    result = []
    for entry in cross:
        roles_by_src = entry["roles_by_src"]
        years_by_src = entry.get("years_by_src", {})

        # Sources where this person held a STRICT (gatekeeper) role
        power_sources = {
            src: sorted(set(roles) & STRICT_INST_ROLES)
            for src, roles in roles_by_src.items()
            if set(roles) & STRICT_INST_ROLES
        }
        if not power_sources:
            continue

        revolving_door = len(power_sources)
        all_power_roles = sorted({r for roles in power_sources.values() for r in roles})

        # Year range across all power sources
        all_years = sorted({
            y for src in power_sources
            for y in years_by_src.get(src, [])
        })
        if all_years:
            years_range = (all_years[0], all_years[-1])
        else:
            years_range = None

        norm = normalize_name(entry["name"])
        funded_film_count = film_cf_by_name.get(norm, 0)

        result.append({
            "name":             entry["name"],
            "gender":           entry.get("gender", "unknown"),
            "power_sources":    power_sources,           # {src: [roles]}
            "all_sources":      list(roles_by_src.keys()),
            "power_roles":      all_power_roles,
            "revolving_door":   revolving_door,
            "total_sources":    entry["sources"],
            "years_range":      years_range,
            "has_film_conflict": norm in film_cf_by_name,
            "funded_film_count": funded_film_count,
        })

    result = [r for r in result if r["revolving_door"] >= 2]
    result.sort(key=lambda x: (-x["revolving_door"], -x["total_sources"],
                                -x["funded_film_count"]))
    return result


# ── Excel export ───────────────────────────────────────────────────────────────

def export_excel(connections: dict, registry: dict, film_conflicts: list,
                 repeat_winners: list, out_path) -> None:
    """Write a multi-sheet Excel workbook summarising all findings."""
    if not HAS_OPENPYXL:
        print("Warning: openpyxl not installed — skipping Excel export. "
              "Run: pip install openpyxl", file=sys.stderr)
        return

    wb = openpyxl.Workbook()

    # ── Sheet 1: אנשים ──────────────────────────────────────────────────────
    ws1 = wb.active
    ws1.title = "אנשים"
    ws1.append(["שם עברית", "שם אנגלית", "מגדר", "תפקידים", "מקורות", "שנים", "קונפליקט"])

    # Collect conflict person names for lookup
    conflict_names = {normalize_name(e["person"]) for e in film_conflicts}
    conflict_names |= {normalize_name(e["name"]) for e in connections.get("conflicts", [])}

    gender_he = {"f": "נקבה", "m": "זכר", "unknown": "לא ידוע"}

    for entry in connections.get("cross_source", []):
        name_he = entry["name"]
        name_en = ""
        # Look up English name from registry
        for pid, prec in registry.get("people", {}).items():
            if prec["canonical_name_he"] == name_he:
                name_en = prec.get("canonical_name_en") or ""
                break
        roles_str   = ", ".join(entry.get("all_roles", []))
        sources_str = ", ".join(sorted(entry.get("roles_by_src", {}).keys()))
        # Year range from all years_by_src values
        all_years = sorted({y for ys in entry.get("years_by_src", {}).values() for y in ys})
        years_str = f"{all_years[0]}-{all_years[-1]}" if len(all_years) > 1 else (
            str(all_years[0]) if all_years else "")
        is_conflict = "כן" if normalize_name(name_he) in conflict_names else "לא"
        gender_label = gender_he.get(entry.get("gender", "unknown"), "לא ידוע")
        ws1.append([name_he, name_en, gender_label, roles_str, sources_str, years_str, is_conflict])

    # ── Sheet 2: קונפליקטים ─────────────────────────────────────────────────
    ws2 = wb.create_sheet("קונפליקטים")
    ws2.append(["שם", "תפקיד א", "מקור א", "שנים א", "תפקיד ב", "מקור ב", "שנים ב", "חוזק"])

    for entry in connections.get("conflicts", []):
        name = entry["name"]
        years_by_src = entry.get("years_by_src", {})
        for flag in entry.get("flags", []):
            role_a   = ", ".join(he_role(r) for r in flag.get("role_a", []))
            role_b   = ", ".join(he_role(r) for r in flag.get("role_b", []))
            src_a    = ", ".join(flag.get("src_a", []))
            src_b    = ", ".join(flag.get("src_b", []))
            ya = sorted({y for s in flag.get("src_a", []) for y in years_by_src.get(s, [])})
            yb = sorted({y for s in flag.get("src_b", []) for y in years_by_src.get(s, [])})
            ya_str = f"{ya[0]}-{ya[-1]}" if len(ya) > 1 else (str(ya[0]) if ya else "")
            yb_str = f"{yb[0]}-{yb[-1]}" if len(yb) > 1 else (str(yb[0]) if yb else "")
            ws2.append([name, role_a, src_a, ya_str, role_b, src_b, yb_str, ""])

    # ── Sheet 3: זוכים חוזרים ───────────────────────────────────────────────
    ws3 = wb.create_sheet("זוכים חוזרים")
    ws3.append(["שם", "מספר סרטים", "קרנות", "תפקיד מוסדי", "שמות סרטים"])

    for rw in repeat_winners:
        sources_str = ", ".join(he_source(s) for s in rw["sources"])
        roles_str   = ", ".join(he_role(r) for r in rw["inst_roles"])
        films_str   = " | ".join(
            f'{f["title"]} ({f["year"]})' if f.get("year") else f["title"]
            for f in rw["films"]
        )
        ws3.append([rw["person"], rw["film_count"], sources_str, roles_str, films_str])

    # ── Sheet 4: חברות הפקה ─────────────────────────────────────────────────
    ws4 = wb.create_sheet("חברות הפקה")
    ws4.append(["שם החברה", "מקורות", "אזכורים"])

    prod_orgs = [
        o for o in registry.get("organizations", {}).values()
        if "production_company" in (o.get("types") or [])
    ]
    prod_orgs.sort(key=lambda o: -o["mention_count"])
    for o in prod_orgs[:50]:
        sources_str = ", ".join(sorted(o["sources"].keys()))
        ws4.append([o["canonical_name_he"], sources_str, o["mention_count"]])

    wb.save(out_path)


# ── HTML generation ────────────────────────────────────────────────────────────

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
       background: #f1f5f9; color: #1e293b; font-size: 14px; line-height: 1.5; }
a { color: #3b82f6; text-decoration: none; }
a:hover { text-decoration: underline; }

/* Header */
.header { background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%);
          color: white; padding: 32px 40px; }
.header h1 { font-size: 22px; font-weight: 700; letter-spacing: -0.3px; }
.header .subtitle { color: #94a3b8; font-size: 13px; margin-top: 6px; }
.header .meta { color: #64748b; font-size: 12px; margin-top: 4px; }

/* Stats bar */
.stats-bar { display: flex; gap: 16px; padding: 20px 40px;
             background: #fff; border-bottom: 1px solid #e2e8f0; flex-wrap: wrap; }
.stat { text-align: center; min-width: 100px; }
.stat .value { font-size: 28px; font-weight: 700; color: #0f172a; }
.stat .label { font-size: 11px; color: #64748b; text-transform: uppercase;
               letter-spacing: 0.5px; margin-top: 2px; }

/* Main layout */
.main { max-width: 1400px; margin: 0 auto; padding: 32px 40px; }
.section { margin-bottom: 40px; }
/* Table of contents */
.toc { background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px;
       padding:18px 22px; margin-bottom:32px; }
.toc-title { font-size:13px; font-weight:700; color:#475569;
             letter-spacing:.3px; margin-bottom:12px; }
.toc-links { display:flex; flex-wrap:wrap; gap:8px; }
.toc-link { display:flex; align-items:center; gap:6px; padding:6px 12px;
            background:#fff; border:1px solid #e2e8f0; border-radius:20px;
            text-decoration:none; color:#1e293b; font-size:13px;
            transition:border-color .15s, box-shadow .15s; }
.toc-link:hover { border-color:#94a3b8; box-shadow:0 1px 4px rgba(0,0,0,.08); }
.toc-count { font-size:11px; color:#64748b; background:#f1f5f9;
             padding:1px 7px; border-radius:10px; }
.section-title { font-size: 16px; font-weight: 700; color: #0f172a;
                 padding: 12px 4px 10px; border-bottom: 2px solid #e2e8f0;
                 margin-bottom: 18px; display: flex; align-items: center; gap: 10px;
                 position: sticky; top: 0; z-index: 90;
                 background: #f8fafc; box-shadow: 0 2px 8px rgba(0,0,0,.06); }
.section-title .count { font-size: 12px; font-weight: 500; color: #64748b;
                        background: #f1f5f9; padding: 2px 8px;
                        border-radius: 10px; }
/* Floating section beacon */
#section-beacon {
  position: fixed; bottom: 20px; left: 20px; z-index: 200;
  background: #1e293b; color: #f8fafc;
  padding: 6px 14px; border-radius: 20px;
  font-size: 12px; font-weight: 600; direction: rtl;
  box-shadow: 0 4px 16px rgba(0,0,0,.25);
  opacity: 0; transition: opacity .25s;
  pointer-events: none; white-space: nowrap; }
#section-beacon.visible { opacity: 1; }

/* Cards */
.card { background: #fff; border-radius: 10px; border: 1px solid #e2e8f0;
        padding: 18px 20px; margin-bottom: 12px;
        transition: box-shadow .15s; }
.card:hover { box-shadow: 0 4px 16px rgba(0,0,0,.08); }
.card-header { display: flex; align-items: flex-start;
               justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.card-name { font-size: 16px; font-weight: 700; color: #0f172a;
             direction: rtl; text-align: right; }
.card-name .en { font-size: 12px; font-weight: 400; color: #64748b;
                 direction: ltr; display: block; text-align: right; margin-top: 2px; }
.card-meta { display: flex; gap: 8px; flex-shrink: 0; flex-wrap: wrap;
             justify-content: flex-end; }

/* Badges */
.badge { display: inline-flex; align-items: center; padding: 3px 9px;
         border-radius: 12px; font-size: 11px; font-weight: 600;
         white-space: nowrap; }
.badge-source { color: #fff; }
.badge-role { background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }
.badge-power { background: #dbeafe; color: #1d4ed8; border: 1px solid #bfdbfe; }
.badge-count { background: #f8fafc; color: #64748b;
               border: 1px solid #e2e8f0; font-size: 11px; }
.badge-conflict { background: #fef3c7; color: #92400e; border: 1px solid #fde68a; }
.badge-flag { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
.badge-traffic { font-size: 11px; font-weight: 600; border-radius: 9999px; padding: 1px 8px; }
.badge-rd { font-size: 11px; font-weight: 600; border-radius: 9999px; padding: 1px 8px;
            background: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0; }
.rd-stats-grid { display: flex; flex-wrap: wrap; gap: 14px; }
.rd-stat-block { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px;
                 padding: 14px 18px; min-width: 200px; flex: 1; }
.rd-stat-header { display: flex; align-items: center; justify-content: space-between;
                  margin-bottom: 6px; gap: 8px; }
.rd-stat-count { font-size: 22px; font-weight: 700; color: #0f172a; }
.rd-stat-desc { font-size: 12px; color: #64748b; margin-bottom: 6px; }
.rd-stat-names { font-size: 11px; color: #94a3b8; font-style: italic;
                 border-top: 1px solid #e2e8f0; padding-top: 6px; }

/* Source rows inside cards */
.source-rows { margin-top: 14px; display: flex; flex-direction: column; gap: 9px; }
.source-row { display: flex; align-items: flex-start; gap: 10px; flex-wrap: wrap; }
.source-dot { width: 10px; height: 10px; border-radius: 50%;
              flex-shrink: 0; margin-top: 3px; }
.source-label { font-size: 12px; font-weight: 600; color: #374151; min-width: 180px; }
.source-roles { display: flex; gap: 5px; flex-wrap: wrap; align-items: center; }
.source-links { margin-top: 3px; display: flex; gap: 6px 14px; flex-wrap: wrap; margin-left: 20px; }
.source-link { font-size: 12px; color: #2563eb;
               overflow: hidden; text-overflow: ellipsis; max-width: 360px;
               display: inline-block; direction: rtl; text-align: right; }
.source-link:hover { text-decoration: underline; color: #1d4ed8; }
.source-link::before { content: "↖ "; color: #94a3b8; font-size: 10px; }
.source-links { margin-right: 20px; margin-left: 0; }
.source-years { font-size: 11px; color: #94a3b8; margin-right: 4px; }
.source-context { font-size: 11px; color: #6b7280; font-style: italic;
                  margin-right: 20px; margin-top: 2px; width: 100%;
                  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.badge-link { text-decoration: none; cursor: pointer; }
.badge-link:hover { opacity: 0.75; text-decoration: underline; }
.badge-canonical-link { border-style: solid; border-width: 1px; }
.film-source-link::before { content: "↖ "; }

/* Conflict card (role-level) */
.conflict-card { border-right: 4px solid #f59e0b; }
.conflict-flag { background: #fffbeb; border-radius: 6px;
                 padding: 10px 12px; margin-top: 12px;
                 font-size: 12px; color: #78350f; }
.conflict-flag strong { color: #92400e; }

/* Film conflict cards */
.film-conflict-card { background: #fff; border-radius: 10px;
                      border: 1px solid #fca5a5; border-right: 4px solid #dc2626;
                      padding: 18px 20px; margin-bottom: 12px;
                      transition: box-shadow .15s; }
.film-conflict-card:hover { box-shadow: 0 4px 16px rgba(220,38,38,.12); }
/* Soft-tie variant: same layout, calmer color, blue accent */
.film-conflict-card.soft-tie { border-color: #bfdbfe; border-right-color: #2563eb; }
.film-conflict-card.soft-tie:hover { box-shadow: 0 4px 16px rgba(37,99,235,.12); }
.film-conflict-card.soft-tie .film-finding {
    background: #eff6ff; color: #1e3a8a;
}
.film-conflict-card.soft-tie .film-finding strong { color: #1d4ed8; }
.badge-soft { background: #dbeafe; color: #1d4ed8; border: 1px solid #bfdbfe; }

/* Person row at top of each conflict card */
.card-person-row { display: flex; justify-content: space-between; align-items: flex-start;
                   gap: 12px; flex-wrap: wrap; margin-bottom: 10px; }
.card-person-name { font-size: 18px; font-weight: 700; color: #0f172a;
                    direction: rtl; text-align: right; }
.card-person-meta { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end;
                    align-items: center; }

/* Films list inside a conflict card */
.film-list { list-style: none; margin: 12px 0 10px; padding: 8px 12px;
             background: #fafafa; border: 1px solid #e2e8f0; border-radius: 8px; }
.film-conflict-card.soft-tie .film-list { background: #f8fafc; border-color: #dbeafe; }
.conflict-fund-block { border-top: 1px solid #f1f5f9; padding: 10px 0 4px; }
.conflict-fund-block:first-of-type { border-top: none; padding-top: 0; }
.conflict-fund-meta { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 6px; }
.pro-profile-link { font-size: 12px; color: #2563eb; text-decoration: none;
                    margin-right: 10px; font-weight: 400; }
.pro-profile-link:hover { text-decoration: underline; }
.film-row { display: flex; justify-content: space-between; align-items: center;
            gap: 10px; padding: 6px 4px;
            border-bottom: 1px solid #f1f5f9; }
.film-row:last-child { border-bottom: none; }
.film-row-title { direction: rtl; text-align: right; font-weight: 500; flex: 1; }
.film-row-link { color: #0f172a; }
.film-row-link:hover { color: #2563eb; text-decoration: underline; }
.film-row-year { color: #94a3b8; font-weight: 400; font-size: 12px; margin-right: 4px; }

/* Consolidated warning bar inside a card */
.card-warning { background: #fffbeb; border-right: 3px solid #f59e0b;
                color: #92400e; font-size: 12px; line-height: 1.5;
                padding: 8px 12px; border-radius: 6px; margin-top: 10px; }
.card-warning strong { color: #b45309; }
.film-title { font-size: 17px; font-weight: 700; direction: rtl;
              color: #0f172a; margin-bottom: 12px; }
.film-meta { display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
             margin-bottom: 10px; }
.film-finding { background: #fef2f2; border-radius: 6px; padding: 10px 14px;
                font-size: 13px; color: #7f1d1d; line-height: 1.6; margin-top: 10px; }
.film-finding strong { color: #991b1b; }
.film-sources { margin-top: 10px; display: flex; gap: 12px; flex-wrap: wrap;
                font-size: 12px; }
.film-source-link { color: #3b82f6; }
.film-source-link::before { content: "↗ "; }

/* Power map table */
.power-map-table { width: 100%; border-collapse: collapse; background: #fff;
                   border-radius: 10px; border: 1px solid #e2e8f0; overflow: hidden; }
.power-map-table th { background: #0f172a; color: #f8fafc; text-align: right;
                      padding: 10px 14px; font-size: 11px; letter-spacing: 0.4px;
                      border-bottom: 2px solid #1e293b; font-weight: 600; }
.power-map-table td { padding: 9px 14px; border-bottom: 1px solid #f1f5f9;
                      vertical-align: middle; }
.power-map-table tr:last-child td { border-bottom: none; }
.power-map-table tr:hover td { background: #f8fafc; }
.pm-rank { color: #94a3b8; font-size: 11px; font-weight: 700; min-width: 28px;
           text-align: center; }
.pm-name { font-weight: 700; font-size: 14px; direction: rtl; }
.pm-name a { color: #1e293b; text-decoration: none; }
.pm-name a:hover { text-decoration: underline; color: #1d4ed8; }
.pm-rd { text-align: center; font-weight: 800; font-size: 16px; }
.pm-rd-high  { color: #dc2626; }
.pm-rd-med   { color: #d97706; }
.pm-rd-low   { color: #64748b; }
.pm-roles  { font-size: 11px; color: #374151; direction: rtl; }
.pm-years  { font-size: 11px; color: #94a3b8; white-space: nowrap; }
.pm-film-flag { text-align: center; }
.pm-sources-dots { display: flex; flex-wrap: wrap; gap: 4px; justify-content: flex-end; }

/* Org table */
.org-table { width: 100%; border-collapse: collapse; background: #fff;
             border-radius: 10px; border: 1px solid #e2e8f0; overflow: hidden; }
.org-table th { background: #f8fafc; text-align: right; padding: 10px 14px;
                font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;
                color: #64748b; border-bottom: 1px solid #e2e8f0; }
.org-table td { padding: 10px 14px; border-bottom: 1px solid #f1f5f9;
                vertical-align: top; text-align: right; }
.org-table tr:last-child td { border-bottom: none; }
.org-table tr:hover td { background: #f8fafc; }
.org-name-he { font-weight: 600; direction: rtl; text-align: right; }
.org-name-en { font-size: 11px; color: #94a3b8; }

/* Fuzzy pairs */
.pair-table { width: 100%; border-collapse: collapse; background: #fff;
              border-radius: 10px; border: 1px solid #e2e8f0; overflow: hidden; }
.pair-table th { background: #f8fafc; text-align: right; padding: 8px 14px;
                 font-size: 11px; text-transform: uppercase; color: #64748b;
                 border-bottom: 1px solid #e2e8f0; }
.pair-table td { padding: 8px 14px; border-bottom: 1px solid #f1f5f9;
                 font-size: 13px; text-align: right; }
.pair-table tr:last-child td { border-bottom: none; }
.score-high { color: #dc2626; font-weight: 700; }
.score-med  { color: #d97706; font-weight: 600; }

/* Confidence badges */
.badge-conf-high   { background: #d1fae5; color: #065f46; border: 1px solid #6ee7b7; }
.badge-conf-medium { background: #fef9c3; color: #854d0e; border: 1px solid #fde68a; }
.badge-conf-low    { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }

/* Canonical / manual evidence pill */
.manual-evidence { background: #ecfdf5; color: #047857; padding: 4px 10px;
                   border: 1px solid #6ee7b7; border-radius: 12px;
                   font-size: 12px; font-weight: 600; cursor: default; }
.manual-evidence::before { content: none; }

/* Filters */
.filters { display: flex; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
.filter-btn { padding: 5px 14px; border-radius: 20px; font-size: 12px;
              font-weight: 600; cursor: pointer; border: 2px solid transparent;
              background: #f1f5f9; color: #475569; transition: all .15s; }
.filter-btn.active { background: #0f172a; color: #fff; }
.filter-btn:hover:not(.active) { background: #e2e8f0; }

/* Footer */
.footer { text-align: center; padding: 24px; color: #94a3b8;
          font-size: 12px; border-top: 1px solid #e2e8f0; margin-top: 20px; }

/* ── Resume / professional profile cards ───────────────────────────────────── */
.resume-card { padding: 16px 20px; }
.resume-header { display: flex; justify-content: space-between; align-items: flex-start;
                 gap: 12px; flex-wrap: wrap; }
.resume-name { font-size: 17px; font-weight: 700; color: #0f172a; direction: rtl; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.resume-wiki-link { display: inline-flex; align-items: center; justify-content: center;
                    width: 20px; height: 20px; border-radius: 50%; background: #f8f9fa;
                    border: 1px solid #c8ccd1; text-decoration: none; flex-shrink: 0; }
.resume-wiki-icon { font-size: 11px; font-weight: 700; color: #202122; font-family: sans-serif; }
.resume-wiki-link:hover { background: #eaecf0; }
.resume-birth-year { font-size: 13px; font-weight: 400; color: #64748b; }
.resume-chips { display: flex; gap: 5px; flex-wrap: wrap; margin-top: 8px; }
.resume-chip { display: inline-flex; align-items: center; padding: 3px 9px;
               border-radius: 10px; font-size: 11px; font-weight: 600; white-space: nowrap; }
.resume-chip-inst     { background: #dbeafe; color: #1d4ed8; border: 1px solid #bfdbfe; }
.resume-chip-creative { background: #d1fae5; color: #065f46; border: 1px solid #6ee7b7; }
.resume-chip-soft     { background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }
.resume-meta { display: flex; gap: 6px; flex-shrink: 0; flex-wrap: wrap;
               justify-content: flex-end; align-items: flex-start; }
.resume-meta-badge { display: inline-flex; align-items: center; padding: 3px 9px;
                     border-radius: 12px; font-size: 11px; font-weight: 600;
                     background: #f8fafc; color: #64748b; border: 1px solid #e2e8f0; }
.resume-meta-inst { background: #dbeafe; color: #1d4ed8; border-color: #bfdbfe; }
.resume-body { margin-top: 14px; display: flex; flex-direction: column; gap: 10px; }
.resume-section { border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; }
.resume-section-label { background: #f8fafc; border-bottom: 1px solid #e2e8f0;
                        padding: 5px 12px; font-size: 10px; font-weight: 700;
                        color: #94a3b8; text-transform: uppercase; letter-spacing: 0.6px;
                        direction: rtl; text-align: right; }
.resume-entry { display: flex; align-items: center; gap: 10px; padding: 8px 12px;
                border-bottom: 1px solid #f1f5f9; direction: rtl; }
.resume-entry:last-child { border-bottom: none; }
.resume-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.resume-entry-body { display: flex; align-items: center; gap: 8px;
                     flex-wrap: wrap; flex: 1; direction: rtl; }
.resume-entry-org { font-weight: 600; font-size: 13px; color: #0f172a; }
a.resume-entry-org { color: #2563eb; }
a.resume-entry-org:hover { text-decoration: underline; }
.resume-entry-role { font-size: 11px; background: #f1f5f9; color: #475569;
                     padding: 1px 6px; border-radius: 8px; border: 1px solid #e2e8f0; }
.resume-entry-year { font-size: 11px; color: #94a3b8; }
.resume-film-entry { display: flex; align-items: center; gap: 10px; padding: 8px 12px;
                     border-bottom: 1px solid #f1f5f9; direction: rtl; }
.resume-film-entry:last-child { border-bottom: none; }
.resume-film-icon { font-size: 12px; flex-shrink: 0; }
.resume-film-body { display: flex; align-items: center; gap: 7px;
                    flex-wrap: wrap; flex: 1; direction: rtl; }
.resume-film-title { font-weight: 600; font-size: 13px; }
.resume-film-link { color: #0f172a; }
.resume-film-link:hover { color: #2563eb; text-decoration: underline; }
.resume-film-year { font-size: 11px; color: #94a3b8; }
.resume-film-role { font-size: 11px; background: #f1f5f9; color: #475569;
                    padding: 1px 6px; border-radius: 8px; border: 1px solid #e2e8f0; }
.resume-film-funder { font-size: 10px; color: #fff; padding: 1px 7px;
                      border-radius: 8px; font-weight: 600; }
.resume-quote { font-size: 11px; color: #6b7280; font-style: italic; direction: rtl;
                padding: 5px 10px; background: #f8fafc; border-radius: 6px;
                border-right: 2px solid #e2e8f0; overflow: hidden;
                text-overflow: ellipsis; white-space: nowrap; margin: 2px 0; }
.resume-note-osint { font-size: 11.5px; color: #374151; direction: rtl; text-align: right;
                     padding: 7px 12px; background: #f0f9ff; border-radius: 6px;
                     border-right: 3px solid #93c5fd; border-left: none; line-height: 1.55;
                     white-space: normal; margin: 4px 0 6px; }
.resume-note-osint a { color: #1d4ed8; text-decoration: underline; }

/* site nav */
.site-nav { background:#0f172a; padding:6px 40px; display:flex; gap:4px; direction:rtl;
            position:sticky; top:0; z-index:1000; border-bottom:1px solid rgba(255,255,255,.05); }
.site-nav a { color:#94a3b8; text-decoration:none; font-size:12px; font-weight:500;
              padding:5px 12px; border-radius:6px; transition:background .15s, color .15s; white-space:nowrap; }
.site-nav a:hover { background:#1e293b; color:#e2e8f0; text-decoration:none; }
.site-nav a.active { background:#1e3a5f; color:#fff; font-weight:600; }
"""

JS = """
function filterCards(type) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  document.querySelectorAll('.person-card').forEach(card => {
    if (type === 'all') { card.style.display = ''; return; }
    if (type === 'power' && card.dataset.power === '1') { card.style.display = ''; }
    else if (type === 'power') { card.style.display = 'none'; }
    if (type === 'film' && card.dataset.power === '0') { card.style.display = ''; }
    else if (type === 'film' && card.dataset.power === '1') { card.style.display = 'none'; }
  });
}

(function() {
  var beacon = document.getElementById('section-beacon');
  if (!beacon) return;
  var sections = [
    { id: 'sec-film-conflicts', label: '🎬 ניגודי עניינים ישירים', color: '#dc2626' },
    { id: 'sec-cross-people',    label: '👤 פרופיל מקצועי',        color: '#1e293b' },
    { id: 'sec-orgs',            label: '🏢 ארגונים',              color: '#0369a1' },
    { id: 'sec-repeat-winners',  label: '⭐ זוכים חוזרים',         color: '#b45309' },
    { id: 'sec-prod-companies',  label: '🏭 חברות הפקה',           color: '#166534' },
    { id: 'sec-power-map',       label: '🔑 מרכז הרשת',            color: '#312e81' },
  ];
  var observer = new IntersectionObserver(function(entries) {
    entries.forEach(function(e) {
      var sec = sections.find(function(s) { return s.id === e.target.id; });
      if (!sec) return;
      if (e.isIntersecting) {
        beacon.textContent = sec.label;
        beacon.style.background = sec.color;
        beacon.classList.add('visible');
      }
    });
  }, { threshold: 0 });
  sections.forEach(function(s) {
    var el = document.getElementById(s.id);
    if (el) observer.observe(el);
  });
})();
"""


def source_color(source: str, color_map: dict) -> str:
    if source not in color_map:
        color_map[source] = SOURCE_PALETTE[len(color_map) % len(SOURCE_PALETTE)]
    return color_map[source]


def he(text: str) -> str:
    return f'<span dir="rtl">{text}</span>'


def person_slug(name: str) -> str:
    """URL-safe slug for a person's name — used as HTML anchor id."""
    import unicodedata
    n = unicodedata.normalize("NFC", normalize_name(name))
    n = re.sub(r"[^\w֐-׿]", "-", n)
    n = re.sub(r"-+", "-", n).strip("-")
    return f"prof-{n}"


def gendered(word_f: str, word_m: str, word_unknown: str, gender: str) -> str:
    """Return the gender-appropriate Hebrew word form."""
    if gender == "f":
        return word_f
    if gender == "m":
        return word_m
    return word_unknown


def role_badge(role: str) -> str:
    cls = "badge-power" if role in POWER_ROLES else "badge-role"
    return f'<span class="badge {cls}">{he_role(role)}</span>'


def source_badge(src: str, color: str) -> str:
    return (f'<span class="badge badge-source" '
            f'style="background:{color}">{he_source(src)}</span>')


def render_power_map_section(power_map: list, color_map: dict,
                              film_conflict_names: set) -> str:
    """Render the 'heart of the network' power map table."""
    if not power_map:
        return ""

    # Role labels for display
    ROLE_SHORT = {
        "lector": "לקטור", "appeal_lector": "לקטור ערר",
        "fund_manager": "מנהל קרן", "ceo": 'מנכ"ל', "co_ceo": 'מנכ"ל משותף',
        "foundation_director": "מנהל", "director_general": 'מנכ"ל כללי',
        "board_member": "חבר הנהלה", "chairperson": 'יו"ר', "committee_chair": "ראש ועדה",
        "council_member": "חבר מועצה", "committee_member": "חבר ועדה",
        "ministry_official": "פקיד משרד",
        "jury_member": "חבר ועדה / חבר שופטים", "festival_director": "מנהל פסטיבל",
        "festival_programmer": "מתכנת", "prize_committee_member": "חבר ועדת פרס",
        "guild_board_member": "חבר הנהלה (גילדה)", "guild_chair": "יו\"ר גילדה",
        "לקטור": "לקטור",
    }

    rows = ""
    for i, pm in enumerate(power_map, 1):
        name     = pm["name"]
        rd       = pm["revolving_door"]
        rd_cls   = "pm-rd-high" if rd >= 3 else ("pm-rd-med" if rd == 2 else "pm-rd-low")
        gender   = pm.get("gender", "unknown")

        # Source dots for power sources
        dots = "".join(
            '<span class="source-dot" style="background:' + color_map.get(s, "#94a3b8") + '" '
            'title="' + he_source(s) + '"></span>'
            for s in sorted(pm["power_sources"].keys())
        )
        dots_html = f'<div class="pm-sources-dots">{dots}</div>'

        # Power roles (short labels, deduplicated)
        role_labels = " · ".join(
            ROLE_SHORT.get(r, r) for r in sorted(set(pm["power_roles"]))
        )

        # Years range
        yr = pm.get("years_range")
        yr_html = f'{yr[0]}–{yr[1]}' if yr and yr[0] != yr[1] else (str(yr[0]) if yr else "")

        # Film conflict flag
        norm_name = normalize_name(name)
        is_cf = norm_name in film_conflict_names
        cf_flag = (
            '<span style="color:#dc2626;font-size:16px" title="מופיע גם בקרדיטים של סרטים ממומנים">⚑</span>'
            if is_cf else ""
        )
        film_count = pm.get("funded_film_count", 0)
        if film_count > 0:
            cf_flag += (f' <span style="color:#94a3b8;font-size:11px">({film_count} סרטים)</span>')

        rows += f"""
<tr>
  <td class="pm-rank">{i}</td>
  <td class="pm-name" dir="rtl"><a href="#{person_slug(name)}" title="פרופיל מקצועי">{he(name)}</a></td>
  <td class="pm-rd {rd_cls}">{rd}</td>
  <td>{dots_html}</td>
  <td class="pm-roles" dir="rtl">{role_labels}</td>
  <td class="pm-years">{yr_html}</td>
  <td class="pm-film-flag">{cf_flag}</td>
</tr>"""

    return f"""
<div class="section" id="sec-power-map">
  <div class="section-title" style="border-color:#0f172a;background:#0f172a;color:#f8fafc;border-radius:8px;padding:12px 18px">
    🔑 מרכז הרשת — בעלי כוח מוסדי
    <span class="count" style="background:#1e293b;color:#cbd5e1">{len(power_map)} אנשים</span>
  </div>
  <p style="color:#64748b;font-size:13px;margin:14px 0;line-height:1.7">
    האנשים הבאים כיהנו ב<strong>תפקידי שומר-סף</strong> (לקטור, חבר הנהלה, מנכ"ל, חבר מועצה) ב<strong>גופי מימון מרובים</strong>.
    <strong>מדד הדלת המסתובבת</strong> = מספר הגופים שונים שבהם אדם החזיק בכוח מוסדי.
    הסמל ⚑ מציין שאותו אדם מופיע גם כמפיק/במאי בסרטים שמומנו על-ידי אותם גופים.
  </p>
  <div style="overflow-x:auto">
  <table class="power-map-table">
    <thead>
      <tr>
        <th>#</th>
        <th>שם</th>
        <th title="מספר גופים שבהם כיהן בתפקיד שומר-סף">🔄 דלת מסתובבת</th>
        <th>גופים</th>
        <th>תפקידים</th>
        <th>שנים</th>
        <th>⚑</th>
      </tr>
    </thead>
    <tbody>{rows}
    </tbody>
  </table>
  </div>
</div>"""


def render_person_card(entry: dict, color_map: dict, is_conflict: bool = False,
                       url_to_film: dict = None, wiki_enrichment: dict = None,
                       dc_html: str = "") -> str:
    name            = entry["name"]
    roles_by_src    = entry["roles_by_src"]
    is_power        = entry.get("is_power", False)
    url_to_film     = url_to_film or {}
    _title_to_url   = url_to_film.get("__title_to_url__") or {}
    wiki_enrichment = wiki_enrichment or {}
    conflict_class  = " conflict-card" if is_conflict else ""
    power_val       = "1" if is_power else "0"

    # ── Wiki enrichment data ─────────────────────────────────────────────────
    wiki_info       = wiki_enrichment.get(name) or {}
    wiki_url        = wiki_info.get("wiki_url", "")
    birth_year      = wiki_info.get("birth_year")
    wiki_title      = wiki_info.get("wiki_title_he", "")

    urls_by_src        = entry.get("urls_by_src", {})
    film_urls_by_src   = entry.get("film_urls_by_src", {})
    event_urls_by_src  = entry.get("event_urls_by_src", {})
    years_by_src       = entry.get("years_by_src", {})
    contexts_by_src    = entry.get("contexts_by_src", {})
    person_notes       = entry.get("notes", [])
    _card_gender       = entry.get("gender", "unknown")

    # ── Role chips (top of card) ─────────────────────────────────────────────
    unique_roles = {r for roles in roles_by_src.values() for r in roles}
    inst_r       = unique_roles & (STRICT_INST_ROLES | SOFT_INST_ROLES)
    creative_r   = unique_roles & CREATIVE_ROLES
    other_r      = (unique_roles - inst_r - creative_r) - SUPPRESS_CHIP_ROLES

    # Build tooltip text for school-role chips — show specific school name(s).
    _faculty_schools = []
    for _fsrc in ("film_schools", "sam_spiegel"):
        for u in dedupe_urls(urls_by_src.get(_fsrc, [])):
            real = canonical_url_for(u) if u.startswith("manual://") else u
            lbl  = he_source_for_url(_fsrc, real) or SOURCE_LABELS_HE.get(_fsrc, _fsrc)
            if lbl not in _faculty_schools:
                _faculty_schools.append(lbl)
    _chip_tooltips: dict[str, str] = {}
    if _faculty_schools:
        _school_tip = " · ".join(_faculty_schools)
        for _school_role in ("faculty", "administrator", "technician",
                              "librarian", "archivist", "cinematheque_director"):
            if _school_role in unique_roles:
                _chip_tooltips[_school_role] = _school_tip

    def _dedup_chips(roles, css_class, seen_labels: set):
        chips = []
        for r in sorted(roles):
            lbl = he_role_g(r, _card_gender)
            if lbl not in seen_labels:
                seen_labels.add(lbl)
                tip = _chip_tooltips.get(r, "")
                tip_attr = f' title="{tip}"' if tip else ""
                chips.append(f'<span class="resume-chip {css_class}"{tip_attr}>{lbl}</span>')
        return "".join(chips)

    _chip_seen: set = set()
    role_chips = (
        _dedup_chips(inst_r,     "resume-chip-inst",     _chip_seen) +
        _dedup_chips(creative_r, "resume-chip-creative", _chip_seen) +
        _dedup_chips(other_r,    "resume-chip-soft",     _chip_seen)
    )

    # ── Helper: best institutional URL for a source ──────────────────────────
    def best_url_for_src(src_urls: list) -> tuple[str, bool, str]:
        src_urls = dedupe_urls(src_urls)
        for u in src_urls:
            if u.startswith("manual://"):
                real = canonical_url_for(u)
                if real:
                    return real, True, list_date_label_for(u)
        # Filter out search-result pages — they should never be shown as institutional evidence
        non_search = [u for u in src_urls
                      if not re.search(r"[?&](keywords|search|q|s)=", u, re.IGNORECASE)]
        if not non_search:
            return "", False, ""  # all URLs are search pages — show org name without link
        non_film = [u for u in non_search
                    if not re.search(r"/(film|films|movie|movies|סרט|סרטים)/", u, re.IGNORECASE)]
        return (non_film[0] if non_film else non_search[0]), False, ""

    # ── Institutional positions ──────────────────────────────────────────────
    # Two passes: first collect raw rows per source, then merge rows sharing
    # the same (org_label, display_year) so the card doesn't show duplicates
    # like "סם שפיגל / 2026 / סגל מינהלי" + "סם שפיגל / 2026 / מרצה" when the
    # same person is tagged from two sources for the same institution.
    # Manual:// prefixes for film schools that have no real source URL
    _MANUAL_SCHOOL_LABELS = {
        "manual://film_schools/outside-the-frame-faculty-2026/": "מחוץ לפריים",
    }
    def _school_label_for(u: str) -> str:
        real = canonical_url_for(u) if u.startswith("manual://") else u
        if real:
            lbl = he_source_for_url("film_schools", real)
            if lbl and lbl != SOURCE_LABELS_HE.get("film_schools"):
                return lbl
        for prefix, lbl in _MANUAL_SCHOOL_LABELS.items():
            if u.startswith(prefix):
                return lbl
        return ""

    _inst_raw: dict[tuple, dict] = {}  # (org_label, display_year) → {roles, color, url, year, ctx}
    for src, roles in sorted(roles_by_src.items()):
        src_inst = set(roles) & (STRICT_INST_ROLES | SOFT_INST_ROLES)
        if not src_inst:
            continue
        color    = source_color(src, color_map)
        years    = years_by_src.get(src, [])
        if len(years) > 1 and (years[-1] - years[0]) > len(years) - 1:
            yr_str = ", ".join(str(y) for y in years)
        elif len(years) > 1:
            yr_str = f"{years[0]}–{years[-1]}"
        else:
            yr_str = str(years[0]) if years else ""

        # For film_schools, split URLs by school so each row names a specific school.
        src_url_list = urls_by_src.get(src, [])
        if src == "film_schools":
            url_groups: dict[str, list] = {}
            for u in dedupe_urls(src_url_list):
                lbl = _school_label_for(u) or SOURCE_LABELS_HE.get(src, src)
                url_groups.setdefault(lbl, []).append(u)
            if not url_groups:
                url_groups = {SOURCE_LABELS_HE.get(src, src): []}
            url_group_items = list(url_groups.items())
        else:
            url_group_items = [(None, src_url_list)]

        for _forced_label, _group_urls in url_group_items:
            best_url, _, date_label = best_url_for_src(_group_urls)
            display_year = yr_str if yr_str else date_label
            _org_label = _forced_label if _forced_label else he_source_for_url(src, best_url)
            _inst_key = (_org_label, display_year)
            slot = _inst_raw.setdefault(_inst_key, {
                "roles": [], "color": color, "url": best_url,
                "sort_year": years[-1] if years else 0, "ctx": "",
            })
            for r in sorted(src_inst):
                lbl = he_role_g(r, _card_gender)
                if lbl not in slot["roles"]:
                    slot["roles"].append(lbl)
            if not slot["url"] and best_url:
                slot["url"] = best_url
            if years and years[-1] > slot["sort_year"]:
                slot["sort_year"] = years[-1]
            if not slot["ctx"]:
                ctx_quotes = contexts_by_src.get(src, [])
                if ctx_quotes:
                    _ctx = ctx_quotes[0]
                    _name_parts = [p for p in name.split() if len(p) > 2]
                    if any(part in _ctx for part in _name_parts):
                        slot["ctx"] = _ctx

    inst_entries = []
    for (_org_label, display_year), slot in _inst_raw.items():
        role_str = " / ".join(slot["roles"])
        best_url = slot["url"]
        if best_url and is_valid_url(best_url):
            org_html = (f'<a href="{best_url}" target="_blank" class="resume-entry-org">'
                        f'{he(_org_label)}</a>')
        else:
            org_html = f'<span class="resume-entry-org">{he(_org_label)}</span>'
        yr_html  = (f'<span class="resume-entry-year">{display_year}</span>' if display_year else "")
        row_html = (
            f'<div class="resume-entry">'
            f'<span class="resume-dot" style="background:{slot["color"]}"></span>'
            f'<div class="resume-entry-body">{org_html}'
            f'{yr_html}'
            f'<span class="resume-entry-role">{role_str}</span>'
            f'</div></div>'
        )
        if slot["ctx"]:
            row_html += f'<div class="resume-quote">״{he(slot["ctx"])}״</div>'
        inst_entries.append((slot["sort_year"], row_html))

    inst_rows = "".join(h for _, h in sorted(inst_entries, key=lambda x: -x[0]))
    inst_section = (
        '<div class="resume-section">'
        '<div class="resume-section-label">תפקידים מוסדיים</div>'
        + inst_rows + '</div>'
    ) if inst_rows else ""

    # ── Festival events (speaker / participant / jury at specific films) ──────
    event_rows = ""
    seen_event_urls: set = set()
    seen_event_titles: set = set()
    for src, evt_urls in sorted(event_urls_by_src.items()):
        color = source_color(src, color_map)
        for u in sorted(evt_urls):
            nu = normalize_url(u)
            if nu in seen_event_urls:
                continue
            film = url_to_film.get(nu)
            if not film or not film.get("title"):
                continue
            title_norm = normalize_film_title(film["title"])
            if title_norm in seen_event_titles:
                continue
            seen_event_urls.add(nu)
            seen_event_titles.add(title_norm)
            # Strip episode suffix for cleaner display (series dedup)
            title = _FILM_SUFFIX_RE.sub("", film["title"]).strip()
            year  = str(film["year"]) if film.get("year") else ""
            festival_label = he_source_for_url(src, u)
            title_html = (
                f'<a href="{u}" target="_blank" class="resume-film-link">{title}</a>'
                if is_valid_url(u) else title
            )
            yr_html = f'<span class="resume-film-year">({year})</span>' if year else ""
            fest_badge = (f'<span class="resume-film-funder" style="background:{color}">'
                          f'{festival_label}</span>')
            event_rows += (
                f'<div class="resume-film-entry">'
                f'<span class="resume-film-icon">🎤</span>'
                f'<div class="resume-film-body">'
                f'<span class="resume-film-title">{title_html}</span>'
                f'{yr_html}{fest_badge}'
                f'</div></div>'
            )
    event_section = (
        '<div class="resume-section">'
        '<div class="resume-section-label">השתתפות באירועים</div>'
        + event_rows + '</div>'
    ) if event_rows else ""

    # ── Notes (OSINT / manual bio notes) ─────────────────────────────────────
    notes_section = ""
    if person_notes:
        best_note = max(person_notes, key=len)  # show the richest note
        # Convert [label](url) markdown links to <a> tags
        linked = re.sub(
            r'\[([^\]]+)\]\((https?://[^\)]+)\)',
            r'<a href="\2" target="_blank" rel="noopener">\1</a>',
            best_note
        )
        notes_section = f'<div class="resume-note-osint">{linked}</div>'

    # ── Film credits (sourced from movies_db.json — single source of truth) ──
    # Previously this filmography was re-derived from raw mention URLs (url_to_film
    # plus search-page / transliteration / bilingual-slug filters), which made it
    # disagree with films.html and graph.html — both of which read movies_db.json.
    # Now it comes from the same DB: person_films(name) looks up by registry_id
    # (exact) with a normalized-name fallback for unresolved crew rows.
    film_rows = ""
    _pf = person_films(name)
    for c in sorted(_pf, key=lambda c: (str(c.get("year") or ""), he(c["title"]))):
        year_str = str(c["year"]) if c.get("year") else ""
        # Strip episode suffix for display ("מגש הכסף – פרק 2" → "מגש הכסף").
        display_title = _FILM_SUFFIX_RE.sub("", c["title"]).strip()
        # Prefer the Hebrew role labels stored in movies_db; fall back to he_role().
        role_labels = [r for r in sorted(c["roles_he"]) if r] or \
                      [he_role(r) for r in sorted(c["roles"]) if r]
        role_str = " / ".join(dict.fromkeys(role_labels))
        u = c.get("url") or ""
        title_html = (
            f'<a href="{u}" target="_blank" class="resume-film-link">{he(display_title)}</a>'
            if is_valid_url(u) else f'<span>{he(display_title)}</span>'
        )
        # Fund badges come straight from the film's funds[] in movies_db. movies_db
        # carries no per-fund URL, so these are non-link chips (was a link before).
        funder_badges = "".join(
            f'<span class="resume-film-funder" style="background:{source_color(fk, color_map)}">'
            f'{he(SOURCE_LABELS_HE.get(fk, fk))}</span>'
            for fk in (c.get("funds") or [])
        )
        film_rows += (
            f'<div class="resume-film-entry">'
            f'<span class="resume-film-icon">🎬</span>'
            f'<div class="resume-film-body">'
            f'<span class="resume-film-title">{title_html}</span>'
            + (f'<span class="resume-film-year">{year_str}</span>' if year_str else "")
            + (f'<span class="resume-film-role">{role_str}</span>' if role_str else "")
            + funder_badges
            + f'</div></div>'
        )

    film_section = (
        '<div class="resume-section">'
        '<div class="resume-section-label">קרדיטים בסרטים</div>'
        + film_rows + '</div>'
    ) if film_rows else ""

    # ── Other appearances (sources not covered by inst or film) ─────────────
    soft_entries = []
    for src, roles in sorted(roles_by_src.items()):
        src_roles = set(roles)
        has_inst  = bool(src_roles & (STRICT_INST_ROLES | SOFT_INST_ROLES))
        has_film  = any(
            url_to_film.get(normalize_url(u), {}).get("title")
            for u in urls_by_src.get(src, [])
        )
        if has_inst or has_film:
            continue
        color    = source_color(src, color_map)
        years    = years_by_src.get(src, [])
        if len(years) > 1 and (years[-1] - years[0]) > len(years) - 1:
            yr_str = ", ".join(str(y) for y in years)
        elif len(years) > 1:
            yr_str = f"{years[0]}–{years[-1]}"
        else:
            yr_str = str(years[0]) if years else ""
        role_str = " / ".join(dict.fromkeys(he_role(r) for r in sorted(src_roles)))
        best_url, _, _ = best_url_for_src(urls_by_src.get(src, []))
        _org_label = he_source_for_url(src, best_url)
        if best_url and is_valid_url(best_url):
            org_html = (f'<a href="{best_url}" target="_blank" class="resume-entry-org">'
                        f'{he(_org_label)}</a>')
        else:
            org_html = f'<span class="resume-entry-org">{he(_org_label)}</span>'
        yr_html = (f'<span class="resume-entry-year">{yr_str}</span>' if yr_str else "")
        row_html = (
            f'<div class="resume-entry">'
            f'<span class="resume-dot" style="background:{color}"></span>'
            f'<div class="resume-entry-body">{org_html}'
            f'{yr_html}'
            f'<span class="resume-entry-role">{role_str}</span>'
            f'</div></div>'
        )
        ctx_quotes = contexts_by_src.get(src, [])
        if ctx_quotes:
            _ctx = ctx_quotes[0]
            _name_parts = [p for p in name.split() if len(p) > 2]
            if any(part in _ctx for part in _name_parts):
                row_html += f'<div class="resume-quote">״{he(_ctx)}״</div>'
        _sort_year = years[-1] if years else 0
        soft_entries.append((_sort_year, row_html))

    soft_rows = "".join(h for _, h in sorted(soft_entries, key=lambda x: -x[0]))
    soft_section = (
        '<div class="resume-section">'
        '<div class="resume-section-label">הופעות נוספות</div>'
        + soft_rows + '</div>'
    ) if soft_rows else ""

    # ── Card meta ────────────────────────────────────────────────────────────
    meta_html = (f'<span class="resume-meta-badge">'
                 f'{entry["sources"]} מקורות · {entry["mentions"]} אזכורים</span>')
    if is_power:
        meta_html += '<span class="resume-meta-badge resume-meta-inst">תפקיד מוסדי</span>'

    # ── Conflict flags ───────────────────────────────────────────────────────
    conflict_html = ""
    if is_conflict and entry.get("flags"):
        # Non-employer sources: databases and film schools record credits/student work,
        # not employment — suppress "at X" phrasing in conflict flag text
        _NON_EMPLOYER_SRCS = {"edb", "sam_spiegel", "film_schools", "filmmaker_profiles", "jff_staff"}
        # Sources that refer to the same real-world institution under different
        # scrape pipelines — coalesce so the conflict sentence doesn't show two
        # chunks for "Jerusalem Film Festival" with cosmetically different labels.
        _SRC_ALIASES = {
            "jff_staff": "jff",   # both = פסטיבל ירושלים
            "nfct_new":  "nfct",  # both = הקרן החדשה לקולנוע וטלוויזיה
        }
        def _canon_src(s):
            return _SRC_ALIASES.get(s, s)
        _roles_by_src = entry.get("roles_by_src", {})

        def _fmt_years(yrs):
            # 1 yr → "(2025)"; contiguous → "(2020–2025)"; with gaps → "(2020, 2025)".
            # Gap-aware form prevents "lectured 2020 and 2025" from reading as 6yr tenure.
            if not yrs:
                return ""
            if len(yrs) == 1:
                return f" ({yrs[0]})"
            if yrs[-1] - yrs[0] + 1 == len(yrs):
                return f" ({yrs[0]}–{yrs[-1]})"
            return f" ({', '.join(str(y) for y in yrs)})"

        # Per-flag set of films already cited — dedupe across sources so
        # "שכבות (2024)" doesn't repeat once per festival source. Reset at
        # the top of each flag below.
        _flag_films_seen: set = set()

        def _films_for_src(s, max_n=3):
            # Return up to max_n film titles credited via this source, excluding
            # any already cited in this flag's earlier clauses.
            urls = film_urls_by_src.get(s, []) or []
            titles = []
            for u in urls:
                nu = normalize_url(u)
                f  = url_to_film.get(nu)
                if not f or not f.get("title"):
                    continue
                t = normalize_film_title(f["title"])
                if t in _flag_films_seen:
                    continue
                _flag_films_seen.add(t)
                # Title only — clause already carries its own (year) suffix; nesting
                # parens would read "(שכבות (2024))" which is ugly.
                titles.append(f'<em>{he(f["title"])}</em>')
                if len(titles) >= max_n:
                    break
            return titles

        def _role_chunk(roles, gender):
            return f'<strong>{he_roles_g(roles, gender)}</strong>'

        def _per_src_at(s, gender):
            # "ב<src>" with optional years suffix.
            return f'ב{he_source(s)}'

        def _join_clauses(clauses):
            # Join free-form clauses with Hebrew connectors:
            # 1 → as-is; 2 → "A ו-B"; 3+ → "A, B ו-C".
            if not clauses:
                return ""
            if len(clauses) == 1:
                return clauses[0]
            return ", ".join(clauses[:-1]) + " ו" + clauses[-1]

        def _coalesce_sources(src_list):
            # Group input sources by canonical alias, preserving first occurrence
            # order. Returns {canonical_src: [original_src, ...]} so callers can
            # union years/roles/films across all aliased sources for one chunk.
            buckets: dict = {}
            for s in src_list:
                c = _canon_src(s)
                buckets.setdefault(c, []).append(s)
            return buckets

        def _years_for(srcs):
            ys = set()
            for s in srcs:
                ys.update(years_by_src.get(s, []))
            return sorted(ys)

        def _roles_at(srcs, role_set):
            r = set()
            for s in srcs:
                r |= (set(_roles_by_src.get(s, [])) & role_set)
            return sorted(r)

        def _films_for_srcs(srcs, max_n=3):
            out = []
            for s in srcs:
                out += _films_for_src(s, max_n=max_n - len(out))
                if len(out) >= max_n:
                    break
            return out

        for flag in entry["flags"]:
            _flag_films_seen.clear()
            _gender    = entry.get("gender", "unknown")
            role_a_set = set(flag.get("role_a", []))
            role_b_set = set(flag.get("role_b", []))
            # Coalesce aliased sources (jff + jff_staff → one chunk) before
            # splitting into "both / only-a / only-b" buckets.
            buckets_a  = _coalesce_sources(flag.get("src_a", []))
            buckets_b  = _coalesce_sources(
                [s for s in flag.get("src_b", []) if s not in _NON_EMPLOYER_SRCS]
            )
            both_srcs = [c for c in buckets_a if c in buckets_b]
            only_a    = [c for c in buckets_a if c not in buckets_b]
            only_b    = [c for c in buckets_b if c not in buckets_a]

            clauses = []

            # 1. Same-institution clauses first — the strongest signal:
            #    "בקרן מקור: שימשה כלקטורית (2024) וכבמאית (2024) — סרט X, Y"
            for cs in both_srcs:
                src_group = list(dict.fromkeys(buckets_a[cs] + buckets_b[cs]))
                roles_a_here = _roles_at(src_group, role_a_set)
                roles_b_here = _roles_at(src_group, role_b_set)
                if not roles_a_here or not roles_b_here:
                    continue
                yrs   = _years_for(src_group)
                ra_he = _role_chunk(roles_a_here, _gender)
                rb_he = _role_chunk(roles_b_here, _gender)
                films = _films_for_srcs(src_group, max_n=3)
                films_he = (f' — סרטים: {", ".join(films)}' if films else "")
                clauses.append(
                    f'ב{he_source(cs)}: כ{ra_he} וגם כ{rb_he}{_fmt_years(yrs)}{films_he}'
                )

            # 2. Lector-only sources (gatekeeping)
            for cs in only_a:
                src_group = buckets_a[cs]
                roles_here = _roles_at(src_group, role_a_set)
                if not roles_here:
                    continue
                r_he = _role_chunk(roles_here, _gender)
                yrs  = _years_for(src_group)
                clauses.append(f'כ{r_he} ב{he_source(cs)}{_fmt_years(yrs)}')

            # 3. Creator-only sources (recipient side) — include up to 3 film titles
            for cs in only_b:
                src_group = buckets_b[cs]
                roles_here = _roles_at(src_group, role_b_set)
                if not roles_here:
                    continue
                r_he  = _role_chunk(roles_here, _gender)
                yrs   = _years_for(src_group)
                films = _films_for_srcs(src_group, max_n=3)
                films_he = (f' ({", ".join(films)})' if films else "")
                clauses.append(f'כ{r_he} ב{he_source(cs)}{_fmt_years(yrs)}{films_he}')

            if not clauses or (not both_srcs and (not only_a or not only_b)):
                continue
            _served = gendered("כיהנה", "כיהן", "כיהן/ה", _gender)
            conflict_html += (
                f'<div class="conflict-flag">'
                f'⚑ <strong>{he(name)}</strong> {_served} {_join_clauses(clauses)}'
                f'</div>'
            )

    # ── Wiki link + birth year in header ─────────────────────────────────────
    wiki_html = ""
    if wiki_url:
        label = wiki_title or "ויקיפדיה"
        year_tag = f' <span class="resume-birth-year">({birth_year})</span>' if birth_year else ""
        wiki_html = (f'<a href="{wiki_url}" target="_blank" class="resume-wiki-link" '
                     f'title="{label}">'
                     f'<span class="resume-wiki-icon">W</span>'
                     f'</a>{year_tag}')

    _card_id = person_slug(name)
    return f"""
<div class="card resume-card{conflict_class} person-card" id="{_card_id}" data-power="{power_val}">
  <div class="resume-header">
    <div>
      <div class="resume-name">{he(name)}{wiki_html}</div>
      <div class="resume-chips">{role_chips}</div>
    </div>
    <div class="resume-meta">{meta_html}</div>
  </div>
  <div class="resume-body">
    {notes_section}
    {inst_section}
    {event_section}
    {film_section}
    {soft_section}
    {conflict_html}
    {(('<div class="resume-section"><div class="resume-section-label" style="color:#f59e0b">🔗 ניגודים נגזרים</div>' + dc_html + '</div>') if dc_html else "")}
  </div>
</div>"""


# Hebrew labels for role types (used in badges and finding sentences)
ROLE_LABELS_HE = {
    "lector": "לקטור",
    "appeal_lector": "לקטור ערעורים",
    "fund_manager": "מנהל הקרן",
    "foundation_director": "מנהל הקרן",
    "ceo": "מנכ\"ל",
    "co_ceo": "מנכ\"ל משותף",
    "board_member": "חבר הנהלה",
    "chairperson": "יו\"ר",
    "chairman": "יו\"ר",
    "council_member": "חבר מועצה",
    "committee_member": "חבר ועדה",
    "committee_chair": "ראש ועדה",
    "ministry_official": "פקיד משרד",
    "art_director": "מנהל אמנותי",
    "director_general": "מנכ\"ל",
    "judge": "שופט",
    "mentor": "מנטור",
    "festival_staff": "צוות פסטיבל",
    "owner": "בעלים",
    "partner": "שותף",
    "filmmaker": "יוצר",
    "director": "במאי",
    "directed": "במאי",
    "producer": "מפיק",
    "produced": "מפיק",
    "co_producer": "מפיק שותף",
    "co_produced": "מפיק שותף",
    "executive_producer": "מפיק בכיר",
    "screenwriter": "תסריטאי",
    "scriptwriter": "תסריטאי",
    "writer": "כותב",
    "editor": "עורך",
    "cinematographer": "צלם",
    "actor": "שחקן",
    "sound_designer": "מעצב פסקול",
    "composer": "מלחין",
    "researcher": "חוקר",
    "event_speaker": "דובר באירוע",
    "guest_speaker": "דובר אורח",
    "panelist": "משתתף בפאנל",
    "event_participant": "משתתף באירוע",
    "acknowledged_partner": "שותף מוכר",
    "other": "אחר",
    "לקטור": "לקטור",
    # Institutional / academic
    "faculty":                  "מרצה",
    "academic_director":        "מנהל אקדמי",
    "department_head":          "ראש מחלקה",
    "alumni":                   "בוגר",
    "lab_mentor":               "מנטור מעבדה",
    "guild_board_member":       "חבר הנהלת האיגוד",
    "guild_chair":              'יו"ר האיגוד',
    "guild_member":             "חבר איגוד",
    "executive_director":       "מנכ\"ל",
    "artistic_director":        "מנהל אמנותי",
    "festival_director":        "מנהל פסטיבל",
    "festival_programmer":      "אוצר פסטיבל",
    "jury_member":              "חבר שופטים",
    "prize_committee_member":   "חבר ועדת פרס",
    "prize_winner":             "זוכה פרס",
    # School admin & operational
    "administrator":            "סגל מינהלי",
    "technician":               "טכנאי",
    "librarian":                "ספרן",
    "archivist":                "אחראי ארכיון",
    "cinematheque_director":    "מנהל סינמטק",
    # Critics
    "critic":               "מבקר קולנוע",
    # Creative extras
    "co_creator":           "יוצר שותף",
    "distributor":          "מפיץ",
    "advisor":              "יועץ",
    "art_advisor":          "יועץ אמנותי",
    "art_consultant":       "יועץ אמנותי",
    "artistic_consultant":  "יועץ אמנותי",
    "artistic_advisor":     "יועץ אמנותי",
    "script_editor":        "עורך תסריט",
    # Common institutional / staff roles
    "contact_person":       "איש קשר",
    "fund_director":        "מנהל הקרן",
    "staff":                "צוות",
    "directing_mentor":     "מנטור במאי",
    # Common creative/crew roles (LLM output without Hebrew labels)
    "script":               "תסריט",
    "original_soundtrack":  "פסקול מקורי",
    "sound_editor":         "עורך פסקול",
    "soundtrack_editor":    "עורך פסקול",
    "creator":              "יוצר",
    "music":                "מוזיקה",
    "animator":             "אנימטור",
    "filming":              "צילום",
    "color_designer":       "מעצב צבע",
    "colourist":            "מתקן צבע",
    "moderator":            "מנחה",
    "voice_actor":          "שחקן קול",
    "cast":                 "שחקן",
    "editing":              "עריכה",
    "research":             "מחקר",
    "co_director":          "במאי שותף",
    "music_composer":       "מלחין",
    "co_creator":           "יוצר שותף",
    "animation_director":   "במאי אנימציה",
    "visual_effects_supervisor": "מפקח אפקטים",
    "xr_creator":           "יוצר XR",
    "designer":             "מעצב",
    "founder":              "מייסד",
    "representative":       "נציג",
    "broadcaster":          "מגיש",
    "sound_mixer":          "מיקסר קול",
    "image_and_color_designer": "מעצב תמונה וצבע",
    "post_production_online": "פוסט-פרודקשן אונליין",
    "set_designer":         "מעצב סט",
    "online editor":        "עורך אונליין",
    "accountant":           "חשבונאי",
    "dancer":               "רקדן",
    "multi-disciplinary artist":   "אמן רב-תחומי",
    "multidisciplinary artist":    "אמן רב-תחומי",
    "actress":              "שחקנית",
    # Mentors / project guidance (FDOC)
    "overall_mentor":       "מלווה כולל",
    "project_mentor":       "מלווה פרויקט",
    "editing_mentor":       "מלווה עריכה",
    # Film department / school roles
    "head_of_film_department":        "מנהל מחלקת קולנוע",
    "head_of_multimedia":             "ראש מולטימדיה",
    "cinematheque_director":          "מנהל סינמטק",
    "continuing_studies_coordinator": "רכזת לימודי המשך",
    "cluster_manager":                "מנהל אשכול",
    "project_manager":                "מנהל פרויקטים",
    # Production crew
    "casting_director":    "מנהל ליהוק",
    "line_producer":       "מנהל הפקה",
    "production_designer": "מעצב הפקה",
    "online_editor":       "עורך אונליין",
    "colorist":            "מתקן צבע",
    "color_grader":        "מתקן צבע",
    "sound_recordist":     "מקליט קול",
    "mixer":               "מיקסר",
    "mastering_engineer":  "מהנדס מאסטרינג",
    "post_production":     "פוסט-פרודקשן",
    "drone_cinematographer": "צלם רחפן",
    "visual_designer":     "מעצב ויזואלי",
    "content_editor":      "עורך תוכן",
}


ROLE_LABELS_HE_F: dict[str, str] = {
    "producer":           "מפיקה",
    "produced":           "מפיקה",
    "co_producer":        "מפיקה שותפה",
    "co_produced":        "מפיקה שותפה",
    "directed":           "במאית",
    "executive_producer": "מפיקה בכירה",
    "director":           "במאית",
    "filmmaker":          "יוצרת",
    "screenwriter":       "תסריטאית",
    "scriptwriter":       "תסריטאית",
    "writer":             "כותבת",
    "editor":             "עורכת",
    "cinematographer":    "צלמת",
    "actor":              "שחקנית",
    "sound_designer":     "מעצבת פסקול",
    "composer":           "מלחינה",
    "researcher":         "חוקרת",
    "mentor":             "מנטורית",
    "lector":             "לקטורית",
    "ceo":                'מנכ"לית',
    "fund_manager":       "מנהלת הקרן",
    "foundation_director": "מנהלת הקרן",
    "board_member":       "חברת הנהלה",
    "council_member":     "חברת מועצה",
    "committee_member":   "חברת ועדה",
    "judge":              "שופטת",
    "panelist":           "משתתפת בפאנל",
    "art_director":       "מנהלת אמנותית",
    "faculty":                "מרצה",
    "alumni":                 "בוגרת",
    "administrator":          "סגל מינהלי",
    "technician":             "טכנאית",
    "librarian":              "ספרנית",
    "archivist":              "אחראית ארכיון",
    "cinematheque_director":  "מנהלת סינמטק",
    "prize_winner":       "זוכת פרס",
    "festival_programmer": "אוצרת פסטיבל",
    "critic":             "מבקרת קולנוע",
    "overall_mentor":     "מלווה כוללת",
    "project_mentor":     "מלווה פרויקט",
    "editing_mentor":     "מלווה עריכה",
    "head_of_film_department":        "מנהלת מחלקת קולנוע",
    "cinematheque_director":          "מנהלת סינמטק",
    "project_manager":                "מנהלת פרויקטים",
    "casting_director":    "מנהלת ליהוק",
    "line_producer":       "מנהלת הפקה",
    "production_designer": "מעצבת הפקה",
    "online_editor":       "עורכת אונליין",
    "colorist":            "מתקנת צבע",
    "color_grader":        "מתקנת צבע",
    "sound_recordist":     "מקליטת קול",
    "visual_designer":     "מעצבת ויזואלית",
    "content_editor":      "עורכת תוכן",
}


def he_role(role: str) -> str:
    """Translate a role identifier to Hebrew display label."""
    return ROLE_LABELS_HE.get(role.lower().strip(), role)


def he_role_g(role: str, gender: str) -> str:
    """Return gender-correct Hebrew label for a role."""
    k = role.lower().strip()
    if gender == "f" and k in ROLE_LABELS_HE_F:
        return ROLE_LABELS_HE_F[k]
    return ROLE_LABELS_HE.get(k, role)


def he_roles(roles) -> str:
    return "، ".join(he_role(r) for r in roles) if roles else "—"


def he_roles_g(roles, gender: str) -> str:
    return "، ".join(he_role_g(r, gender) for r in roles) if roles else "—"


def confidence_badge(page_count: int, has_canonical: bool = False) -> str:
    if has_canonical:
        return ('<span class="badge badge-conf-high" '
                'title="מאומת על-ידי רשימת הלקטורים הרשמית של מקור">'
                '✓ מקור רשמי</span>')
    if page_count >= 3:
        return (f'<span class="badge badge-conf-high" title="{page_count} עמודים שונים באתר המוסד שבהם הופיע התפקיד">'
                f'✓ {page_count} עמודים — מאומת</span>')
    elif page_count == 2:
        return (f'<span class="badge badge-conf-medium" title="{page_count} עמודים שונים באתר המוסד שבהם הופיע התפקיד">'
                f'~ {page_count} עמודים — סביר</span>')
    else:
        return (f'<span class="badge badge-conf-low" title="עמוד אחד בלבד — ייתכן זיהוי שגוי של ה-LLM">'
                f'⚠ עמוד אחד — דרושה אימות</span>')


_SEARCH_URL_RE = re.compile(
    r"movies-archive|keywords=|[&?]search=|[&?]category=", re.IGNORECASE)
_FILM_PATH_RE2 = re.compile(r"/(film|films|movie|movies|סרט|סרטים)/", re.IGNORECASE)

STRENGTH_ORDER  = {"strong": 0, "medium": 1, "weak": 2}
STRENGTH_COLORS = {"strong": "#dc2626", "medium": "#f59e0b", "weak": "#22c55e"}
STRENGTH_LABELS = {"strong": "חפיפה", "medium": "סמוך", "weak": "היסטורי"}

# Revolving-door classification: temporal relationship between gatekeeper and filmmaker roles
RD_FILMMAKER_FIRST  = "filmmaker_first"   # made films BEFORE becoming gatekeeper
RD_GATEKEEPER_FIRST = "gatekeeper_first"  # was gatekeeper BEFORE films were made
RD_SIMULTANEOUS     = "simultaneous"      # both roles overlap in time
RD_UNKNOWN          = "unknown"

def classify_revolving_door(inst_years: list, film_years: list) -> str:
    iy = sorted(y for y in (inst_years or []) if y)
    fy = sorted(y for y in (film_years or []) if y)
    if not iy or not fy:
        return RD_UNKNOWN
    # Allow 1-year grace period (production timelines span years)
    if max(fy) < min(iy) - 1:
        return RD_FILMMAKER_FIRST
    if max(iy) < min(fy) - 1:
        return RD_GATEKEEPER_FIRST
    return RD_SIMULTANEOUS
STRENGTH_BG     = {"strong": "#fef2f2", "medium": "#fffbeb", "weak": "#f0fdf4"}


def _render_fund_block(fc: dict, color_map: dict, gender: str,
                       person_html: str) -> str:
    """Render one fund-level conflict block inside a unified person card."""
    src        = fc["source"]
    color      = source_color(src, color_map)
    films      = fc.get("films", [])
    tie_type   = fc.get("tie_type", "strict")
    is_soft    = (tie_type == "soft")
    roles_for_label = fc["inst_roles"] if not is_soft else fc.get("soft_roles", [])
    inst       = he_roles(roles_for_label)
    same_page  = fc.get("same_page", False)
    page_count = fc.get("inst_page_count", 1)
    tie_note   = fc.get("tie_note", "")
    strength   = fc.get("conflict_strength", "medium")
    gap        = fc.get("conflict_gap")
    rd_type    = fc.get("revolving_door_type", RD_UNKNOWN)

    strength_color = STRENGTH_COLORS[strength]
    strength_label = STRENGTH_LABELS[strength]
    strength_bg    = STRENGTH_BG[strength]

    src_badge  = (f'<span class="badge badge-source" style="background:{color}">'
                  f'{he_source(src)}</span>')
    inst_badge_cls = "badge-soft" if is_soft else "badge-power"
    inst_badge = f'<span class="badge {inst_badge_cls}">{inst}</span>'
    has_canonical_for_badge = any(u.startswith("manual://") for u in fc.get("inst_urls", []))
    conf_badge = confidence_badge(page_count, has_canonical_for_badge) if not is_soft else ""
    gap_note = f"~{gap} שנים" if gap is not None else "פער לא ידוע"
    traffic_badge = (
        f'<span class="badge badge-traffic" '
        f'style="background:{strength_bg};color:{strength_color};border:1px solid {strength_color}" '
        f'title="{gap_note} בין תפקיד מוסדי לסרט">● {strength_label}</span>'
    ) if not is_soft else ""
    _RD_BADGE_INFO = {
        RD_FILMMAKER_FIRST:  ("🎬→🔑", "יוצר שהפך לסוקר"),
        RD_GATEKEEPER_FIRST: ("🔑→🎬", "סוקר שהפך ליוצר"),
        RD_SIMULTANEOUS:     ("⚡",    "כיהן ויצר במקביל"),
    }
    if not is_soft and rd_type in _RD_BADGE_INFO:
        _rd_icon, _rd_label = _RD_BADGE_INFO[rd_type]
        rd_badge = (f'<span class="badge badge-rd" title="{_rd_label}">'
                    f'{_rd_icon} {_rd_label}</span>')
    else:
        rd_badge = ""
    films_count_badge = (
        '<span class="badge badge-count">סרט אחד</span>' if len(films) == 1
        else f'<span class="badge badge-count">{len(films)} סרטים</span>'
    )

    # Institutional evidence links
    film_url_set  = {normalize_url(f["url"]) for f in films if f.get("url")}
    inst_urls_all = fc.get("inst_urls", [])
    inst_urls     = [u for u in inst_urls_all if normalize_url(u) not in film_url_set]
    has_canonical = any(u.startswith("manual://") for u in inst_urls_all)
    fallback_film_url = next((f["url"] for f in films
                              if f.get("url") and not _SEARCH_URL_RE.search(f["url"])), "")
    inst_urls_sorted  = sorted(inst_urls, key=lambda u: 0 if u.startswith("manual://") else 1)
    display_urls      = inst_urls_sorted[:2] or ([fallback_film_url] if fallback_film_url else [])

    link_items = []
    seen_canonical = False
    for u in display_urls:
        if u.startswith("manual://"):
            if seen_canonical:
                continue
            seen_canonical = True
            real  = canonical_url_for(u)
            _src  = u.split("/")[2] if u.count("/") >= 2 else ""
            _fund = SOURCE_LABELS_HE.get(_src, _src)
            _sfx  = " (PDF)" if real.endswith(".pdf") else ""
            label = f"📋 רשימת לקטורים רשמית של {_fund}{_sfx}"
            link_items.append(
                f'<a class="film-source-link manual-evidence" href="{real}" '
                f'target="_blank" title="{real}">{label}</a>' if real else
                f'<span class="film-source-link manual-evidence" title="{u}">{label}</span>'
            )
            continue
        if normalize_url(u) in film_url_set or _FILM_PATH_RE2.search(u):
            try:
                _host = _urlparse_mod.urlparse(u).netloc.replace("www.", "")
            except Exception:
                _host = ""
            label = f"עמוד הסרט ב-{_host}" if _host else "עמוד הסרט"
        else:
            try:
                _p    = _urlparse_mod.urlparse(u)
                _host = _p.netloc.replace("www.", "")
                _slug = [s for s in _p.path.strip("/").split("/") if s]
                _slug_str = _urlparse_mod.unquote(_slug[-1] if _slug else "").replace("-", " ")[:40]
                label = f"{_slug_str} ({_host})" if _slug_str else f"עמוד מוסדי ({_host})"
            except Exception:
                label = "עמוד מוסדי"
        link_items.append(f'<a class="film-source-link" href="{u}" target="_blank">{label}</a>')
    sources_html = "".join(link_items)

    # Warning
    warning_html = ""
    if not is_soft and not has_canonical:
        reasons = []
        if same_page or not inst_urls:
            reasons.append("מתועד רק בעמוד הסרט עצמו")
        if page_count == 1 and not (same_page or not inst_urls):
            reasons.append("עמוד אחד בלבד של ראיה מוסדית")
        if reasons:
            warning_html = (
                f'<div class="card-warning">'
                f'⚠ <strong>סבירות נמוכה:</strong> {" · ".join(reasons)}. אמת לפני ציטוט.'
                f'</div>'
            )

    # Film list
    film_rows = ""
    for f in films:
        ftitle    = f.get("title", "")
        furl      = f.get("url", "")
        frole     = f.get("crew_role", "")
        fyear     = f.get("year")
        year_html = f' <span class="film-row-year">({fyear})</span>' if fyear else ''
        _is_search = bool(furl and _SEARCH_URL_RE.search(furl))
        title_html = (
            f'<a href="{furl}" target="_blank" class="film-row-link">{he(ftitle)}</a>'
            if furl and not _is_search else he(ftitle)
        )
        film_rows += (
            f'<li class="film-row">'
            f'<span class="film-row-title">{title_html}{year_html}</span>'
            f'<span class="badge badge-role">{he_role(frole)}</span>'
            f'</li>'
        )
    films_block = f'<ul class="film-list">{film_rows}</ul>' if film_rows else ''

    n_films    = len(films)
    films_word = "סרט אחד" if n_films == 1 else f"{n_films} סרטים"

    years = sorted(fc.get("inst_years", []) or [])
    if not years:
        year_phrase = ""
    elif len(years) == 1:
        year_phrase = f' ב-<strong>{years[0]}</strong>'
    else:
        year_phrase = f' ב-<strong>{years[0]}-{years[-1]}</strong>'

    fund_label_he = SOURCE_LABELS_HE.get(fc["source"], fc["fund_label"])

    gap_html = ""
    if gap is not None and not is_soft:
        gap_html = (f' <span style="color:{strength_color};font-size:12px">'
                    f'(פער: ~{gap} שנים בין תפקיד לסרט)</span>')

    _appeared  = gendered("הופיעה",  "הופיע",  "הופיע/ה",  gender)
    _appears   = gendered("ומופיעה", "ומופיע", "ומופיע/ה", gender)
    _served_as = gendered("כיהנה",   "כיהן",   "כיהן/ה",   gender)

    if is_soft:
        ctx = f' <em>({tie_note})</em>' if tie_note else ''
        finding_html = (
            f"{_appeared} כ<strong>{inst}</strong> "
            f"ב<strong>{fund_label_he}</strong>{year_phrase}{ctx} "
            f"— {_appears} בקרדיטים של <strong>{films_word}</strong> שמומנו על-ידי אותה קרן:"
        )
    else:
        finding_html = (
            f"{_served_as} כ<strong>{inst}</strong> "
            f"ב<strong>{fund_label_he}</strong>{year_phrase} "
            f"— {_appears} בקרדיטים של <strong>{films_word}</strong> שמומנו על-ידי אותה קרן:{gap_html}"
        )

    return (
        f'<div class="conflict-fund-block">'
        f'<div class="conflict-fund-meta">'
        f'{src_badge}{inst_badge}{traffic_badge}{rd_badge}{films_count_badge}{conf_badge}'
        f'</div>'
        f'<div class="film-finding">{finding_html}</div>'
        f'{films_block}'
        f'{warning_html}'
        f'<div class="film-sources">'
        f'<span style="color:#94a3b8;font-size:11px;letter-spacing:.2px">ראיה מוסדית:</span> '
        f'{sources_html or "<span style=\"color:#94a3b8;font-size:11px\">אין</span>"}'
        f'</div>'
        f'</div>'
    )


def render_film_conflict_card(fc_list: list, color_map: dict, gender: str = "unknown",
                               has_pro_profile: bool = False) -> str:
    """One card per person — all fund-level conflicts as sub-blocks inside."""
    # Sort: strict conflicts first, then strongest-first
    fc_list = sorted(
        fc_list,
        key=lambda fc: (
            1 if fc.get("tie_type", "strict") == "soft" else 0,
            STRENGTH_ORDER.get(fc.get("conflict_strength", "medium"), 1),
        ),
    )

    inst_name  = fc_list[0]["person"]
    all_strict = [fc for fc in fc_list if fc.get("tie_type", "strict") != "soft"]
    has_strict = bool(all_strict)
    total_films = sum(len(fc.get("films", [])) for fc in fc_list)

    # Card border = worst strict strength (or soft style if no strict entries)
    if has_strict:
        worst_strength = min(
            (fc.get("conflict_strength", "medium") for fc in all_strict),
            key=lambda s: STRENGTH_ORDER.get(s, 1),
        )
        border_color = STRENGTH_COLORS[worst_strength]
        low_opacity  = all(
            fc.get("inst_page_count", 1) == 1 and fc.get("conflict_strength") != "strong"
            for fc in all_strict
        )
        card_class = "film-conflict-card"
        card_style = (f' style="opacity:0.85;border-right-color:{border_color}"'
                      if low_opacity else f' style="border-right-color:{border_color}"')
    else:
        card_class = "film-conflict-card soft-tie"
        card_style = ' style="border-right-color:#94a3b8"'

    person_html = he(inst_name)
    slug        = person_slug(inst_name)
    pro_link    = (
        f'<a href="#{slug}" class="pro-profile-link" title="פרופיל מקצועי מלא">↗ פרופיל מקצועי</a>'
        if has_pro_profile else ""
    )
    header_badge = (
        '<span class="badge badge-flag">ניגוד עניינים</span>' if has_strict
        else '<span class="badge badge-soft">קשר רך</span>'
    )
    total_badge = (
        '<span class="badge badge-count">סרט אחד</span>' if total_films == 1
        else f'<span class="badge badge-count">{total_films} סרטים</span>'
    )
    fund_blocks = "".join(
        _render_fund_block(fc, color_map, gender, person_html) for fc in fc_list
    )

    return f"""
<div class="{card_class}"{card_style}>
  <div class="card-person-row">
    <div class="card-person-name">{person_html}{f" {pro_link}" if pro_link else ""}</div>
    <div class="card-person-meta">{header_badge}{total_badge}</div>
  </div>
  {fund_blocks}
</div>"""


def generate_html(connections: dict, registry: dict, ambiguous: list,
                  people_groups: dict, org_groups: dict, sources_list: list,
                  film_conflicts: list, url_to_film: dict = None,
                  repeat_winners: list = None, wiki_enrichment: dict = None) -> str:
    url_to_film    = url_to_film or {}
    repeat_winners = repeat_winners or []
    wiki_enrichment = wiki_enrichment or {}

    color_map: dict = {}
    # Pre-assign colors in sorted order for consistency
    for src in sorted(sources_list):
        source_color(src, color_map)

    cross = connections["cross_source"]
    conflicts = connections["conflicts"]

    n_people   = len(registry["people"])
    n_orgs     = len(registry["organizations"])
    n_cross    = len(cross)
    n_conf     = len(conflicts)
    n_film_cf      = len({normalize_name(fc["person"]) for fc in film_conflicts})
    n_film_entries = sum(len(g.get("films", [])) for g in film_conflicts)
    n_sources  = len(sources_list)
    n_records  = sum(len(v) for v in people_groups.values())
    n_pages    = len({m["url"] for grp in people_groups.values() for m in grp
                      if not m["url"].startswith("manual://")})
    n_films    = len(url_to_film)
    # Format: "6 ביוני 2026, 14:29 (שעון ישראל)" — Hebrew month name, Israel time
    try:
        from zoneinfo import ZoneInfo
        _now_il = datetime.now(ZoneInfo("Asia/Jerusalem"))
    except Exception:
        _now_il = datetime.now()
    _HE_MONTHS = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
                  "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"]
    gen_time = (f"{_now_il.day} ב{_HE_MONTHS[_now_il.month - 1]} {_now_il.year}, "
                f"{_now_il.strftime('%H:%M')} (שעון ישראל)")

    # Gender breakdown across all resolved people (registry stores pre-computed gender)
    _gcount_all     = {"f": 0, "m": 0, "unknown": 0}
    _gcount_power   = {"f": 0, "m": 0, "unknown": 0}
    _gcount_film_cf = {"f": 0, "m": 0, "unknown": 0}
    for prec in registry["people"].values():
        g = prec.get("gender") or infer_gender(prec["canonical_name_he"])
        _gcount_all[g] += 1
    for entry in cross:
        if entry.get("is_power"):
            g = entry.get("gender", "unknown")
            _gcount_power[g] += 1
    _film_cf_people = {normalize_name(fc["person"]) for fc in film_conflicts}
    for prec in registry["people"].values():
        if normalize_name(prec["canonical_name_he"]) in _film_cf_people:
            g = prec.get("gender") or infer_gender(prec["canonical_name_he"])
            _gcount_film_cf[g] += 1

    # Legend
    legend_html = "".join(
        f'<span class="badge badge-source" style="background:{color_map[s]};margin:2px">'
        f'{he_source(s)}</span>'
        for s in sorted(sources_list)
    )

    # Power map — heart of the network
    power_map = compute_power_map(cross, film_conflicts)
    _film_cf_norm_names = {normalize_name(fc["person"]) for fc in film_conflicts}
    power_map_html = render_power_map_section(power_map, color_map, _film_cf_norm_names)
    n_power_map = len(power_map)

    # Pre-compute conflict lookups (needed before card rendering)
    _cross_norm_set    = {normalize_name(e["name"]) for e in cross}
    _conf_norm_set     = {normalize_name(e["name"]) for e in conflicts}
    _conflicts_by_norm = {normalize_name(e["name"]): e for e in conflicts}

    # Predict which norms will actually get a rendered profile card — used to guard
    # derived-conflict links from pointing to anchors that never get emitted (T19).
    _fc_norm_names_needed: set = {normalize_name(fc["person"]) for fc in film_conflicts}
    _fc_norm_names_needed |= _conf_norm_set
    _will_render_norms: set = {normalize_name(e["name"]) for e in cross[:600]}
    for _e in cross[600:]:
        _n = normalize_name(_e["name"])
        if _n in _fc_norm_names_needed or _e.get("is_power"):
            _will_render_norms.add(_n)

    # ── Derived conflicts — build per-person lookup for card badges ──────────
    _dc_path = Path("data/derived_conflicts.json")
    _dc_by_person: dict[str, str] = {}   # normalized_name → pre-rendered HTML snippet
    if _dc_path.exists():
        try:
            _dc = json.loads(_dc_path.read_text(encoding="utf-8"))

            _FUND_LABEL = {
                "makor": "קרן מקור", "filmfund": "הקרן הישראלית לקולנוע",
                "rabinovich_cinema": "קרן רבינוביץ",
                "jerusalem_film_fund": "קרן ירושלים לקולנוע",
                "nfct": "הקרן החדשה לקולנוע וטלוויזיה",
                "fdoc": "הפורום הדוקומנטרי", "gesher": "קרן גשר",
                "festival_data": "פסטיבלים",
            }
            _FUND_URL = {
                "makor":               "https://www.makor-foundation.org.il/",
                "filmfund":            "https://www.filmfund.org.il/",
                "rabinovich_cinema":   "https://www.ravina.co.il/cinema/",
                "jerusalem_film_fund": "https://www.jerusalem.muni.il/culture/cinema/",
                "nfct":                "https://www.nfct.org.il/",
                "fdoc":                "https://www.fdoc.co.il/",
                "gesher":              "https://gesherfilm.org.il/",
            }
            def _fl(k):
                label = _FUND_LABEL.get(k, k.replace("_", " "))
                url   = _FUND_URL.get(k)
                if url:
                    return f'<a href="{url}" target="_blank" style="color:#1d4ed8;text-decoration:underline">{label}</a>'
                return label

            def _plink_dc(pname):
                if normalize_name(pname) not in _will_render_norms:
                    return f'<strong>{pname}</strong>'
                slug = person_slug(pname)
                return f'<a href="#{slug}" style="color:#0f172a;font-weight:600;text-decoration:underline dotted #94a3b8">{pname}</a>'

            def _dc_row(icon, color, text):
                return (f'<div style="display:flex;align-items:flex-start;gap:6px;'
                        f'padding:5px 8px;border-right:3px solid {color};'
                        f'margin-bottom:4px;font-size:12px;color:#334155">'
                        f'<span style="color:{color};flex-shrink:0">{icon}</span>'
                        f'{text}</div>')

            def _add_dc(person_name, html_row):
                k = normalize_name(person_name)
                _dc_by_person[k] = _dc_by_person.get(k, "") + html_row

            # 1. Critics on fund committees
            for e in _dc.get("critic_committee", []):
                funds_str = " · ".join(_fl(f) for f in e["funds"])
                roles_str = ", ".join(e["fund_roles"])
                _add_dc(e["person"], _dc_row("✍", "#f59e0b",
                    f'מבקר/עיתונאי שמכהן גם בוועדת קרן — {funds_str}'
                    f'<span style="color:#94a3b8;margin-right:6px">({roles_str})</span>'))

            # 2. Family pairs — add badge for both persons
            for e in _dc.get("family_pairs", []):
                shared = " · ".join(_fl(f) for f in e["shared_funds"]) if e["shared_funds"] else "קרנות נפרדות"
                verify = '<span style="color:#94a3b8;font-size:10px"> ⚠ נדרש אימות</span>'
                _add_dc(e["person_a"], _dc_row("👨‍👩‍👦", "#c084fc",
                    f'קשר משפחתי אפשרי עם {_plink_dc(e["person_b"])} · {shared}{verify}'))
                _add_dc(e["person_b"], _dc_row("👨‍👩‍👦", "#c084fc",
                    f'קשר משפחתי אפשרי עם {_plink_dc(e["person_a"])} · {shared}{verify}'))

            # 3. Collaborators on same committee — add badge for both
            for e in _dc.get("collab_committee", []):
                films_str = " · ".join(e.get("shared_films", [])[:2])
                fund_str  = _fl(e["fund"])
                _add_dc(e["person_a"], _dc_row("🎬", "#22d3ee",
                    f'שותף יצירה עם {_plink_dc(e["person_b"])} — שניהם בוועדת {fund_str}'
                    + (f' · <span style="color:#94a3b8">{films_str}</span>' if films_str else "")))
                _add_dc(e["person_b"], _dc_row("🎬", "#22d3ee",
                    f'שותף יצירה עם {_plink_dc(e["person_a"])} — שניהם בוועדת {fund_str}'
                    + (f' · <span style="color:#94a3b8">{films_str}</span>' if films_str else "")))

            # 4. Festival + fund committee
            for e in _dc.get("festival_committee", []):
                funds_str = " · ".join(_fl(f) for f in e["funds"])
                fest_str  = " · ".join(e.get("festival_roles", []))
                _add_dc(e["person"], _dc_row("🎪", "#86efac",
                    f'מנהל/אוצר פסטיבל שמכהן גם בוועדת קרן — {funds_str}'
                    f'<span style="color:#94a3b8;margin-right:6px">({fest_str})</span>'))

            # 5. Exec filmmakers
            for e in _dc.get("exec_filmmaker", []):
                funds_str = " · ".join(_fl(f) for f in e["funds"])
                exec_str  = " · ".join(e.get("exec_roles", []))
                film_str  = " · ".join(e.get("filmmaker_roles", []))
                _add_dc(e["person"], _dc_row("🔑", "#f97316",
                    f'מנהל קרן ({exec_str}) שהוא גם יוצר פעיל ({film_str}) — {funds_str}'))

        except Exception as _dc_err:
            import traceback; traceback.print_exc()
            print(f"Warning: could not build derived conflicts lookup: {_dc_err}", file=__import__("sys").stderr)

    # Cross-source people cards
    power_cards = [e for e in cross if e["is_power"]]
    film_cards  = [e for e in cross if not e["is_power"]]

    # Profile cards: first 600 cross-source people, plus any film/role-conflict person
    # or power-role person beyond that rank so all conflict figures get a visible card.
    _rendered_norms: set = set()
    cross_html = ""
    for entry in cross[:600]:
        _norm = normalize_name(entry["name"])
        # Use the conflict entry (has flags) when available so ⚑ flags show inline
        _render_entry  = _conflicts_by_norm.get(_norm, entry)
        _is_conflict   = _norm in _conf_norm_set
        cross_html += render_person_card(_render_entry, color_map,
                                         is_conflict=_is_conflict,
                                         url_to_film=url_to_film,
                                         wiki_enrichment=wiki_enrichment,
                                         dc_html=_dc_by_person.get(_norm, ""))
        _rendered_norms.add(_norm)
    for entry in cross[600:]:
        norm = normalize_name(entry["name"])
        if norm in _fc_norm_names_needed or entry.get("is_power"):
            _render_entry = _conflicts_by_norm.get(norm, entry)
            _is_conflict  = norm in _conf_norm_set
            cross_html += render_person_card(_render_entry, color_map,
                                             is_conflict=_is_conflict,
                                             url_to_film=url_to_film,
                                             wiki_enrichment=wiki_enrichment,
                                             dc_html=_dc_by_person.get(norm, ""))
            _rendered_norms.add(norm)

    # conflict_html is no longer a standalone section — flags are folded into cross cards above
    conflict_html = ""

    # Film-conflict cards — grouped by person (one card per person, all funds inside)
    _cross_norm_names = _rendered_norms  # only people with actual profile cards
    _fc_gender: dict = {}
    for prec in registry["people"].values():
        _fc_gender[normalize_name(prec["canonical_name_he"])] = (
            prec.get("gender") or infer_gender(prec["canonical_name_he"])
        )
    from collections import defaultdict as _defaultdict
    _fc_by_person: dict = _defaultdict(list)
    for fc in film_conflicts:
        _fc_by_person[normalize_name(fc["person"])].append(fc)
    # Sort persons: strict conflicts first, then by total film count desc
    def _person_sort_key(norm):
        entries = _fc_by_person[norm]
        has_strict = any(e.get("tie_type", "strict") != "soft" for e in entries)
        total = sum(len(e.get("films", [])) for e in entries)
        return (0 if has_strict else 1, -total)
    _fc_persons_sorted = sorted(_fc_by_person.keys(), key=_person_sort_key)
    film_conflict_html = "".join(
        render_film_conflict_card(
            _fc_by_person[norm],
            color_map,
            gender=_fc_gender.get(norm, "unknown"),
            has_pro_profile=(norm in _cross_norm_names),
        )
        for norm in _fc_persons_sorted
    )

    # Top orgs table
    top_orgs = sorted(registry["organizations"].values(),
                      key=lambda x: (-x["mention_count"], -x["source_count"]))[:80]
    org_rows = ""
    for o in top_orgs:
        src_badges = "".join(
            f'<span class="badge badge-source" style="background:{source_color(s,color_map)}'
            f';margin:1px">{he_source(s)}</span>'
            for s in sorted(o["sources"])
        )
        en = f'<div class="org-name-en">{o["canonical_name_en"]}</div>' if o["canonical_name_en"] else ""
        type_str = ", ".join(o.get("types") or [])
        org_rows += (
            f'<tr><td><div class="org-name-he">{he(o["canonical_name_he"])}</div>{en}</td>'
            f'<td>{type_str}</td>'
            f'<td>{src_badges}</td>'
            f'<td>{o["mention_count"]}</td></tr>'
        )

    # Repeat winners section
    if repeat_winners:
        rw_rows = ""
        for rw in repeat_winners:
            src_badges = "".join(
                f'<span class="badge badge-source" style="background:{source_color(s, color_map)}'
                f';margin:1px">{he_source(s)}</span>'
                for s in rw["sources"]
            )
            role_badges = "".join(
                f'<span class="badge badge-power">{he_role(r)}</span>'
                for r in rw["inst_roles"]
            ) or '<span class="badge badge-role">—</span>'
            films_text = "، ".join(
                f'{f["title"]} ({f["year"]})' if f.get("year") else f["title"]
                for f in rw["films"]
            )
            count_badge = (
                f'<span class="badge badge-flag" style="font-size:13px;padding:2px 10px">'
                f'{rw["film_count"]}</span>'
            )
            rw_rows += (
                f'<tr>'
                f'<td><strong dir="rtl">{he(rw["person"])}</strong></td>'
                f'<td style="text-align:center">{count_badge}</td>'
                f'<td>{src_badges}</td>'
                f'<td>{role_badges}</td>'
                f'</tr>'
                f'<tr><td colspan="4" style="padding:2px 14px 10px;color:#64748b;font-size:12px;direction:rtl">'
                f'{films_text}</td></tr>'
            )
        _repeat_winners_section = f"""
<div class="section" id="sec-repeat-winners">
  <div class="section-title">
    זוכים חוזרים
    <span class="count">{len(repeat_winners)}</span>
  </div>
  <p style="color:#64748b;font-size:12px;margin-bottom:12px">
    אנשים המופיעים בקרדיטי 3 סרטים ממומנים או יותר על-ידי אותן קרנות.
  </p>
  <table class="org-table">
    <thead><tr><th>שם</th><th style="text-align:center">סרטים ממומנים</th><th>קרנות</th><th>תפקיד מוסדי</th></tr></thead>
    <tbody>{rw_rows}</tbody>
  </table>
</div>"""
    else:
        _repeat_winners_section = ""

    # Production companies section
    prod_orgs = sorted(
        [o for o in registry["organizations"].values()
         if "production_company" in (o.get("types") or [])],
        key=lambda o: -o["mention_count"]
    )[:50]

    if prod_orgs:
        prod_rows = ""
        for o in prod_orgs:
            src_badges = "".join(
                f'<span class="badge badge-source" style="background:{source_color(s, color_map)}'
                f';margin:1px">{he_source(s)}</span>'
                for s in sorted(o["sources"])
            )
            # Don't link to film pages — URLs in sources[] are fund/festival pages
            # where the company appeared, not the company's own site.
            name_html = f'<div class="org-name-he">{he(o["canonical_name_he"])}</div>'
            prod_rows += (
                f'<tr><td>{name_html}</td>'
                f'<td>{src_badges}</td>'
                f'<td>{o["mention_count"]}</td></tr>'
            )
        _prod_companies_section = f"""
<div class="section" id="sec-prod-companies">
  <div class="section-title">
    חברות הפקה
    <span class="count">{len(prod_orgs)}</span>
  </div>
  <table class="org-table">
    <thead><tr><th>שם החברה</th><th>מקורות</th><th>אזכורים</th></tr></thead>
    <tbody>{prod_rows}</tbody>
  </table>
</div>"""
    else:
        _prod_companies_section = ""

    # ── Revolving door summary ────────────────────────────────────────────────
    strict_fcs = [fc for fc in film_conflicts if fc.get("tie_type", "strict") != "soft"]
    _rd_counts = {RD_FILMMAKER_FIRST: 0, RD_GATEKEEPER_FIRST: 0, RD_SIMULTANEOUS: 0, RD_UNKNOWN: 0}
    for fc in strict_fcs:
        _rd_counts[fc.get("revolving_door_type", RD_UNKNOWN)] += 1

    _rd_labels_he = {
        RD_FILMMAKER_FIRST:  ("🎬→🔑", "יוצר שהפך לסוקר",   "עשה/תה סרטים לפני שנכנס לתפקיד הסינון"),
        RD_GATEKEEPER_FIRST: ("🔑→🎬", "סוקר שהפך ליוצר",   "כיהן בתפקיד סינון לפני שיצר סרטים"),
        RD_SIMULTANEOUS:     ("⚡",    "כיהן ויצר במקביל",   "חפיפה בין תפקיד מוסדי לפעילות יצירתית"),
        RD_UNKNOWN:          ("❓",    "ללא נתוני שנה",       "לא ניתן לקבוע כיוון — חסרים נתוני שנה"),
    }

    # Top cases per category (by film count, show up to 5)
    _rd_top: dict[str, list] = {k: [] for k in _rd_labels_he}
    for fc in strict_fcs:
        k = fc.get("revolving_door_type", RD_UNKNOWN)
        _rd_top[k].append(fc)
    for k in _rd_top:
        _rd_top[k].sort(key=lambda x: -len(x.get("films", [])))
        _rd_top[k] = _rd_top[k][:5]

    _rd_stat_blocks = ""
    for rd_key, (icon, label_he, desc_he) in _rd_labels_he.items():
        cnt = _rd_counts[rd_key]
        if cnt == 0:
            continue
        top_names = ", ".join(he(fc["person"]) for fc in _rd_top[rd_key])
        _rd_stat_blocks += (
            f'<div class="rd-stat-block">'
            f'<div class="rd-stat-header">'
            f'<span class="badge badge-rd">{icon} {label_he}</span>'
            f'<span class="rd-stat-count">{cnt}</span>'
            f'</div>'
            f'<div class="rd-stat-desc">{desc_he}</div>'
            f'<div class="rd-stat-names">{top_names}</div>'
            f'</div>'
        )

    _rd_inner = f"""
  <div style="margin-top:24px;border-top:1px solid #e2e8f0;padding-top:18px">
    <div style="font-size:13px;font-weight:700;color:#0f172a;margin-bottom:8px">
      🔄 ניתוח כרונולוגי — דלת מסתובבת
      <span style="font-size:12px;font-weight:400;color:#64748b;margin-right:8px">{len(strict_fcs)}</span>
    </div>
    <p style="color:#64748b;font-size:12px;margin-bottom:12px;line-height:1.7">
      סיווג כל ניגוד עניינים לפי הכיוון הכרונולוגי בין תפקיד מוסדי לבין קרדיטים בסרטים.
    </p>
    <div class="rd-stats-grid">{_rd_stat_blocks}</div>
  </div>""" if strict_fcs else ""
    _rd_section = _rd_inner  # keep name for backward compat

    # ── Table of contents ────────────────────────────────────────────────────
    toc_entries = [
        ("sec-film-conflicts",    "🎬 ניגודי עניינים ישירים",  f"{n_film_cf} אנשים"),
        ("sec-cross-people",      "👤 פרופיל מקצועי",           f"{n_cross} אנשים"),
        ("sec-orgs",              "🏢 ארגונים",                 f"{n_orgs:,}"),
    ]
    if repeat_winners:
        toc_entries.append(("sec-repeat-winners", "⭐ זוכים חוזרים", f"{len(repeat_winners)} אנשים"))
    if prod_orgs:
        toc_entries.append(("sec-prod-companies", "🏭 חברות הפקה", f"{len(prod_orgs)} חברות"))
    toc_entries.append(("sec-power-map", "🔑 מרכז הרשת", f"{n_power_map} אנשים"))

    toc_links = "".join(
        f'<a href="#{sec_id}" class="toc-link">'
        f'<span class="toc-label">{label}</span>'
        f'<span class="toc-count">{count}</span>'
        f'</a>'
        for sec_id, label, count in toc_entries
    )
    films_link = (
        '<a href="films.html" class="toc-link" target="_blank">'
        '<span class="toc-label">🎬 קטלוג סרטים</span>'
        '<span class="toc-count">↗</span>'
        '</a>'
    )
    toc_html = (
        f'<nav class="toc"><div class="toc-title">תוכן עניינים</div>'
        f'<div class="toc-links">{toc_links}{films_link}</div></nav>'
    )

    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>תעשיית הקולנוע הישראלית — דוח חיבורי גופים</title>
  <style>{CSS}</style>
</head>
<body>

<nav class="site-nav">
  <a href="graph.html">🔗 גרף ניגודי עניינים</a>
  <a href="connections_report.html" class="active">📋 דוח חיבורים</a>
  <a href="films.html">🎬 קטלוג סרטים</a>
</nav>

<div class="header">
  <h1>תעשיית הקולנוע הישראלית — דוח חיבורי גופים</h1>
  <div class="subtitle">מיפוי קשרים בין מקורות גלויים · P-Valyou</div>
  <div class="meta">נוצר {gen_time} · {n_sources} מקורות נתונים</div>
</div>

<div class="stats-bar">
  <div class="stat"><div class="value">{n_people:,}</div><div class="label">אנשים</div></div>
  <div class="stat"><div class="value">{n_pages:,}</div><div class="label">דפים נסרקו</div></div>
  <div class="stat"><div class="value">{n_films:,}</div><div class="label">סרטים זוהו</div></div>
  <div class="stat"><div class="value">{n_cross:,}</div><div class="label">עם פרופיל מקצועי</div></div>
  <div class="stat"><div class="value" style="color:#1e293b;font-weight:800">{n_power_map}</div><div class="label">מרכז הרשת</div></div>
  <div class="stat"><div class="value">{len(power_cards)}</div><div class="label">תפקידים מוסדיים</div></div>
  <div class="stat"><div class="value" style="color:#dc2626">{n_film_cf}</div><div class="label">אנשים מסומנים</div></div>
  <div class="stat"><div class="value" style="color:#dc2626">{n_film_entries}</div><div class="label">סרטים מעורבים</div></div>
  <div class="stat"><div class="value" style="color:#f59e0b">{n_conf}</div><div class="label">ניגודי תפקיד</div></div>
  <div class="stat"><div class="value">{len(repeat_winners)}</div><div class="label">זוכים חוזרים</div></div>
</div>

<div style="background:#fff;border-bottom:1px solid #e2e8f0;padding:10px 40px;font-size:12px;color:#475569;display:flex;gap:32px;flex-wrap:wrap">
  <span><strong>מגדר — כלל האנשים:</strong> {_gcount_all["f"]} נשים · {_gcount_all["m"]} גברים · {_gcount_all["unknown"]} לא ידוע</span>
  <span><strong>תפקידי כוח:</strong> {_gcount_power["f"]} נשים · {_gcount_power["m"]} גברים · {_gcount_power["unknown"]} לא ידוע</span>
  <span><strong>מסומנים בניגוד עניינים:</strong> {_gcount_film_cf["f"]} נשים · {_gcount_film_cf["m"]} גברים · {_gcount_film_cf["unknown"]} לא ידוע</span>
</div>

<div class="main">

  {DISCLAIMER_HTML}

  {toc_html}

  <!-- Source legend -->
  <div style="margin-bottom:28px">
    <div style="font-size:11px;color:#64748b;letter-spacing:.2px;margin-bottom:8px">מקורות</div>
    {legend_html}
  </div>

  <!-- Film-level conflicts + revolving door (merged) -->
  <div class="section" id="sec-film-conflicts">
    <div class="section-title" style="border-color:#dc2626">
      🎬 ניגודי עניינים ישירים
      <span class="count" style="background:#fee2e2;color:#991b1b">{n_film_cf} אנשים</span>
    </div>
    <p style="color:#64748b;font-size:13px;margin-bottom:14px;line-height:1.7">
      <strong style="color:#991b1b">ניגוד עניינים</strong>: אדם כיהן בתפקיד מוסדי ברור
      (לקטור, חבר הנהלה, מנכ"ל) בקרן <em>וגם</em> מופיע כמפיק או במאי בסרט שמומן על-ידי אותה קרן.<br>
      <strong style="color:#1d4ed8">קשר רך</strong>: אדם הופיע באירוע של הקרן או הוזכר בה פומבית,
      <em>וגם</em> מקבל קרדיט בסרט שמומן על-ידי אותה קרן.
    </p>
    {film_conflict_html if film_conflict_html else
     '<div style="color:#94a3b8;font-size:13px;padding:20px">לא זוהו ניגודי עניינים ברמת הסרט.</div>'}
    {_rd_inner}
  </div>

  <!-- Professional profiles -->
  <div class="section" id="sec-cross-people">
    <div class="section-title">
      👤 פרופיל מקצועי
      <span class="count">{n_cross}</span>
    </div>
    <p style="color:#64748b;font-size:12px;margin-bottom:14px;direction:rtl;text-align:right">
      קורות חיים מקצועיים לכל אדם שהוזכר ביותר ממקור אחד — תפקידים מוסדיים, קרדיטים בסרטים והופעות נוספות.
    </p>
    <div class="filters">
      <button class="filter-btn active" onclick="filterCards('all')">הכול ({n_cross})</button>
      <button class="filter-btn" onclick="filterCards('power')">מוסדיים ({len(power_cards)})</button>
      <button class="filter-btn" onclick="filterCards('film')">יוצרים ({len(film_cards)})</button>
    </div>
    {cross_html if cross_html else
     '<div style="color:#94a3b8;font-size:13px;padding:20px">לא נמצאו פרופילים מקצועיים.</div>'}
  </div>

  <!-- Top organisations -->
  <div class="section" id="sec-orgs">
    <div class="section-title">
      ארגונים מובילים
      <span class="count">{n_orgs:,}</span>
    </div>
    <table class="org-table">
      <thead><tr><th>שם</th><th>סוג</th><th>מקורות</th><th>אזכורים</th></tr></thead>
      <tbody>{org_rows}</tbody>
    </table>
  </div>

  <!-- Repeat winners -->
  {_repeat_winners_section}

  <!-- Production companies -->
  {_prod_companies_section}

  <!-- Heart of the network — power map -->
  {power_map_html}

</div>

<div class="footer">
  מיפוי קשרים בתעשיית הקולנוע הישראלית · P-Valyou · {gen_time}<br>
  <small style="color:#cbd5e1">מקורות פתוחים בלבד · למחקר בלבד · אינו מסמך משפטי · נדרש אימות עצמאי לפני פרסום</small>
</div>

<div id="section-beacon"></div>
<script>{JS}</script>
</body>
</html>"""


# ── Network graph export ───────────────────────────────────────────────────────

_SCHOOL_LABELS = {
    "sam_spiegel":         "בית הספר סם שפיגל לקולנוע וטלוויזיה",
    "tel_aviv_university": "אוניברסיטת תל אביב – בית הספר לקולנוע וטלוויזיה",
    "sapir_college":       "מכללת ספיר – בית הספר לאמנויות הקול והמסך",
    "minshar":             "מנשר לאמנות – בית הספר לקולנוע וטלוויזיה",
    "beit_berl":           "מכללת בית ברל – המחלקה לאמנות",
}

# (pattern, school_key) — match against wiki intro_snippet to detect alumni.
# Use [^.]{0,N} to stay within one sentence and avoid greedy over-matching.
_ALUMNI_PATTERNS: list[tuple] = [
    # Sam Spiegel: "בוגר/ת ... סם שפיגל" anywhere in same sentence
    (re.compile(r'בוגר[ת]?[^.]{0,80}סם\s+שפיגל', re.UNICODE), "sam_spiegel"),
    # TAU film: "בוגר/ת ... החוג/בית הספר ... קולנוע ... תל אביב"
    (re.compile(r'בוגר[ת]?[^.]{0,60}(?:חוג|בית\s+הספר)[^.]{0,60}(?:קולנוע|טלוויזיה)[^.]{0,40}תל\s+אביב', re.UNICODE), "tel_aviv_university"),
    # TAU simpler: "בוגר/ת אוניברסיטת תל אביב" (person is a filmmaker — film context is implied)
    (re.compile(r'בוגר[ת]?\s+אוניברסיטת\s+תל\s+אביב', re.UNICODE), "tel_aviv_university"),
    # Sapir — require "קולנוע" or "מסך" nearby to avoid non-film Sapir (e.g. social sciences lecturers)
    (re.compile(r'בוגר[ת]?[^.]{0,60}(?:מכללת\s+)?ספיר[^.]{0,60}(?:קולנוע|מסך|סרט)', re.UNICODE), "sapir_college"),
    (re.compile(r'בוגר[ת]?[^.]{0,30}ספיר[^.]{0,30}', re.UNICODE), "sapir_college"),  # fallback
    (re.compile(r'בוגר[ת]?[^.]{0,40}מנשר', re.UNICODE), "minshar"),
    (re.compile(r'בוגר[ת]?[^.]{0,60}(?:מכללת\s+)?בית\s+ברל', re.UNICODE), "beit_berl"),
]


def build_network_graph(film_conflicts: list, connections: dict, registry: dict,
                        wiki_enrichment: dict = None) -> dict:
    """
    Build a bipartite person ↔ fund network graph for Gephi / vis.js.

    Nodes:
      - type="person" — everyone who appears in film_conflicts or cross-source
      - type="fund"   — every source/fund that has a conflict edge

    Edges:
      - type="institutional" — person held an institutional role at fund
      - type="film_funded"   — person's film was funded by fund
    """
    nodes: dict[str, dict] = {}
    edges: list[dict]      = []

    # People from film_conflicts
    conflict_people = {normalize_name(fc["person"]) for fc in film_conflicts
                       if fc.get("tie_type", "strict") != "soft"}
    soft_people     = {normalize_name(fc["person"]) for fc in film_conflicts
                       if fc.get("tie_type", "strict") == "soft"}

    def _person_node(name_he: str) -> str:
        nid = f"person::{normalize_name(name_he)}"
        if nid not in nodes:
            prec = registry["people"].get(normalize_name(name_he)) or {}
            gender = prec.get("gender") or infer_gender(name_he)
            has_strict = normalize_name(name_he) in conflict_people
            has_soft   = normalize_name(name_he) in soft_people
            nodes[nid] = {
                "id":           nid,
                "label":        name_he,
                "type":         "person",
                "gender":       gender,
                "has_strict_conflict": has_strict,
                "has_soft_conflict":   has_soft,
                "source_count": prec.get("source_count", 1),
                "group":        "conflict" if has_strict else ("soft" if has_soft else "person"),
            }
        return nid

    def _fund_node(src: str) -> str:
        nid = f"fund::{src}"
        if nid not in nodes:
            nodes[nid] = {
                "id":    nid,
                "label": SOURCE_LABELS_HE.get(src, src),
                "type":  "fund",
                "group": "fund",
            }
        return nid

    # Build edges from film_conflicts
    seen_inst:  set[tuple] = set()
    seen_film:  set[tuple] = set()

    for fc in film_conflicts:
        pnid = _person_node(fc["person"])
        fnid = _fund_node(fc["source"])

        # Institutional edge (one per person-fund pair)
        inst_key = (pnid, fnid, "institutional")
        if inst_key not in seen_inst:
            seen_inst.add(inst_key)
            edges.append({
                "id":         f"e{len(edges)}",
                "source":     pnid,
                "target":     fnid,
                "type":       "institutional",
                "tie_type":   fc.get("tie_type", "strict"),
                "roles":      fc.get("inst_roles", []),
                "rd_type":    fc.get("revolving_door_type", RD_UNKNOWN),
                "strength":   fc.get("conflict_strength", "medium"),
                "weight":     3 if fc.get("tie_type", "strict") != "soft" else 1,
            })

        # Film edges (one per unique film)
        for film in fc.get("films", []):
            film_key = (pnid, fnid, film.get("title", ""), film.get("year"))
            if film_key not in seen_film:
                seen_film.add(film_key)
                edges.append({
                    "id":         f"e{len(edges)}",
                    "source":     pnid,
                    "target":     fnid,
                    "type":       "film_funded",
                    "film_title": film.get("title", ""),
                    "film_year":  film.get("year"),
                    "crew_role":  film.get("crew_role", ""),
                    "weight":     1,
                })

    # Also add cross-source people who don't have film conflicts
    for entry in connections.get("cross_source", []):
        _person_node(entry["name"])

    # Seed critic nodes from out/critics/ and out/edb_critics/ sources.
    # Critics appear in only one source so analyze_connections() drops them;
    # but we need them as nodes so reviewed edges can connect them to films.
    for _critic_src in ("out/critics/mentions.jsonl", "out/edb_critics/mentions.jsonl"):
        _cpath = Path(_critic_src)
        if not _cpath.exists():
            continue
        try:
            for _line in _cpath.read_text(encoding="utf-8").splitlines():
                if not _line.strip():
                    continue
                _rec = json.loads(_line)
                if _rec.get("status") != "ok":
                    continue
                for _p in ((_rec.get("data") or {}).get("entities") or {}).get("people", {}).values():
                    if not _p or not _p.get("name_he"):
                        continue
                    _name = _p["name_he"].strip()
                    if _name and not is_junk_name(_name):
                        _person_node(_name)
        except Exception:
            pass

    # Shared helper: normalized person name → node id (rebuilt after all people added)
    def _build_norm_to_node() -> dict[str, str]:
        return {
            normalize_name(n["label"]): nid
            for nid, n in nodes.items() if n.get("type") == "person"
        }

    # ── Collaborator edges from EDB Phase 3 ───────────────────────────────────
    # Load edb_persons.json and add collaborated_with edges between any two
    # persons who are already in the network (don't add isolated nodes).
    n_collab = 0
    edb_persons_path = Path("data/edb/edb_persons.json")
    if edb_persons_path.exists():
        try:
            persons_data = json.loads(edb_persons_path.read_text(encoding="utf-8"))
            id_to_name: dict[str, str] = {
                p["edb_id"]: p["name_he"]
                for p in persons_data if p.get("edb_id") and p.get("name_he")
            }
            norm_to_node = _build_norm_to_node()
            seen_collab: set[frozenset] = set()
            for person in persons_data:
                src_nid = norm_to_node.get(normalize_name(person.get("name_he", "")))
                if not src_nid:
                    continue
                for collab_id in person.get("collaborators", []):
                    tgt_name = id_to_name.get(collab_id, "")
                    tgt_nid  = norm_to_node.get(normalize_name(tgt_name))
                    if not tgt_nid or tgt_nid == src_nid:
                        continue
                    pair = frozenset((src_nid, tgt_nid))
                    if pair in seen_collab:
                        continue
                    seen_collab.add(pair)
                    edges.append({
                        "id":     f"e{len(edges)}",
                        "source": src_nid,
                        "target": tgt_nid,
                        "type":   "collaborated_with",
                        "weight": 1,
                    })
                    n_collab += 1
        except Exception as exc:
            print(f"Warning: could not load collaborator edges: {exc}", file=sys.stderr)

    # ── Film nodes + co_credited edges from EDB film data ─────────────────────
    # For each EDB film: add a film node, then emit crew_credit (person→film)
    # edges and co_credited (person↔person) edges weighted by shared-film count.
    # Only persons already in the graph get edges — no new isolated person nodes.
    n_film_nodes   = 0
    n_crew_credit  = 0
    n_co_credited  = 0
    edb_films_path = Path("data/edb/edb_films.json")
    if edb_films_path.exists():
        try:
            films_data = json.loads(edb_films_path.read_text(encoding="utf-8"))
            norm_to_node_f = _build_norm_to_node()
            # co_credited_weights[(nid_a, nid_b)] — keyed as sorted tuple for dedup
            co_weights: dict[tuple, int] = {}

            for film in films_data:
                film_id  = film.get("film_id", "")
                title    = (film.get("title") or "").strip()
                if not film_id or not title:
                    continue

                film_nid = f"film::{film_id}"
                if film_nid not in nodes:
                    nodes[film_nid] = {
                        "id":       film_nid,
                        "label":    title,
                        "type":     "film",
                        "group":    "film",
                        "year":     film.get("year"),
                        "is_short": film.get("is_short", False),
                        "url":      film.get("url", ""),
                    }
                    n_film_nodes += 1

                # Crew members already in the graph
                in_graph: list[tuple[str, str]] = []  # (node_id, role)
                for c in (film.get("crew") or []):
                    c_name = (c.get("name_he") or "").strip()
                    if not c_name:
                        continue
                    c_nid = norm_to_node_f.get(normalize_name(c_name))
                    if c_nid:
                        in_graph.append((c_nid, c.get("role", "")))

                # crew_credit edges: person → film
                for c_nid, c_role in in_graph:
                    edges.append({
                        "id":     f"e{len(edges)}",
                        "source": c_nid,
                        "target": film_nid,
                        "type":   "crew_credit",
                        "role":   c_role,
                        "weight": 1,
                    })
                    n_crew_credit += 1

                # Accumulate co_credited weight for every in-graph pair
                for i in range(len(in_graph)):
                    for j in range(i + 1, len(in_graph)):
                        nid_a = in_graph[i][0]
                        nid_b = in_graph[j][0]
                        if nid_a == nid_b:
                            continue
                        key = (min(nid_a, nid_b), max(nid_a, nid_b))
                        co_weights[key] = co_weights.get(key, 0) + 1

            # Emit co_credited edges
            for (nid_a, nid_b), weight in co_weights.items():
                edges.append({
                    "id":     f"e{len(edges)}",
                    "source": nid_a,
                    "target": nid_b,
                    "type":   "co_credited",
                    "weight": weight,
                })
                n_co_credited += 1

        except Exception as exc:
            print(f"Warning: could not load EDB film nodes: {exc}", file=sys.stderr)

    # ── Reviewed edges from EDB critics blog ──────────────────────────────────
    # edb_critics/mentions.jsonl records each have a critic (person entity) and
    # a list of `reviewed` relationships whose target_id is an EDB film ID.
    # We create reviewed edges only when both the critic and the film already
    # have nodes in the graph (no isolated new nodes added here).
    n_reviewed = 0
    edb_critics_path = Path("out/edb_critics/mentions.jsonl")
    if edb_critics_path.exists():
        try:
            norm_to_node_c = _build_norm_to_node()
            for line in edb_critics_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                if rec.get("status") != "ok":
                    continue
                data_c    = rec.get("data") or {}
                people_c  = (data_c.get("entities") or {}).get("people") or {}
                rels_c    = data_c.get("relationships") or []
                if not rels_c:
                    continue
                # Collect critic entity ids → node ids
                pid_to_nid: dict[str, str] = {}
                for eid, p in people_c.items():
                    if not p or not p.get("name_he"):
                        continue
                    nid = norm_to_node_c.get(normalize_name(p["name_he"]))
                    if nid:
                        pid_to_nid[eid] = nid
                if not pid_to_nid:
                    continue
                for rel in rels_c:
                    if rel.get("relationship_type") != "reviewed":
                        continue
                    src_eid = rel.get("source_id", "")
                    film_id = rel.get("target_id", "")
                    if not film_id or src_eid not in pid_to_nid:
                        continue
                    film_nid = f"film::{film_id}"
                    if film_nid not in nodes:
                        continue
                    critic_nid = pid_to_nid[src_eid]
                    edges.append({
                        "id":     f"e{len(edges)}",
                        "source": critic_nid,
                        "target": film_nid,
                        "type":   "reviewed",
                        "weight": 1,
                    })
                    n_reviewed += 1
        except Exception as exc:
            print(f"Warning: could not load reviewed edges: {exc}", file=sys.stderr)

    # ── School nodes + studied_at edges from wiki intro snippets ──────────────
    # enrich/wiki_persons.json intro_snippet fields contain "בוגר/ת SCHOOL"
    # patterns that identify school alumni. We add school nodes and studied_at
    # edges for persons already in the graph; no new person nodes are added.
    n_school_nodes = 0
    n_studied_at   = 0
    wiki_data = wiki_enrichment or {}
    if wiki_data:
        try:
            norm_to_node_w = _build_norm_to_node()

            def _school_node(school_key: str) -> str:
                nid = f"school::{school_key}"
                if nid not in nodes:
                    nodes[nid] = {
                        "id":    nid,
                        "label": _SCHOOL_LABELS[school_key],
                        "type":  "school",
                        "group": "school",
                    }
                    nonlocal n_school_nodes
                    n_school_nodes += 1
                return nid

            seen_studied: set[tuple] = set()
            for person_name, wiki_info in wiki_data.items():
                if not wiki_info:
                    continue
                snippet = (wiki_info.get("intro_snippet") or "").strip()
                if not snippet:
                    continue
                person_nid = norm_to_node_w.get(normalize_name(person_name))
                if not person_nid:
                    continue
                for pattern, school_key in _ALUMNI_PATTERNS:
                    if pattern.search(snippet):
                        school_nid = _school_node(school_key)
                        key = (person_nid, school_nid)
                        if key not in seen_studied:
                            seen_studied.add(key)
                            edges.append({
                                "id":     f"e{len(edges)}",
                                "source": person_nid,
                                "target": school_nid,
                                "type":   "studied_at",
                                "weight": 1,
                            })
                            n_studied_at += 1
                        break  # one school per person from wiki (first match wins)
        except Exception as exc:
            print(f"Warning: could not build studied_at edges: {exc}", file=sys.stderr)

    # Summary stats
    n_person = sum(1 for n in nodes.values() if n["type"] == "person")
    n_fund   = sum(1 for n in nodes.values() if n["type"] == "fund")
    n_inst   = sum(1 for e in edges if e["type"] == "institutional")
    n_film_e = sum(1 for e in edges if e["type"] == "film_funded")
    print(f"Network graph: {n_person} people, {n_fund} funds, {n_film_nodes} film nodes, "
          f"{n_school_nodes} school nodes, "
          f"{n_inst} institutional + {n_film_e} film_funded + "
          f"{n_collab} collaborated_with + {n_crew_credit} crew_credit + "
          f"{n_co_credited} co_credited + {n_reviewed} reviewed + "
          f"{n_studied_at} studied_at edges")

    return {
        "meta": {
            "generated_at":      datetime.now().isoformat(),
            "node_count":        len(nodes),
            "edge_count":        len(edges),
            "person_count":      n_person,
            "fund_count":        n_fund,
            "film_node_count":   n_film_nodes,
            "school_node_count": n_school_nodes,
            "inst_edges":        n_inst,
            "film_edges":        n_film_e,
            "collab_edges":      n_collab,
            "crew_credit_edges": n_crew_credit,
            "co_credited_edges": n_co_credited,
            "reviewed_edges":    n_reviewed,
            "studied_at_edges":  n_studied_at,
        },
        "nodes": list(nodes.values()),
        "edges": edges,
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", default=".", help="Directory for output files")
    parser.add_argument("--no-fuzzy", action="store_true", help="(ignored, kept for compat)")
    parser.add_argument("--fuzzy", action="store_true",
                        help="Run fuzzy name-matching to find near-duplicates (slow — O(n²))")
    parser.add_argument("--fuzzy-threshold", type=int, default=FUZZY_THRESHOLD,
                        help=f"Fuzzy match threshold (default {FUZZY_THRESHOLD})")
    parser.add_argument("--export-excel", action="store_true",
                        help="Write connections_report.xlsx in the output directory")
    parser.add_argument("--phase", choices=["resolve", "render", "all"], default="all",
                        help="resolve = write entity_registry.json + ambiguous_pairs.json only "
                             "(does not read movies_db.json); render = write "
                             "connections_report.html + network_graph.json from a FRESH "
                             "movies_db.json; all = both (default). Splitting these breaks the "
                             "resolve↔movies_db cycle — see docs/plan_pipeline_refactor.md.")
    args = parser.parse_args()
    do_resolve = args.phase in ("resolve", "all")
    do_render  = args.phase in ("render", "all")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    use_fuzzy = args.fuzzy
    if use_fuzzy and not HAS_RAPIDFUZZ:
        print("Warning: rapidfuzz not installed, skipping fuzzy matching. "
              "Run: pip install rapidfuzz", file=sys.stderr)
        use_fuzzy = False

    # Load wiki enrichment (optional — silently skipped if file absent)
    wiki_enrichment: dict = {}
    _wiki_path = Path("enriched/wiki_persons.json")
    if _wiki_path.exists():
        try:
            wiki_enrichment = json.loads(_wiki_path.read_text(encoding="utf-8"))
            n_wiki = sum(1 for v in wiki_enrichment.values() if v and v.get("wiki_url"))
            print(f"Loaded wiki enrichment: {len(wiki_enrichment)} cached, {n_wiki} with hits")
        except Exception as e:
            print(f"Warning: could not load wiki enrichment: {e}", file=sys.stderr)

    # Load — read all JSONL files exactly once; reuse in-memory cache for all phases
    print("Loading mentions...")
    _cache = _load_raw_records(MENTIONS_GLOB)
    people_raw, orgs_raw = load_mentions(MENTIONS_GLOB, _cache=_cache)

    all_sources = sorted({m["source"] for m in people_raw + orgs_raw})
    print(f"Sources: {all_sources}")

    # Resolve
    print("Resolving people...")
    people_groups, _, people_ambiguous = resolve(people_raw, "p", use_fuzzy)
    print(f"  {len(people_raw):,} mentions → {len(people_groups):,} canonical people"
          f" · {len(people_ambiguous)} ambiguous pairs")

    print("Resolving organizations...")
    org_groups, _, org_ambiguous = resolve(orgs_raw, "o", use_fuzzy)
    print(f"  {len(orgs_raw):,} mentions → {len(org_groups):,} canonical orgs"
          f" · {len(org_ambiguous)} ambiguous pairs")

    all_ambiguous = sorted(people_ambiguous + org_ambiguous, key=lambda x: -x["score"])

    # Analyze connections
    print("Analyzing cross-source connections...")
    connections = analyze_connections(people_groups)
    print(f"  {len(connections['cross_source'])} cross-source people"
          f" · {len(connections['conflicts'])} role conflicts")

    print("Extracting film-level conflicts...")
    film_conflicts = extract_film_conflicts(MENTIONS_GLOB, _cache=_cache)

    print("Building URL → film map...")
    url_to_film = load_url_to_film(MENTIONS_GLOB, _cache=_cache)
    print(f"  {len(url_to_film):,} URLs mapped to films")

    print("Computing repeat winners...")
    repeat_winners = compute_repeat_winners(film_conflicts)
    print(f"  {len(repeat_winners)} repeat winners (3+ films)")

    # Build registry
    registry = build_registry(people_groups, org_groups)
    registry["generated_at"] = datetime.now().isoformat()
    # Expose minimal film_conflict data so T06 (circular-evidence check) has something to test
    registry["film_conflicts"] = [
        {
            "person":     fc["person"],
            "film_title": fc.get("film_title", ""),
            "film_url":   fc.get("film_url", ""),
            "inst_urls":  fc.get("inst_urls", []),
        }
        for fc in film_conflicts
    ]

    # ── Write outputs (gated by --phase) ─────────────────────────────────────
    # resolve phase: registry + ambiguous pairs only. Does NOT read movies_db.json
    # (generate_html / person_films is skipped), so movies_db can be (re)built next
    # without a circular dependency.
    if do_resolve:
        registry_path = out_dir / REGISTRY_FILE
        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)
        print(f"Wrote {registry_path}")

        pairs_path = out_dir / PAIRS_FILE
        with open(pairs_path, "w", encoding="utf-8") as f:
            json.dump(all_ambiguous, f, ensure_ascii=False, indent=2)
        print(f"Wrote {pairs_path} ({len(all_ambiguous)} pairs)")

    # render phase: report + graph, sourcing filmographies from the FRESH movies_db.json.
    if do_render:
        html_path = out_dir / HTML_FILE
        html = generate_html(connections, registry, all_ambiguous,
                             people_groups, org_groups, all_sources, film_conflicts,
                             url_to_film, repeat_winners,
                             wiki_enrichment=wiki_enrichment)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Wrote {html_path}")

        print("Building network graph...")
        graph = build_network_graph(film_conflicts, connections, registry,
                                    wiki_enrichment=wiki_enrichment)
        graph_path = out_dir / "network_graph.json"
        with open(graph_path, "w", encoding="utf-8") as f:
            json.dump(graph, f, ensure_ascii=False, indent=2)
        print(f"Wrote {graph_path}")

        if args.export_excel:
            excel_path = out_dir / "connections_report.xlsx"
            export_excel(connections, registry, film_conflicts, repeat_winners, excel_path)
            print(f"Wrote {excel_path}")

    # Quick console summary
    print("\n── Top cross-source people ──")
    for e in connections["cross_source"][:10]:
        srcs = ", ".join(sorted(e["roles_by_src"]))
        print(f"  {e['name']:30s} {e['sources']} srcs  {e['mentions']:3} mentions  [{srcs}]")

    if connections["conflicts"]:
        print("\n── Potential conflicts ──")
        for e in connections["conflicts"][:10]:
            print(f"  ⚑ {e['name']:30s}  {e['all_roles']}")


if __name__ == "__main__":
    main()
