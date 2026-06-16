"""The edge's closed Vega vocabulary — the recipe builders (docs/specs/visual-recipe-set.md).

The writer NEVER emits Vega. The edge owns a small, closed set of vetted RECIPES (Vega/Vega-Lite
spec templates). A block's payload is the edge's OWN tiny schema (data + light config); this module
expands that schema into the chosen recipe's Vega(-Lite) spec dict. `render.py` then hands the spec to
`vl-convert`, the existing sanitizer inlines the SVG.

Each recipe declares its required fields and validates the payload BEFORE building a spec. A malformed
payload (missing/empty data, wrong types) yields a clear error string — the caller fails closed (a
genus comment), never a crash and never a blank chart that still satisfies a presentation floor.

The Vega surface is the spec's auditable allowlist (marks/encodings/transforms). There is NO raw-Vega
passthrough — Vega is an implementation detail behind the block, invisible to the writer.

Pure Python: no I/O, no vl-convert import here (rendering lives in render.py). Import-clean on bare
python3.

Each public builder returns (spec, error):
  - on a valid payload: (spec_dict, None)
  - on a malformed payload: (None, "a clear human reason")
The caller renders `spec` only when `error is None`.
"""
import math
from collections import defaultdict, deque

# The schema version the recipe templates in THIS module were authored against. A payload authored at
# `v` renders under its own `v`'s template semantics (replay stability, ADR-0006/0010). The guarantee is
# SEMANTIC, not byte-level: a recipe change that alters the MEANING of a payload is a new `v` (old `v`
# template retained); a pure visual/toolchain change keeps `v`. We currently ship v=1 for every recipe.
RECIPE_VERSION = 1

# Provenance stamp recorded per render (diagnosis, not a byte-identity promise). render.py reads this.
PROVENANCE = {"recipes": RECIPE_VERSION}


# ===========================================================================
# Validation helpers — small, shared, fail-closed
# ===========================================================================

def _is_number(x):
    """A real number (bool excluded — `True` is not a data value)."""
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _nonempty_list(v):
    return isinstance(v, list) and len(v) > 0


def _nonblank_str(v):
    return isinstance(v, str) and bool(v.strip())


# ===========================================================================
# CHARTS — Vega-Lite spec dicts
# ===========================================================================
#
# Each chart builder validates its payload then returns a Vega-Lite v5 spec. The optional `facet`
# modifier (any field name present on the rows) turns the chart into Tufte small multiples.

def _apply_facet(spec, data, facet_field):
    """Wrap a single-view Vega-Lite spec into faceted small multiples on `facet_field`.

    Validation: the field must be a non-blank string AND present on every row (else the facet would
    silently drop rows / render blank). Returns (spec, None) or (None, reason). When facet_field is
    falsy this is a no-op pass-through.
    """
    if not facet_field:
        return spec, None
    if not _nonblank_str(facet_field):
        return None, "facet must be a non-blank field name"
    for row in data:
        if not isinstance(row, dict) or facet_field not in row:
            return None, f"facet field {facet_field!r} missing from a data row"
    # Lift the encoding/mark into a faceted spec; the inner view keeps the same encoding+mark. The
    # faceted wrapper DROPS top-level width/height (D-F) — so each small-multiple cell must carry its
    # own sizing, else the inner views auto-layout to portrait. Per-cell is smaller (landscape) since
    # there are `columns` of them.
    inner = {"mark": spec["mark"], "encoding": spec["encoding"]}
    cell_w = spec.get("width", 480)
    cell_h = spec.get("height", 300)
    inner["width"] = max(160, cell_w // 2)
    inner["height"] = max(100, int(inner["width"] * (cell_h / cell_w))) if cell_w else 120
    faceted = {
        "$schema": spec["$schema"],
        "data": spec["data"],
        "facet": {"field": facet_field, "type": "nominal"},
        "spec": inner,
        "columns": 2,
    }
    if "title" in spec:
        faceted["title"] = spec["title"]
    return faceted, None


def _vl_base(data_values):
    # Default LANDSCAPE dimensions (D-F) — Vega-Lite auto-layout makes few-category charts tall/narrow
    # portraits (the 288x405 2-bar mess). An explicit landscape default fixes it; sparkline overrides to
    # 120x30 after this, and dag/force build their own Vega specs (untouched).
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "background": "white",
        "width": 480,
        "height": 300,
        "data": {"values": data_values},
    }


