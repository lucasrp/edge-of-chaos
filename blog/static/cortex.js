// cortex.js — the Cortex render island. Draws the whole-Cortex {nodes, edges} payload as a dark,
// luminous, trust-weighted graph centered on space-0. Loaded ONLY on /cortex (a JS island, not the
// app shell — M19). Read-only: orbit/pan/zoom, click a node to inspect it.
//
// Slice 2 — the 3D force-directed cloud (3d-force-graph) as the DEFAULT renderer, behind the M21
// fallback ladder: WebGL→3D, else the 2D Cytoscape island, else a server-rendered searchable list,
// else the honest message. The ladder gates on the 3D renderer ACTUALLY initializing + first-painting
// (the probe is necessary, NOT sufficient). The PURE pieces are factored + exported for headless Node
// tests: CortexFilters (search/filter, Slice 6), webglSupported (the capability probe, Slice 1), and
// CortexRender (the ladder decision + the trust-weighted 3D node/edge style mappers, Slice 2).

(function (root) {
  "use strict";

  // ── Pure island logic — no DOM, deterministic over the loaded payload (testable in Node) ────────
  //
  // SURFACE.md: search is a find-and-jump LOCATOR (label/type match), NOT semantic retrieval — the
  // banned fetch posture. visible() is a PURE function of (payload, control-state): it recomputes the
  // shown set from scratch every call, so there is no accumulated hidden/visible state — toggling a
  // filter off restores the full set cleanly (the no-stale-state contract).
  var CortexFilters = {
    // typeSelection(allLabels, checkedLabels) → the `types` value for visible()/render(). When EVERY
    // control is checked (the default), returns null = "no type filter" so a schema-drifted node whose
    // label is NOT in the fixed control list (the live fold tolerates unknown labels — _map_node maps
    // them to `extracted`) stays visible + searchable by default (codex round-2 [medium]). Only once
    // the user actually UNCHECKS a type does it become an explicit allow-list. An empty selection →
    // [] (hide all), distinct from null.
    typeSelection: function (allLabels, checkedLabels) {
      var all = (allLabels || []).length;
      var checked = (checkedLabels || []).length;
      if (all > 0 && checked === all) return null; // all checked → no filter (whole graph)
      return (checkedLabels || []).slice();
    },

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
        // the haystack includes the stable `ref` (Slice 6b round-6) so a correction's node ref (a
        // uuid, distinct from the render id) is searchable — the /chat provenance link is keyed by it.
        var hay = (
          String(n.title == null ? "" : n.title) + "\n" +
          String(n.label == null ? "" : n.label) + "\n" +
          String(n.id == null ? "" : n.id) + "\n" +
          String(n.ref == null ? "" : n.ref)
        ).toLowerCase();
        if (hay.indexOf(q) !== -1) {
          if (matchId === null) matchId = n.id;
          count++;
        }
      }
      return { matchId: matchId, count: count };
    },

    // locate(payload, ref) → the RENDER id of the node whose stable `ref` matches (then a render-id
    // fallback), or null. Drives the /cortex?node=<stable-ref> provenance link from a node correction
    // (Slice 6b round-6): the persisted target is the stable ref (a uuid), distinct from the volatile
    // render id, so the locator must match `ref` first to center the originating node.
    locate: function (payload, ref) {
      var want = String(ref == null ? "" : ref);
      if (!want) return null;
      var nodes = (payload && payload.nodes) || [];
      var i;
      for (i = 0; i < nodes.length; i++) {
        if (String(nodes[i].ref == null ? "" : nodes[i].ref) === want) return nodes[i].id;
      }
      for (i = 0; i < nodes.length; i++) {
        if (String(nodes[i].id == null ? "" : nodes[i].id) === want) return nodes[i].id;
      }
      return null;
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
    //   collapseEpisodic— true → fold the faint `episodic` haze out of the RENDERED set (the Slice-6
    //                    perf lever, SURFACE.md). A client-side render decision over the SAME payload
    //                    (the fold is untouched); the episodic's MENTIONS edges drop with it.
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
        // Episodic-collapse perf lever (Slice 6, SURFACE.md): when engaged, the faint `episodic`
        // haze (~91 nodes + their MENTIONS edges) folds OUT of the rendered set so it stops costing
        // render budget beyond the M22 floor. A CLIENT-SIDE render decision over the EXISTING payload
        // — one more independent AND predicate, recomputed from scratch (no stale state); the data /
        // fold / _map_node are untouched. The episodic's MENTIONS edges drop with it (an endpoint is
        // hidden), collapsing it into its parent in the render — exactly the density reduction.
        // An Earmarked episodic is NEVER folded out (M4 / SURFACE.md harm-surfacing: harm overrides
        // the trust-tier treatment, just as it overrides the trust-dim — so the harm stays visible
        // and its correction composer reachable even with the lever on).
        if (state.collapseEpisodic && n.trust === "episodic" && !n.earmarked) continue;
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
            String(n.id == null ? "" : n.id) + "\n" +
            String(n.ref == null ? "" : n.ref)
          ).toLowerCase();
          if (hay.indexOf(q) !== -1) {
            if (searchHit === null) searchHit = n.id;
            searchCount++;
          }
        }
      }
      return { visibleIds: visibleIds, searchHit: searchHit, searchCount: searchCount };
    },

    // traversalOrder(payload, state) → an ARRAY of node ids in a STABLE, server-INDEPENDENT order, for
    // PREV/NEXT (M15). The order is computed CLIENT-SIDE over explicit node fields — sort by
    //   (trust-tier rank, label, normalized title, ref-or-id)
    // with the ref (then id) the final tie-breaker — NOT raw Neo4j payload row order (Q8): the Cortex
    // fold runs its Cypher with no ORDER BY and serializes .data() directly, so row order is NOT stable
    // across requests/versions/plans. The client sort over stable fields makes traversal repeatable
    // across a reload with no server change. The set is INTERSECTED with the active filter (visible()),
    // so PREV/NEXT walks the filtered+sorted set, never resurrecting a filtered-out node (consistent
    // with render()'s no-resurrection rule). Pure + deterministic → testable headless.
    traversalOrder: function (payload, state) {
      var visibleIds = this.visible(payload, state);
      var nodes = ((payload && payload.nodes) || []).filter(function (n) {
        return visibleIds.has(n.id);
      });
      var sorted = nodes.slice().sort(function (a, b) {
        var ra = traversalTierRank(a.trust), rb = traversalTierRank(b.trust);
        if (ra !== rb) return ra - rb;
        var la = String(a.label == null ? "" : a.label);
        var lb = String(b.label == null ? "" : b.label);
        if (la !== lb) return la < lb ? -1 : 1;
        var ta = normalizeTitle(a.title), tb = normalizeTitle(b.title);
        if (ta !== tb) return ta < tb ? -1 : 1;
        // the STABLE ref (a uuid, falling back to the render id when a node carries no ref) is the
        // primary tie-breaker. When two nodes COLLIDE on ref (schema/data-dedup drift), break the tie
        // on the render `id` so the order is a TOTAL order (codex Slice-5 round-4 [medium]) — never a
        // comparator 0 that lets the unstable Neo4j row order leak through stable sort. So traversal is
        // deterministic + reload-stable even under duplicate refs (the drift this client sort survives).
        var ka = String(a.ref == null ? a.id : a.ref);
        var kb = String(b.ref == null ? b.id : b.ref);
        if (ka !== kb) return ka < kb ? -1 : 1;
        var ia = String(a.id), ib = String(b.id);
        if (ia !== ib) return ia < ib ? -1 : 1;
        return 0;
      });
      return sorted.map(function (n) { return n.id; });
    },
  };

  // traversalTierRank(trust) → the trust-tier ORDER for the stable traversal sort (space-0 core first,
  // episodic haze last). An unknown tier ranks AFTER episodic (a defined constant, never NaN), so a
  // schema-drifted node still sorts deterministically by the later (label/title/ref) keys.
  var TRAVERSAL_TIER_RANK = { space0: 0, asserted: 1, extracted: 2, episodic: 3 };
  function traversalTierRank(trust) {
    var r = TRAVERSAL_TIER_RANK[trust];
    return typeof r === "number" ? r : 4;
  }

  // normalizeTitle(title) → the title lowercased + whitespace-collapsed, so the sort is stable across
  // incidental case / spacing differences (the stable-ordering key, not a display string).
  function normalizeTitle(title) {
    return String(title == null ? "" : title).trim().replace(/\s+/g, " ").toLowerCase();
  }

  // webglSupported(canvasFactory) → boolean. The capability seam the M21 fallback ladder branches on
  // (Slice 1 / audit G4): a side-effect-free try/catch that asks a throwaway <canvas> for a `webgl`
  // (then `experimental-webgl`) context and reports whether one is available. The probe is necessary
  // but NOT sufficient for 3D (Slice 2 also wraps the renderer's construct + first-paint) — here it
  // only reports the capability. `canvasFactory` is injectable so the probe is testable headless under
  // Node (no `document`); in the browser it defaults to document.createElement("canvas"). With no
  // factory and no `document` (Node) it returns false — callable, never throwing, so the DOM island
  // guard (below) still gates real use. Any throw (a hardened/blocked context) is caught → false,
  // never propagated (a throw here would crash the island before the fallback can engage).
  function webglSupported(canvasFactory) {
    try {
      var make = canvasFactory;
      if (typeof make !== "function") {
        if (typeof document === "undefined") return false; // Node, no injected factory
        make = function () { return document.createElement("canvas"); };
      }
      var canvas = make();
      if (!canvas || typeof canvas.getContext !== "function") return false;
      var gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
      if (!gl) return false;
      // Release the throwaway context (codex Slice-1 round-1): WebGL context quotas are low on
      // constrained browsers / VMs, so the probe must not leak the context it acquires — that could
      // starve the real Slice-2 renderer this probe gates. Best-effort: a missing/throwing cleanup
      // API must not break the probe (it still reports true).
      try {
        var lose = typeof gl.getExtension === "function" ? gl.getExtension("WEBGL_lose_context") : null;
        if (lose && typeof lose.loseContext === "function") lose.loseContext();
      } catch (cleanupErr) { /* best-effort release; ignore */ }
      return true;
    } catch (e) {
      return false;
    }
  }

  // ── CortexRender — pure, exported render logic (Slice 2): the M21 fallback-ladder DECISION and the
  // trust-weighted 3D node/edge style mappers. Factored out of the DOM island so the ladder hierarchy
  // (M21) and the trust legibility (M3/M3b/M4) are testable headless under Node, exactly as
  // CortexFilters / webglSupported are. ────────────────────────────────────────────────────────────
  //
  // TIER — the single trust-weight table (space-0 brightest core → asserted bright → extracted dim →
  // episodic faintest haze). Trust is the SOLE size+brightness axis (Q2: no second centrality axis).
  // `edge` is the per-tier edge opacity (M3b: asserted spine edges read STRONGER than the haze).
  var RENDER_TIER = {
    space0:    { opacity: 1.00, size: 9.0, color: "#cfe0ff", edge: 0.85 },
    asserted:  { opacity: 0.95, size: 5.2, color: "#7aa2f7", edge: 0.55 },
    extracted: { opacity: 0.42, size: 3.0, color: "#9aa3b8", edge: 0.22 },
    episodic:  { opacity: 0.18, size: 2.0, color: "#69728a", edge: 0.10 },
  };
  function renderTier(t) { return RENDER_TIER[t] || RENDER_TIER.extracted; }

  var CortexRender = {
    TIER: RENDER_TIER,

    // chooseRenderer(caps) → which M21 rung renders, a STRICT hierarchy (the M-GATE). caps:
    //   webgl       — webglSupported() (the capability probe; necessary, NOT sufficient).
    //   force3dOk   — the 3D constructor + first-paint actually succeeded (probe true is not enough:
    //                 a missing/corrupt lib, a throw on init, a blank first paint, or a lost context
    //                 all set this false → drop to rung 2, never a blank-with-data /cortex).
    //   cytoscapeOk — the 2D Cytoscape island rendered (rung 2, the single mandated WebGL fallback).
    //   listOk      — the searchable list rendered (rung 3, tertiary).
    // Returns '3d' | 'cytoscape' | 'list' | 'message' (rung 4, the honest floor).
    chooseRenderer: function (caps) {
      caps = caps || {};
      if (caps.webgl && caps.force3dOk) return "3d";       // rung 1 — the 3D cloud (default)
      if (caps.cytoscapeOk) return "cytoscape";            // rung 2 — the 2D Cytoscape island
      if (caps.listOk) return "list";                      // rung 3 — the searchable list
      return "message";                                    // rung 4 — the honest message (floor)
    },

    // node3dStyle(node) → {color, size, opacity, earmarked} for the 3D render. M3: trust-weighted
    // luminosity (brightness + size both fall with trust). M4: an Earmarked node is NEVER dimmed
    // (harm overrides the trust-dim) and carries the harm cue for the red overlay.
    node3dStyle: function (node) {
      node = node || {};
      var t = renderTier(node.trust);
      var earmarked = !!node.earmarked;
      return {
        color: t.color,
        size: t.size,
        // harm overrides the dim — an Earmarked node reads at full brightness regardless of its tier.
        opacity: earmarked ? 1 : t.opacity,
        earmarked: earmarked,
      };
    },

    // edge3dStyle(node) → {opacity} for an edge, weighted by its SOURCE node's trust tier (M3b):
    // asserted-spine edges (GROUNDS/ANCHORS/SERVES) read stronger than extracted/episodic (the
    // hypothesis haze) — the curated-vs-hypothesis channel, not styling.
    edge3dStyle: function (sourceNode) {
      return { opacity: renderTier((sourceNode || {}).trust).edge };
    },

    // edge3dColor(sourceNode) → the trust-LUMINOSITY-baked hex color for an edge (M3b). Same reason
    // as node3dColor: the vendored build hides THREE, so a per-link MATERIAL opacity is not reachable;
    // the source tier's edge brightness (TIER.edge) is baked into the edge COLOR by blending the base
    // edge hue toward the dark background by (1 - edge-opacity). So an asserted-spine edge
    // (GROUNDS/ANCHORS/SERVES) reads BRIGHT and an extracted/episodic edge collapses toward the
    // background haze — the curated-vs-hypothesis channel preserved as luminosity, via the supported
    // linkColor accessor (not just edge WIDTH). Pure + deterministic → testable headless.
    edge3dColor: function (sourceNode) {
      return blendToBg("#5b6479", renderTier((sourceNode || {}).trust).edge);
    },

    // node3dColor(node) → the trust-LUMINOSITY-baked hex color for the 3D render. The vendored
    // 3d-force-graph build does not expose its THREE namespace, so per-node MATERIAL opacity is not
    // reachable; instead the tier's luminosity (opacity) is baked into the COLOR by blending the tier
    // hue toward the dark background (#0a0c11) by (1 - opacity) — so a faint episodic node reads as a
    // dim haze and the bright space-0 core pops, the SAME trust-luminosity legibility, via the
    // supported nodeColor accessor (M3/R4). An Earmarked node is full red, never blended (M4: harm
    // overrides the dim). Pure + deterministic → testable headless.
    node3dColor: function (node) {
      node = node || {};
      if (node.earmarked) return "#f87171";       // M4 — harm reads red, never dimmed
      var t = renderTier(node.trust);
      return blendToBg(t.color, t.opacity);
    },
  };

  // blendToBg(hex, opacity) → the hex color blended toward the dark background by (1-opacity). The
  // background is the Cortex dark space (#0a0c11). A high-opacity tier stays near its hue; a faint
  // tier collapses toward the background → the luminosity haze, baked into the color channel.
  var BG_RGB = [0x0a, 0x0c, 0x11];
  function blendToBg(hex, opacity) {
    var h = String(hex).replace("#", "");
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16);
    var a = Math.max(0, Math.min(1, opacity));
    function mix(c, bg) { return Math.round(c * a + bg * (1 - a)); }
    function hx(v) { var s = v.toString(16); return s.length === 1 ? "0" + s : s; }
    return "#" + hx(mix(r, BG_RGB[0])) + hx(mix(g, BG_RGB[1])) + hx(mix(b, BG_RGB[2]));
  }

  // Export the pure logic for Node (tests) AND attach it to the browser global (the DOM island reads
  // it below). Requiring this file in Node only defines + exports the pure namespaces — the DOM island
  // block is guarded on `document`, so it never runs without a browser.
  if (typeof module !== "undefined" && module.exports)
    module.exports = { CortexFilters: CortexFilters, webglSupported: webglSupported,
                       CortexRender: CortexRender };
  root.CortexFilters = CortexFilters;
  root.webglSupported = webglSupported;
  root.CortexRender = CortexRender;


  // ── DOM island — only in the browser, with the mount + the payload. The renderer libs are loaded
  // per the M21 ladder: the island runs even when `cytoscape` is undefined (the 3D renderer does not
  // need it; cytoscape is only rung 2). ────────────────────────────────────────────────────────────
  if (typeof document === "undefined") return;

  var dataEl = document.getElementById("cortex-data");
  var mount = document.getElementById("cortex");
  if (!dataEl || !mount) return; // no payload block / no mount → fail-dark page or another surface

  var payload;
  try {
    payload = JSON.parse(dataEl.textContent);
  } catch (e) {
    mount.textContent = "cortex: payload ilegível.";
    return;
  }

  // ── Shared inspect panel + node lookups (used by WHICHEVER renderer rung mounts) ─────────────────
  var nodeById = {};
  payload.nodes.forEach(function (n) { nodeById[n.id] = n; });

  // The drill-down into the node's source surface — built with DOM APIs (createElement + assign
  // a.href / a.textContent), NEVER by interpolating the graph-derived href into an `href="..."`
  // attribute STRING (codex round-1 [high]): esc() does not escape quotes, so a poisoned value
  // carrying `" onclick=...` would break out of a string attribute and bind a same-origin handler →
  // an authenticated mutating POST, defeating the Slice-1 gate. Assigning a.href sets the attribute
  // verbatim. Only an INTERNAL same-origin path (leading "/", not "//") is ever linked.
  // label/className default to the legacy "abrir fonte →"/"source" (the unchanged drill semantics);
  // Slice 3 passes distinct labels for the FULL DEFINITION's READ MORE and the SEEN-IN-THE-WILD
  // provenance — same DOM-API construction, same internal-path-only guard. Returns true iff a link was
  // appended (so M10b can OMIT the SEEN-IN-THE-WILD block when the node has no internal href).
  function appendLink(into, href, label, className) {
    if (typeof href !== "string" || href.charAt(0) !== "/" || href.charAt(1) === "/") return false;
    var p = document.createElement("p");
    p.className = className || "source";
    var a = document.createElement("a");
    a.href = href;                 // verbatim attribute assignment — no string interpolation
    a.textContent = label || "abrir fonte →";
    p.appendChild(a);
    into.appendChild(p);
    return true;
  }

  // The correction composer for an Earmarked node — a small Voz composer that POSTs a voz.comment
  // whose target_ref is the node ref. Built with DOM APIs (createElement + assign form.action), NEVER
  // by interpolating the graph-derived node id into an action="..." attribute STRING (the same
  // breakout defense as appendLink). The id is url-encoded into the same-origin route path; the POST
  // is same-origin, so it rides the Slice-1 auth/CSRF gate exactly like every other Voz write.
  function appendCorrection(into, nodeId) {
    var form = document.createElement("form");
    form.className = "composer correction";
    form.action = "/cortex/" + encodeURIComponent(nodeId) + "/comment";
    form.method = "post";
    var heading = document.createElement("p");
    heading.className = "correction-label meta";
    heading.textContent = "corrigir este nó (vira um Directive) →";
    var ta = document.createElement("textarea");
    ta.name = "body";
    ta.required = true;
    ta.placeholder = "o que está errado / o que corrigir…";
    var btn = document.createElement("button");
    btn.type = "submit";
    btn.textContent = "corrigir";
    form.appendChild(heading);
    form.appendChild(ta);
    form.appendChild(btn);
    var status = document.createElement("p");
    status.className = "correction-status meta";
    // A render-unique idempotent nonce base (codex round-2 [medium]): a fresh token per panel build,
    // advancing after each successful submit, so a double-fire within one render dedupes while a
    // deliberate repeat after a rebuild still lands. Same stable-then-advance pattern as the Voz rail.
    var renderToken = Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
    var nonceN = 0;
    function nonce() { return "corr:" + nodeId + ":" + renderToken + ":" + nonceN; }
    form.addEventListener("submit", function (evt) {
      evt.preventDefault();
      var body = ta.value;
      if (!body || !body.trim()) return;
      fetch(form.action, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: "body=" + encodeURIComponent(body) +
              "&comment_nonce=" + encodeURIComponent(nonce()),
      }).then(function (r) {
        if (r.ok) { ta.value = ""; nonceN++; status.textContent = "correção registrada"; }
        else status.textContent = "correção recusada (" + r.status + ")";
      }).catch(function () { status.textContent = "falha ao enviar"; });
    });
    into.appendChild(form);
    into.appendChild(status);
  }

  // The enriched slide-in inspect panel (Slice 3, M7/M8/M10/M10b/M12/M13). The MARKUP is the
  // server-rendered `inspect_panel` Jinja macro shell (components/ui.html), present in the shipped
  // /cortex DOM (G5/M20: the shared component is USED on the surface, not a JS-only one-off). The
  // island POPULATES the shell's data-panel-region slots by DOM API + .textContent on select —
  // keeping the no-string-interpolation breakout defense (R5/M17): a poisoned title/content stays
  // inert TEXT (textContent never parses markup, the same defense the M6 labels use). The
  // node object (from the renderer) carries the display fields; the FULL DEFINITION `content` lives on
  // the full payload node (nodeById), which the renderer's local copy omits.
  var panel = document.getElementById("cortex-inspect");
  function panelRegion(name) {
    return panel ? panel.querySelector('[data-panel-region="' + name + '"]') : null;
  }

  function showPanel(node) {
    if (!node) return;
    // M15 (Slice 5) — showPanel is the ONE sink every selection flows through (3D click, Cytoscape
    // tap, list locate, search, deep-link, PREV/NEXT). Anchor the traversal cursor here so a manual
    // node click then PREV/NEXT steps from the CLICKED node — not a stale search/deep-link/older
    // cursor. Set BEFORE the panel guard so the cursor anchors even when the panel DOM is absent
    // (degraded rungs). `traversalCursor` is hoisted (declared below); by call time it is live.
    traversalCursor = node.id;
    if (!panel) return;  // the panel-fill below needs the server-rendered macro shell
    var full = nodeById[node.id] || node;  // the full payload node carries the untruncated `content`
    // M8 — term + one-line definition: label + title, set as TEXT (.textContent), never markup.
    var termEl = panelRegion("term");
    if (termEl) termEl.textContent = node.label == null ? "" : String(node.label);
    var defEl = panelRegion("definition");
    if (defEl) defEl.textContent = node.title == null ? "" : String(node.title);

    // M10 — FULL DEFINITION prose = the untruncated `content` (text-only), + the source drill as
    // READ MORE → (the existing internal-path-only appendLink guard, unchanged construction).
    var fullEl = panelRegion("full");
    if (fullEl) {
      fullEl.textContent = "";
      var prose = full.content;
      if (prose != null && String(prose).trim() !== "") {
        var pp = document.createElement("p");
        pp.className = "full-definition";
        pp.textContent = String(prose);   // TEXT-only — no innerHTML from payload (R5/M17)
        fullEl.appendChild(pp);
      }
      appendLink(fullEl, node.href, "ler mais / abrir fonte →", "read-more");
    }

    // M10b — SEEN IN THE WILD = the node's REAL href provenance (no fabricated quote). When the node
    // has an internal href, surface it as the where-this-is-seen affordance; when it does NOT,
    // appendLink returns false and the block stays EMPTY (omitted — no dead link, no placeholder).
    var wildEl = panelRegion("wild");
    if (wildEl) {
      wildEl.textContent = "";
      var label = document.createElement("p");
      label.className = "wild-label meta";
      label.textContent = "visto na prática →";
      var linked = appendLink(wildEl, node.href, "abrir a fonte de origem →", "wild-source");
      if (linked) wildEl.insertBefore(label, wildEl.firstChild);
      else wildEl.textContent = "";  // M10b: omit the block entirely when there is no provenance href
    }

    // M12 — the Earmarked correction composer, preserved VERBATIM in the composer slot: only a harm
    // node gets it, targeted by its STABLE ref (not the volatile render id), same DOM-safe form.action
    // + encodeURIComponent + stable-then-advance nonce + same-origin POST through the Slice-1 gate.
    var composerEl = panelRegion("composer");
    if (composerEl) {
      composerEl.textContent = "";
      if (node.earmarked) appendCorrection(composerEl, node.ref || node.id);
    }
    panel.classList.remove("hidden");
    panel.setAttribute("aria-hidden", "false");
  }
  function hidePanel() {
    if (!panel) return;
    panel.classList.add("hidden");
    panel.setAttribute("aria-hidden", "true");
  }
  // M13 — the close affordance dismisses the panel back to the free-flight cloud (the existing
  // tap-background dismiss is wired per-renderer; this is the explicit close control on the shell).
  if (panel) {
    var closeBtn = panel.querySelector(".cortex-inspect-close");
    if (closeBtn) closeBtn.addEventListener("click", hidePanel);
  }

  // hideList() — the server renders #cortex-list VISIBLE (the JS-dead navigable fallback, codex
  // round-1 [high]); when a GRAPH rung (3D or Cytoscape) successfully paints, the island hides the
  // list so it does not double-render under the canvas. Progressive enhancement: no graph rung → the
  // list stays visible (a failed/absent cortex.js leaves a navigable list, never a blank area).
  function hideList() {
    var list = document.getElementById("cortex-list");
    if (list) list.hidden = true;
  }

  // The ?node=<stable-ref> deep-link (the /chat provenance link from a node correction, Slice 6b):
  // located by its STABLE ref (not the volatile render id) via the unchanged CortexFilters.locate.
  function deepLinkId() {
    var deepRef = null;
    try { deepRef = new URLSearchParams(location.search).get("node"); } catch (e) { deepRef = null; }
    return deepRef ? CortexFilters.locate(payload, deepRef) : null;
  }

  // ── Filter controls (Slice 6, retained) — the shared controlState + the bound `render()` are wired
  // to WHICHEVER renderer mounted via a small adapter the renderer provides. ───────────────────────
  var search = document.getElementById("cortex-search");
  var searchStatus = document.getElementById("cortex-search-status");
  var earmarkedBox = document.getElementById("cortex-earmarked");
  var recencyRange = document.getElementById("cortex-recency");
  var collapseBox = document.getElementById("cortex-collapse"); // the Episodic-collapse perf lever (Slice 6)
  var typeBoxes = Array.prototype.slice.call(
    document.querySelectorAll('input[name="cortex-type"]'));

  function controlState() {
    var types = null;
    if (typeBoxes.length) {
      var allLabels = typeBoxes.map(function (b) { return b.value; });
      var checked = typeBoxes.filter(function (b) { return b.checked; })
                             .map(function (b) { return b.value; });
      types = CortexFilters.typeSelection(allLabels, checked);
    }
    var recencyFraction = 0;
    if (recencyRange) recencyFraction = (parseFloat(recencyRange.value) || 0) / 100;
    return {
      types: types,
      earmarkedOnly: !!(earmarkedBox && earmarkedBox.checked),
      recencyFraction: recencyFraction,
      collapseEpisodic: !!(collapseBox && collapseBox.checked),
      query: search ? search.value : "",
    };
  }

  // currentAdapter — the ONE active renderer's control adapter. The control listeners are wired ONCE
  // (wireControls) and always dispatch to whatever currentAdapter is NOW (codex round-4 [medium]): on
  // a late demotion (WebGL context loss / async blank-paint), the ladder swaps currentAdapter to the
  // fallback rung's adapter — it does NOT re-bind listeners. So a stale 3D adapter (whose Graph is
  // destroyed) never fires against search/filter input after the failure it is meant to survive.
  var currentAdapter = null;
  var controlsWired = false;
  function render() {
    var adapter = currentAdapter;
    if (!adapter) return;                 // no active renderer (e.g. the message floor) → controls no-op
    var r = CortexFilters.render(payload, controlState());
    adapter.applyVisible(r.visibleIds, r.searchHit);
    var q = (search ? search.value : "").trim();
    if (searchStatus) {
      if (!q) searchStatus.textContent = "";
      else if (r.searchHit == null) searchStatus.textContent = "sem resultado";
      else searchStatus.textContent =
        r.searchCount > 1 ? r.searchCount + " resultados" : "1 resultado";
    }
    if (r.searchHit != null && adapter.flyTo) adapter.flyTo(r.searchHit);
    // M15 — seed the PREV/NEXT cursor on a search hit (M14 fly-to + M15 share a position), so stepping
    // continues FROM where search landed; a no-hit / empty query leaves the cursor where it was.
    if (r.searchHit != null) traversalCursor = r.searchHit;
  }
  function wireControls() {
    if (controlsWired) return;            // bind exactly once — a re-mount only swaps currentAdapter
    controlsWired = true;
    typeBoxes.forEach(function (b) { b.addEventListener("change", render); });
    if (earmarkedBox) earmarkedBox.addEventListener("change", render);
    if (recencyRange) recencyRange.addEventListener("input", render);
    if (collapseBox) collapseBox.addEventListener("change", render);
    if (search) search.addEventListener("input", render);
    if (prevBtn) prevBtn.addEventListener("click", function () { step(-1); });
    if (nextBtn) nextBtn.addEventListener("click", function () { step(1); });
  }

  // ── M15 PREV / NEXT traversal — step the selection + fly the camera along the STABLE, filter-
  // respecting order CortexFilters.traversalOrder computes (NOT payload order, Q8). The cursor is a
  // module-scoped id (seeded by search / deep-link); each step recomputes the order from the LIVE
  // control state (so it tracks the active filter), finds the cursor, and moves one place. ──────────
  var prevBtn = document.getElementById("cortex-prev");
  var nextBtn = document.getElementById("cortex-next");
  var traversalCursor = null;   // the id PREV/NEXT last landed on (or the search/deep-link seed)

  // writeNodeParam(ref) — persist the SELECTED node into ?node=<stable-ref> via replaceState (no
  // history spam): the stable `ref` (a uuid, what locate() resolves inbound), not the volatile render
  // id, so a reload re-centers the same node. Same-origin URL mutation only; best-effort (a hostile
  // history API must never break a step).
  function writeNodeParam(ref) {
    if (!ref || typeof history === "undefined" || !history.replaceState) return;
    try {
      var url = new URL(location.href);
      url.searchParams.set("node", String(ref));
      history.replaceState(history.state, "", url.toString());
    } catch (e) { /* best-effort URL write — a step must never throw on it */ }
  }

  // selectNode(id) — the shared selection move PREV/NEXT drives: fly the camera (the active adapter),
  // open the inspect panel, persist ?node=, and advance the cursor. Reuses the existing Slice-2
  // selection path (the adapter.flyTo + the shared showPanel), so it works on whatever rung mounted.
  function selectNode(id) {
    var node = nodeById[id];
    if (!node) return;
    traversalCursor = id;
    if (currentAdapter && currentAdapter.flyTo) currentAdapter.flyTo(id);
    showPanel(node);
    writeNodeParam(node.ref || node.id);
  }

  // step(delta) — move one place along the current (filtered) traversalOrder. With no prior cursor,
  // delta>0 starts at the first node and delta<0 at the last; otherwise it walks from the cursor,
  // CLAMPING at the ends (no wrap — the reference's PREV/NEXT stop cleanly at the boundary). A cursor
  // that the active filter has hidden is treated as "off the order" → the step re-enters at an end.
  function step(delta) {
    var order = CortexFilters.traversalOrder(payload, controlState());
    if (!order.length) return;            // nothing visible to traverse
    var idx = traversalCursor == null ? -1 : order.indexOf(traversalCursor);
    var next;
    if (idx === -1) next = delta > 0 ? 0 : order.length - 1;
    else next = idx + delta;
    if (next < 0 || next >= order.length) return;   // clamp at the ends (no wrap)
    selectNode(order[next]);
  }

  // seed the cursor from a ?node= deep-link so the FIRST PREV/NEXT continues from the deep-linked
  // node (its render id, resolved by the unchanged locate()), not from an end of the order.
  traversalCursor = deepLinkId();

  // ── Rung 1: the 3D force-directed cloud (M1–M6 + the M22 freeze). Returns a control adapter on
  // success, or null on ANY init/first-paint failure (so the ladder drops to rung 2 — the regression
  // M21 prevents: a blank-with-data /cortex when the probe passed but the renderer did not paint). ──
  function mount3D() {
    if (typeof ForceGraph3D === "undefined") return null; // lib missing/corrupt → drop to rung 2
    try {
      // Build the lib's {nodes, links} from the payload (consumed unchanged). Each node carries its
      // trust-weighted SIZE (CortexRender.node3dStyle) + its luminosity-baked COLOR (node3dColor,
      // M3/M4); each link its source-tier luminosity color (edge3dColor) + width weight (edge3dStyle,
      // M3b) — all from the PURE, headless-tested CortexRender mappers.
      var idSet = {};
      payload.nodes.forEach(function (n) { idSet[n.id] = true; });
      var gnodes = payload.nodes.map(function (n) {
        var s = CortexRender.node3dStyle(n);
        return { id: n.id, ref: n.ref || n.id, label: n.label, title: n.title, trust: n.trust,
                 href: n.href || null, earmarked: !!n.earmarked,
                 // M3: luminosity baked into the color (the vendored build hides THREE), size by tier.
                 __color: CortexRender.node3dColor(n), __size: s.size };
      });
      var glinks = [];
      payload.edges.forEach(function (e) {
        if (!idSet[e.source] || !idSet[e.target]) return; // defensive: scoped fold should match
        var src = nodeById[e.source];
        glinks.push({ source: e.source, target: e.target, type: e.type,
                      // M3b: source-tier edge brightness — baked into the COLOR (luminosity), with
                      // width as the SECONDARY trust signal (asserted spine thicker).
                      __opacity: CortexRender.edge3dStyle(src).opacity,
                      __color: CortexRender.edge3dColor(src) });
      });

      // M22 metrics — the browser gate reads window.__cortexMetrics to assert the force tick freezes
      // (≤300 ticks / ≤2.0s, then `stopped`) and is not unbounded. tickStart is stamped on the first
      // tick; frozenAt on engine stop. Production-harmless (a tiny counter object).
      var metrics = { ticks: 0, started: Date.now(), tickStart: null, frozenAt: null, stopped: false };
      if (typeof window !== "undefined") window.__cortexMetrics = metrics;

      var Graph = ForceGraph3D()(mount)
        .backgroundColor("#0a0c11")          // the dark space (the edge's dark identity, M3/M20)
        .showNavInfo(false)
        .enableNodeDrag(false)               // read-only camera — nodes are NOT draggable (M2, analog of autoungrabify)
        .nodeRelSize(1)
        .nodeVal(function (n) { return n.__size; })           // size = trust tier (M3)
        // M3/M4: the trust-LUMINOSITY-baked color (haze blended toward bg) — Earmarked → full red.
        // Trust is the SOLE size+brightness axis (Q2), legible against depth (R4: no fog to fight it).
        .nodeColor(function (n) { return n.__color; })
        // M3b: per-link luminosity by source tier — the asserted spine reads BRIGHT, the extracted/
        // episodic haze collapses toward the bg. linkColor carries the brightness; width is secondary.
        .linkColor(function (l) { return l.__color; })
        .linkOpacity(1)                                    // opacity is baked into the per-link color
        .linkWidth(function (l) { return l.__opacity > 0.5 ? 0.6 : 0.2; })  // secondary: asserted spine thicker (M3b)
        // M22 — the force tick FREEZES: cap at 300 ticks OR 2.0s wall-clock, whichever first, then the
        // sim stops (no unbounded live tick on a growing graph). This is the pinned ceiling (rung ii).
        .cooldownTicks(300)
        .cooldownTime(2000)
        .onEngineTick(function () {
          if (metrics.tickStart == null) metrics.tickStart = Date.now();
          metrics.ticks++;
        })
        .onNodeClick(function (n) { selectedId = n.id; showPanel(nodeById[n.id]); flyTo3D(n); updateLabels(); })
        .onBackgroundClick(function () { selectedId = null; hidePanel(); updateLabels(); })
        .graphData({ nodes: gnodes, links: glinks });

      // ── M6 labels — legible against the dark cloud, TEXT-ONLY, never raw-HTML from payload (R5).
      // The vendored build hides its THREE namespace (no sprite labels reachable), so labels are HTML
      // overlay <div>s tracked over the canvas via the lib's graph2ScreenCoords. space-0 is ALWAYS
      // labeled (the literal "space-0", a constant — never payload); the selected/search-hit node is
      // labeled with its TITLE set via .textContent (NOT innerHTML), so a poisoned title is inert.
      var labelLayer = document.createElement("div");
      labelLayer.className = "cortex-labels";
      labelLayer.setAttribute("aria-hidden", "true");
      mount.appendChild(labelLayer);
      var labelEls = {};   // nodeId → overlay div
      var selectedId = null;
      function labelText(n) {
        return n.trust === "space0" ? "space-0" : (n.title == null ? "" : String(n.title));
      }
      function ensureLabel(id) {
        if (labelEls[id]) return labelEls[id];
        var el = document.createElement("div");
        el.className = "cortex-label";
        labelLayer.appendChild(el);
        labelEls[id] = el;
        return el;
      }
      function labeledIds() {
        var ids = {};
        payload.nodes.forEach(function (n) { if (n.trust === "space0") ids[n.id] = true; });
        if (selectedId) ids[selectedId] = true;
        return ids;
      }
      function updateLabels() {
        var want = labeledIds();
        // drop labels no longer wanted
        Object.keys(labelEls).forEach(function (id) {
          if (!want[id]) { labelLayer.removeChild(labelEls[id]); delete labelEls[id]; }
        });
        var gd = Graph.graphData ? Graph.graphData() : { nodes: [] };
        gd.nodes.forEach(function (n) {
          if (!want[n.id] || typeof n.x !== "number" || !Graph.graph2ScreenCoords) return;
          var c = Graph.graph2ScreenCoords(n.x, n.y, n.z);
          var el = ensureLabel(n.id);
          var txt = labelText(nodeById[n.id] || n);
          if (el.textContent !== txt) el.textContent = txt;   // TEXT-only — no innerHTML from payload
          el.style.left = c.x + "px";
          el.style.top = c.y + "px";
        });
      }

      // Center / orient on space-0 on load (M5), or center+select a ?node= deep-link (R6). A correct
      // camera cut is acceptable v1 (tweening is N3); set the camera after the engine settles.
      var deepId = deepLinkId();
      Graph.onEngineStop(function () {
        // M22 — the sim has converged + frozen (cooldownTicks/cooldownTime reached). Stamp the freeze
        // so the browser gate can assert it happened within the pinned ceiling and then idles.
        if (!metrics.stopped) { metrics.stopped = true; metrics.frozenAt = Date.now(); }
        var targetId = deepId;
        if (!targetId) {
          var core = payload.nodes.filter(function (n) { return n.trust === "space0"; })[0];
          targetId = core ? core.id : (payload.nodes[0] && payload.nodes[0].id);
        }
        var node = targetId && Graph.graphData().nodes.filter(
          function (n) { return n.id === targetId; })[0];
        if (node && typeof node.x === "number") {
          flyTo3D(node, true);
          if (deepId) showPanel(nodeById[deepId]);
        }
      });

      // flyTo3D(node, instant) — move the camera to look at a node (the search/deep-link fly target).
      function flyTo3D(node, instant) {
        if (!node || typeof node.x !== "number") return;
        var dist = 120;
        var ratio = 1 + dist / Math.hypot(node.x || 1, node.y || 1, node.z || 1);
        Graph.cameraPosition(
          { x: (node.x || 0) * ratio, y: (node.y || 0) * ratio, z: (node.z || 0) * ratio },
          { x: node.x || 0, y: node.y || 0, z: node.z || 0 },
          instant ? 0 : 600);
      }

      // First-paint / non-blank check (M21 rung 1's success gate): the WebGL renderer must have a live
      // canvas with non-zero size. If the lib produced no canvas, or a lost context, treat init as a
      // FAILURE → the caller drops to rung 2 (never a blank-with-data /cortex).
      var canvas = mount.querySelector("canvas");
      if (!canvas || !canvas.width || !canvas.height) {
        try { if (Graph._destructor) Graph._destructor(); } catch (e) {}
        mount.innerHTML = "";
        return null;
      }
      // a lost context AFTER init also drops to the 2D fallback (the renderer can't keep painting).
      canvas.addEventListener("webglcontextlost", function () {
        demote3D();
      });

      // a test/forced-failure hook: window.__cortexForce3dFail makes init report failure (so the
      // browser gate can exercise the init-failure rung with WebGL genuinely present).
      if (typeof window !== "undefined" && window.__cortexForce3dFail) {
        try { if (Graph._destructor) Graph._destructor(); } catch (e) {}
        mount.innerHTML = "";
        return null;
      }

      // demote3D() — tear down the 3D rung and re-enter the ladder at the 2D Cytoscape rung. Guarded
      // so a blank-check AND a later context-loss cannot both demote (double mount).
      var demoted = false;
      function demote3D() {
        if (demoted) return;
        demoted = true;
        try { if (Graph._destructor) Graph._destructor(); } catch (e) {}
        mount.innerHTML = "";
        mount.removeAttribute("data-renderer");
        if (typeof window !== "undefined") window.__cortexGraph = null;
        mountLadderFrom("cytoscape");
      }

      // ASYNC first-PAINT / non-blank PIXEL check (codex round-1 [high]): a sized canvas is necessary
      // but NOT sufficient — a 3d-force-graph that allocates a WebGL canvas yet paints NOTHING (renders
      // no nodes, clears to background, silently fails) would otherwise set data-renderer="3d" and block
      // the lower rungs (the exact blank-with-data regression M21 prevents). 3d-force-graph paints on
      // requestAnimationFrame, so the readback waits two frames, then samples the GL drawing buffer
      // (gl.readPixels) for ANY non-background pixel. All-background after first paint → the renderer is
      // blank → demote to the 2D Cytoscape rung. (preserveDrawingBuffer is not set, so we read inside a
      // RAF — the buffer is valid until the next paint.) Failure handling (codex round-8 [medium]): if we
      // HAVE a usable GL context but the readback itself THROWS, that is an anomalous/broken renderer →
      // DEMOTE (do not trust a 3D rung whose buffer we cannot read). Only when we genuinely cannot
      // OBTAIN a context to verify (gl null / no readPixels — a browser that hides it on a HEALTHY
      // renderer) do we leave 3D up on the canvas-exists evidence, rather than false-demote a working
      // cloud. So an unverifiable-because-broken path demotes; an unverifiable-because-unavailable path
      // (context present, healthy, readback simply not exposed) does not.
      function firstPaintCheck() {
        if (typeof window !== "undefined" && window.__cortexForceBlank) { demote3D(); return; }
        var gl = null;
        try {
          var r = Graph.renderer && Graph.renderer();
          gl = r && (r.getContext ? r.getContext() : null);
        } catch (e) { gl = null; }
        if (!gl || typeof gl.readPixels !== "function") return; // no context to verify → leave 3D up
        try {
          // test hook: simulate a broken-renderer readback that throws (so the gate can prove the
          // throwing-readback path DEMOTES, codex round-8 [medium]). Production-absent.
          if (typeof window !== "undefined" && window.__cortexForceReadbackThrow)
            throw new Error("forced readback failure");
          var w = canvas.width, h = canvas.height;
          var sw = Math.min(64, w), sh = Math.min(64, h);
          var x = Math.max(0, Math.floor((w - sw) / 2)), y = Math.max(0, Math.floor((h - sh) / 2));
          var buf = new Uint8Array(sw * sh * 4);
          gl.readPixels(x, y, sw, sh, gl.RGBA, gl.UNSIGNED_BYTE, buf);
          var painted = false;
          // the background is #0a0c11 (r=10,g=12,b=17). A pixel that differs beyond a small tolerance
          // from the background = real painted content (a node/edge/label).
          for (var i = 0; i < buf.length; i += 4) {
            if (Math.abs(buf[i] - 10) > 6 || Math.abs(buf[i + 1] - 12) > 6 ||
                Math.abs(buf[i + 2] - 17) > 6) { painted = true; break; }
          }
          if (!painted) demote3D();
        } catch (e) {
          // we HAD a GL context but the readback threw → an anomalous/broken renderer; do not trust a
          // 3D rung whose drawing buffer we cannot read → demote to the 2D Cytoscape fallback.
          demote3D();
        }
      }
      if (typeof requestAnimationFrame === "function") {
        requestAnimationFrame(function () { requestAnimationFrame(firstPaintCheck); });
      }

      mount.setAttribute("data-renderer", "3d");
      hideList();   // a graph rung painted → hide the JS-dead list fallback (no double-render)
      // expose the live Graph for the browser gate (the FPS-window orbit reads it). Harmless in prod.
      if (typeof window !== "undefined") window.__cortexGraph = Graph;

      // keep the M6 overlay labels positioned over their nodes every frame (camera moves + the layout
      // settling). Stops when the rung is demoted (the loop checks `demoted`). Cheap: a handful of
      // labels (space-0 + the selected node), positioned via the lib's graph2ScreenCoords.
      (function labelLoop() {
        if (demoted) return;
        updateLabels();
        if (typeof requestAnimationFrame === "function") requestAnimationFrame(labelLoop);
      })();

      // a test-only counter so the browser gate can prove a DEFAULT first mount does NOT re-push the
      // graph (which would reheat the sim). Negligible in production.
      if (typeof window !== "undefined") window.__cortexGraphDataCalls = 0;
      return {
        applyVisible: function (visibleIds, hitId) {
          var nodes = payload.nodes.filter(function (n) { return visibleIds.has(n.id); });
          var nodeOk = {}; nodes.forEach(function (n) { nodeOk[n.id] = true; });
          var links = glinks.filter(function (l) {
            var s = l.source.id || l.source, t = l.target.id || l.target;
            return nodeOk[s] && nodeOk[t];
          });
          if (typeof window !== "undefined") window.__cortexGraphDataCalls++;
          Graph.graphData({
            nodes: gnodes.filter(function (n) { return nodeOk[n.id]; }),
            links: links,
          });
          if (hitId != null) selectedId = hitId;   // M6: the search hit gets labeled
          updateLabels();
        },
        flyTo: function (id) {
          var node = Graph.graphData().nodes.filter(function (n) { return n.id === id; })[0];
          if (node) { selectedId = id; flyTo3D(node); showPanel(nodeById[id]); updateLabels(); }
        },
      };
    } catch (e) {
      // ANY throw on construction (a missing/corrupt lib, a bad WebGL context) → drop to rung 2.
      try { mount.innerHTML = ""; } catch (e2) {}
      return null;
    }
  }

  // ── Rung 2: the 2D Cytoscape island (the existing, tested renderer — the single mandated WebGL /
  // init-failure fallback, NEVER deleted). Returns a control adapter, or null if cytoscape is absent
  // or cannot render (then drop to rung 3). ───────────────────────────────────────────────────────
  function mountCytoscape() {
    if (typeof cytoscape === "undefined") return null;
    var TIER = {
      space0:    { opacity: 1.00, size: 46, color: "#cfe0ff", border: "#7aa2f7", edge: 0.85 },
      asserted:  { opacity: 0.95, size: 26, color: "#7aa2f7", border: "#5b7fd6", edge: 0.55 },
      extracted: { opacity: 0.42, size: 16, color: "#9aa3b8", border: "#69728a", edge: 0.22 },
      episodic:  { opacity: 0.18, size: 11, color: "#69728a", border: "#3a4154", edge: 0.10 },
    };
    function tier(t) { return TIER[t] || TIER.extracted; }
    try {
      var elements = [];
      var nodeIds = {};
      payload.nodes.forEach(function (n) {
        nodeIds[n.id] = true;
        elements.push({
          data: { id: n.id, ref: n.ref || n.id, label: n.label, title: n.title, trust: n.trust,
                  href: n.href || null, earmarked: !!n.earmarked },
          classes: "tier-" + n.trust + (n.earmarked ? " earmarked" : ""),
        });
      });
      payload.edges.forEach(function (e, i) {
        if (!nodeIds[e.source] || !nodeIds[e.target]) return;
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
          { selector: "node", style: {
              "background-color": function (n) { return tier(n.data("trust")).color; },
              "width": function (n) { return tier(n.data("trust")).size; },
              "height": function (n) { return tier(n.data("trust")).size; },
              "opacity": function (n) { return tier(n.data("trust")).opacity; },
              "border-width": 1,
              "border-color": function (n) { return tier(n.data("trust")).border; },
              "label": "" } },
          { selector: "node.tier-space0", style: {
              "label": "space-0", "color": "#e8ebf3", "font-size": 13,
              "text-valign": "center", "text-halign": "center",
              "text-outline-width": 3, "text-outline-color": "#0a0c11" } },
          { selector: "edge", style: {
              "width": 1, "curve-style": "haystack", "line-color": "#3a4154",
              "opacity": function (e) {
                var s = e.source();
                return s.length ? tier(s.data("trust")).edge : 0.2; } } },
          { selector: "node.earmarked", style: {
              "border-color": "#f87171", "border-width": 3, "opacity": 1 } },
          { selector: "node.search-hit", style: {
              "border-color": "#facc15", "border-width": 4, "opacity": 1,
              "label": "data(title)", "color": "#e8ebf3", "font-size": 12,
              "text-valign": "bottom", "text-margin-y": 6, "text-wrap": "wrap",
              "text-max-width": "220px", "text-outline-width": 3, "text-outline-color": "#0a0c11" } },
          { selector: "node.filtered-out", style: { "display": "none" } },
          { selector: "node:selected", style: {
              "border-color": "#9d7cf7", "border-width": 3, "opacity": 1,
              "label": "data(title)", "color": "#e8ebf3", "font-size": 12,
              "text-valign": "bottom", "text-margin-y": 6, "text-wrap": "wrap",
              "text-max-width": "220px", "text-outline-width": 3, "text-outline-color": "#0a0c11" } },
        ],
        layout: { name: "cose", idealEdgeLength: 90, nodeOverlap: 8, gravity: 0.6,
                  numIter: 1000, animate: false, randomize: true },
      });

      cy.ready(function () {
        var deepId = deepLinkId();
        var deep = deepId ? cy.getElementById(deepId) : null;
        if (deep && deep.length) {
          deep.select(); cy.center(deep);
          cy.zoom({ level: 1.1, position: deep.position() });
          showPanel(nodeById[deepId]);
          return;
        }
        var core = cy.nodes(".tier-space0");
        if (core.length) { cy.center(core); cy.zoom({ level: 0.6, position: core.position() }); }
        else cy.fit(undefined, 40);
      });

      cy.on("tap", "node", function (evt) { showPanel(nodeById[evt.target.id()]); });
      cy.on("tap", function (evt) { if (evt.target === cy) hidePanel(); });

      mount.setAttribute("data-renderer", "cytoscape");
      hideList();   // a graph rung painted → hide the JS-dead list fallback (no double-render)
      return {
        applyVisible: function (visibleIds, hitId) {
          cy.batch(function () {
            cy.nodes().forEach(function (n) {
              var id = n.id();
              if (visibleIds.has(id)) n.removeClass("filtered-out");
              else n.addClass("filtered-out");
              if (id === hitId) n.addClass("search-hit");
              else n.removeClass("search-hit");
            });
          });
        },
        flyTo: function (id) {
          var hit = cy.getElementById(id);
          if (hit.length) cy.animate({ center: { eles: hit }, zoom: 1.1 }, { duration: 280 });
          // open the inspect panel for the located node too (codex Slice-5 round-3 [medium]): the 3D +
          // list flyTo paths reach showPanel, so the rung-2 fallback must match — search / PREV/NEXT on
          // the Cytoscape rung opens the SAME panel (Slice-7 UX parity), and routes the selection
          // through the one showPanel sink (so the traversal cursor anchors here as well).
          if (nodeById[id]) showPanel(nodeById[id]);
        },
      };
    } catch (e) {
      try { mount.innerHTML = ""; } catch (e2) {}
      return null;
    }
  }

  // ── Rung 3: the server-rendered SEARCHABLE list (#cortex-list, rendered VISIBLE by the route — the
  // JS-dead fallback). Bind node selection + make it genuinely searchable: a search hit MARKS +
  // SCROLLS the matching item into view + opens its panel (codex round-1 [medium]); filters hide the
  // non-visible items. Returns the adapter, or null if the block is absent (then drop to rung 4). ──
  function mountList() {
    var list = document.getElementById("cortex-list");
    if (!list) return null;
    try {
      mount.style.display = "none";          // hide the dead canvas mount
      list.hidden = false;                   // ensure visible even if a prior rung had hidden it
      var items = Array.prototype.slice.call(list.querySelectorAll(".cortex-list-item"));
      // make each item open the inspect panel (node selection — keeps the list navigable). The item
      // text/source are already server-escaped + internal-only; selection just opens the same panel.
      payload.nodes.forEach(function (n, i) {
        var el = items[i];
        if (!el) return;
        el.setAttribute("role", "button");
        el.setAttribute("tabindex", "0");
        el.addEventListener("click", function (evt) {
          if (evt.target.tagName === "A") return; // let the source link navigate
          locateInList(n.id);
        });
      });

      // locateInList(id) — mark the matching item, scroll it into view, open its panel. The list's
      // analog of the 3D/2D camera fly-to (so the degraded rung is genuinely searchable, not a
      // manual scan of 353+ rows).
      function locateInList(id) {
        var idx = -1;
        payload.nodes.forEach(function (n, i) { if (n.id === id) idx = i; });
        if (idx < 0) return;
        items.forEach(function (el) { el.classList.remove("list-hit"); });
        var el = items[idx];
        if (el) {
          el.classList.add("list-hit");
          if (el.scrollIntoView) el.scrollIntoView({ block: "center" });
        }
        showPanel(nodeById[id]);
      }

      // M5/R6 — the ?node=<stable-ref> provenance deep-link (the /chat correction link) must resolve
      // on the LIST rung too (codex round-7 [medium]): when WebGL AND Cytoscape are degraded, the list
      // is the navigable fallback, so it must still locate + open the originating node — else node-
      // targeted correction provenance is unauditable exactly when the graph renderers are down.
      var deepId = deepLinkId();
      if (deepId) locateInList(deepId);

      return {
        applyVisible: function (visibleIds, hitId) {
          payload.nodes.forEach(function (n, i) {
            if (items[i]) items[i].hidden = !visibleIds.has(n.id);
          });
          // a search hit on the list MARKS + SCROLLS the match (no camera — this IS the navigation).
          items.forEach(function (el) { if (el) el.classList.remove("list-hit"); });
          if (hitId != null) locateInList(hitId);
        },
        // the list's analog of a camera move (codex Slice-5 round-1 [medium]): PREV/NEXT drives the
        // active adapter's flyTo, so on the degraded list rung a step must MARK + SCROLL the traversed
        // item (locateInList), not just open the panel + write the URL — else the visible fallback
        // navigation surface goes stale while the cursor advances.
        flyTo: function (id) { locateInList(id); },
      };
    } catch (e) { return null; }
  }

  // ── Rung 4: the honest message (the floor) — the renderer is gone, but say so honestly (distinct
  // from fail-dark M16, which is for ABSENT data; here the data is present, the renderer is not). ──
  function mountMessage() {
    mount.style.display = "block";
    mount.innerHTML = "";
    var box = document.createElement("section");
    box.className = "cortex-list cortex-message";
    var h = document.createElement("h2");
    h.textContent = "cortex — renderizador indisponível";
    var p = document.createElement("p");
    p.className = "meta";
    p.textContent = "Nenhum renderizador disponível neste cliente (sem WebGL, sem canvas 2D, " +
                    "e sem a lista). Os dados do grafo existem; abra /cortex num navegador com " +
                    "WebGL ou canvas para navegar.";
    box.appendChild(h); box.appendChild(p);
    mount.appendChild(box);
  }

  // ── The M21 ladder driver — pick the rung by capability + actual render success, mount it, and bind
  // the controls to it. mountLadderFrom(rung) lets a late failure (a lost WebGL context) re-enter the
  // ladder at the next rung down without re-probing. ──────────────────────────────────────────────
  // Forced-failure hooks (read at mount time; absent in production → no behavior change) let the
  // browser gate exercise every rung deterministically: force the WebGL probe false (rung 2 probe-
  // false, case b), force the 3D init to fail with WebGL present (rung 2 init-failure, case a2 — read
  // inside mount3D), force the Cytoscape render to fail (rung 3, case c), force the list to fail
  // (rung 4, case d). The forced-failure flags only ever make a rung FAIL — they never resurrect one.
  function forced(name) {
    return typeof window !== "undefined" && window[name];
  }

  function mountLadderFrom(startRung) {
    var adapter = null, rung = "message";

    if (startRung === "3d" || startRung == null) {
      // the probe is necessary, NOT sufficient: WebGL present → also require the 3D renderer to
      // actually construct + first-paint (mount3D returns null on any init/first-paint failure).
      var webgl = forced("__cortexForceWebgl") === false ? false : webglSupported();
      var a3d = webgl ? mount3D() : null;
      if (a3d) { adapter = a3d; rung = "3d"; }
      else startRung = "cytoscape";              // probe false OR 3D init/first-paint failed → rung 2
    }
    if (!adapter && (startRung === "cytoscape")) {
      var acy = forced("__cortexForceCytoscapeFail") ? null : mountCytoscape();
      if (acy) { adapter = acy; rung = "cytoscape"; }
      else startRung = "list";
    }
    if (!adapter && (startRung === "list")) {
      var al = forced("__cortexForceListFail") ? null : mountList();
      if (al) { adapter = al; rung = "list"; }
      else startRung = "message";
    }
    if (!adapter) { mountMessage(); rung = "message"; }

    document.documentElement.setAttribute("data-cortex-renderer", rung);
    // SWAP the active adapter (codex round-4 [medium]) — a re-entry (a late 3D demotion) replaces the
    // adapter the ONE set of control listeners dispatches to; the stale 3D adapter is dropped, never
    // left bound. Controls are wired exactly once (wireControls is idempotent).
    currentAdapter = adapter;             // null on the message floor → controls no-op
    if (adapter) {
      wireControls();
      // REPLAY the live control state into the freshly mounted adapter (codex round-5 [medium]) — but
      // ONLY when it is NON-DEFAULT (codex round-6 [medium]): on a late demotion where the user had
      // already entered a query / changed filters, re-apply it so the fallback mounts WITH the current
      // hit + filter set. On a DEFAULT first mount (no query, all types, no Earmarked/recency) the
      // adapter already holds the full graph, so skip the replay — calling render() would push the full
      // graph through the renderer a SECOND time (3d-force-graph would reheat the sim + race the
      // first-paint check, burning the M22 budget).
      if (!isDefaultControlState(controlState())) render();
    }
    return rung;
  }

  // isDefaultControlState(state) → true iff no narrowing is active (no query, no type filter, no
  // Earmarked-only, no recency, no Episodic-collapse) — i.e. the adapter's freshly-loaded full graph
  // already matches it. The collapse lever counts as a narrowing: with it engaged, a late demotion
  // must REPLAY it into the fallback (so the haze stays folded) rather than skipping the replay.
  function isDefaultControlState(state) {
    state = state || {};
    var q = String(state.query == null ? "" : state.query).trim();
    return q === "" && state.types == null && !state.earmarkedOnly &&
           !(typeof state.recencyFraction === "number" && state.recencyFraction > 0) &&
           !state.collapseEpisodic;
  }

  mountLadderFrom("3d");
})(typeof globalThis !== "undefined" ? globalThis : this);
