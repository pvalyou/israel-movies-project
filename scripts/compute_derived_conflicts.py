#!/usr/bin/env python3
"""
compute_derived_conflicts.py — Derive higher-order conflicts from entity_registry.json
and network_graph.json.

Seven conflict categories:
  1. critic_committee    — Film critics who also vote on fund committees
  2. family_pairs        — Family pairs with overlapping institutional positions
  3. collab_committee    — Two filmmakers who worked together AND both sit on same fund committee
  4. multi_fund          — People serving on 3+ fund committees simultaneously
  5. faculty_committee   — Film school faculty who vote on the same funds their students apply to
  6. festival_committee  — Festival directors/programmers who also vote on fund committees
  7. exec_filmmaker      — Fund executives who are active filmmakers

Output: data/derived_conflicts.json

Run: python3 scripts/compute_derived_conflicts.py
"""
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime

REGISTRY_PATH = Path("entity_registry.json")
NETWORK_PATH  = Path("network_graph.json")
OUT_PATH      = Path("data/derived_conflicts.json")
RESEARCH_PATH = Path("data/new_conflicts_found.json")

RESEARCH_SKIP_TYPES = {
    "data_correction", "source_update", "staff_change", "duplicate_person",
    "family_source_update", "monopoly_source_update_2026",
    "ceo_spousal_business_conflict_detail_update", "systemic_reform_detail",
}


def load_research_conflicts(people: dict | None = None):
    if not RESEARCH_PATH.exists():
        return []
    # Build alias→canonical from registry people if provided
    alias_to_canonical: dict[str, str] = {}
    if people:
        import re
        def _nm(s):
            return re.sub(r"\s+", " ", (s or "").strip())
        for _p in people.values():
            can = _p.get("canonical_name_he")
            if not can:
                continue
            alias_to_canonical[_nm(can)] = can
            for al in _p.get("aliases", []) or []:
                alias_to_canonical[_nm(al)] = can

    def _resolve(name):
        if not name:
            return name
        return alias_to_canonical.get(name.strip(), name)

    raw = json.loads(RESEARCH_PATH.read_text(encoding="utf-8"))
    out = []
    for c in raw.get("conflicts", []):
        if c.get("type") in RESEARCH_SKIP_TYPES:
            continue
        urls = [c[k] for k in sorted(c.keys()) if k.startswith("source_url") and c.get(k)]
        out.append({
            "type":        c.get("type"),
            "person_a":    _resolve(c.get("person_a")),
            "person_b":    _resolve(c.get("person_b")),
            "fund":        c.get("fund"),
            "evidence":    c.get("evidence", ""),
            "source_urls": urls,
            "confidence":  c.get("confidence", "unknown"),
        })
    return out

FUND_KEYS = {
    "makor", "filmfund", "rabinovich_cinema", "jerusalem_film_fund",
    "nfct", "fdoc", "gesher", "festival_data",
}
FUND_ROLES = {"lector", "board_member", "chairperson", "committee_chair", "ceo",
              "fund_manager", "committee_member", "executive_director"}
CRITIC_ROLES    = {"critic", "journalist"}
FACULTY_ROLES   = {"faculty", "head_of_department", "department_head", "coordinator"}
FESTIVAL_ROLES  = {"festival_director", "artistic_director", "festival_programmer",
                   "programming_committee"}
FILMMAKER_ROLES = {"director", "producer", "screenwriter"}
EXEC_ROLES      = {"ceo", "fund_manager", "executive_director"}

SOURCE_LABELS = {
    "makor":               "קרן מקור",
    "rabinovich_cinema":   "קרן רבינוביץ' (קולנוע)",
    "jerusalem_film_fund": "קרן ירושלים לקולנוע",
    "filmfund":            "הקרן הישראלית לקולנוע",
    "gesher":              "קרן גשר",
    "nfct":                "הקרן החדשה לקולנוע וטלוויזיה",
    "fdoc":                "הפורום הדוקומנטרי",
    "festival_data":       "פסטיבלים",
    "sam_spiegel":         "סם שפיגל",
    "tel_aviv_university": "אוניברסיטת תל אביב",
    "sapir_college":       "מכללת ספיר",
    "minshar_art_school":  "מנשר לאמנות",
    "beit_berl_college":   "מכללת בית ברל",
    "film_schools":        "בתי ספר לקולנוע",
}


def fund_label(key: str) -> str:
    return SOURCE_LABELS.get(key, key.replace("_", " "))


def _fund_sources(person: dict) -> list[str]:
    return [k for k in person.get("sources", {}) if k in FUND_KEYS]


