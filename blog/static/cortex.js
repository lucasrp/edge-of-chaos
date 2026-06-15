// cortex.js — the Cytoscape island. Draws the whole-Cortex {nodes, edges} payload as a dark,
// force-directed constellation centered on space-0, trust-weighted by brightness. Read-only:
// pan / zoom / click a node to inspect it. Loaded ONLY on /cortex (a JS island, not the app shell).
(function () {
  "use strict";

  var dataEl = document.getElementById("cortex-data");
  var mount = document.getElementById("cortex");
  if (!dataEl || !mount || typeof cytoscape === "undefined") return;

  var payload;
  try {
    payload = JSON.parse(dataEl.textContent);
  } catch (e) {
    mount.textContent = "cortex: payload ilegível.";
    return;
  }

  // Brightness per trust tier — space-0 brightest, asserted spine bright, extracted dim,
  // Episodic faintest (background haze). Subtractive legibility via opacity, not removal.
  var TIER = {
    space0:    { opacity: 1.00, size: 46, color: "#cfe0ff", border: "#7aa2f7", edge: 0.85 },
    asserted:  { opacity: 0.95, size: 26, color: "#7aa2f7", border: "#5b7fd6", edge: 0.55 },
    extracted: { opacity: 0.42, size: 16, color: "#9aa3b8", border: "#69728a", edge: 0.22 },
    episodic:  { opacity: 0.18, size: 11, color: "#69728a", border: "#3a4154", edge: 0.10 },
  };
  function tier(t) { return TIER[t] || TIER.extracted; }

  var elements = [];
  var nodeIds = {};
  payload.nodes.forEach(function (n) {
    nodeIds[n.id] = true;
    elements.push({
      data: { id: n.id, label: n.label, title: n.title, trust: n.trust, href: n.href || null },
      classes: "tier-" + n.trust + (n.earmarked ? " earmarked" : ""),
    });
  });
  payload.edges.forEach(function (e, i) {
    // skip edges whose endpoints are not in the payload (defensive — the scoped fold should match)
    if (!nodeIds[e.source] || !nodeIds[e.target]) return;
    // edge id from the server (relationship id); namespaced fallback never collides with a node id
    var id = e.id != null ? e.id : "rel:" + i;
    elements.push({ data: { id: id, source: e.source, target: e.target, type: e.type } });
  });

  var cy = cytoscape({
    container: mount,
    elements: elements,
    minZoom: 0.05,
    maxZoom: 4,
    wheelSensitivity: 0.25,
    boxSelectionEnabled: false,
    autoungrabify: true, // read-only: nodes are not draggable
    style: [
      {
        selector: "node",
        style: {
          "background-color": function (n) { return tier(n.data("trust")).color; },
          "width": function (n) { return tier(n.data("trust")).size; },
          "height": function (n) { return tier(n.data("trust")).size; },
          "opacity": function (n) { return tier(n.data("trust")).opacity; },
          "border-width": 1,
          "border-color": function (n) { return tier(n.data("trust")).border; },
          "label": "",
        },
      },
      {
        // space-0: the luminous core, always labelled
        selector: "node.tier-space0",
        style: {
          "label": "space-0",
          "color": "#e8ebf3",
          "font-size": 13,
          "text-valign": "center",
          "text-halign": "center",
          "text-outline-width": 3,
          "text-outline-color": "#0a0c11",
        },
      },
      {
        selector: "edge",
        style: {
          "width": 1,
          "curve-style": "haystack",
          "line-color": "#3a4154",
          // edge brightness follows its source node's trust tier. Use the edge's own source
          // element (e.source()) — reading the outer `cy` here would fail: mappers run while
          // cytoscape() is still constructing, before `cy` is assigned.
          "opacity": function (e) {
            var s = e.source();
            return s.length ? tier(s.data("trust")).edge : 0.2;
          },
        },
      },
      {
        // Earmarked overlay — harm overrides the dim, never dimmed regardless of trust tier.
        selector: "node.earmarked",
        style: {
          "border-color": "#f87171",
          "border-width": 3,
          "opacity": 1,
        },
      },
      {
        selector: "node:selected",
        style: {
          "border-color": "#9d7cf7",
          "border-width": 3,
          "opacity": 1,
          "label": "data(title)",
          "color": "#e8ebf3",
          "font-size": 12,
          "text-valign": "bottom",
          "text-margin-y": 6,
          "text-wrap": "wrap",
          "text-max-width": "220px",
          "text-outline-width": 3,
          "text-outline-color": "#0a0c11",
        },
      },
    ],
    layout: {
      name: "cose",
      idealEdgeLength: 90,
      nodeOverlap: 8,
      gravity: 0.6,
      numIter: 1000,
      animate: false,
      randomize: true,
    },
  });

  // Center the view on space-0 once laid out — the gravitational core the mentee orients from.
  cy.ready(function () {
    var core = cy.nodes(".tier-space0");
    if (core.length) {
      cy.center(core);
      cy.zoom({ level: 0.6, position: core.position() });
    } else {
      cy.fit(undefined, 40);
    }
  });

  // Inspect node (v1): click → show its title in a read-only panel.
  var panel = document.createElement("div");
  panel.id = "cortex-inspect";
  panel.className = "cortex-inspect hidden";
  document.body.appendChild(panel);

  cy.on("tap", "node", function (evt) {
    var n = evt.target;
    panel.innerHTML =
      '<span class="kind">' + esc(n.data("label")) + "</span>" +
      '<p class="title">' + esc(n.data("title")) + "</p>";
    appendLink(panel, n.data("href"));
    panel.classList.remove("hidden");
  });

  // The drill-down into the node's source surface — the graph stops being an island (Slice 5b).
  // Built with DOM APIs (createElement + assign a.href / a.textContent), NEVER by interpolating the
  // graph-derived href into an `href="..."` attribute STRING (codex round-1 [high]): the panel's
  // esc() does not escape quotes, so a poisoned value carrying `" onclick=...` would break out of a
  // string attribute and bind a same-origin handler → an authenticated mutating POST, defeating the
  // Slice-1 gate. Assigning a.href sets the attribute value verbatim — there is no attribute syntax
  // to break out of. Only an INTERNAL same-origin path (a leading "/", not "//") is ever linked: a
  // "javascript:" / "http://evil" / "//host" value is dropped, not turned into a live anchor.
  function appendLink(into, href) {
    if (typeof href !== "string" || href.charAt(0) !== "/" || href.charAt(1) === "/") return;
    var p = document.createElement("p");
    p.className = "source";
    var a = document.createElement("a");
    a.href = href;                 // verbatim attribute assignment — no string interpolation
    a.textContent = "abrir fonte →";
    p.appendChild(a);
    into.appendChild(p);
  }
  cy.on("tap", function (evt) {
    if (evt.target === cy) panel.classList.add("hidden"); // tap background → dismiss
  });

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
})();
