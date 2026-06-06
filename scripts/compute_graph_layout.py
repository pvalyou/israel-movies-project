#!/usr/bin/env python3
"""Compute spring layout positions for network_graph.json.
Writes network_graph_viz.json with x, y coordinates on every node.

Run once before opening graph.html:
    python3 scripts/compute_graph_layout.py
"""
import json, math, time
import networkx as nx

INPUT  = "network_graph.json"
OUTPUT = "network_graph_viz.json"
SCALE  = 1000   # coordinate range fed to Sigma

# Only these edge types drive layout (co_credited/collaborated_with make a hairball)
LAYOUT_EDGE_TYPES = {"institutional", "film_funded", "crew_credit", "studied_at"}


def main():
    print(f"Loading {INPUT}...")
    g = json.load(open(INPUT, encoding="utf-8"))
    nodes, edges = g["nodes"], g["edges"]

    G = nx.Graph()
    for n in nodes:
        G.add_node(n["id"])
    for e in edges:
        if e["type"] in LAYOUT_EDGE_TYPES:
            G.add_edge(e["source"], e["target"], weight=min(e.get("weight", 1), 3))

    n = len(G)
    k = 8.0 / math.sqrt(n)   # larger k = more spread, less node overlap
    iters = 120
    print(f"Running spring layout: {n} nodes, {G.number_of_edges()} layout edges, {iters} iterations...")
    t0 = time.time()
    pos = nx.spring_layout(G, k=k, iterations=iters, seed=42, weight="weight")
    print(f"Layout done in {time.time() - t0:.1f}s")

    pos_map = {nid: (float(x) * SCALE, float(y) * SCALE) for nid, (x, y) in pos.items()}

    # Nodes not in any layout edge get a random scatter in the periphery
    rng = __import__("random"); rng.seed(99)
    for node in nodes:
        if node["id"] not in pos_map:
            pos_map[node["id"]] = (
                rng.uniform(-SCALE * 1.2, SCALE * 1.2),
                rng.uniform(-SCALE * 1.2, SCALE * 1.2),
            )

    for node in nodes:
        x, y = pos_map[node["id"]]
        node["x"] = round(x, 2)
        node["y"] = round(y, 2)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump({"nodes": nodes, "edges": edges}, f, ensure_ascii=False, separators=(",", ":"))

    size = __import__("os").path.getsize(OUTPUT) // 1024
    print(f"Written {OUTPUT} — {len(nodes)} nodes, {len(edges)} edges ({size} KB)")
    print(f"Open graph.html after starting a local server:")
    print(f"    python3 -m http.server 8000")
    print(f"    open http://localhost:8000/graph.html")


if __name__ == "__main__":
    main()
