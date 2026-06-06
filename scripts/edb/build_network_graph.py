#!/usr/bin/env python3
"""
Phase 5: Build enriched network_graph.json merging all data sources.

Fixes applied:
  1. Stub person nodes for all EDB crew (no dangling co_credited edges)
  2. Stub film nodes for reviewed films not in the 285 Israeli set
  3. Title-matched fund_recipient edges (skip when no match)

Usage: python3 build_network_graph.py
"""

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ── Helpers ──────────────────────────────────────────────────────────────────

def stable_id(prefix: str, name: str) -> str:
    h = hashlib.md5(name.strip().encode("utf-8")).hexdigest()[:8]
    return f"{prefix}_{h}"


def normalize_name(name: str) -> str:
    if not name:
        return ""
    n = name.strip()
    n = re.sub(r"^ד[\"״״]ר|פרופ['’׳]?|מר|גב['’׳]|עו[\"״״]ד|רו[\"״״]ח\s+", "", n)
    n = re.sub(r"[\"'״׳׳״.,]", "", n)
    n = re.sub(r"[\-–—]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def film_node_id(edb_id: str, title: str) -> str:
    if edb_id:
        return f"film::{edb_id}"
    return f"film::{stable_id('f', title)}"


def person_node_id(name: str, edb_id: str = "", registry_lookup: dict = None) -> str:
    if registry_lookup:
        norm = normalize_name(name)
        if norm in registry_lookup:
            return f"person::{registry_lookup[norm]}"
    if edb_id:
        return f"person::{edb_id}"
    return f"person::{name}"


# ── Bug A: Name dedup normalization ──────────────────────────────────────────

# Global lookup built from existing graph nodes + stub nodes as they're created.
# Key: normalized name (stripped of punctuation variants).
# Value: existing canonical node ID to reuse.
_norm_to_id: dict[str, str] = {}


def norm_for_dedup(name: str) -> str:
    """Strip punctuation variants that differ between edb and pipeline sources."""
    n = unicodedata.normalize("NFKC", name or "")
    n = re.sub(r"[''׳']", "", n)          # all apostrophe forms
    n = re.sub(r"[-־]", " ", n)            # hyphen/maqaf → space
    n = re.sub(r"\s+", " ", n).strip()
    return n


def init_dedup_index(existing_nodes: dict):
    """Seed _norm_to_id from the existing graph before loading new data."""
    _norm_to_id.clear()
    for nid, n in existing_nodes.items():
        if n.get("type") == "person" and n.get("label"):
            norm = norm_for_dedup(n["label"])
            if norm and norm not in _norm_to_id:
                _norm_to_id[norm] = nid


# ── Fix 1: Stub person node (with Bug A dedup) ───────────────────────────────

def ensure_person_node(nodes_dict: dict, name_he: str, edb_id: str = ""):
    norm = norm_for_dedup(name_he)
    # Bug A: if an existing node matches (by normalized name), reuse it
    if norm in _norm_to_id:
        return _norm_to_id[norm]

    node_id = f"person::{name_he}"
    if node_id not in nodes_dict:
        nodes_dict[node_id] = {
            "id": node_id,
            "label": name_he,
            "type": "person",
            "group": "person",
            "edb_id": edb_id or "",
            "has_strict_conflict": False,
            "has_soft_conflict": False,
            "source_count": 0,
            "roles": [],
        }
        _norm_to_id[norm] = node_id
    return node_id


# ── Fix 2: Stub film node ───────────────────────────────────────────────────

FILM_NODE_DEFAULTS = {
    "id": "", "label": "", "type": "film", "group": "film",
    "year": None, "edb_id": "", "edb_url": "", "is_short": False,
}


def ensure_film_node(nodes_dict: dict, edb_film_id: str, title: str = "", year: int = None):
    node_id = f"film::{edb_film_id}"
    if node_id not in nodes_dict:
        node = dict(FILM_NODE_DEFAULTS)
        node["id"] = node_id
        node["label"] = title or edb_film_id
        node["year"] = year
        node["edb_id"] = edb_film_id
        node["edb_url"] = f"https://www.edb.co.il/title/{edb_film_id}/"
        nodes_dict[node_id] = node
    else:
        # Update empty fields in existing node
        existing = nodes_dict[node_id]
        for k, v in {"label": title, "year": year, "edb_id": edb_film_id}.items():
            if v is not None and (not existing.get(k)):
                existing[k] = v
    return node_id


# ── Title normalization for Fix 3 ────────────────────────────────────────────

def norm_film_title(t: str) -> str:
    t = unicodedata.normalize("NFKC", t or "")
    t = re.sub(r"[\"'״׳.,!?]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def load_edb_persons(path: str = "data/edb/edb_persons.json") -> tuple[dict, list]:
    """Load Phase 3 person pages → add actor roles to person nodes + collaborator edges."""
    nodes = {}
    edges = []
    seen_collab_edges = set()

    if not Path(path).exists():
        print(f"  WARNING: {path} not found")
        return nodes, []

    with open(path, encoding="utf-8") as f:
        persons = json.load(f)

    # First pass: create/update person nodes
    actors_added = 0
    roles_updated = 0
    for p in persons:
        name_he = p.get("name_he", "")
        edb_id = p.get("edb_id", "")
        if not name_he:
            continue
        pid = ensure_person_node(nodes, name_he, edb_id)

        # Collect unique roles from filmography
        person_roles = set()
        for film in p.get("films", []):
            role = film.get("role", "")
            if role:
                person_roles.add(role)

        node = nodes.get(pid)
        if node:
            existing_roles = set(node.get("roles", []))
            new_roles = person_roles - existing_roles
            if new_roles:
                if not node.get("roles"):
                    node["roles"] = sorted(person_roles)
                else:
                    node["roles"] = sorted(existing_roles | person_roles)
                roles_updated += 1

            # Track actor count
            if "actor" in person_roles and "actor" not in existing_roles:
                actors_added += 1

    # Second pass: collaborator edges
    for p in persons:
        name_he = p.get("name_he", "")
        if not name_he:
            continue
        pid = ensure_person_node(nodes, name_he, p.get("edb_id", ""))

        for collab_id in p.get("collaborators", []):
            # Find collaborator's node (by edb_id in person data)
            collab_name = ""
            for cp in persons:
                if cp.get("edb_id") == collab_id:
                    collab_name = cp.get("name_he", "")
                    break
            if not collab_name:
                continue

            cpid = ensure_person_node(nodes, collab_name, collab_id)

            # Normalize order
            a_id, b_id = sorted([pid, cpid])
            collab_key = (a_id, b_id)
            if collab_key in seen_collab_edges:
                continue
            seen_collab_edges.add(collab_key)

            edges.append({
                "id": f"e_col_{len(seen_collab_edges)}",
                "source": a_id,
                "target": b_id,
                "type": "collaborated_with",
                "weight": 1,
            })

    person_count = sum(1 for n in nodes.values() if n.get("type") == "person")
    film_count = sum(1 for n in nodes.values() if n.get("type") == "film")
    print(f"  EDB persons: {person_count} person + {film_count} film nodes, "
          f"{actors_added} actors added, {roles_updated} roles updated, "
          f"{len(edges)} collaborator edges")
    return nodes, edges


# ── Load existing graph ──────────────────────────────────────────────────────

def load_existing_graph_only_original_edges(path: str = "network_graph.json") -> dict:
    """Load only the original node/edge types from the existing graph.
    Discards co_credited, reviewed, fund_recipient — those will be rebuilt fresh.
    Also removes leftover stub nodes with no roles and no edges.
    Also removes edb-ID-keyed nodes (e.g. person::n0013128) which are duplicates from
    a previous broken build."""
    if not Path(path).exists():
        return {"nodes": [], "edges": []}
    with open(path, encoding="utf-8") as f:
        g = json.load(f)

    ORIGINAL_EDGE_TYPES = {"institutional", "film_funded"}
    clean_edges = [e for e in g.get("edges", []) if e["type"] in ORIGINAL_EDGE_TYPES]

    # Build set of node IDs referenced by kept edges
    used_ids = {e["source"] for e in clean_edges} | {e["target"] for e in clean_edges}

    # Drop person nodes that:
    #  - Are keyed by edb numeric ID (person::n...)
    #  - Have no roles AND no edges
    # Keep: fund nodes, film nodes, person nodes referenced by kept edges
    EDB_ID_NODE = re.compile(r"^person::n\d+$")
    clean_nodes = []
    stripped = 0
    for n in g.get("nodes", []):
        nid = n.get("id", "")
        ntype = n.get("type", "")
        # Always keep fund and film nodes
        if ntype in ("fund", "film"):
            clean_nodes.append(n)
            used_ids.add(nid)
        elif nid in used_ids:
            clean_nodes.append(n)
        elif EDB_ID_NODE.match(nid):
            stripped += 1  # old buggy critic stub
        elif ntype == "person" and not n.get("roles") and n.get("source_count", 0) == 0:
            stripped += 1  # leftover stub from previous run
        else:
            clean_nodes.append(n)

    print(f"  Stripped {len(g['edges']) - len(clean_edges)} edges (non-original types), "
          f"keeping {len(clean_edges)} (institutional + film_funded)")
    if stripped:
        print(f"  Stripped {stripped} orphan/stub/edb-id nodes")
    g["nodes"] = clean_nodes
    g["edges"] = clean_edges
    return g


def build_registry_lookup(path: str = "entity_registry.json") -> dict:
    if not Path(path).exists():
        return {}
    with open(path, encoding="utf-8") as f:
        registry = json.load(f)
    lookup = {}
    for pid, info in registry.get("people", {}).items():
        canonical = info.get("canonical_name_he", "")
        if canonical:
            lookup[normalize_name(canonical)] = canonical
    return lookup


# ── Load EDB film data (Fix 1 applied) ────────────────────────────────────────

def load_edb_films(path: str = "out/edb/mentions.jsonl",
                  registry_lookup: dict = None) -> tuple[dict, list, list]:
    """Load film nodes and co_credited edges. If movies_db.json exists,
    use it as primary source (richer metadata, multi-source).
    Otherwise fall back to EDB mentions."""
    nodes = {}
    edges = []
    seen_films = set()
    seen_co = set()

    # Prefer movies_db if available
    movies_db_path = "data/movies_db.json"
    if Path(movies_db_path).exists():
        path = movies_db_path
        print(f"  Using movies_db.json for richer film data")
    elif not Path(path).exists():
        print(f"  WARNING: {path} not found")
        return nodes, [], []

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
        if isinstance(data, list):
            films = data
        else:
            films = data.get("films", data.get("all", []))

    for film in films:
        if not film:
            continue

        # movies_db format uses different field names
        if "crew" in film and isinstance(film["crew"], list) and film["crew"]:
            # movies_db format
            title = film.get("title_he", "")
            edb_ids = film.get("edb_ids", [])
            edb_id = edb_ids[0] if edb_ids else ""
            year = film.get("year")
            is_short = film.get("is_short", False)
            crew_raw = film.get("crew", [])
        else:
            # old EDB format
            title = film.get("title_he", film.get("title", ""))
            edb_id = film.get("edb_id", film.get("film_id", ""))
            year = film.get("year")
            is_short = film.get("is_short", False)
            crew_raw = film.get("crew", [])

            # Handle nested film_001
            films_nested = film.get("films", {})
            if films_nested:
                fdata = list(films_nested.values())[0] if films_nested else {}
                title = title or fdata.get("title_he", "")
                edb_id = edb_id or fdata.get("edb_id", "")
                year = year or fdata.get("year")
                is_short = is_short or fdata.get("is_short", False)
                crew_raw = crew_raw or fdata.get("crew", [])

        if not title or not crew_raw:
            continue

        fid = film_node_id(edb_id, title)
        if fid in seen_films:
            continue
        seen_films.add(fid)

        nodes[fid] = {
            "id": fid,
            "label": title,
            "type": "film",
            "group": "film" if not is_short else "short_film",
            "year": int(year) if year else None,
            "edb_id": edb_id,
            "edb_url": f"https://www.edb.co.il/title/{edb_id}/" if edb_id else None,
            "is_short": is_short,
        }

        # Create stub person nodes for all crew members
        crew_nodes = []
        for c in crew_raw:
            cname = c.get("name_he", "")
            if not cname:
                continue
            cedb = c.get("edb_id", "")
            pid = ensure_person_node(nodes, cname, cedb)
            crew_nodes.append({"id": pid, "name": cname, "role": c.get("role", "other")})

        # Co_credited edges between all crew pairs
        for i, ca in enumerate(crew_nodes):
            for cb in crew_nodes[i + 1:]:
                a_id, b_id = sorted([ca["id"], cb["id"]])
                co_key = (a_id, b_id, fid)
                if co_key in seen_co:
                    continue
                seen_co.add(co_key)
                edges.append({
                    "id": f"e_cc_{len(seen_co)}",
                    "source": ca["id"],
                    "target": cb["id"],
                    "type": "co_credited",
                    "film_id": fid,
                    "film_title": title,
                    "year": int(year) if year else None,
                    "role_a": ca["role"],
                    "role_b": cb["role"],
                    "weight": 1,
                })

    film_node_count = sum(1 for n in nodes.values() if n.get("type") == "film")
    person_stub_count = sum(1 for n in nodes.values() if n.get("type") == "person")
    print(f"  EDB films: {film_node_count} film + {person_stub_count} person nodes, "
          f"{len(edges)} co_credited edges")
    return nodes, [], edges  # return nodes dict, empty extra, edges list


# ── Load EDB critics data (Fix 2 applied) ────────────────────────────────────

def load_edb_critics(blog_path: str = "data/edb/edb_blog_reviews.json",
                     mentions_path: str = "out/edb_critics/mentions.jsonl") -> tuple[dict, list]:
    """Load critic nodes and reviewed edges. Creates stub film nodes for reviewed films.

    Bug B fix: Critics are keyed by name (person::cname), not edb ID.
    Blog film_meta stores title/year for reviewed film stubs.
    """
    nodes = {}
    edges = []
    seen_critics = set()
    seen_reviews = set()

    # Build a film-id → {title, year} map from blog checkpoint
    film_meta = {}
    if Path(blog_path).exists():
        with open(blog_path, encoding="utf-8") as f:
            blog_data = json.load(f)
        for d in blog_data:
            if not d.get("author_name") or not d.get("film_ids"):
                continue
            year = d.get("year")
            for fid in d["film_ids"]:
                if fid not in film_meta:
                    film_meta[fid] = {"title": "", "year": year}
        print(f"  Blog metadata: {len(film_meta)} unique films indexed")

    if not Path(mentions_path).exists():
        print(f"  WARNING: {mentions_path} not found")
        return nodes, []

    with open(mentions_path, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("status") != "ok":
                continue
            people = rec.get("data", {}).get("entities", {}).get("people", {})
            rels = rec.get("data", {}).get("relationships", [])

            for pk, pdata in people.items():
                if not pdata:
                    continue
                cname = pdata.get("name_he", "")
                if not cname:
                    continue

                # Bug B: Use name-based ID, not edb ID
                # Check dedup index first — ensure_person_node would, but we check early
                norm = norm_for_dedup(cname)
                if norm in _norm_to_id:
                    pid = _norm_to_id[norm]
                else:
                    pid = f"person::{cname}"

                if pid not in seen_critics:
                    seen_critics.add(pid)
                    nodes[pid] = {
                        "id": pid,
                        "label": cname,
                        "type": "person",
                        "group": "critic",
                        "gender": pdata.get("gender", "unknown"),
                        "edb_id": pdata.get("edb_id", ""),
                        "has_strict_conflict": False,
                        "has_soft_conflict": False,
                        "source_count": 0,
                        "roles": [],
                    }

                for rel in rels:
                    if rel.get("relationship_type") != "reviewed":
                        continue
                    target_fid = rel.get("target_id", "")
                    if not target_fid:
                        continue

                    film_nid = f"film::{target_fid}"

                    # Fix 2: Ensure film node exists (stub if not in the 285 Israeli set)
                    meta = film_meta.get(target_fid, {})
                    ensure_film_node(nodes, target_fid, meta.get("title", ""), meta.get("year"))

                    rev_key = (pid, film_nid)
                    if rev_key in seen_reviews:
                        continue
                    seen_reviews.add(rev_key)

                    edges.append({
                        "id": f"e_rv_{len(seen_reviews)}",
                        "source": pid,
                        "target": film_nid,
                        "type": "reviewed",
                        "outlet": rel.get("outlet", "edb"),
                        "year": rel.get("year"),
                        "weight": 1,
                    })

    critic_count = sum(1 for n in nodes.values() if n.get("group") == "critic")
    film_count = sum(1 for n in nodes.values() if n.get("type") == "film")
    print(f"  EDB critics: {critic_count} critic + {film_count} film nodes, "
          f"{len(edges)} reviewed edges")
    return nodes, edges


# ── Load funding amounts (Fix 3 applied) ─────────────────────────────────────

def load_funding(path: str = "out/funding_amounts/mentions.jsonl",
                 film_nodes: dict = None) -> list:
    """Load fund_recipient edges, matching to film nodes by Hebrew title."""
    edges = []
    seen_fr = set()

    if not Path(path).exists():
        print(f"  WARNING: {path} not found")
        return edges

    title_to_fid = {}
    if film_nodes:
        for nid, n in film_nodes.items():
            if n.get("type") == "film" and n.get("label"):
                title_to_fid[norm_film_title(n["label"])] = nid

    matched = 0
    skipped = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("status") != "ok":
                continue
            source_name = rec.get("source_name", "")
            fund_nid = f"fund::{source_name}"
            rels = rec.get("data", {}).get("relationships", [])
            films = rec.get("data", {}).get("entities", {}).get("films", {})
            url = rec.get("url", "")

            for rel in rels:
                amount = rel.get("amount_ils")
                if not amount:
                    continue

                # Try to find matching film
                source_fid = ""
                for fk, fdata in films.items():
                    ftitle = fdata.get("title_he", "")
                    if ftitle:
                        ntitle = norm_film_title(ftitle)
                        if ntitle in title_to_fid:
                            source_fid = title_to_fid[ntitle]
                            break

                # Fix 3: Skip if no film match (or empty source)
                if not source_fid:
                    skipped += 1
                    continue

                fr_key = (source_fid, fund_nid, amount)
                if fr_key in seen_fr:
                    continue
                seen_fr.add(fr_key)
                matched += 1

                edges.append({
                    "id": f"e_fr_{len(seen_fr)}",
                    "source": source_fid,
                    "target": fund_nid,
                    "type": "fund_recipient",
                    "year": rel.get("year"),
                    "amount_ils": amount,
                    "weight": 1,
                    "source_url": url,
                })

    print(f"  Funding: {matched} fund_recipient edges (skipped {skipped} unmatched)")
    return edges


# ── Merge & deduplicate ──────────────────────────────────────────────────────

def merge_graphs(existing: dict, new_nodes: dict, new_edges: list) -> dict:
    existing_nodes = existing.get("nodes", [])
    existing_edges = existing.get("edges", [])

    node_map = {n["id"]: n for n in existing_nodes}
    edge_map = {(e.get("source"), e.get("target"), e.get("type")): e for e in existing_edges}

    for nid, n in new_nodes.items():
        if nid in node_map:
            existing_n = node_map[nid]
            for k, v in n.items():
                if k not in existing_n or existing_n.get(k) in (None, "", 0, []):
                    existing_n[k] = v
        else:
            node_map[nid] = n

    for e in new_edges:
        key = (e.get("source"), e.get("target"), e.get("type"))
        if key in edge_map:
            edge_map[key]["weight"] = edge_map[key].get("weight", 1) + 1
        else:
            edge_map[key] = e

    # Remove edges whose source or target doesn't exist
    all_ids = set(node_map.keys())
    clean_edges = [e for e in edge_map.values() if e["source"] in all_ids and e["target"] in all_ids]
    dropped = len(edge_map) - len(clean_edges)
    if dropped:
        print(f"\n  Dropped {dropped} dangling edges (source/target not in graph)")

    merged = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "node_count": len(node_map),
            "edge_count": len(clean_edges),
            "person_count": sum(1 for n in node_map.values() if n.get("type") == "person"),
            "fund_count": sum(1 for n in node_map.values() if n.get("type") == "fund"),
            "film_count": sum(1 for n in node_map.values() if n.get("type") == "film"),
            "inst_edges": sum(1 for e in clean_edges if e.get("type") == "institutional"),
            "film_edges": sum(1 for e in clean_edges if e.get("type") == "film_funded"),
            "co_credited_edges": sum(1 for e in clean_edges if e.get("type") == "co_credited"),
            "reviewed_edges": sum(1 for e in clean_edges if e.get("type") == "reviewed"),
            "fund_recipient_edges": sum(1 for e in clean_edges if e.get("type") == "fund_recipient"),
            "collaborated_with_edges": sum(1 for e in clean_edges if e.get("type") == "collaborated_with"),
        },
        "nodes": list(node_map.values()),
        "edges": clean_edges,
    }
    return merged


# ── Stats + verification ─────────────────────────────────────────────────────

def print_stats(graph: dict):
    meta = graph["meta"]
    print(f"\n{'='*60}")
    print(f"Network Graph Summary")
    print(f"{'='*60}")
    print(f"  Total nodes: {meta['node_count']}")
    print(f"    persons: {meta['person_count']}")
    print(f"    funds:   {meta['fund_count']}")
    print(f"    films:   {meta.get('film_count', 0)}")
    print(f"  Total edges: {meta['edge_count']}")
    print(f"    institutional:    {meta['inst_edges']}")
    print(f"    film_funded:      {meta['film_edges']}")
    print(f"    co_credited:      {meta.get('co_credited_edges', 0)}")
    print(f"    reviewed:         {meta.get('reviewed_edges', 0)}")
    print(f"    fund_recipient:   {meta.get('fund_recipient_edges', 0)}")
    print(f"    collaborated_with:{meta.get('collaborated_with_edges', 0)}")


def verify(graph: dict):
    node_ids = {n["id"] for n in graph["nodes"]}
    dangling = [e for e in graph["edges"] if e["source"] not in node_ids or e["target"] not in node_ids]
    if dangling:
        by_type = defaultdict(int)
        for e in dangling:
            by_type[e["type"]] += 1
        print(f"\n  VERIFY FAILED: {len(dangling)} dangling edges ({dict(by_type)})")
        return False

    persons = [n for n in graph["nodes"] if n["type"] == "person"]
    cc = [e for e in graph["edges"] if e["type"] == "co_credited"]
    films = [n for n in graph["nodes"] if n["type"] == "film"]

    print(f"\n  VERIFY PASSED: 0 dangling edges")
    print(f"    {len(persons)} persons, {len(films)} films, {len(cc)} co_credited")
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=== Phase 5: Building Enriched Network Graph ===\n")

    registry_lookup = build_registry_lookup()
    print(f"Registry: {len(registry_lookup)} canonical names\n")

    print("Loading existing graph (original edge types only)...")
    existing = load_existing_graph_only_original_edges()
    print(f"  Existing: {len(existing.get('nodes',[]))} nodes, {len(existing.get('edges',[]))} edges")

    # Bug A: Seed dedup index from existing person nodes before loading new data
    init_dedup_index({n["id"]: n for n in existing.get("nodes", [])})
    print(f"  Dedup index: {len(_norm_to_id)} normalized names\n")

    print("\nLoading new data...")
    edb_nodes, _, co_edges = load_edb_films(registry_lookup=registry_lookup)
    critic_nodes, critic_edges = load_edb_critics()
    person_nodes, collab_edges = load_edb_persons()

    # Merge all film nodes first (needed for funding title matching)
    all_film_nodes = dict(edb_nodes)
    for source in [critic_nodes, person_nodes]:
        for nid, n in source.items():
            if n.get("type") == "film" and nid not in all_film_nodes:
                all_film_nodes[nid] = n
    all_person_nodes = dict(edb_nodes)
    for source in [critic_nodes, person_nodes]:
        for nid, n in source.items():
            if n.get("type") == "person" and nid not in all_person_nodes:
                all_person_nodes[nid] = n

    all_nodes = {**all_person_nodes, **all_film_nodes}
    fund_edges = load_funding(film_nodes=all_film_nodes)

    all_new_edges = co_edges + critic_edges + collab_edges + fund_edges
    print(f"\n  New total: {len(all_nodes)} nodes, {len(all_new_edges)} edges")

    print("\nMerging...")
    graph = merge_graphs(existing, all_nodes, all_new_edges)

    output_path = "network_graph.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {output_path}")

    print_stats(graph)
    verify(graph)


if __name__ == "__main__":
    main()