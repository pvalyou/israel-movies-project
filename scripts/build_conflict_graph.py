#!/usr/bin/env python3
"""
build_conflict_graph.py — Build conflict_graph.json from network_graph.json,
enriched with:
  - Film nodes + crew_credit edges (from data/movies_db.json)
  - Fund_recipient edges (from film.funds field, populated by match_fund_films.py)
  - School nodes + affiliated_with edges (from film_faculty_data/faculty_members.json)
  - Derived conflict edges (from data/derived_conflicts.json):
      critic_committee, family_conflict, collab_committee, festival_committee

Output: conflict_graph.json (used by graph.html)

Run: python3 scripts/build_conflict_graph.py
"""
import json, re, hashlib
from pathlib import Path
from collections import defaultdict

NETWORK_GRAPH     = Path("network_graph.json")
MOVIES_DB         = Path("data/movies_db.json")
FACULTY_DATA      = Path("film_faculty_data/faculty_members.json")
DERIVED_CONFLICTS = Path("data/derived_conflicts.json")
OUT               = Path("conflict_graph.json")

SCHOOL_IDS = {
    "sam_spiegel":         "school::sam_spiegel",
    "tel_aviv_university": "school::tel_aviv_university",
    "sapir_college":       "school::sapir_college",
    "minshar_art_school":  "school::minshar",
    "beit_berl_college":   "school::beit_berl",
    "tau_arts_admin":      "school::tel_aviv_university",
}
SCHOOL_LABELS = {
    "sam_spiegel":         "בית הספר סם שפיגל לקולנוע וטלוויזיה",
    "tel_aviv_university": "אוניברסיטת תל אביב – בית הספר לקולנוע וטלוויזיה",
    "sapir_college":       "מכללת ספיר – בית הספר לאמנויות הקול והמסך",
    "minshar_art_school":  "מנשר לאמנות – בית הספר לקולנוע וטלוויזיה",
    "beit_berl_college":   "מכללת בית ברל – המחלקה לאמנות",
    "tau_arts_admin":      "אוניברסיטת תל אביב – פקולטה לאמנויות (מינהל)",
}