def _school_sources(person: dict) -> list[str]:
    school_keys = {"sam_spiegel", "tel_aviv_university", "sapir_college",
                   "minshar_art_school", "beit_berl_college", "film_schools"}
    return [k for k in person.get("sources", {}) if k in school_keys]


def build_person_fund_map(net: dict):
    """person_id → set of fund node ids where they have institutional edges."""
    person_funds: dict[str, set] = defaultdict(set)
    for e in net["edges"]:
        if e["type"] == "institutional":
            person_funds[e["source"]].add(e["target"])
    return person_funds


def build_collab_film_map(net: dict):
    """(person_a, person_b) → list of shared film titles (from co_credited edges)."""
    collab: dict[tuple, list] = defaultdict(list)
    for e in net["edges"]:
        if e["type"] == "co_credited":
            a, b = e["source"], e["target"]
            key = (min(a, b), max(a, b))
            title = e.get("film_title", "")
            if title and title not in collab[key]:
                collab[key].append(title)
    return collab


def compute_critic_committee(people: dict) -> list[dict]:
    results = []
    for pid, person in people.items():
        roles = set(person.get("all_roles", []))
        if not (roles & CRITIC_ROLES):
            continue
        fund_r = roles & FUND_ROLES
        if not fund_r:
            continue
        funds = _fund_sources(person)
        if not funds:
            continue
        results.append({
            "person":       person.get("canonical_name_he", ""),
            "funds":        funds,
            "fund_roles":   sorted(fund_r),
            "also_faculty": bool(roles & FACULTY_ROLES),
            "also_director": "director" in roles,
            "also_producer": "producer" in roles,
        })
    results.sort(key=lambda x: (-len(x["funds"]), x["person"]))
    return results


# Verified false positives — surname matches that are NOT actual family pairs.
# Add tuples of (canonical_name_he_a, canonical_name_he_b) to suppress.
FAMILY_PAIR_FALSE_POSITIVES: set[tuple[str, str]] = {
    ("נדב לפיד", "אסף לפיד"),         # confirmed: unrelated; Nadav's brother is Itamar Lapid
    ("נואית גבע", "נוית גבע"),         # duplicate entry of same person (spelling variant)
    ("אסתר גולדברג", "דנה גולדברג"),  # unverified; no family source found
    ("דנה גולדברג", "בועז גולדברג"),  # unverified; no family source found
    ("אסתר גולדברג", "בועז גולדברג"), # confirmed false positive: Boaz's father is Prof. Giora Goldberg (Bar-Ilan); unrelated to Esther
    ("אורית זמיר", "סמדר זמיר"),      # unverified; no family source found
}

