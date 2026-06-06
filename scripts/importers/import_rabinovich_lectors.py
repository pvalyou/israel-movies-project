#!/usr/bin/env python3
"""
import_rabinovich_lectors.py — Parse 5 Rabinovich Cinema Project lectors PDFs
(2013-2025) and write synthetic mentions.jsonl records to
out/rabinovich_cinema/mentions.jsonl.

PDFs are in sources/rabinovich_cinema/files/ and have per-character reversed
Hebrew tokens due to PDF RTL encoding.  To recover correct Hebrew:
  1. Reverse each whitespace-delimited token's characters.
  2. Reverse the order of tokens on each line.
  Year/number tokens are also character-reversed (e.g. '5102' → '2015').

Run: python3 import_rabinovich_lectors.py [--dry-run]
"""

import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("pdfplumber is required: pip install pdfplumber", file=sys.stderr)
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────

SOURCE_NAME = "rabinovich_cinema"
ORG_NAME_HE = "קרן רבינוביץ' לאמנויות - פרויקט הקולנוע"
ORG_NAME_EN = "Rabinowitz Foundation for the Arts – Cinema Project"

PDF_DIR = Path("sources/rabinovich_cinema/files")
OUT_JSONL = Path("out/rabinovich_cinema/mentions.jsonl")
CANONICAL_BASE = "manual://rabinovich_cinema/lectors-list"

# (path, years this PDF is authoritative for)
PDF_FILES = [
    (PDF_DIR / "rabinovich__lectors2015.pdf",      [2013, 2014, 2015]),
    (PDF_DIR / "rabinovich__lectors2017.pdf",      [2016, 2017]),
    (PDF_DIR / "rabinovich__lectors2023.pdf",      [2020, 2021, 2022, 2023]),
    (PDF_DIR / "rabinovich__lectors-2024.pdf",     [2024]),
    (PDF_DIR / "rabinovich__lectors-2025.pdf",     [2025]),
    # Official published list (Jan 2026, cinemaproject.org.il/download=29) —
    # cross-check source covering 2022-2025 in one consolidated document.
    (PDF_DIR / "rabinovich__lectors-2022-2025.pdf", [2022, 2023, 2024, 2025]),
]

# Known false positives: (name, year) pairs verified wrong via the official published PDF.
# These are removed after deduplication regardless of which source PDF produced them.
KNOWN_EXCLUSIONS: set[tuple[str, int]] = {
    ("קובי מזרחי", 2020),  # Official 2022-2025 PDF shows only 2023-2024
}

# Track keyword patterns → slug (applied to correctly decoded Hebrew lines)
# Note: some PDFs have OCR artifacts (e.g. 'סרטם' instead of 'סרטים', space
# in 'סרטי ם', 'איזוריים' instead of 'אזוריים').  Patterns are written to
# tolerate these.
TRACK_PATTERNS = [
    (re.compile(r"סרט[יםם]\s*ם?\s+עלילתיים\s+קצרים"),  "feature-short"),
    (re.compile(r"סרט[יםם]\s*ם?\s+עלילתיים"),           "feature"),
    (re.compile(r"סרטי\s+תעודה"),                         "documentary"),
    (re.compile(r"סרטי\s+סטודנטים"),                      "student"),
    (re.compile(r"סרט[יםם]\s*ם?\s+[אא]יזוריים"),         "regional"),
]

# ── Decoding ──────────────────────────────────────────────────────────────────

def decode_line(raw: str) -> str:
    """
    Decode a raw PDF line by reversing each token's characters AND reversing
    the token order.  Also unreverse any numeric tokens (years, ranges).
    """
    tokens = raw.split()
    decoded_tokens = []
    for tok in reversed(tokens):
        rev = tok[::-1]
        # If the token looks like a reversed number or range (e.g. '5102', '7102-3102')
        # re-reverse it to get the correct digits.
        if re.match(r"^[\d:\-]+$", rev):
            rev = tok  # original token already has digits the right way? No—reverse back
            # Actually: '5102' reversed = '2015', so rev is already correct.
            # We reversed tok → '5102'[::-1] = '2015'.  That IS correct.
            # Re-check: tok='5102', tok[::-1]='2015'. Yes, rev='2015' is correct.
        decoded_tokens.append(rev)
    return " ".join(decoded_tokens)


