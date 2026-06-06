#!/usr/bin/env python3
"""
Combine LLM + NER extraction results into a tiered confidence ranking.

Tier 1 — Both LLMs + NER all-3       (max trust, 3 independent signals)
Tier 2 — Both LLMs agree             (strong trust, 2 LLMs cross-check)
Tier 3 — Haiku + any NER model       (medium trust, LLM + statistical NER)
Tier 4 — Haiku only                  (lower trust, single model)
Skipped — GPT only / regex only / NER only without LLM corroboration

Relationships come exclusively from Haiku (GPT produces almost none).
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path


def load_inputs(llm_path, ner_path):
    llm = json.loads(Path(llm_path).read_text())
    ner = json.loads(Path(ner_path).read_text())
    return llm, ner


def build_ner_sets(ner):
    all3      = set(ner.get("found_by_all_3", []))
    ner_only  = set(ner.get("ner_only_missed_by_regex", []))  # DictaBERT/HeBERT
    # "any NER" = all3 + ner_only (excludes regex-only noise)
    any_ner   = all3 | ner_only
    return all3, any_ner


def collect_llm_people(llm_pages):
    """Return dicts: name -> list of haiku person records, name -> set of GPT names."""
    haiku_records = defaultdict(list)   # name -> [person dicts with roles/orgs/rels]
    gpt_names     = set()

    for page in llm_pages:
        url = page.get("url", "")

        for p in page.get("haiku", {}).get("people", []):
            if p.get("is_fictional"):
                continue
            name = p.get("name", "").strip()
            if not name:
                continue
            haiku_records[name].append({
                "roles":    p.get("roles", []),
                "orgs":     p.get("organizations", []),
                "conf":     p.get("confidence", ""),
                "evidence": p.get("evidence", ""),
                "url":      url,
            })

        for p in page.get("gpt4o_mini", {}).get("people", []):
            if p.get("is_fictional"):
                continue
            name = p.get("name", "").strip()
            if name:
                gpt_names.add(name)

    return haiku_records, gpt_names


def collect_haiku_relationships(llm_pages):
    rels = []
    for page in llm_pages:
        url = page.get("url", "")
        for r in page.get("haiku", {}).get("relationships", []):
            rels.append({**r, "url": url})
    return rels


def merge_person(name, records):
    """Merge multiple Haiku extractions of the same person across pages."""
    roles = []
    orgs  = []
    urls  = []
    evidence = []
    confs = []

    for r in records:
        roles.extend(r.get("roles", []))
        orgs.extend(r.get("orgs", []))
        if r.get("url"):
            urls.append(r["url"])
        if r.get("evidence"):
            evidence.append(r["evidence"])
        if r.get("conf"):
            confs.append(r["conf"])

    # Confidence: if any record is high, use high; else medium; else low
    conf_rank = {"high": 2, "medium": 1, "low": 0}
    best_conf = max(confs, key=lambda c: conf_rank.get(c, 0)) if confs else "low"

    return {
        "name":     name,
        "roles":    sorted(set(roles)),
        "orgs":     sorted(set(orgs)),
        "evidence": evidence[:2],       # keep up to 2 supporting sentences
        "urls":     list(set(urls)),
        "haiku_confidence": best_conf,
    }


def assign_tier(name, in_gpt, ner_all3, any_ner):
    in_ner_all3 = name in ner_all3
    in_any_ner  = name in any_ner

    if in_gpt and in_ner_all3:
        return 1, "Both LLMs + NER all-3"
    if in_gpt:
        return 2, "Both LLMs"
    if in_any_ner:
        return 3, "Haiku + NER"
    return 4, "Haiku only"


def run(llm_path, ner_path, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(exist_ok=True)

    llm, ner = load_inputs(llm_path, ner_path)
    ner_all3, any_ner = build_ner_sets(ner)
    haiku_records, gpt_names = collect_llm_people(llm["pages"])
    relationships = collect_haiku_relationships(llm["pages"])

    people = []
    for name, records in haiku_records.items():
        merged = merge_person(name, records)
        tier, reason = assign_tier(name, name in gpt_names, ner_all3, any_ner)
        merged["tier"]        = tier
        merged["tier_reason"] = reason
        people.append(merged)

    people.sort(key=lambda p: (p["tier"], p["name"]))

    # ── JSON output ──────────────────────────────────────────────────────────
    out_json = out_dir / "combined_people.json"
    out_json.write_text(
        json.dumps({"people": people, "relationships": relationships},
                   ensure_ascii=False, indent=2)
    )

    # ── CSV output ───────────────────────────────────────────────────────────
    out_csv = out_dir / "combined_people.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tier", "tier_reason", "name", "roles", "orgs",
                    "haiku_confidence", "evidence", "urls"])
        for p in people:
            w.writerow([
                p["tier"],
                p["tier_reason"],
                p["name"],
                "; ".join(p["roles"]),
                "; ".join(p["orgs"]),
                p["haiku_confidence"],
                " | ".join(p["evidence"]),
                "; ".join(p["urls"]),
            ])

    # ── Console summary ──────────────────────────────────────────────────────
    from collections import Counter
    tier_counts = Counter(p["tier"] for p in people)

    print("\n" + "=" * 60)
    print("COMBINED EXTRACTION RESULTS")
    print("=" * 60)
    print(f"Total unique people (Haiku-extracted): {len(people)}")
    print(f"Total relationships (Haiku):           {len(relationships)}")
    print()
    print("By tier:")
    tier_labels = {
        1: "Tier 1 — Both LLMs + NER all-3   (max trust)",
        2: "Tier 2 — Both LLMs               (strong trust)",
        3: "Tier 3 — Haiku + NER             (medium trust)",
        4: "Tier 4 — Haiku only              (lower trust)",
    }
    for t in [1, 2, 3, 4]:
        print(f"  {tier_labels[t]}: {tier_counts.get(t, 0)}")

    print()
    for tier in [1, 2, 3, 4]:
        tier_people = [p for p in people if p["tier"] == tier]
        if not tier_people:
            continue
        print(f"\n── Tier {tier}: {tier_labels[tier]} ──")
        for p in tier_people:
            roles = ", ".join(p["roles"]) or "—"
            orgs  = ", ".join(p["orgs"])  or "—"
            print(f"  {p['name']:<30} roles: {roles:<20} orgs: {orgs}")

    print(f"\n✅ JSON: {out_json}")
    print(f"✅ CSV:  {out_csv}")


if __name__ == "__main__":
    llm_path = sys.argv[1] if len(sys.argv) > 1 else "/Users/moran/output/llm_comparison.json"
    ner_path = sys.argv[2] if len(sys.argv) > 2 else "/Users/moran/projects/israeli-movies-ind/arava_film_fund/output/ner_comparison.json"
    out_dir  = sys.argv[3] if len(sys.argv) > 3 else "/Users/moran/output"

    run(llm_path, ner_path, out_dir)