# Manually confirmed family/spousal pairs not caught by surname algorithm.
# Each entry mirrors the compute_family_pairs output format.
FAMILY_PAIR_MANUAL: list[dict] = [
    {
        "person_a":       "דן גבע",
        "person_b":       "נואית גבע",
        "shared_surname": "גבע",
        "shared_funds":   ["nfct"],
        "funds_a":        ["nfct"],
        "funds_b":        ["nfct"],
        "fund_roles_a":   [],
        "fund_roles_b":   [],
        "verified":       True,
        "relationship":   "spousal",
        "source_urls_a":  ["https://www.ynet.co.il/articles/0,7340,L-3036457,00.html"],
        "source_urls_b":  ["https://www.ynet.co.il/articles/0,7340,L-3036457,00.html"],
    },
    {
        "person_a":       "אורי ברבש",
        "person_b":       "בני ברבש",
        "shared_surname": "ברבש",
        "shared_funds":   ["filmfund"],
        "funds_a":        ["filmfund", "jerusalem_film_fund", "makor", "nfct", "rabinovich_cinema"],
        "funds_b":        ["filmfund", "gesher", "jerusalem_film_fund"],
        "fund_roles_a":   ["lector"],
        "fund_roles_b":   ["lector"],
        "verified":       True,
        "relationship":   "siblings",
        # Wikipedia confirms: "אחיו, בני ברבש". Both fund lectors + directors.
        # Together directed "גבעה 24" (2023, filmfund.org.il/Movie?movieId=508)
        # produced by Academy Chair אסף אמיר — compound 4-way institutional conflict.
        "source_urls_a":  ["https://he.wikipedia.org/wiki/%D7%90%D7%95%D7%A8%D7%99_%D7%91%D7%A8%D7%91%D7%A9"],
        "source_urls_b":  ["https://he.wikipedia.org/wiki/%D7%90%D7%95%D7%A8%D7%99_%D7%91%D7%A8%D7%91%D7%A9"],
    },
    {
        "person_a":       "מרגריטה לינטון",
        "person_b":       "יניב לינטון",
        "shared_surname": "לינטון",
        "shared_funds":   ["filmfund", "makor", "nfct", "rabinovich_cinema"],
        "funds_a":        ["filmfund", "makor", "nfct", "rabinovich_cinema"],
        "funds_b":        ["filmfund", "makor", "nfct", "rabinovich_cinema"],
        "fund_roles_a":   ["lector"],
        "fund_roles_b":   ["lector"],
        "verified":       True,
        "relationship":   "spousal",
        # Confirmed: met at Sam Spiegel Film School; 16-year relationship; two daughters.
        # Both serve as lectors at the SAME 4 funds simultaneously.
        # Yaniv was DoP on Margaritta's "בת האמן" (Ophir Award Best Short Documentary 2022).
        "source_urls_a":  ["https://www.ynet.co.il/laisha/article/s1c1ac411o"],
        "source_urls_b":  ["https://www.ynet.co.il/laisha/article/s1c1ac411o"],
    },
    {
        "person_a":       "נדב לפיד",
        "person_b":       "איתמר לפיד",
        "shared_surname": "לפיד",
        "shared_funds":   ["filmfund"],
        "funds_a":        ["filmfund", "rabinovich_cinema"],
        "funds_b":        ["filmfund"],
        "fund_roles_a":   ["lector"],
        "fund_roles_b":   [],
        "verified":       True,
        "relationship":   "siblings",
        "note":           "Nadav was lector Aug 2018; filmfund invested 100K NIS in Itamar's film 2021 — gap noted",
        "source_urls_a":  ["https://www.ynet.co.il/articles/0,7340,L-5277774,00.html"],
        "source_urls_b":  ["https://www.filmfund.org.il/Movie?movieId=17"],
    },
    {
        "person_a":       "אבי נשר",
        "person_b":       "תום נשר",
        "shared_surname": "נשר",
        "shared_funds":   ["rabinovich_cinema"],
        "funds_a":        ["filmfund", "gesher", "jerusalem_film_fund", "nfct", "rabinovich_cinema"],
        "funds_b":        ["rabinovich_cinema"],
        "fund_roles_a":   ["lector"],
        "fund_roles_b":   [],
        "verified":       True,
        "relationship":   "parent_child",
        # Avi Nesher is a lector at rabinovich_cinema while his daughter Tom Nesher
        # received a 1,000,000 NIS grant from the same fund for her film "הארוסה"
        "source_urls_a":  ["https://www.rabinovich.org.il/"],
        "source_urls_b":  ["https://www.rabinovich.org.il/"],
    },
]


def _best_source_urls(person: dict, fund_keys: set) -> list[str]:
    srcs = person.get("sources", {})
    urls = []
    for k in fund_keys:
        for u in srcs.get(k, []):
            if u.startswith("http") and u not in urls:
                urls.append(u)
    for k, ulist in srcs.items():
        for u in ulist:
            if u.startswith("http") and u not in urls:
                urls.append(u)
    return urls[:3]


def compute_family_pairs(people: dict, net: dict) -> list[dict]:
    person_funds = build_person_fund_map(net)

    # Build surname → list of people who have institutional edges
    surname_groups: dict[str, list] = defaultdict(list)
    for pid, person in people.items():
        name = person.get("canonical_name_he", "")
        parts = name.split()
        if len(parts) < 2:
            continue
        surname = parts[-1]
        nid = f"person::{name}"
        if nid in person_funds:
            surname_groups[surname].append({"name": name, "nid": nid, "person": person})

    results = []
    seen = set()
    for surname, members in surname_groups.items():
        if len(members) < 2:
            continue
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                key = tuple(sorted([a["name"], b["name"]]))
                if key in seen:
                    continue
                seen.add(key)
                # Skip confirmed false positives
                if key in FAMILY_PAIR_FALSE_POSITIVES or key[::-1] in FAMILY_PAIR_FALSE_POSITIVES:
                    continue
                funds_a = person_funds.get(a["nid"], set())
                funds_b = person_funds.get(b["nid"], set())
                shared_funds = sorted(
                    f.replace("fund::", "") for f in funds_a & funds_b
                )
                roles_a = sorted(set(a["person"].get("all_roles", [])) & FUND_ROLES)
                roles_b = sorted(set(b["person"].get("all_roles", [])) & FUND_ROLES)
                shared_fund_keys = set(shared_funds) if shared_funds else set()
                results.append({
                    "person_a":    a["name"],
                    "person_b":    b["name"],
                    "shared_surname": surname,
                    "shared_funds":   shared_funds,
                    "funds_a":     sorted(f.replace("fund::", "") for f in funds_a),
                    "funds_b":     sorted(f.replace("fund::", "") for f in funds_b),
                    "fund_roles_a": roles_a,
                    "fund_roles_b": roles_b,
                    "source_urls_a": _best_source_urls(a["person"], shared_fund_keys),
                    "source_urls_b": _best_source_urls(b["person"], shared_fund_keys),
                })

    # Prepend manually confirmed pairs (they're higher confidence)
    results = FAMILY_PAIR_MANUAL + results
    results.sort(key=lambda x: (-len(x["shared_funds"]), -int(x.get("verified", False)), x["person_a"]))
    return results