# ── Parsing helpers ───────────────────────────────────────────────────────────

def classify_track(text: str) -> str | None:
    """Return track slug if text contains a track keyword."""
    for pattern, slug in TRACK_PATTERNS:
        if pattern.search(text):
            return slug
    return None


def extract_names(raw: str) -> list[str]:
    """Split a comma-separated name segment into individual clean names."""
    raw = raw.rstrip(".").strip()
    # Remove any trailing/leading apostrophes from round labels that leaked in
    parts = re.split(r"[,،]", raw)
    names = []
    for p in parts:
        p = p.strip().strip(".'\"")
        # Remove bracketed notes
        p = re.sub(r"\([^)]*\)", "", p).strip()
        if len(p) < 2:
            continue
        # Must contain at least one Hebrew character
        if not re.search(r"[א-ת]", p):
            continue
        names.append(p)
    return names


def parse_year_token(token: str) -> int | None:
    """
    Return year if token is a (possibly colon-suffixed) 4-digit year, else None.
    Works on already-decoded tokens, so year digits are in correct order.
    """
    s = token.rstrip(":.'\"")
    if re.match(r"^\d{4}$", s):
        yr = int(s)
        if 2010 <= yr <= 2030:
            return yr
    return None


def parse_round_label(line: str) -> str | None:
    """
    Return round label ('א', 'ב', ...) if line is a round marker.
    Handles: "מועד א':" or "מועד א ':" (with space before apostrophe) or similar.
    """
    m = re.match(r"^מועד\s+([אבגד])\s*['.:]?\s*['.:]?\s*$", line.strip())
    if m:
        return m.group(1)
    return None


# ── Main PDF parser ───────────────────────────────────────────────────────────

def parse_pdf(path: Path, authoritative_years: list[int]) -> list[dict]:
    """
    Parse one PDF and return list of records:
      {year, track, round_label, names: [str]}
    Only returns records whose year is in authoritative_years.
    """
    auth_set = set(authoritative_years)
    decoded_lines: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for raw_line in text.splitlines():
                if not raw_line.strip():
                    continue
                decoded_lines.append(decode_line(raw_line))

    records: list[dict] = []
    current_year: int | None = None
    current_track: str | None = None
    current_round: str = "א"
    # Buffer for name continuation lines within the same track+round
    pending_names: list[str] = []

    def flush_pending():
        nonlocal pending_names
        if pending_names and current_year and current_track:
            if current_year in auth_set:
                records.append({
                    "year": current_year,
                    "track": current_track,
                    "round_label": current_round,
                    "names": list(pending_names),
                })
        pending_names = []

    for line in decoded_lines:
        line = line.strip()
        if not line:
            continue

        # Skip header line
        if "לקטורים שהועסקו על ידי הקרן" in line:
            continue

        # ── Year marker ──────────────────────────────────────────────────────
        # Handles standalone year lines: '2015:' or '2015' or '2023'
        # (bare digits, optional trailing colon/quote)
        stripped_yr = line.strip(":.'\" ")
        yr = parse_year_token(stripped_yr) if re.match(r"^[\d]+$", stripped_yr) else None
        if yr is not None:
            flush_pending()
            current_year = yr
            current_track = None
            current_round = "א"
            continue

        # ── Round marker ─────────────────────────────────────────────────────
        round_lbl = parse_round_label(line)
        if round_lbl is not None:
            flush_pending()
            current_round = round_lbl
            continue

        # ── Section header (with or without inline names) ────────────────────
        # Format: "תחום סרטי תעודה: name1, name2..."  or  "תחום סרטי תעודה:"
        # Also: "תחום סרטים עלילתיים באורך מלא (כל מועדי הקריאה): names"
        if line.startswith("תחום"):
            # Find the colon that separates header from names
            colon_idx = line.find(":")
            if colon_idx != -1:
                header_part = line[:colon_idx]
                names_part = line[colon_idx + 1:].strip()
                track = classify_track(header_part)
                if track is not None:
                    flush_pending()
                    current_track = track
                    # Check if it's the "(כל מועדי הקריאה)" all-rounds variant
                    if "כל מועדי" in header_part:
                        current_round = "כל"
                    if names_part:
                        names = extract_names(names_part)
                        if names:
                            pending_names.extend(names)
                    continue
            else:
                # Section header without colon (shouldn't normally occur but handle it)
                track = classify_track(line)
                if track is not None:
                    flush_pending()
                    current_track = track
                    continue

        # ── Round+names line (2015/2014/2013 format) ─────────────────────────
        # Format: "מועד קריאה א': name1, name2..."
        m = re.match(
            r"מועד קריאה\s+([אבגד'][\s'.]*)\s*[:\-]\s*(.+)$",
            line,
        )
        if m and current_year and current_track:
            flush_pending()
            letter = re.search(r"[אבגד]", m.group(1))
            current_round = letter.group(0) if letter else "א"
            names = extract_names(m.group(2))
            if names:
                pending_names.extend(names)
            continue

        # ── Continuation name line ────────────────────────────────────────────
        if current_year and current_track:
            # Check it looks like a name list (has Hebrew, possible commas)
            he_count = sum(1 for c in line if "א" <= c <= "ת")
            if he_count >= 3 and not line.startswith("תחום") and not line.startswith("מועד"):
                names = extract_names(line)
                if names:
                    pending_names.extend(names)

    flush_pending()
    return records


