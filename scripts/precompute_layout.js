#!/usr/bin/env node
// Precompute fcose node positions headlessly so graph.html can use an instant
// `preset` layout instead of running fcose in the browser (~5s → instant).
// Params MUST match runLayout() in graph.html.
//
//   node scripts/precompute_layout.js
//
// Bakes {x, y} onto every node in conflict_graph.json (in place).

const fs = require("fs");
const path = require("path");
const cytoscape = require("cytoscape");
const fcose = require("cytoscape-fcose");
cytoscape.use(fcose);

const FILE = path.join(__dirname, "..", "conflict_graph.json");

function nodeSize(n, deg) {
  if (n.type === "fund") return 46;
  if (n.type === "school") return 34;
  if (n.type === "film") return 12;
  return Math.min(Math.max(10 + Math.sqrt(deg || 0) * 3.5, 12), 42);
}

function main() {
  const data = JSON.parse(fs.readFileSync(FILE, "utf-8"));

  const degreeMap = {};
  for (const e of data.edges) {
    degreeMap[e.source] = (degreeMap[e.source] || 0) + 1;
    degreeMap[e.target] = (degreeMap[e.target] || 0) + 1;
  }

  const els = [];
  for (const n of data.nodes) {
    const deg = n.type === "person" ? (degreeMap[n.id] || 0) : 0;
    els.push({ data: { id: n.id, ntype: n.type, size: nodeSize(n, deg) } });
  }
  const seen = new Set();
  let i = 0;
  for (const e of data.edges) {
    const key = e.source + "|" + e.target + "|" + e.type;
    if (seen.has(key)) continue;
    seen.add(key);
    els.push({ data: { id: "e" + (i++), source: e.source, target: e.target, etype: e.type } });
  }

  const cy = cytoscape({
    headless: true,
    elements: els,
    // fcose reads node bounding boxes for overlap avoidance — give it real sizes.
    style: [{ selector: "node", style: { width: "data(size)", height: "data(size)" } }],
  });

  console.log(`Running fcose: ${cy.nodes().length} nodes, ${cy.edges().length} edges...`);
  const t0 = Date.now();
  const layout = cy.layout({
    name: "fcose",
    quality: "proof",
    animate: false,
    randomize: true,
    nodeRepulsion: 22000,
    idealEdgeLength: e => (e.data("etype") === "institutional" ? 90 : 160),
    edgeElasticity: 0.35,
    gravity: 0.2,
    gravityRange: 3.8,
    nestingFactor: 0.1,
    numIter: 3000,
    nodeSeparation: 180,
    packComponents: true,
  });
  layout.run();
  console.log(`Layout done in ${((Date.now() - t0) / 1000).toFixed(1)}s`);

  // ── Hub separation pass ─────────────────────────────────────────────────────
  // The 8 funds are hyper-connected super-hubs, so fcose's gravity collapses them
  // all onto the centroid (min pair distance ~11px for 46px-wide nodes) and their
  // labels overlap into an unreadable pile. Schools attach to distinct faculty
  // clusters and are already well spread, so we treat them as FIXED obstacles and
  // only push the funds: each fund repels off every other fund (both move) and off
  // every school (fund moves only) until pairs clear a minimum distance. This
  // un-piles the funds without disturbing the organic people cloud.
  const MIN_FUND_FUND = 320;
  const MIN_FUND_SCHOOL = 270;
  const funds   = cy.nodes().filter(n => n.data("ntype") === "fund");
  const schools = cy.nodes().filter(n => n.data("ntype") === "school");
  for (let iter = 0; iter < 600; iter++) {
    let moved = 0;
    for (let a = 0; a < funds.length; a++) {
      for (let b = a + 1; b < funds.length; b++) {
        const na = funds[a], nb = funds[b];
        const pa = na.position(), pb = nb.position();
        const dx = pa.x - pb.x, dy = pa.y - pb.y;
        const dist = Math.hypot(dx, dy) || 0.01;
        if (dist < MIN_FUND_FUND) {
          const push = (MIN_FUND_FUND - dist) / 2;
          const ux = dx / dist, uy = dy / dist;
          na.position({ x: pa.x + ux * push, y: pa.y + uy * push });
          nb.position({ x: pb.x - ux * push, y: pb.y - uy * push });
          moved++;
        }
      }
      const pf = funds[a].position();
      for (let s = 0; s < schools.length; s++) {
        const ps = schools[s].position();
        const dx = pf.x - ps.x, dy = pf.y - ps.y;
        const dist = Math.hypot(dx, dy) || 0.01;
        if (dist < MIN_FUND_SCHOOL) {
          const push = MIN_FUND_SCHOOL - dist;            // only the fund moves
          funds[a].position({ x: pf.x + (dx / dist) * push, y: pf.y + (dy / dist) * push });
          moved++;
        }
      }
    }
    if (!moved) break;
  }
  {
    let mn = Infinity;
    for (let a = 0; a < funds.length; a++)
      for (let b = a + 1; b < funds.length; b++) {
        const pa = funds[a].position(), pb = funds[b].position();
        mn = Math.min(mn, Math.hypot(pa.x - pb.x, pa.y - pb.y));
      }
    console.log(`Hub separation done — min fund-fund distance now ${Math.round(mn)}px`);
  }

  const posMap = {};
  cy.nodes().forEach(n => {
    const p = n.position();
    posMap[n.id()] = [Math.round(p.x * 100) / 100, Math.round(p.y * 100) / 100];
  });

  for (const n of data.nodes) {
    const p = posMap[n.id];
    if (p) { n.x = p[0]; n.y = p[1]; }
  }

  fs.writeFileSync(FILE, JSON.stringify(data), "utf-8");
  const kb = Math.round(fs.statSync(FILE).size / 1024);
  console.log(`Baked x/y onto ${data.nodes.length} nodes → conflict_graph.json (${kb} KB)`);
}

main();