def normalize_name(name: str) -> str:
    n = name.strip()
    n = re.sub(r'["\'"״׳׳״.,]', "", n)
    n = re.sub(r"[\-–—]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n




def strip_title(name: str) -> str:
    """Remove academic title prefixes like ד\"ר, פרופ', etc."""
    n = re.sub(r'^(ד["\'"״]ר|פרופ\'?\s*חבר|פרופ\'?|פרופסור\s*חבר|פרופסור)\s+', "", name.strip())
    # Strip trailing role suffix (e.g. "– מרצה")
    n = re.sub(r'\s*[–—-]\s*(עמית.*|עוזר.*|סגל.*|מרצה.*|פרופסור.*|בדימוס|אמריטוס)$', "", n)
    return normalize_name(n)


def extract_faculty_names(faculty_data: dict) -> dict[str, list[str]]:
    """Return {school_key: [normalized_name, ...]}"""
    result = {}
    for school_key, data in faculty_data.items():
        if school_key == "_meta":
            continue
        names = []
        for field, val in data.items():
            if not isinstance(val, list) or field in ("institution", "website"):
                continue
            for item in val:
                if isinstance(item, str):
                    raw = item
                elif isinstance(item, dict):
                    raw = item.get("name") or item.get("name_he") or ""
                else:
                    continue
                cleaned = strip_title(raw)
                if cleaned and len(cleaned) > 1:
                    names.append(cleaned)
        result[school_key] = list(dict.fromkeys(names))  # dedupe preserving order
    return result


def main():
    print("Loading network_graph.json...")
    g = json.loads(NETWORK_GRAPH.read_text(encoding="utf-8"))
    all_nodes = g["nodes"]
    all_edges = g["edges"]

    # ── Base conflict set ─────────────────────────────────────────────────────
    conflict_ids = {
        n["id"] for n in all_nodes
        if n.get("has_strict_conflict") or n.get("has_soft_conflict")
        or n.get("type") in ("fund", "school")
    }
    node_by_id = {n["id"]: n for n in all_nodes}
    nodes_out: dict[str, dict] = {nid: node_by_id[nid] for nid in conflict_ids}
    edges_out: list[dict] = []

    # Base edges (both endpoints in conflict set)
    seen_edges: set[str] = set()
    for e in all_edges:
        if e["source"] in conflict_ids and e["target"] in conflict_ids:
            key = f"{e['source']}|{e['target']}|{e['type']}"
            if key not in seen_edges:
                seen_edges.add(key)
                edges_out.append(e)

    # ── Normalize-name lookup for person nodes ────────────────────────────────
    norm_to_person_id: dict[str, str] = {}
    for nid, n in nodes_out.items():
        if n.get("type") == "person":
            norm_to_person_id[normalize_name(n["label"])] = nid

    # Also build norm→id for ALL persons in the full graph (for faculty matching)
    norm_to_all_person_id: dict[str, str] = {}
    for n in all_nodes:
        if n.get("type") == "person":
            norm_to_all_person_id[normalize_name(n["label"])] = n["id"]

    # ── School nodes + affiliated_with edges from faculty data ────────────────
    print("Loading faculty data...")
    faculty_raw = json.loads(FACULTY_DATA.read_text(encoding="utf-8"))
    faculty_by_school = extract_faculty_names(faculty_raw)

    n_faculty_matched = 0
    ei = len(edges_out)
    for school_key, names in faculty_by_school.items():
        school_id = SCHOOL_IDS.get(school_key)
        if not school_id:
            continue
        school_label = SCHOOL_LABELS.get(school_key, school_key)

        n_school_matched = 0
        for name in names:
            # Match against ALL persons in the graph (not just conflict persons)
            person_id = norm_to_all_person_id.get(name)
            if not person_id:
                continue
            # Ensure school node exists
            if school_id not in nodes_out:
                nodes_out[school_id] = {
                    "id":    school_id,
                    "label": school_label,
                    "type":  "school",
                    "group": "school",
                }
            # Add person node if not already present
            if person_id not in nodes_out:
                nodes_out[person_id] = node_by_id[person_id]

            key = f"{person_id}|{school_id}|affiliated_with"
            if key not in seen_edges:
                seen_edges.add(key)
                edges_out.append({
                    "id":     f"e_fac_{ei}",
                    "source": person_id,
                    "target": school_id,
                    "type":   "affiliated_with",
                    "roles":  ["faculty"],
                    "weight": 1,
                })
                ei += 1
                n_faculty_matched += 1
                n_school_matched += 1

        print(f"  {school_label}: {n_school_matched} faculty added")

    # ── Fund node IDs ────────────────────────────────────────────────────────
    fund_node_ids = {f"fund::{k}" for k in
                     ["nfct", "filmfund", "gesher", "makor", "rabinovich_cinema",
                      "jerusalem_film_fund", "fdoc"]}

    # ── Film nodes + crew_credit edges from movies_db ─────────────────────────
    print("Loading movies_db.json...")
    movies_db = json.loads(MOVIES_DB.read_text(encoding="utf-8"))

    n_films_added = 0
    n_crew_edges  = 0
    n_fund_edges  = 0
    for film in movies_db:
        crew = film.get("crew", [])
        if not crew:
            continue

        # Only link films where a CONFLICT person is in the crew
        matched_crew = []
        for c in crew:
            name = c.get("name_he", "")
            person_id = norm_to_person_id.get(normalize_name(name))
            if person_id:
                matched_crew.append((person_id, c.get("role", ""), c.get("role_he", "")))

        if not matched_crew:
            continue

        # Build film node id
        film_id = film.get("film_id")
        if not film_id:
            title_key = film.get("title_he") or film.get("title_en", "")
            film_id = "f_" + hashlib.md5(title_key.encode()).hexdigest()[:8]
        node_id = f"film::{film_id}"

        title = film.get("title_he") or film.get("title_en", "")
        year  = film.get("year")

        if node_id not in nodes_out:
            nodes_out[node_id] = {
                "id":    node_id,
                "label": f"{title}{' (' + str(year) + ')' if year else ''}",
                "type":  "film",
                "group": "film",
                "year":  year,
            }
            n_films_added += 1

        # Add crew_credit edges (person is already in nodes_out — they're conflict people)
        for (person_id, role_en, role_he) in matched_crew:
            key = f"{person_id}|{node_id}|crew_credit"
            if key not in seen_edges:
                seen_edges.add(key)
                edges_out.append({
                    "id":     f"e_crew_{ei}",
                    "source": person_id,
                    "target": node_id,
                    "type":   "crew_credit",
                    "roles":  [role_he or role_en],
                    "weight": 1,
                })
                ei += 1
                n_crew_edges += 1

        # Add fund_recipient edges: film → fund (only the known funds)
        for fund_key in (film.get("funds") or []):
            fnid = f"fund::{fund_key}"
            if fnid not in fund_node_ids:
                continue
            # Materialize the fund node if it isn't in the subgraph yet — funds with
            # no institutional edge weren't copied from the full graph, but the richer
            # movies_db now produces fund_recipient edges to them (else: dangling edge
            # → Cytoscape "nonexistent target" crash in precompute_layout.js).
            if fnid not in nodes_out:
                full_n = node_by_id.get(fnid)
                nodes_out[fnid] = full_n if full_n else {
                    "id": fnid, "label": fund_key, "type": "fund", "group": "fund"}
            key = f"{node_id}|{fnid}|fund_recipient"
            if key not in seen_edges:
                seen_edges.add(key)
                edges_out.append({
                    "id":     f"e_fund_{ei}",
                    "source": node_id,
                    "target": fnid,
                    "type":   "fund_recipient",
                    "weight": 1,
                })
                ei += 1
                n_fund_edges += 1

    # ── Derived conflicts ──────────────────────────────────────────────────────
    n_derived = 0
    if DERIVED_CONFLICTS.exists():
        print("Loading derived_conflicts.json...")
        dc = json.loads(DERIVED_CONFLICTS.read_text(encoding="utf-8"))

        # Helper: ensure a person node exists (add if absent)
        def _ensure_person(name: str) -> str:
            nid = f"person::{name}"
            if nid not in nodes_out:
                # Try to find in full graph
                full_n = node_by_id.get(nid)
                if full_n:
                    nodes_out[nid] = {**full_n, "has_derived_conflict": True}
                else:
                    nodes_out[nid] = {
                        "id":    nid, "label": name, "type": "person",
                        "group": "derived_conflict", "has_derived_conflict": True,
                    }
            else:
                nodes_out[nid]["has_derived_conflict"] = True
            return nid

        # Helper: ensure a fund node exists
        def _ensure_fund(key: str) -> str:
            nid = f"fund::{key}"
            if nid not in nodes_out:
                # try full graph
                full_n = node_by_id.get(nid)
                if full_n:
                    nodes_out[nid] = full_n
                else:
                    nodes_out[nid] = {"id": nid, "label": key, "type": "fund", "group": "fund"}
            return nid

        # 1. critic_committee — critic→fund edges
        for entry in dc.get("critic_committee", []):
            pnid = _ensure_person(entry["person"])
            for fund_key in entry.get("funds", []):
                fnid = _ensure_fund(fund_key)
                key  = f"{pnid}|{fnid}|critic_committee"
                if key not in seen_edges:
                    seen_edges.add(key)
                    edges_out.append({
                        "id":     f"e_dc_{ei}",
                        "source": pnid,
                        "target": fnid,
                        "type":   "critic_committee",
                        "roles":  entry.get("fund_roles", []),
                        "weight": 2,
                    })
                    ei += 1
                    n_derived += 1

        # 2. family_pairs — person↔person edges
        for entry in dc.get("family_pairs", []):
            a = _ensure_person(entry["person_a"])
            b = _ensure_person(entry["person_b"])
            key = f"{min(a,b)}|{max(a,b)}|family_conflict"
            if key not in seen_edges:
                seen_edges.add(key)
                shared = entry.get("shared_funds", [])
                edges_out.append({
                    "id":           f"e_dc_{ei}",
                    "source":       a,
                    "target":       b,
                    "type":         "family_conflict",
                    "shared_funds": shared,
                    "roles":        [f"שם משפחה משותף: {entry['shared_surname']}"],
                    "source_urls_a": entry.get("source_urls_a", []),
                    "source_urls_b": entry.get("source_urls_b", []),
                    "weight":       2,
                })
                ei += 1
                n_derived += 1

        # 3. collab_committee — person↔person edges (collaborated + same fund committee)
        for entry in dc.get("collab_committee", []):
            a = _ensure_person(entry["person_a"])
            b = _ensure_person(entry["person_b"])
            key = f"{min(a,b)}|{max(a,b)}|collab_committee|{entry['fund']}"
            if key not in seen_edges:
                seen_edges.add(key)
                edges_out.append({
                    "id":          f"e_dc_{ei}",
                    "source":      a,
                    "target":      b,
                    "type":        "collab_committee",
                    "fund":        entry["fund"],
                    "shared_films": entry.get("shared_films", []),
                    "roles":       [f"שותפים בוועדת {entry['fund']}"],
                    "weight":      1,
                })
                ei += 1
                n_derived += 1

        # 4. festival_committee — person→fund edges
        for entry in dc.get("festival_committee", []):
            pnid = _ensure_person(entry["person"])
            for fund_key in entry.get("funds", []):
                fnid = _ensure_fund(fund_key)
                key  = f"{pnid}|{fnid}|festival_committee"
                if key not in seen_edges:
                    seen_edges.add(key)
                    edges_out.append({
                        "id":     f"e_dc_{ei}",
                        "source": pnid,
                        "target": fnid,
                        "type":   "festival_committee",
                        "roles":  entry.get("festival_roles", []) + entry.get("fund_roles", []),
                        "weight": 1,
                    })
                    ei += 1
                    n_derived += 1

        # 5. lector_filmmaker — person→fund edges (revolving door: lector + filmmaker)
        for entry in dc.get("lector_filmmaker", []):
            pnid = _ensure_person(entry["person"])
            for fund_key in entry.get("funds", []):
                fnid = _ensure_fund(fund_key)
                key  = f"{pnid}|{fnid}|lector_filmmaker"
                if key not in seen_edges:
                    seen_edges.add(key)
                    edges_out.append({
                        "id":     f"e_dc_{ei}",
                        "source": pnid,
                        "target": fnid,
                        "type":   "lector_filmmaker",
                        "roles":  entry.get("fund_roles", []) + entry.get("filmmaker_roles", []),
                        "weight": 1,
                    })
                    ei += 1
                    n_derived += 1

        # 6. research_conflicts — person↔person edges with evidence & sources
        for entry in dc.get("research_conflicts", []):
            pa, pb = entry.get("person_a"), entry.get("person_b")
            if not pa:
                continue
            a = _ensure_person(pa)
            if not pb or pb == pa:
                if entry.get("fund"):
                    fnid = _ensure_fund(entry["fund"])
                    key = f"{a}|{fnid}|research_conflict|{entry.get('type','')}"
                    if key not in seen_edges:
                        seen_edges.add(key)
                        edges_out.append({
                            "id":          f"e_dc_{ei}",
                            "source":      a,
                            "target":      fnid,
                            "type":        "research_conflict",
                            "subtype":     entry.get("type"),
                            "evidence":    entry.get("evidence"),
                            "source_urls": entry.get("source_urls", []),
                            "confidence":  entry.get("confidence"),
                            "weight":      2,
                        })
                        ei += 1
                        n_derived += 1
                continue
            b = _ensure_person(pb)
            key = f"{min(a,b)}|{max(a,b)}|research_conflict|{entry.get('type','')}"
            if key not in seen_edges:
                seen_edges.add(key)
                edges_out.append({
                    "id":          f"e_dc_{ei}",
                    "source":      a,
                    "target":      b,
                    "type":        "research_conflict",
                    "subtype":     entry.get("type"),
                    "fund":        entry.get("fund"),
                    "evidence":    entry.get("evidence"),
                    "source_urls": entry.get("source_urls", []),
                    "confidence":  entry.get("confidence"),
                    "weight":      2,
                })
                ei += 1
                n_derived += 1

        print(f"  Derived conflict edges added: {n_derived}")
    else:
        print("  data/derived_conflicts.json not found — skipping derived conflicts")

    # ── Write output ──────────────────────────────────────────────────────────
    out_nodes = list(nodes_out.values())
    out = {"nodes": out_nodes, "edges": edges_out}
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    from collections import Counter
    ntypes = Counter(n["type"] for n in out_nodes)
    etypes = Counter(e["type"] for e in edges_out)
    size_kb = OUT.stat().st_size // 1024

    print(f"\n=== conflict_graph.json ===")
    print(f"Nodes: {len(out_nodes)} — {dict(ntypes)}")
    print(f"Edges: {len(edges_out)} — {dict(etypes)}")
    print(f"  Faculty matched: {n_faculty_matched}, Films added: {n_films_added}, Crew edges: {n_crew_edges}, Fund edges: {n_fund_edges}, Derived: {n_derived}")
    print(f"File: {size_kb} KB → {OUT}")


if __name__ == "__main__":
    main()