def chart_line(payload):
    """line — change over time / a sequence. data:[{x, y, series?}]; x_label?, y_label?, title?, facet?."""
    data = payload.get("data")
    if not _nonempty_list(data):
        return None, "line: `data` must be a non-empty list of {x, y} rows"
    for i, row in enumerate(data):
        if not isinstance(row, dict) or "x" not in row or "y" not in row:
            return None, f"line: data row {i} must be a dict with `x` and `y`"
        if not _is_number(row["y"]):
            return None, f"line: data row {i} `y` must be a number"
    spec = _vl_base(data)
    spec["mark"] = {"type": "line", "point": True}
    enc = {
        "x": {"field": "x", "type": _x_type(data), "title": payload.get("x_label")},
        "y": {"field": "y", "type": "quantitative", "title": payload.get("y_label")},
    }
    if any(isinstance(r, dict) and "series" in r for r in data):
        enc["color"] = {"field": "series", "type": "nominal"}
        enc["detail"] = {"field": "series", "type": "nominal"}
    spec["encoding"] = enc
    if _nonblank_str(payload.get("title")):
        spec["title"] = payload["title"]
    return _apply_facet(spec, data, payload.get("facet"))


def chart_sparkline(payload):
    """sparkline — inline trend dataword. data:[y, y, …] (a flat list of numbers)."""
    data = payload.get("data")
    if not _nonempty_list(data):
        return None, "sparkline: `data` must be a non-empty list of numbers"
    if not all(_is_number(y) for y in data):
        return None, "sparkline: every `data` value must be a number"
    values = [{"i": i, "y": y} for i, y in enumerate(data)]
    spec = _vl_base(values)
    spec["mark"] = {"type": "line"}
    spec["width"] = 120
    spec["height"] = 30
    spec["encoding"] = {
        "x": {"field": "i", "type": "quantitative", "axis": None},
        "y": {"field": "y", "type": "quantitative", "axis": None},
    }
    return spec, None


def chart_bar(payload):
    """bar — magnitude / ranking across categories. data:[{label, value}]; horizontal?, title?, facet?."""
    data = payload.get("data")
    if not _nonempty_list(data):
        return None, "bar: `data` must be a non-empty list of {label, value} rows"
    for i, row in enumerate(data):
        if not isinstance(row, dict) or "label" not in row or "value" not in row:
            return None, f"bar: data row {i} must be a dict with `label` and `value`"
        if not _is_number(row["value"]):
            return None, f"bar: data row {i} `value` must be a number"
    spec = _vl_base(data)
    spec["mark"] = "bar"
    cat = {"field": "label", "type": "nominal"}
    val = {"field": "value", "type": "quantitative"}
    horizontal = bool(payload.get("horizontal"))
    x_enc, y_enc = (val, cat) if horizontal else (cat, val)
    # Honor the producer's in-language axis titles by FINAL axis position (x_label → the x axis,
    # y_label → the y axis) — assign AFTER the orientation swap so a horizontal bar doesn't get the
    # titles crossed. Else Vega shows the raw field names 'label'/'value' (English-ish chrome).
    xt = _axis_safe(payload["x_label"]) if _nonblank_str(payload.get("x_label")) else None
    yt = _axis_safe(payload["y_label"]) if _nonblank_str(payload.get("y_label")) else None
    x_enc = {**x_enc, "axis": {"title": xt}}
    y_enc = {**y_enc, "axis": {"title": yt}}
    if not horizontal:                       # category ticks on x → keep them horizontal (readable)
        x_enc["axis"]["labelAngle"] = 0
    spec["encoding"] = {"x": x_enc, "y": y_enc}
    if _nonblank_str(payload.get("title")):
        spec["title"] = payload["title"]
    return _apply_facet(spec, data, payload.get("facet"))


