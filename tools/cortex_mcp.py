"""cortex_mcp — the standing, READ-ONLY `cortex` MCP server: the Cortex (the edge's own memory) made
pull-able at EVERY step of self-work, not only the wake-time push (REQUISITES-CORTEX-MEMORY, ADR-0014
recall-as-seed). Genotype tool — subject-blind, no identity literals (N2).

The single-shot `claude -p` beat can only reach mid-turn information through a tool call, so the
omnipresent door is a standing MCP server. This is a minimal stdio JSON-RPC 2.0 server (initialize /
tools/list / tools/call ONLY) — zero new runtime deps, no `mcp` SDK (N2), unit-testable with injectable
backends and `EDGE_CORTEX_FIXTURE`.

Four read tools, all group-scoped, all reusing the existing backends (never a forked read path, R10):
  - cortex_recall  → the salient seed subgraph         (recall.recall_subgraph)
  - cortex_surf    → the typed associative peer web     (recall.surf_subgraph, *1..2 hops)
  - cortex_node    → a node + immediate neighbors        (filter server.cortex_fold)
  - cortex_search  → nodes by label/title substring (v1) (filter server.cortex_fold)

Two failure classes, NEVER conflated (ADR-0015, F6/N6):
  - Unresolved identity (no group) FAILS LOUD at startup: the server REFUSES to construct/serve, so an
    unidentified install never darkens silently (which would hide empty/foreign state — the exact
    multi-tenant contamination ADR-0015 forbids). This is NOT the C1 dark path.
  - Transient graph health of a RESOLVED group FAILS DARK per call: a {"dark": true, "leg": "cortex",
    "reason": ...} marker, never a raise (CONTRACT C1, ADR-0011: name the dark leg, never block the beat).

Read-only (F5): no tool writes the graph; all curated writes stay owned by the close/grill (ADR-0008).
"""
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import cortex_usage  # noqa: E402 — the Usage signal: off-truth-path telemetry + A/B re-rank (F7/N4)
import cortex_provenance  # noqa: E402 — the two orthogonal markers on every read (F9/C5)

PROTOCOL_VERSION = "2024-11-05"

# Tool input schemas (MCP tools/list). Minimal + explicit so a caller (and the harness) can validate.
_TOOLS = [
    {
        "name": "cortex_recall",
        "description": ("The seed: the salient subgraph of your own memory rooted at space-0 "
                        "(identity → objective → bets → salient Artefatos → distilled clusters). "
                        "The same content pushed at wake, now pullable mid-turn. Capped small; "
                        "pull deeper with cortex_surf/cortex_node."),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "cortex_surf",
        "description": ("Walk the typed associative peer web from seed Artefato slugs "
                        "(BUILDS_ON|SUPERSEDES|CONTRADICTS|RELATES_TO|CITES, <=2 hops; SERVES "
                        "excluded). Active, agent-controlled navigation: pick the next hop from "
                        "evidence in hand."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "seeds": {"type": "array", "items": {"type": "string"},
                          "description": "Artefato slugs to surf from."},
                "hops": {"type": "integer", "description": "1 or 2 (clamped to 2)."},
            },
            "required": ["seeds"],
        },
    },
    {
        "name": "cortex_node",
        "description": "A node and its immediate neighbors, by ref/slug.",
        "inputSchema": {
            "type": "object",
            "properties": {"ref": {"type": "string", "description": "The node ref/slug."}},
            "required": ["ref"],
        },
    },
    {
        "name": "cortex_search",
        "description": ("Locate nodes by label/title substring (v1: substring — a fallback locator; "
                        "navigation is the primary recall mode)."),
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "A label/title substring."}},
            "required": ["query"],
        },
    },
]

_TOOL_NAMES = {t["name"] for t in _TOOLS}
MAX_HOPS = 2

# R6/N5 — the per-cognition policy as an ALLOWLIST (fail-closed, codex Slice-4 [high]).
#
# THE PRIMARY ENFORCEMENT IS CONFIG-SIDE, NOT HERE (codex Slice-4 [high], honest boundary): a delta/
# world dispatch is given a --mcp-config that registers NO cortex server at all (cortex_config.mcp_config
# returns {} for a non-granted subject) AND the delta SKILL declares `disallowed-tools: mcp__cortex__*`.
# So the world-reading subject never inherits the door in the first place — that is the wall. This
# server-side check is a SECONDARY, best-effort guard: a standing stdio server cannot see a PER-CALLER
# subject over one shared pipe, so it enforces the subject of the PROCESS it was launched as
# (EDGE_CORTEX_SUBJECT, baked per-config). It catches a server mistakenly launched FOR a world subject;
# it cannot, alone, stop a world subagent that inherited a lead-scoped server — which is exactly why the
# config-side omission + skill deny are the v1-required wall, not this check.
#
# The door is GRANTED only to an explicit self-cognition; an explicitly-UNKNOWN subject is DENIED. A
# server with NO subject signal is the LEAD's own default server (the live main() path) — granted.
GRANTED_SUBJECTS = {
    "lead", "recall", "assemble", "wake", "beat", "consolidate",
    "report", "map", "plan", "research", "critique", "discovery", "grill",
    # ticket 05: lazer is a first-class producer (recall/consolidação like every producer).
    "lazer",
}