# ── Deduplication ─────────────────────────────────────────────────────────────

def deduplicate_records(records: list[dict]) -> list[dict]:
    """
    Merge records with the same (year, track, round_label).
    Within each group, deduplicate names while preserving order.
    Removes entries listed in KNOWN_EXCLUSIONS.
    """
    seen_names: dict[tuple, set] = {}
    merged: dict[tuple, dict] = {}
    for rec in records:
        key = (rec["year"], rec["track"], rec["round_label"])
        if key not in merged:
            seen_names[key] = set()
            merged[key] = {**rec, "names": []}
        for name in rec["names"]:
            if (name, rec["year"]) in KNOWN_EXCLUSIONS:
                continue
            if name not in seen_names[key]:
                seen_names[key].add(name)
                merged[key]["names"].append(name)
    return [v for v in merged.values() if v["names"]]


# ── JSONL record builder ──────────────────────────────────────────────────────

def make_canonical_url(year: int, track: str, round_label: str) -> str:
    round_slug = {"א": "alef", "ב": "bet", "ג": "gimel", "כל": "all"}.get(
        round_label, round_label
    )
    return f"{CANONICAL_BASE}/{year}/track-{track}/round-{round_slug}"


TRACK_NAME_HE = {
    "feature":       "סרטים עלילתיים באורך מלא",
    "feature-short": "סרטים עלילתיים קצרים",
    "documentary":   "סרטי תעודה",
    "student":       "סרטי סטודנטים",
    "regional":      "סרטים אזוריים",
}
ROUND_NAME_HE = {
    "א": "מועד א'",
    "ב": "מועד ב'",
    "ג": "מועד ג'",
    "כל": "כל מועדי הקריאה",
}