def compute_collab_committee(net: dict) -> list[dict]:
    person_funds = build_person_fund_map(net)
    collab_films = build_collab_film_map(net)

    fund_members: dict[str, set] = defaultdict(set)
    for nid, funds in person_funds.items():
        for f in funds:
            fund_members[f].add(nid)

    results = []
    seen = set()
    for fund, members in fund_members.items():
        member_list = list(members)
        for i in range(len(member_list)):
            for j in range(i + 1, len(member_list)):
                a, b = member_list[i], member_list[j]
                pair_key = (min(a, b), max(a, b))
                films = collab_films.get(pair_key, [])
                if not films:
                    continue
                result_key = (*pair_key, fund)
                if result_key in seen:
                    continue
                seen.add(result_key)
                results.append({
                    "person_a":    a.replace("person::", ""),
                    "person_b":    b.replace("person::", ""),
                    "fund":        fund.replace("fund::", ""),
                    "shared_films": films[:5],
                })

    results.sort(key=lambda x: (-len(x["shared_films"]), x["fund"]))
    return results


def compute_multi_fund(net: dict, min_funds: int = 2) -> list[dict]:
    person_funds = build_person_fund_map(net)
    results = []
    for nid, funds in person_funds.items():
        unique_funds = sorted(f.replace("fund::", "") for f in funds)
        if len(unique_funds) < min_funds:
            continue
        results.append({
            "person":     nid.replace("person::", ""),
            "funds":      unique_funds,
            "fund_count": len(unique_funds),
        })
    results.sort(key=lambda x: (-x["fund_count"], x["person"]))
    return results


def compute_faculty_committee(people: dict) -> list[dict]:
    results = []
    for pid, person in people.items():
        roles = set(person.get("all_roles", []))
        if not (roles & FACULTY_ROLES):
            continue
        fund_r = roles & FUND_ROLES
        if not fund_r:
            continue
        funds = _fund_sources(person)
        schools = _school_sources(person)
        if not funds or not schools:
            continue
        results.append({
            "person":     person.get("canonical_name_he", ""),
            "schools":    schools,
            "funds":      funds,
            "fund_roles": sorted(fund_r),
        })
    results.sort(key=lambda x: (-len(x["funds"]) - len(x["schools"]), x["person"]))
    return results


def compute_festival_committee(people: dict) -> list[dict]:
    results = []
    for pid, person in people.items():
        roles = set(person.get("all_roles", []))
        if not (roles & FESTIVAL_ROLES):
            continue
        fund_r = roles & FUND_ROLES
        if not fund_r:
            continue
        funds = _fund_sources(person)
        if not funds:
            continue
        results.append({
            "person":         person.get("canonical_name_he", ""),
            "festival_roles": sorted(roles & FESTIVAL_ROLES),
            "funds":          funds,
            "fund_roles":     sorted(fund_r),
        })
    results.sort(key=lambda x: (-len(x["funds"]), x["person"]))
    return results


# People confirmed to be administrators/academics where "director" role is
# organisational (artistic director, festival director) not filmmaker.
EXEC_FILMMAKER_EXCLUSIONS: set[str] = {
    "נועה רגב",     # Israeli Film Fund CEO; PhD academic + cinematheque director; NOT a filmmaker
    "אוראל טורנר",  # New NFCT CEO; 'filmmaker' tag is an extraction error — was production company staff
}