def _usage_key(node):
    """The ONE durable usage/re-rank key for a node (codex final [P2]): the SLUG when present (the key
    surf/recall record and rerank by — stable across graph rebuilds), else the ref/id. So a node's
    drill-down usage (cortex_node) lands under the SAME key its surf/search usage does, and a later
    surf rerank/heat for that node sees the accumulated signal — no key fragmentation across tools."""
    return node.get("slug") or node.get("ref") or node.get("id")


def _dark(reason):
    """The honest dark marker — the SAME shape the recall brief's dark leg uses (Appendix A). A
    structured value the caller orients away from; NEVER an exception (C1, ADR-0011)."""
    return {"dark": True, "leg": "cortex", "reason": reason}


class CortexServer:
    """The standing read door. Backends are injectable (unit tests pass fixtures; production wires the
    reused recall/fold functions), so the server is testable without a live neo4j or the `mcp` SDK.

    `group` is resolved by the caller (the live entrypoint resolves it LOUD via _identity.require_group
    at startup). A falsy group here means an unidentified install: the constructor RAISES (F6/N6,
    ADR-0015) — the server refuses to serve `cortex_*` at all. Only a RESOLVED group's runtime outage
    is allowed to fail dark, and that is decided per call (a backend returning None / raising)."""

    def __init__(self, group, recall_fn=None, surf_fn=None, fold_fn=None, subject=None, run_id=None):
        if not group:
            # FAIL LOUD — the identity wall (ADR-0015). An unidentified install must not serve a single
            # cortex_* call; a silent dark here would hide empty/foreign state (multi-tenant leak).
            raise RuntimeError(
                "cortex MCP: no graph group resolved — refusing to serve an unidentified install "
                "(set EDGE_GROUP or agent.yaml name/codename; ADR-0015: never silently darken "
                "an unidentified install — that hides empty/foreign state)")
        self.group = group
        # R6/N5 — the subject scope, ALLOWLIST + FAIL-CLOSED (codex final [high]). The door is granted
        # ONLY to an explicit self-cognition in GRANTED_SUBJECTS; ANY other subject — unknown OR
        # MISSING/empty — is DENIED. A missing EDGE_CORTEX_SUBJECT must not default open (that would
        # weaken the defense-in-depth boundary). The generated lead config ALWAYS bakes
        # EDGE_CORTEX_SUBJECT=lead, so the real lead path is granted explicitly; a server with no
        # subject signal at all is treated as untrusted and serves nothing.
        self.subject = subject or os.environ.get("EDGE_CORTEX_SUBJECT")
        s = (self.subject or "").lower()
        self._denied = s not in GRANTED_SUBJECTS
        self.run_id = run_id or os.environ.get("EDGE_RUN_ID")
        self._recall_fn = recall_fn or self._live_recall
        self._surf_fn = surf_fn or self._live_surf
        self._fold_fn = fold_fn or self._live_fold

    def _visible_tools(self):
        """The tools this subject may see — none for a denied (delta/world) subject (R6/N5)."""
        return [] if self._denied else _TOOLS

    # --- live backends (the reuse: never a forked read path, R10) ---------------------------------
    def _live_recall(self, group=None):
        import recall
        return recall.recall_subgraph(group or self.group)

    def _live_surf(self, seeds, group=None):
        import recall
        return recall.surf_subgraph(seeds, group=group or self.group)

    def _live_fold(self):
        sys.path.insert(0, str(REPO / "blog"))
        import server
        return server.cortex_fold(self.group)

    # --- JSON-RPC dispatch ------------------------------------------------------------------------
    def handle(self, msg):
        """Dispatch one JSON-RPC message. A request (has `id`) returns a response object; a
        notification (no `id`) returns None. NEVER raises out (availability is the standing door's
        contract): a malformed envelope is -32600, a bad method -32601, bad params/tool -32602, a
        runtime outage a dark tool result, and any UNEXPECTED internal error -32603 — the process
        survives model-generated bad args or a client bug (codex Slice-2 [medium])."""
        if not isinstance(msg, dict):
            return self._err(None, -32600, "invalid request: not a JSON object")
        method = msg.get("method")
        mid = msg.get("id")
        if "id" not in msg:
            # a notification is the ABSENCE of `id` (e.g. notifications/initialized) — accept, no
            # response. A request carrying an EXPLICIT `id: null` is a request (JSON-RPC permits a null
            # id), and must get a response with id null — never silently dropped (codex Slice-2 [medium]).
            return None
        try:
            if method == "initialize":
                return self._ok(mid, {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "cortex", "version": "1"},
                })
            if method == "tools/list":
                return self._ok(mid, {"tools": self._visible_tools()})
            if method == "tools/call":
                params = msg.get("params") or {}
                if not isinstance(params, dict):
                    raise _ToolError("invalid params: expected an object")
                payload = self._call_tool(params)
                # MCP CallToolResult envelope (codex Slice-4 [high]): a tools/call result is NOT the
                # raw domain payload — it is {content:[{type:text,...}], structuredContent: payload}.
                # A dark leg sets isError=true so the client sees an honest failed-but-structured read.
                return self._ok(mid, {
                    "content": [{"type": "text", "text": json.dumps(payload)}],
                    "structuredContent": payload,
                    "isError": bool(isinstance(payload, dict) and payload.get("dark")),
                })
            return self._err(mid, -32601, f"method not found: {method}")
        except _ToolError as e:
            return self._err(mid, -32602, str(e))
        except Exception as e:  # noqa: BLE001 — the standing server must survive ANY unexpected error
            return self._err(mid, -32603, f"internal error: {type(e).__name__}")

    def _call_tool(self, params):
        name = params.get("name")
        if name not in _TOOL_NAMES:
            raise _ToolError(f"unknown tool: {name}")
        if self._denied:
            # R6/N5 — a denied subject cannot call the door even by name (the deny is not cosmetic).
            raise _ToolError(f"tool denied to subject '{self.subject}': {name}")
        args = params.get("arguments")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            raise _ToolError("invalid arguments: expected an object")
        fn = getattr(self, f"_t_{name}")
        return fn(args)

    @staticmethod
    def _ok(mid, result):
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    @staticmethod
    def _err(mid, code, message):
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}

    # --- the four read tools ----------------------------------------------------------------------
    # Every tool wraps its backend so a runtime outage (None) OR a raising backend darkens THIS leg
    # only (C1) — never the server. The identity wall is already past (constructor); here it is pure
    # runtime fail-dark.
    def _record(self, tool, refs):
        """Append the Usage signal for this read — ONLY when EDGE_CORTEX_USAGE=on, and ALWAYS AFTER
        the result is built/ranked (N3: the current write never affects its own ordering). Off-truth-
        path, non-authoritative, best-effort (N4)."""
        cortex_usage.record(tool, refs, run_id=self.run_id)

    def _t_cortex_recall(self, args):
        try:
            sub = self._recall_fn(group=self.group)
        except Exception as e:  # noqa: BLE001 — defense in depth: a raising backend darkens the leg
            return _dark(f"recall backend error: {type(e).__name__}")
        if sub is None:
            return _dark("graph offline (recall)")
        # F9/R8b — the SEED carries BOTH markers on EVERY returned memory node (the first + most-likely
        # read, the worst place to drop one), INCLUDING the Objective and the Direction bets — the spine
        # head — not only artefatos/clusters (codex final [high]). The spine is asserted; its content is
        # order-bearing by origin UNLESS the node carries a low-tier stamp (authority is orthogonal to
        # trust — a low-tier-stamped Direction is context_only even though asserted). Clusters are the
        # extracted half (context_only fail-safe). Each is normalized to a structured node + marked.
        sub = dict(sub)
        obj = sub.get("objective")
        if obj is not None:
            sub["objective"] = cortex_provenance.mark_node(
                obj if isinstance(obj, dict) else {"body": obj}, label="Objective")
        sub["bets"] = [cortex_provenance.mark_node(
            b if isinstance(b, dict) else {"body": b}, label="Direction")
            for b in (sub.get("bets") or [])]
        sub["artefatos"] = [cortex_provenance.mark_node(a, label="Artefato")
                            for a in (sub.get("artefatos") or [])]
        sub["clusters"] = [cortex_provenance.mark_node(
            {"cluster": c} if not isinstance(c, dict) else c, label="Entity")
            for c in (sub.get("clusters") or [])]
        self._record("cortex_recall", [a.get("slug") for a in sub["artefatos"]])
        return sub

    def _t_cortex_surf(self, args):
        # Validate the schema HERE (codex final [P2]): an omitted/non-list seeds would silently dark,
        # and a STRING seed would be treated as a char-iterable by surf_subgraph — both return no
        # navigation on a HEALTHY graph. A non-empty list of strings is required; bad input is a param
        # error (the caller sees the mistake), not a silent dark.
        seeds = args.get("seeds")
        if not isinstance(seeds, list) or not seeds or not all(isinstance(s, str) and s for s in seeds):
            raise _ToolError("invalid seeds: expected a non-empty list of slug strings")
        hops = args.get("hops", MAX_HOPS)
        try:
            hops = min(max(int(hops), 1), MAX_HOPS)   # clamp to 1..2 (F3 structural bound)
        except (TypeError, ValueError):
            hops = MAX_HOPS
        try:
            peers = self._surf_fn(seeds, group=self.group)
        except Exception as e:  # noqa: BLE001
            return _dark(f"surf backend error: {type(e).__name__}")
        if peers is None:
            return _dark("graph offline (surf)")
        peers = [p for p in peers if p.get("hops") is None or p.get("hops") <= hops]
        # F9 — mark BOTH axes on every surfed peer (tier from labels(n); context_only fail-safe).
        peers = [cortex_provenance.mark_node(p) for p in peers]
        # F7/N3 — re-rank over PRIOR telemetry, THEN record this read (rank before write, so the
        # current call never reinforces its own order). OFF → rerank is a no-op (base hops,slug order).
        peers = cortex_usage.rerank(peers, key="slug")
        self._record("cortex_surf", [p.get("slug") for p in peers])
        return {"nodes": peers, "hops": hops}

    def _t_cortex_node(self, args):
        ref = args.get("ref")
        if not isinstance(ref, str):
            raise _ToolError("invalid ref: expected a string")
        fold = self._safe_fold()
        if fold is None:
            return _dark("graph offline (node)")
        nodes = {n.get("ref") or n.get("id"): n for n in fold.get("nodes", [])}
        # Resolve the lookup by ref/id OR the SLUG/key surf+recall actually return (codex final [P1]):
        # _map_node sets `ref` to uuid/elementId, but cortex_recall/cortex_surf emit Artefato SLUGS, so
        # slug-based drill-down (the advertised navigation flow) must resolve here or it dead-ends on a
        # healthy graph. Build an alias index (ref/id/slug/key) over the fold; the canonical ref wins.
        node = nodes.get(ref) or self._resolve_alias(ref, fold)
        if node is None:
            # a ref absent from a HEALTHY fold is "no such node", not a dark graph.
            return {"node": None, "neighbors": []}
        ref = node.get("ref") or node.get("id")   # normalize to the canonical ref for neighbor lookup
        neighbor_refs = self._neighbor_refs(ref, fold)
        neighbors = [nodes[r] for r in neighbor_refs if r in nodes]
        # F9 — mark BOTH axes on the node AND every neighbor (the fold node carries `label`/props).
        node = cortex_provenance.mark_node(node)
        neighbors = [cortex_provenance.mark_node(nb) for nb in neighbors]
        # F7 — a cortex_node read SURFACES the node AND its neighbors, so the usage signal records ALL
        # of them (codex final [P3]). Record by the SAME durable key surf/recall use — the SLUG when a
        # node has one, else the ref (codex final [P2]): an Artefato's drill-down usage must land under
        # its slug so a later surf rerank/heat for the SAME node sees it (surf/recall rerank by slug).
        self._record("cortex_node", [_usage_key(node)] + [_usage_key(nb) for nb in neighbors])
        return {"node": node, "neighbors": neighbors}

    def _t_cortex_search(self, args):
        q = args.get("query")
        if not isinstance(q, str):
            raise _ToolError("invalid query: expected a string")
        query = q.lower()
        fold = self._safe_fold()
        if fold is None:
            return _dark("graph offline (search)")
        results = []
        for n in fold.get("nodes", []):
            hay = " ".join(str(n.get(f, "")) for f in ("label", "title")).lower()
            if query and query in hay:
                results.append(n)
        # F9 — mark BOTH axes on every search hit.
        results = [cortex_provenance.mark_node(n) for n in results]
        # F7/N3 — re-rank AND record by the SAME derived usage key (codex final [P2]): stamp each row
        # with `_usage_key` (slug-preferred, the key surf/recall use), rerank over PRIOR telemetry by
        # that key, THEN record by it. So prior usage of a node (however surfaced) promotes its search
        # hit too — the A/B re-rank is consistent across all tools, not split by ref-vs-slug.
        for n in results:
            n["_usage_key"] = _usage_key(n)
        results = cortex_usage.rerank(results, key="_usage_key")
        self._record("cortex_search", [n.get("_usage_key") for n in results])
        for n in results:
            n.pop("_usage_key", None)   # an internal ranking field, never part of the returned payload
        return {"results": results}

    # --- fold helpers -----------------------------------------------------------------------------
    def _safe_fold(self):
        """The fold backend, guarded: None (or a raise) → None so the caller darkens this leg."""
        try:
            return self._fold_fn()
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _resolve_alias(ref, fold):
        """Resolve a node by a SLUG/key/title alias (codex final [P1]) — the refs surf/recall emit are
        Artefato slugs, not the uuid/elementId `ref`. First exact match on slug/key wins; falls back to
        a title match. Returns the node or None. Exact-only (no substring) so one slug → one node."""
        for field in ("slug", "key", "title"):
            for n in fold.get("nodes", []):
                if n.get(field) == ref:
                    return n
        return None

    @staticmethod
    def _neighbor_refs(ref, fold):
        """The refs immediately adjacent to `ref` over the fold edges (either direction). Edges carry
        source/target as the node `id`; the fold maps id->ref via _node_ref, so resolve id->ref."""
        id_to_ref = {n.get("id"): (n.get("ref") or n.get("id")) for n in fold.get("nodes", [])}
        ref_to_ids = {}
        for n in fold.get("nodes", []):
            ref_to_ids.setdefault(n.get("ref") or n.get("id"), set()).add(n.get("id"))
        my_ids = ref_to_ids.get(ref, {ref})
        out = []
        seen = set()
        for e in fold.get("edges", []):
            s, t = e.get("source"), e.get("target")
            other = None
            if s in my_ids:
                other = t
            elif t in my_ids:
                other = s
            if other is not None:
                oref = id_to_ref.get(other, other)
                if oref != ref and oref not in seen:
                    seen.add(oref)
                    out.append(oref)
        return out