def make_entry(year: int, track: str, round_label: str, names: list[str], today: str) -> dict:
    url = make_canonical_url(year, track, round_label)
    chash = hashlib.md5(url.encode()).hexdigest()

    track_he = TRACK_NAME_HE.get(track, track)
    round_he = ROUND_NAME_HE.get(round_label, f"מועד {round_label}")
    notes = f"תחום {track_he} — {round_he} {year}"

    people: dict = {}
    roles: list = []
    for idx, name in enumerate(names, 1):
        pid = f"person_{idx:03d}"
        people[pid] = {
            "name_he": name,
            "name_en": None,
            "aliases": [],
            "primary_roles": ["lector"],
            "sources": [url],
        }
        roles.append({
            "id": f"role_{idx:03d}",
            "person_id": pid,
            "organization_id": "org_001",
            "role_type": "lector",
            "start_year": year,
            "end_year": year,
            "notes": notes,
            "sources": [url],
        })

    return {
        "file": f"rabinovich_cinema__lectors-{year}-{track}__manual.md",
        "url": url,
        "source_name": SOURCE_NAME,
        "status": "ok",
        "content_hash": chash,
        "content_length": 0,
        "filter_info": {"reason": "manual_canonical_source"},
        "truncated": False,
        "elapsed_sec": 0,
        "data": {
            "metadata": {
                "source_url": url,
                "source_name": SOURCE_NAME,
                "extraction_date": today,
                "language": "he",
                "canonical_source": "Rabinovich Cinema Project lectors PDFs (2013-2025)",
            },
            "entities": {
                "people": people,
                "organizations": {
                    "org_001": {
                        "name_he": ORG_NAME_HE,
                        "name_en": ORG_NAME_EN,
                        "type": "fund",
                        "subtype": "private_film_fund",
                        "sources": [url],
                    }
                },
                "films": {},
                "events": {},
            },
            "roles": roles,
            "relationships": [],
            "films": [],
        },
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    dry_run = "--dry-run" in sys.argv
    today = date.today().isoformat()

    all_records: list[dict] = []

    for pdf_path, auth_years in PDF_FILES:
        if not pdf_path.exists():
            print(f"WARNING: {pdf_path} not found — skipping", file=sys.stderr)
            continue
        print(f"Parsing {pdf_path.name} (years: {auth_years}) ...")
        records = parse_pdf(pdf_path, auth_years)
        by_year: dict[int, int] = {}
        for r in records:
            by_year[r["year"]] = by_year.get(r["year"], 0) + len(r["names"])
        for yr in sorted(by_year):
            print(f"  {yr}: {by_year[yr]} lector slots across "
                  f"{sum(1 for r in records if r['year'] == yr)} groups")
        all_records.extend(records)

    all_records = deduplicate_records(all_records)
    total_names = sum(len(r["names"]) for r in all_records)
    print(f"\nTotal after dedup: {len(all_records)} groups, {total_names} lector slots")

    # Year summary
    year_totals: dict[int, int] = {}
    for r in all_records:
        year_totals[r["year"]] = year_totals.get(r["year"], 0) + len(r["names"])
    for yr in sorted(year_totals):
        print(f"  {yr}: {year_totals[yr]} names")

    if dry_run:
        print("\n(dry run — nothing written)")
        for r in sorted(all_records, key=lambda x: (x["year"], x["track"], x["round_label"])):
            url = make_canonical_url(r["year"], r["track"], r["round_label"])
            sample = ", ".join(r["names"][:3])
            print(f"  {r['year']} | {r['track']:15s} | {r['round_label']} | "
                  f"{len(r['names'])} names | e.g. {sample}")
        return

    entries = [
        make_entry(r["year"], r["track"], r["round_label"], r["names"], today)
        for r in all_records
    ]

    # Read existing mentions.jsonl, strip previous manual lector entries
    existing_lines: list[str] = []
    if OUT_JSONL.exists():
        for line in OUT_JSONL.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("url", "").startswith(CANONICAL_BASE):
                    continue  # remove stale synthetic entries
            except Exception:
                pass
            existing_lines.append(line)

    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for line in existing_lines:
            f.write(line + "\n")
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(entries)} synthetic entries to {OUT_JSONL}")
    print(f"Preserved {len(existing_lines)} existing (scraped) entries")


if __name__ == "__main__":
    main()