def compute_exec_filmmaker(people: dict) -> list[dict]:
    """A 'fund exec who is also a filmmaker' conflict ONLY at funds where the
    person actually holds an exec role. Using union all_roles would falsely
    attribute the exec role to other funds the person merely shows up at
    (e.g. as a lector). Per-source role data lives in roles_by_src."""
    results = []
    for pid, person in people.items():
        name = person.get("canonical_name_he", "")
        if name in EXEC_FILMMAKER_EXCLUSIONS:
            continue
        roles = set(person.get("all_roles", []))
        film_r = roles & FILMMAKER_ROLES
        if not film_r:
            continue
        # Find the specific funds where this person held an exec role.
        roles_by_src = person.get("roles_by_src") or {}
        exec_by_fund: dict[str, set] = {}
        for src, src_roles in roles_by_src.items():
            er = set(src_roles) & EXEC_ROLES
            if er and src in FUND_KEYS:
                exec_by_fund[src] = er
        if not exec_by_fund:
            continue
        # Union of exec roles across the relevant funds (display only).
        exec_r = set().union(*exec_by_fund.values())
        results.append({
            "person":          name,
            "exec_roles":      sorted(exec_r),
            "filmmaker_roles": sorted(film_r),
            "funds":           sorted(exec_by_fund.keys()),
        })
    results.sort(key=lambda x: (-len(x["funds"]), x["person"]))
    return results


def compute_lector_filmmaker(people: dict) -> list[dict]:
    """Lectors/board-members at film funds who are also active filmmakers.

    This captures the most common revolving-door conflict: a person who
    evaluates and approves funding applications while simultaneously being
    an active filmmaker eligible to receive that funding.  Excludes people
    already covered by critic_committee, faculty_committee, festival_committee,
    or exec_filmmaker (those have a more specific primary role).
    """
    already_covered_roles_non_exec = (
        CRITIC_ROLES | FACULTY_ROLES | FESTIVAL_ROLES
    )
    results = []
    for pid, person in people.items():
        roles = set(person.get("all_roles", []))
        # Must have a fund evaluation role
        fund_r = roles & FUND_ROLES
        if not fund_r:
            continue
        # Must have a filmmaker role
        film_r = roles & FILMMAKER_ROLES
        if not film_r:
            continue
        # Skip if covered by a more specific category (critic/faculty/festival).
        # For EXEC: only skip when the exec role is actually held AT A FUND
        # (i.e. would really match exec_filmmaker). Without this guard, anyone
        # who's a CEO somewhere outside FUND_KEYS (e.g. a regional film project)
        # gets silently dropped from lector_filmmaker too.
        if roles & already_covered_roles_non_exec:
            continue
        roles_by_src = person.get("roles_by_src") or {}
        exec_at_fund = any(
            (set(rs) & EXEC_ROLES) for s, rs in roles_by_src.items() if s in FUND_KEYS
        )
        if exec_at_fund:
            continue
        funds = _fund_sources(person)
        if len(funds) < 3:  # require 3+ funds — more specific revolving door
            continue
        results.append({
            "person":          person.get("canonical_name_he", ""),
            "fund_roles":      sorted(fund_r),
            "filmmaker_roles": sorted(film_r),
            "funds":           funds,
        })
    results.sort(key=lambda x: (-len(x["funds"]), x["person"]))
    return results


def main():
    print("Loading entity_registry.json...")
    reg  = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    people = reg.get("people", {})

    print("Loading network_graph.json...")
    net = json.loads(NETWORK_PATH.read_text(encoding="utf-8"))

    print("Computing derived conflicts...")

    critic_committee   = compute_critic_committee(people)
    family_pairs       = compute_family_pairs(people, net)
    collab_committee   = compute_collab_committee(net)
    multi_fund         = compute_multi_fund(net, min_funds=2)
    faculty_committee  = compute_faculty_committee(people)
    festival_committee = compute_festival_committee(people)
    exec_filmmaker     = compute_exec_filmmaker(people)
    lector_filmmaker   = compute_lector_filmmaker(people)
    research_conflicts = load_research_conflicts(people)

    out = {
        "generated_at":       datetime.now().isoformat(),
        "critic_committee":   critic_committee,
        "family_pairs":       family_pairs,
        "collab_committee":   collab_committee,
        "multi_fund":         multi_fund,
        "faculty_committee":  faculty_committee,
        "festival_committee": festival_committee,
        "exec_filmmaker":     exec_filmmaker,
        "lector_filmmaker":   lector_filmmaker,
        "research_conflicts": research_conflicts,
    }

    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== data/derived_conflicts.json ===")
    print(f"  critic_committee:   {len(critic_committee)}")
    print(f"  family_pairs:       {len(family_pairs)}")
    print(f"  collab_committee:   {len(collab_committee)}")
    print(f"  multi_fund (2+):    {len(multi_fund)}")
    print(f"  faculty_committee:  {len(faculty_committee)}")
    print(f"  festival_committee: {len(festival_committee)}")
    print(f"  exec_filmmaker:     {len(exec_filmmaker)}")
    print(f"  lector_filmmaker:   {len(lector_filmmaker)}")
    print(f"  research_conflicts: {len(research_conflicts)}")
    print(f"  → {OUT_PATH}")


if __name__ == "__main__":
    main()