class _ToolError(Exception):
    """An invalid tool request (unknown tool / bad args) — a JSON-RPC error, NOT a dark leg."""


def _resolve_group_loud():
    """The identity seam (F6/N6, ADR-0015): resolve the install group at startup and FAIL LOUD if
    absent — the server must not serve an unidentified install."""
    import _identity
    return _identity.require_group()


def process_line(server, line):
    """Turn ONE input line into the response object (or None for a blank line / notification). Total:
    a parse failure is a JSON-RPC -32700 parse error (id null), so a client never waits forever on a
    bad frame (codex Slice-2 [medium]); an unexpected handler error is -32603 — the loop never dies."""
    line = line.strip()
    if not line:
        return None
    try:
        msg = json.loads(line)
    except Exception:  # noqa: BLE001 — not only JSONDecodeError: a deeply-nested frame can raise
        # RecursionError, etc. ANY parse failure is a -32700, never a process-killing raise (codex
        # final [P3]) — the standing server's malformed-input availability contract.
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
    try:
        return server.handle(msg)
    except Exception:  # noqa: BLE001 — handle() is already total, but the loop never dies on a bug
        return {"jsonrpc": "2.0", "id": msg.get("id") if isinstance(msg, dict) else None,
                "error": {"code": -32603, "message": "internal error"}}


def serve_stdio(server):
    """The stdio JSON-RPC loop: one JSON message per line in, one response line out (notifications and
    blank lines produce no line). Blocks reading stdin until EOF; the standing-server entrypoint."""
    for line in sys.stdin:
        resp = process_line(server, line)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


def main():
    # Identity resolves ONCE, LOUD, before any call (ADR-0015). An unidentified install exits non-zero
    # at startup — it never serves a single cortex_* call.
    group = _resolve_group_loud()
    # The subject comes from EDGE_CORTEX_SUBJECT, passed through UNCHANGED — NO "lead" fallback (codex
    # final [high]): the live entrypoint must not grant the door without an EXPLICIT subject, or a
    # miswired config (or a direct launch) that omits EDGE_CORTEX_SUBJECT would default OPEN. The
    # generated lead config ALWAYS bakes EDGE_CORTEX_SUBJECT=lead, so the real lead path is granted
    # explicitly; an absent subject fails CLOSED at the server (serves no tools) — the correct posture.
    serve_stdio(CortexServer(group, subject=os.environ.get("EDGE_CORTEX_SUBJECT")))


if __name__ == "__main__":
    main()