def chart_scatter(payload):
    """scatter — relationship between two quantities. data:[{x, y, label?}]; x_label?, y_label?, facet?."""
    data = payload.get("data")
    if not _nonempty_list(data):
        return None, "scatter: `data` must be a non-empty list of {x, y} rows"
    for i, row in enumerate(data):
        if not isinstance(row, dict) or "x" not in row or "y" not in row:
            return None, f"scatter: data row {i} must be a dict with `x` and `y`"
        if not _is_number(row["x"]) or not _is_number(row["y"]):
            return None, f"scatter: data row {i} `x` and `y` must be numbers"
    spec = _vl_base(data)
    spec["mark"] = "point"
    enc = {
        "x": {"field": "x", "type": "quantitative", "title": payload.get("x_label")},
        "y": {"field": "y", "type": "quantitative", "title": payload.get("y_label")},
    }
    if any(isinstance(r, dict) and "label" in r for r in data):
        enc["color"] = {"field": "label", "type": "nominal"}
        enc["tooltip"] = {"field": "label", "type": "nominal"}
    spec["encoding"] = enc
    if _nonblank_str(payload.get("title")):
        spec["title"] = payload["title"]
    return _apply_facet(spec, data, payload.get("facet"))


def chart_slopegraph(payload):
    """slopegraph — before/after across many items (Tufte). data:[{item, before, after}].

    Uses the `fold` transform to pivot before/after into a long form, then a line per item.
    """
    data = payload.get("data")
    if not _nonempty_list(data):
        return None, "slopegraph: `data` must be a non-empty list of {item, before, after} rows"
    for i, row in enumerate(data):
        if not isinstance(row, dict) or not {"item", "before", "after"} <= set(row):
            return None, f"slopegraph: data row {i} must have `item`, `before`, `after`"
        if not _is_number(row["before"]) or not _is_number(row["after"]):
            return None, f"slopegraph: data row {i} `before`/`after` must be numbers"
    before_label = payload.get("before_label") or "before"
    after_label = payload.get("after_label") or "after"
    spec = _vl_base(data)
    spec["transform"] = [{"fold": ["before", "after"], "as": ["stage", "value"]}]
    spec["mark"] = {"type": "line", "point": True}
    spec["encoding"] = {
        "x": {
            "field": "stage", "type": "ordinal",
            "scale": {"domain": ["before", "after"]},
            "axis": {"labelExpr": f"datum.value == 'before' ? '{_axis_safe(before_label)}' "
                                  f": '{_axis_safe(after_label)}'", "title": None},
        },
        "y": {"field": "value", "type": "quantitative"},
        "color": {"field": "item", "type": "nominal"},
        "detail": {"field": "item", "type": "nominal"},
    }
    if _nonblank_str(payload.get("title")):
        spec["title"] = payload["title"]
    return spec, None


def _axis_safe(s):
    """Neutralize quotes in a label injected into a Vega-Lite labelExpr string literal."""
    return str(s).replace("'", "")


def _x_type(data):
    """Infer the Vega-Lite x channel type for line: quantitative if every x is numeric, else ordinal."""
    if all(isinstance(r, dict) and _is_number(r.get("x")) for r in data):
        return "quantitative"
    return "ordinal"


# The chart recipe registry — `chart:` discriminator -> builder.
CHART_RECIPES = {
    "line": chart_line,
    "sparkline": chart_sparkline,
    "bar": chart_bar,
    "scatter": chart_scatter,
    "slopegraph": chart_slopegraph,
}


def _resolve_synonyms(payload, block_type):
    """Map the block's documented field synonyms to their canonical names (recipe→chart, rows→data,
    links→edges, …) so the builders see the same fields `render_block` renders — otherwise a gate
    that hands the RAW block to a builder would judge a valid synonym-authored viz non-renderable.
    Lazy import of `render` avoids the render<->visual_recipes import cycle; BLOCK_SCHEMAS is the one
    source of truth for the synonym map."""
    import render  # noqa: PLC0415 — lazy, breaks the import cycle
    syn = render.BLOCK_SCHEMAS.get(block_type, {}).get("synonyms", {})
    if not any(s in payload for s in syn):
        return payload
    out = dict(payload)
    for s, c in syn.items():
        if s in out and c not in out:
            out[c] = out[s]
    return out


