// cortex.js — the Cytoscape island. Draws the whole-Cortex {nodes, edges} payload as a dark,
// force-directed constellation centered on space-0, trust-weighted by brightness. Read-only:
// pan / zoom / click a node to inspect it. Loaded ONLY on /cortex (a JS island, not the app shell).
//
// Slice 6 — navigate the brain: find-and-jump SEARCH (deterministic label/type/title match → center
// the node) and FILTER (by node type / Earmarked-only / recency) over the one loaded payload, all
// client-side. The pure search/filter logic is factored into CortexFilters (below) so it is testable
// under Node with no DOM (exported via module.exports); the DOM island wires it to the controls.

(function (root) {
  "use strict";

  // ── Pure island logic — no DOM, deterministic over the loaded payload (testable in Node) ────────
  //
  // SURFACE.md: search is a find-and-jump LOCATOR (label/type match), NOT semantic retrieval — the
  // banned fetch posture. visible() is a PURE function of (payload, control-state): it recomputes the
  // shown set from scratch every call, so there is no accumulated hidden/visible state — toggling a
  // filter off restores the full set cleanly (the no-stale-state contract).
  var CortexFilters = {
    // search(payload, query) → {matchId, count}. Deterministic substring match over a node's title,
    // label (node type), and id. Empty / whitespace query → no match (clears the locator, never a
    // match-all). matchId is the FIRST matching node in payload order — the one to center on.
    search: function (payload, query) {
      var q = String(query == null ? "" : query).trim().toLowerCase();
      if (!q) return { matchId: null, count: 0 };
      var nodes = (payload && payload.nodes) || [];
      var matchId = null;
      var count = 0;
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        var hay = (
          String(n.title == null ? "" : n.title) + "\n" +
          String(n.label == null ? "" : n.label) + "\n" +
          String(n.id == null ? "" : n.id)
        ).toLowerCase();
        if (hay.indexOf(q) !== -1) {
          if (matchId === null) matchId = n.id;
          count++;
        }
      }
      return { matchId: matchId, count: count };
    },

    // visible(payload, state) → a Set of node ids to SHOW. state (all optional):
    //   types          — array of selected node-type labels (Genesis…Episodic). Omitted/null = all
    //                     types; an EMPTY array = no type selected → an empty result (not match-all).
    //   earmarkedOnly  — true → keep only Earmarked (the harm subset).
    //   recencyFraction— 0 = recency OFF (show all). f in (0,1] ranks ONLY the STAMPED nodes by `ts`
    //                    and keeps the most-recent ceil((1-f)*Ns) of them (>=1 while engaged); 1 = the
    //                    single most-recent stamped node. An UNSTAMPED node (ts null) has "no recency
    //                    position" (the server contract) → it is NEVER fabricated as recent: with
    //                    recency engaged it is dropped, never an arbitrary keep (codex round-1 [med]).
    // Each predicate is an independent AND — composing filters just intersects them; recompute from
    // the payload, never from a prior result, so there is no stale hidden/visible state.
    visible: function (payload, state) {
      state = state || {};
      var nodes = (payload && payload.nodes) || [];
      var ids = new Set();

      var typeSet = null;
      if (state.types != null) typeSet = new Set(state.types);

      // recency cutoff: rank ONLY stamped nodes; a node must be in this Set to pass when recency is
      // engaged, so an unstamped node (no recency position) is dropped, never invented as recent.
      var recencyKeep = null; // a Set of ids the recency threshold keeps; null = recency OFF
      var f = state.recencyFraction;
      if (typeof f === "number" && f > 0) {
        var stamped = nodes.filter(function (n) { return n.ts != null && String(n.ts) !== ""; });
        stamped.sort(function (a, b) {
          var ta = String(a.ts), tb = String(b.ts);
          if (ta < tb) return -1;
          if (ta > tb) return 1;
          return 0;
        });
        // keep the most-recent ceil((1-f)*Ns) STAMPED nodes; never fewer than 1 while engaged with at
        // least one stamped node — so the slider at max leaves the single newest, and an all-unstamped
        // graph keeps NONE (the kept set is empty, not a fabricated last-payload node).
        var keepCount = Math.ceil((1 - f) * stamped.length);
        if (stamped.length > 0 && keepCount < 1) keepCount = 1;
        recencyKeep = new Set();
        for (var k = stamped.length - keepCount; k < stamped.length; k++) {
          if (k >= 0) recencyKeep.add(stamped[k].id);
        }
      }

      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        if (typeSet && !typeSet.has(n.label)) continue;
        if (state.earmarkedOnly && !n.earmarked) continue;
        if (recencyKeep && !recencyKeep.has(n.id)) continue;
        ids.add(n.id);
      }
      return ids;
    },

    // render(payload, state) → the ONE combined search+filter state the DOM renders from (codex
    // round-1 [medium]): the visible set (filters), plus the search hit — the FIRST node that matches
    // the query AND survives the active filters (search NEVER resurrects a filtered-out node) — and
    // the count of VISIBLE matches. state extends visible()'s with `query`. Pure: recomputed every
    // change, so filter↔search interactions are always consistent (no stale visible state, both
    // empty-result paths resolve cleanly).
    render: function (payload, state) {
      state = state || {};
      var visibleIds = this.visible(payload, state);
      var nodes = (payload && payload.nodes) || [];
      var q = String(state.query == null ? "" : state.query).trim().toLowerCase();
      var searchHit = null;
      var searchCount = 0;
      if (q) {
        for (var i = 0; i < nodes.length; i++) {
          var n = nodes[i];
          if (!visibleIds.has(n.id)) continue; // a hit must be a VISIBLE node — no resurrection
          var hay = (
            String(n.title == null ? "" : n.title) + "\n" +
            String(n.label == null ? "" : n.label) + "\n" +
            String(n.id == null ? "" : n.id)
          ).toLowerCase();
          if (hay.indexOf(q) !== -1) {
            if (searchHit === null) searchHit = n.id;
            searchCount++;
          }
        }
      }
      return { visibleIds: visibleIds, searchHit: searchHit, searchCount: searchCount };
    },
  };

  // Export the pure logic for Node (tests) AND attach it to the browser global (the DOM island reads
  // it below). Requiring this file in Node only defines + exports CortexFilters — the DOM island
  // block is guarded on `document`/`cytoscape`, so it never runs without a browser.
  if (typeof module !== "undefined" && module.exports) module.exports = { CortexFilters: CortexFilters };
  root.CortexFilters = CortexFilters;

  // ── DOM island — only in the browser, only with cytoscape + the mount + the payload ─────────────
  if (typeof document === "undefined" || typeof cytoscape === "undefined") return;

  var dataEl = document.getElementById("cortex-data");
  var mount = document.getElementById("cortex");
  if (!dataEl || !mount) return;

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
        // a search hit — the located node pops above the constellation so the eye lands on it.
        selector: "node.search-hit",
        style: {
          "border-color": "#facc15",
          "border-width": 4,
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
      {
        // a node hidden by a filter — display:none removes it (and its edges) from the canvas.
        selector: "node.filtered-out",
        style: { "display": "none" },
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

  // ── Filter controls — recompute the visible set from the payload + the live control state, then
  // toggle `.filtered-out` deterministically. Pure recompute every change → no stale hidden state. ──
  var search = document.getElementById("cortex-search");
  var searchStatus = document.getElementById("cortex-search-status");
  var earmarkedBox = document.getElementById("cortex-earmarked");
  var recencyRange = document.getElementById("cortex-recency");
  var typeBoxes = Array.prototype.slice.call(
    document.querySelectorAll('input[name="cortex-type"]'));

  function controlState() {
    var types = null;
    if (typeBoxes.length) {
      types = typeBoxes.filter(function (b) { return b.checked; })
                       .map(function (b) { return b.value; });
    }
    var recencyFraction = 0;
    if (recencyRange) recencyFraction = (parseFloat(recencyRange.value) || 0) / 100;
    return {
      types: types,
      earmarkedOnly: !!(earmarkedBox && earmarkedBox.checked),
      recencyFraction: recencyFraction,
      query: search ? search.value : "",
    };
  }

  // Render from ONE combined state every change (codex round-1 [medium]): apply filters AND search
  // together so the search hit is always a VISIBLE node — never resurrect a filtered-out node, and
  // the status is recomputed from the combined set (no stale visible state).
  function render() {
    var r = CortexFilters.render(payload, controlState());
    cy.batch(function () {
      cy.nodes().forEach(function (n) {
        var id = n.id();
        if (r.visibleIds.has(id)) n.removeClass("filtered-out");
        else n.addClass("filtered-out");
        if (id === r.searchHit) n.addClass("search-hit");
        else n.removeClass("search-hit");
      });
    });
    var q = (search ? search.value : "").trim();
    if (searchStatus) {
      if (!q) searchStatus.textContent = "";
      else if (r.searchHit == null) searchStatus.textContent = "sem resultado";
      else searchStatus.textContent = r.searchCount > 1 ? r.searchCount + " resultados" : "1 resultado";
    }
    if (r.searchHit != null) {
      var hit = cy.getElementById(r.searchHit);
      if (hit.length) cy.animate({ center: { eles: hit }, zoom: 1.1 }, { duration: 280 });
    }
  }

  typeBoxes.forEach(function (b) { b.addEventListener("change", render); });
  if (earmarkedBox) earmarkedBox.addEventListener("change", render);
  if (recencyRange) recencyRange.addEventListener("input", render);
  if (search) search.addEventListener("input", render);

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
})(typeof globalThis !== "undefined" ? globalThis : this);