def build_chart(payload):
    """Build a Vega-Lite spec for a `chart` block payload. Returns (spec, error).

    Picks the recipe by `payload["chart"]`. An unknown recipe or a malformed payload returns
    (None, reason); the caller fails closed.
    """
    payload = _resolve_synonyms(payload, "chart")
    recipe = payload.get("chart")
    builder = CHART_RECIPES.get(recipe)
    if builder is None:
        return None, f"unknown chart recipe: {recipe!r} (closed set: {sorted(CHART_RECIPES)})"
    return builder(payload)


# ===========================================================================
# DIAGRAMS — full Vega spec dicts (the graph-layout family)
# ===========================================================================
#
# `dag`  — pure-Python Sugiyama-lite layout (lifted from the validated prototype), Vega only DRAWS.
# `force`— Vega's `force` transform for genuinely non-directional connection maps.


def _validate_topology(payload, recipe):
    """Shared nodes/edges validation for diagram recipes. Returns (nodes, edges, None) or (..., reason)."""
    nodes = payload.get("nodes")
    if not _nonempty_list(nodes):
        return None, None, f"{recipe}: `nodes` must be a non-empty list of {{id, label}}"
    seen = set()
    for i, n in enumerate(nodes):
        if not isinstance(n, dict) or "id" not in n:
            return None, None, f"{recipe}: node {i} must be a dict with an `id`"
        nid = n["id"]
        if not _nonblank_str(nid) and not _is_number(nid):
            return None, None, f"{recipe}: node {i} `id` must be a non-blank string or number"
        if nid in seen:
            return None, None, f"{recipe}: duplicate node id {nid!r}"
        seen.add(nid)
    edges = payload.get("edges") or []
    if not isinstance(edges, list):
        return None, None, f"{recipe}: `edges` must be a list of {{source, target}}"
    for i, e in enumerate(edges):
        if not isinstance(e, dict) or "source" not in e or "target" not in e:
            return None, None, f"{recipe}: edge {i} must be a dict with `source` and `target`"
        for k in ("source", "target"):
            # must be a hashable scalar — the layout uses these in set/dict membership; a list/dict
            # would raise TypeError downstream instead of failing closed here.
            if not _nonblank_str(e[k]) and not _is_number(e[k]):
                return None, None, f"{recipe}: edge {i} `{k}` must be a non-blank string or number"
            # endpoint must name a declared node — else the layout silently drops the edge, rendering
            # a diagram with missing relationships that still satisfies the gates. Fail closed instead.
            if e[k] not in seen:
                return None, None, f"{recipe}: edge {i} `{k}` {e[k]!r} is not a declared node id"
    return nodes, edges, None


# ---------------------------------------------------------------------------
# DAG layout — lifted verbatim (semantics) from the validated /tmp/dag-proto prototype.
# Gotchas honored: edges are `rule` marks (not path); arrowhead rotation atan2(dx, -dy); trim edge
# endpoints to node radius; symbol `size` is AREA (=π·r²); width/height from the computed layout;
# cycles handled by dropping back-edges (never a hang).
# ---------------------------------------------------------------------------

def dag_layout(nodes, edges, spacing=120, barycenter=True):
    """Longest-path layered (Sugiyama-lite) layout. Pure Python — no Graphviz, no Vega transform.

    Returns {"pos": {id:(x,y)}, "rank": {id:int}, "width", "height", "edges": acyclic-subset}.
    """
    ids = [n["id"] for n in nodes]
    idset = set(ids)
    first_seen = {nid: i for i, nid in enumerate(ids)}

    succ = defaultdict(list)
    clean_edges = []
    for e in edges:
        s, t = e["source"], e["target"]
        if s in idset and t in idset:
            succ[s].append(t)
            clean_edges.append({"source": s, "target": t})

    # cycle removal: DFS, drop back-edges so ranking terminates (never a hang)
    WHITE, GREY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in ids}
    back_edges = set()

    def dfs(u):
        # iterative DFS (avoid recursion-depth blowups on long chains)
        stack = [(u, iter(succ[u]))]
        color[u] = GREY
        while stack:
            node, it = stack[-1]
            advanced = False
            for v in it:
                if color[v] == WHITE:
                    color[v] = GREY
                    stack.append((v, iter(succ[v])))
                    advanced = True
                    break
                elif color[v] == GREY:
                    back_edges.add((node, v))
            if not advanced:
                color[node] = BLACK
                stack.pop()

    for nid in ids:
        if color[nid] == WHITE:
            dfs(nid)

    acyclic = [e for e in clean_edges
               if (e["source"], e["target"]) not in back_edges]
    asucc = defaultdict(list)
    apred = defaultdict(list)
    indeg = {nid: 0 for nid in ids}
    for e in acyclic:
        asucc[e["source"]].append(e["target"])
        apred[e["target"]].append(e["source"])
        indeg[e["target"]] += 1

    # longest-path rank via Kahn topological order
    rank = {nid: 0 for nid in ids}
    q = deque(sorted([nid for nid in ids if indeg[nid] == 0],
                     key=lambda n: first_seen[n]))
    deg = dict(indeg)
    while q:
        u = q.popleft()
        for v in asucc[u]:
            rank[v] = max(rank[v], rank[u] + 1)
            deg[v] -= 1
            if deg[v] == 0:
                q.append(v)

    by_rank = defaultdict(list)
    for nid in sorted(ids, key=lambda n: first_seen[n]):
        by_rank[rank[nid]].append(nid)
    max_rank = max(rank.values()) if rank else 0

    order = {}
    for r in range(max_rank + 1):
        for i, nid in enumerate(by_rank[r]):
            order[nid] = i

    # deterministic median/barycenter ordering passes to reduce crossings (no-op on trees)
    if barycenter:
        for _ in range(4):
            for r in range(1, max_rank + 1):
                row = by_rank[r]
                key = {}
                for nid in row:
                    ps = apred[nid]
                    key[nid] = (sum(order[p] for p in ps) / len(ps) if ps else order[nid])
                row.sort(key=lambda n: (key[n], first_seen[n]))
                for i, nid in enumerate(row):
                    order[nid] = i
            for r in range(max_rank - 1, -1, -1):
                row = by_rank[r]
                key = {}
                for nid in row:
                    ss = asucc[nid]
                    key[nid] = (sum(order[s] for s in ss) / len(ss) if ss else order[nid])
                row.sort(key=lambda n: (key[n], first_seen[n]))
                for i, nid in enumerate(row):
                    order[nid] = i

    widest = max((len(by_rank[r]) for r in range(max_rank + 1)), default=1)
    pos = {}
    for r in range(max_rank + 1):
        row = by_rank[r]
        offset = (widest - len(row)) / 2.0
        for i, nid in enumerate(row):
            x = (offset + i) * spacing + spacing
            y = r * spacing + spacing
            pos[nid] = (x, y)

    width = (widest + 1) * spacing
    height = (max_rank + 2) * spacing
    return {"pos": pos, "rank": rank, "width": width, "height": height, "edges": acyclic}


def count_crossings(nodes, edges, spacing=120, barycenter=True):
    """Edge-crossing count of the computed layout (a readability metric for the regression fixtures)."""
    lay = dag_layout(nodes, edges, spacing=spacing, barycenter=barycenter)
    pos = lay["pos"]
    segs = [(pos[e["source"]], pos[e["target"]]) for e in lay["edges"]]
    crossings = 0
    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            if _segments_cross(segs[i][0], segs[i][1], segs[j][0], segs[j][1]):
                crossings += 1
    return crossings


def _ccw(a, b, c):
    return (c[1] - a[1]) * (b[0] - a[0]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_cross(p1, p2, p3, p4):
    # share an endpoint → not a crossing (edges from the same node)
    if p1 in (p3, p4) or p2 in (p3, p4):
        return False
    d1 = _ccw(p3, p4, p1)
    d2 = _ccw(p3, p4, p2)
    d3 = _ccw(p1, p2, p3)
    d4 = _ccw(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _edge_geometry(pos, edges, label_of, node_r=22):
    """Per-edge geometry: endpoints trimmed to the node radius + arrowhead angle.

    Vega's origin is top-left, y grows DOWN; the triangle 'symbol' points UP at angle 0, so the
    rotation aligning it with (dx,dy) in screen space is degrees(atan2(dx, -dy)).
    """
    out = []
    for e in edges:
        sx, sy = pos[e["source"]]
        tx, ty = pos[e["target"]]
        dx, dy = tx - sx, ty - sy
        dist = math.hypot(dx, dy) or 1.0
        ux, uy = dx / dist, dy / dist
        x1, y1 = sx + ux * node_r, sy + uy * node_r
        x2, y2 = tx - ux * node_r, ty - uy * node_r
        angle = math.degrees(math.atan2(dx, -dy))
        rec = {"source": e["source"], "target": e["target"],
               "x": x1, "y": y1, "x2": x2, "y2": y2, "ang": angle,
               "mx": (x1 + x2) / 2.0, "my": (y1 + y2) / 2.0}
        lbl = label_of.get((e["source"], e["target"]))
        if _nonblank_str(lbl):
            rec["label"] = lbl
        out.append(rec)
    return out


def diagram_dag(payload):
    """dag — hierarchy AND dependency graph (lifted prototype). Vega DRAWS the computed layout."""
    nodes, edges, err = _validate_topology(payload, "dag")
    if err:
        return None, err
    spacing, node_r = 120, 22
    lay = dag_layout(nodes, edges, spacing=spacing)
    pos = lay["pos"]
    label = {n["id"]: n.get("label", n["id"]) for n in nodes}
    label_of = {(e["source"], e["target"]): e.get("label")
                for e in edges if isinstance(e, dict)}

    node_data = [{"id": n["id"], "label": str(label[n["id"]]),
                  "x": pos[n["id"]][0], "y": pos[n["id"]][1]} for n in nodes]
    edge_data = _edge_geometry(pos, lay["edges"], label_of, node_r=node_r)

    marks = [
        {  # edge lines — `rule` (straight segment x,y → x2,y2), NOT path
            "type": "rule", "from": {"data": "edges"},
            "encode": {"enter": {
                "x": {"field": "x"}, "y": {"field": "y"},
                "x2": {"field": "x2"}, "y2": {"field": "y2"},
                "stroke": {"value": "#888"}, "strokeWidth": {"value": 1.5}}},
        },
        {  # arrowheads — triangle symbol rotated toward target, sitting on the trimmed endpoint
            "type": "symbol", "from": {"data": "edges"},
            "encode": {"enter": {
                "x": {"field": "x2"}, "y": {"field": "y2"},
                "shape": {"value": "triangle"}, "size": {"value": 90},
                "angle": {"field": "ang"}, "fill": {"value": "#888"}}},
        },
        {  # node circles — symbol `size` is AREA (=π·r²)
            "type": "symbol", "from": {"data": "nodes"},
            "encode": {"enter": {
                "x": {"field": "x"}, "y": {"field": "y"},
                "shape": {"value": "circle"},
                "size": {"value": node_r * node_r * math.pi},
                "fill": {"value": "#e8f0fe"}, "stroke": {"value": "#1a73e8"},
                "strokeWidth": {"value": 2}}},
        },
        {  # node labels
            "type": "text", "from": {"data": "nodes"},
            "encode": {"enter": {
                "x": {"field": "x"}, "y": {"field": "y"},
                "text": {"field": "label"},
                "align": {"value": "center"}, "baseline": {"value": "middle"},
                "fontSize": {"value": 11}, "fill": {"value": "#202124"}}},
        },
    ]
    if any("label" in e for e in edge_data):
        marks.insert(1, {  # edge labels at the segment midpoint
            "type": "text", "from": {"data": "edges"},
            "encode": {"enter": {
                "x": {"field": "mx"}, "y": {"field": "my"},
                "text": {"field": "label"},
                "align": {"value": "center"}, "baseline": {"value": "middle"},
                "fontSize": {"value": 9}, "fill": {"value": "#5f6368"}}},
        })

    spec = {
        "$schema": "https://vega.github.io/schema/vega/v5.json",
        "width": lay["width"], "height": lay["height"], "padding": 10,
        "background": "white",
        "data": [{"name": "nodes", "values": node_data},
                 {"name": "edges", "values": edge_data}],
        "marks": marks,
    }
    if _nonblank_str(payload.get("title")):
        spec["title"] = {"text": payload["title"], "anchor": "start", "fontSize": 14}
    return spec, None


def diagram_force(payload):
    """force — connection map (cycles, non-directional, fan-out). Vega `force` transform."""
    nodes, edges, err = _validate_topology(payload, "force")
    if err:
        return None, err
    # Vega force links reference nodes by integer index, so map ids → index.
    index = {n["id"]: i for i, n in enumerate(nodes)}
    node_data = [{"id": n["id"], "label": str(n.get("label", n["id"]))} for n in nodes]
    link_data = [{"source": index[e["source"]], "target": index[e["target"]]}
                 for e in edges if e["source"] in index and e["target"] in index]
    w, h = 400, 400
    spec = {
        "$schema": "https://vega.github.io/schema/vega/v5.json",
        "width": w, "height": h, "padding": 10, "background": "white",
        "data": [
            {
                "name": "link-data", "values": link_data,
            },
            {
                "name": "node-data", "values": node_data,
                "transform": [{
                    "type": "force", "iterations": 300, "static": True,
                    "forces": [
                        {"force": "center", "x": {"signal": "width / 2"}, "y": {"signal": "height / 2"}},
                        {"force": "collide", "radius": 18},
                        {"force": "nbody", "strength": -40},
                        {"force": "link", "links": "link-data", "distance": 80},
                    ],
                }],
            },
        ],
        "marks": [
            {  # edges — linkpath transform draws each link as a path between its endpoints
                "type": "path", "from": {"data": "link-data"},
                "encode": {"enter": {"stroke": {"value": "#aaa"}, "strokeWidth": {"value": 1}}},
                "transform": [{
                    "type": "linkpath", "shape": "line",
                    "sourceX": "datum.source.x", "sourceY": "datum.source.y",
                    "targetX": "datum.target.x", "targetY": "datum.target.y",
                }],
            },
            {  # nodes
                "type": "symbol", "from": {"data": "node-data"},
                "encode": {"enter": {
                    "shape": {"value": "circle"}, "size": {"value": 22 * 22 * math.pi},
                    "fill": {"value": "#e8f0fe"}, "stroke": {"value": "#1a73e8"},
                    "strokeWidth": {"value": 2}},
                    "update": {"x": {"field": "x"}, "y": {"field": "y"}}},
            },
            {  # labels
                "type": "text", "from": {"data": "node-data"},
                "encode": {"enter": {
                    "text": {"field": "label"},
                    "align": {"value": "center"}, "baseline": {"value": "middle"},
                    "fontSize": {"value": 10}, "fill": {"value": "#202124"}},
                    "update": {"x": {"field": "x"}, "y": {"field": "y"}}},
            },
        ],
    }
    if _nonblank_str(payload.get("title")):
        spec["title"] = {"text": payload["title"], "anchor": "start", "fontSize": 14}
    return spec, None


# The diagram recipe registry — `layout:` discriminator -> builder.
DIAGRAM_RECIPES = {
    "dag": diagram_dag,
    "force": diagram_force,
}


def build_diagram(payload):
    """Build a Vega spec for a `diagram` block payload. Returns (spec, error).

    Picks the recipe by `payload["layout"]`. An unknown recipe or a malformed payload returns
    (None, reason); the caller fails closed.
    """
    payload = _resolve_synonyms(payload, "diagram")
    recipe = payload.get("layout")
    builder = DIAGRAM_RECIPES.get(recipe)
    if builder is None:
        return None, f"unknown diagram layout: {recipe!r} (closed set: {sorted(DIAGRAM_RECIPES)})"
    return builder(payload)
