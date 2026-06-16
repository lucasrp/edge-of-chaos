"""cortex MCP server (Slice 2) — the standing read-only door (REQUISITES-CORTEX-MEMORY F1-F6, N1-N2,
Appendix A). A minimal stdio JSON-RPC 2.0 server (initialize / tools/list / tools/call) exposing the
four read tools — cortex_recall (seed), cortex_surf, cortex_node, cortex_search — over the REUSED
recall/fold backends. No `mcp` SDK dependency (N2). Unit-testable with injectable backends so no live
neo4j is needed; the live path wires recall.recall_subgraph / recall.surf_subgraph / server.cortex_fold.

Startup resolves identity at the canonical seam and FAILS LOUD on an unidentified install (F6/N6,
ADR-0015) — the server refuses to serve `cortex_*` at all. Per-call runtime outage of a RESOLVED group
FAILS DARK ({"dark": true, ...}), never raises (C1, ADR-0011). The two failure classes never conflate.
"""
import os
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import cortex_mcp  # noqa: E402


# A small whole-Cortex fold fixture (the cortex_fold shape: {nodes, edges}); injected as fold_fn so
# cortex_node / cortex_search run with no live neo4j. Nodes carry the trust tier per label.
FOLD = {
    "nodes": [
        {"id": "g0", "ref": "g0", "label": "Genesis", "title": "ed", "trust": "space0"},
        {"id": "o1", "ref": "o1", "label": "Objective", "title": "the hub", "trust": "asserted"},
        {"id": "a1", "ref": "a1", "label": "Artefato", "title": "active-recall", "trust": "asserted"},
        {"id": "a2", "ref": "a2", "label": "Artefato", "title": "passive-topk", "trust": "asserted"},
        {"id": "e1", "ref": "e1", "label": "Entity", "title": "memory", "trust": "extracted"},
        {"id": "s1", "ref": "s1", "label": "Source", "title": "arxiv-2606", "trust": "extracted"},
    ],
    "edges": [
        {"id": "r0", "source": "g0", "target": "o1", "type": "GROUNDS"},
        {"id": "r1", "source": "a1", "target": "o1", "type": "SERVES"},
        {"id": "r2", "source": "a1", "target": "e1", "type": "DISTILLS"},
        {"id": "r3", "source": "e1", "target": "s1", "type": "MENTIONS"},
    ],
}

RECALL_SUBGRAPH = {
    "codename": "ed", "voice": "direct", "objective": "mentor the edge PM",
    "bets": ["ship the cortex door"],
    "artefatos": [{"slug": "active-recall", "kernel": "navigation beats top-k"}],
    "clusters": ["Introspective memory"],
}


def _server(**kw):
    """A server with all four backends injected + a resolved group, so no live neo4j is touched."""
    defaults = dict(
        group="edge-test",
        recall_fn=lambda group=None: dict(RECALL_SUBGRAPH),
        surf_fn=lambda seeds, group=None: [
            {"slug": "passive-topk", "kernel": "the baseline", "labels": ["Artefato"], "hops": 1},
            {"slug": "arxiv-2606", "kernel": "MRAgent", "labels": ["Source"], "hops": 2},
        ],
        fold_fn=lambda: dict(FOLD),
    )
    defaults.update(kw)
    return cortex_mcp.CortexServer(**defaults)


def _call(srv, method, params=None, id=1):
    return srv.handle({"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}})


def _tool(srv, name, args=None):
    """Invoke a tool via tools/call and return the parsed structured result (the tool's payload)."""
    resp = _call(srv, "tools/call", {"name": name, "arguments": args or {}})
    return resp["result"]


class JsonRpcEnvelope(unittest.TestCase):
    """initialize / tools/list / tools/call — the only three methods (N2: a minimal JSON-RPC 2.0
    server, no `mcp` SDK)."""

    def test_initialize_advertises_the_protocol_and_server(self):
        resp = _call(_server(), "initialize")
        self.assertEqual(resp["jsonrpc"], "2.0")
        self.assertEqual(resp["id"], 1)
        self.assertIn("protocolVersion", resp["result"])
        self.assertEqual(resp["result"]["serverInfo"]["name"], "cortex")

    def test_tools_list_advertises_the_four_read_tools(self):
        resp = _call(_server(), "tools/list")
        names = {t["name"] for t in resp["result"]["tools"]}
        self.assertEqual(names, {"cortex_recall", "cortex_surf", "cortex_node", "cortex_search"})
        # every tool carries an inputSchema (MCP requires it for tools/call validation)
        for t in resp["result"]["tools"]:
            self.assertIn("inputSchema", t)
            self.assertEqual(t["inputSchema"]["type"], "object")

    def test_unknown_method_returns_a_jsonrpc_error_never_raises(self):
        resp = _call(_server(), "nonexistent/method")
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32601)   # method not found

    def test_tools_call_unknown_tool_returns_an_error(self):
        resp = _call(_server(), "tools/call", {"name": "cortex_delete", "arguments": {}})
        self.assertIn("error", resp)

    def test_notifications_initialized_is_accepted_with_no_response(self):
        # a JSON-RPC notification (ABSENCE of id) must not get a response object back
        resp = _server().handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertIsNone(resp)

    def test_a_request_with_explicit_null_id_still_gets_a_response(self):
        # JSON-RPC permits a null id on a REQUEST — notification is the ABSENCE of id, not a null
        # value. A request carrying id:null must get a response (id null), never be dropped (codex
        # Slice-2 [medium]: else a client waits forever on a parseable frame).
        resp = _server().handle({"jsonrpc": "2.0", "id": None, "method": "tools/list"})
        self.assertIsNotNone(resp, "an explicit null id is a request, not a notification")
        self.assertIsNone(resp["id"])
        self.assertIn("tools", resp["result"])


class TheFourReadTools(unittest.TestCase):
    """The four read tools return correct group-scoped data against the injected backends
    (Appendix A acceptance a)."""

    def test_cortex_recall_returns_the_salient_seed(self):
        out = _tool(_server(), "cortex_recall")
        self.assertEqual(out["codename"], "ed")
        self.assertEqual(out["objective"], "mentor the edge PM")
        self.assertIn("active-recall", [a["slug"] for a in out["artefatos"]])

    def test_cortex_surf_returns_the_typed_peers(self):
        out = _tool(_server(), "cortex_surf", {"seeds": ["active-recall"], "hops": 2})
        slugs = {n["slug"] for n in out["nodes"]}
        self.assertEqual(slugs, {"passive-topk", "arxiv-2606"})

    def test_cortex_surf_caps_hops_at_two(self):
        # F3: hops <= 2 is the structural bound; a caller asking for more is clamped, never honored.
        captured = {}

        def surf(seeds, group=None):
            return []

        srv = _server(surf_fn=surf)
        out = _tool(srv, "cortex_surf", {"seeds": ["x"], "hops": 9})
        # the tool reports the effective (clamped) hops so the bound is observable
        self.assertLessEqual(out["hops"], 2)

    def test_cortex_node_returns_a_node_and_its_immediate_neighbors(self):
        out = _tool(_server(), "cortex_node", {"ref": "a1"})
        self.assertEqual(out["node"]["ref"], "a1")
        neighbor_refs = {n["ref"] for n in out["neighbors"]}
        # a1 neighbors: o1 (SERVES), e1 (DISTILLS) — directly adjacent in the fold
        self.assertEqual(neighbor_refs, {"o1", "e1"})

    def test_cortex_node_unknown_ref_returns_empty_not_dark(self):
        # a ref absent from a HEALTHY fold is "no such node", not a dark graph
        out = _tool(_server(), "cortex_node", {"ref": "nope"})
        self.assertIsNone(out["node"])
        self.assertEqual(out["neighbors"], [])
        self.assertNotIn("dark", out)

    def test_cortex_search_finds_nodes_by_label_substring(self):
        # F4 v1: case-insensitive label/title substring over the fold.
        out = _tool(_server(), "cortex_search", {"query": "recall"})
        refs = {n["ref"] for n in out["results"]}
        self.assertIn("a1", refs)            # title "active-recall" contains "recall"
        self.assertNotIn("a2", refs)         # "passive-topk" does not

    def test_cortex_search_is_case_insensitive(self):
        out = _tool(_server(), "cortex_search", {"query": "ARXIV"})
        refs = {n["ref"] for n in out["results"]}
        self.assertIn("s1", refs)


class MalformedRequestsNeverCrashTheServer(unittest.TestCase):
    """The standing server must survive malformed-but-valid JSON-RPC (model-generated bad args / a
    client bug): a bad envelope/params/arguments is a JSON-RPC error, never a process-killing raise
    (codex Slice-2 [medium]). Availability is the contract for a STANDING door."""

    def test_params_as_a_list_is_an_invalid_params_error_not_a_crash(self):
        srv = _server()
        resp = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": []})
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32602)

    def test_arguments_as_non_object_is_an_error_not_a_crash(self):
        srv = _server()
        resp = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": "cortex_search", "arguments": "oops"}})
        self.assertIn("error", resp)

    def test_a_non_string_ref_does_not_crash_the_server(self):
        # cortex_node with a list ref must not raise out of handle() (TypeError on nodes.get(ref))
        srv = _server()
        resp = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": "cortex_node", "arguments": {"ref": ["a", "b"]}}})
        # either a structured result or a JSON-RPC error — never an uncaught exception
        self.assertTrue("result" in resp or "error" in resp)

    def test_malformed_json_on_stdio_returns_a_parse_error_not_silence(self):
        # a bad JSON frame must get a -32700 parse-error response (id null), never silent drop — a
        # client that sent a bad frame must not wait forever (codex Slice-2 [medium]).
        resp = cortex_mcp.process_line(_server(), '{"jsonrpc": "2.0" BROKEN')
        self.assertIsNotNone(resp)
        self.assertEqual(resp["error"]["code"], -32700)
        self.assertIsNone(resp["id"])

    def test_blank_line_produces_no_response(self):
        self.assertIsNone(cortex_mcp.process_line(_server(), "   "))

    def test_process_line_routes_a_valid_request(self):
        resp = cortex_mcp.process_line(_server(), '{"jsonrpc":"2.0","id":7,"method":"tools/list"}')
        self.assertEqual(resp["id"], 7)
        self.assertIn("tools", resp["result"])

    def test_an_unexpected_internal_error_becomes_jsonrpc_32603_not_a_crash(self):
        # a tool handler that raises an UNEXPECTED (non-dark, non-ToolError) exception must be caught
        # at the envelope and returned as -32603, never propagated out of handle().
        srv = _server()
        orig = srv._t_cortex_recall
        srv._t_cortex_recall = lambda args: (_ for _ in ()).throw(KeyError("boom"))
        try:
            resp = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                               "params": {"name": "cortex_recall", "arguments": {}}})
            self.assertIn("error", resp)
            self.assertEqual(resp["error"]["code"], -32603)
        finally:
            srv._t_cortex_recall = orig


class SubjectScopeDenyAtTheServer(unittest.TestCase):
    """R6/N5 — the per-cognition deny is enforceable at the server, not only by config. A server
    constructed for a delta/world subject WITHHOLDS the door: tools/list is empty and tools/call is
    refused. The lead/recall subject (default) sees all four. This is the server-side half of the
    Appendix-A acceptance (c) negative tools/list; the config allowlist (Slice 6) is the harness half."""

    def test_a_delta_subject_gets_no_cortex_tools(self):
        srv = _server(subject="delta")
        resp = _call(srv, "tools/list")
        self.assertEqual(resp["result"]["tools"], [],
                         "the delta/world subject must be DENIED cortex_* (ADR-0014 self/world wall)")

    def test_a_world_subject_call_is_refused(self):
        srv = _server(subject="delta")
        resp = _call(srv, "tools/call", {"name": "cortex_recall", "arguments": {}})
        self.assertIn("error", resp)

    def test_the_lead_subject_sees_all_four_tools(self):
        for subj in (None, "lead", "recall", "report"):
            with self.subTest(subject=subj):
                srv = _server(subject=subj)
                names = {t["name"] for t in _call(srv, "tools/list")["result"]["tools"]}
                self.assertEqual(names, {"cortex_recall", "cortex_surf", "cortex_node", "cortex_search"})


class FailLoudIdentityFailDarkRuntime(unittest.TestCase):
    """F6/N6 — the two failure classes never conflate. Absent identity FAILS LOUD at startup (the
    server refuses to construct/serve); a resolved group's transient outage FAILS DARK per call."""

    def test_unidentified_install_fails_loud_at_startup(self):
        # no group resolves -> constructing the server raises (ADR-0015: never silently darken an
        # unidentified install — that hides empty/foreign state). This is NOT the C1 dark path.
        with self.assertRaises(Exception):
            cortex_mcp.CortexServer(group=None,
                                    recall_fn=lambda group=None: {}, surf_fn=lambda s, group=None: [],
                                    fold_fn=lambda: FOLD)

    def test_runtime_outage_of_a_resolved_group_fails_dark_never_raises(self):
        # a RESOLVED group whose backend returns None (neo4j down/slow) -> a dark marker, never a raise
        srv = _server(recall_fn=lambda group=None: None,
                      surf_fn=lambda seeds, group=None: None,
                      fold_fn=lambda: None)
        for name, args in (("cortex_recall", {}), ("cortex_surf", {"seeds": ["x"]}),
                           ("cortex_node", {"ref": "x"}), ("cortex_search", {"query": "x"})):
            with self.subTest(tool=name):
                out = _tool(srv, name, args)
                self.assertTrue(out.get("dark"), f"{name} must fail DARK on a resolved-group outage")
                self.assertEqual(out["leg"], "cortex")

    def test_a_raising_backend_still_fails_dark_never_propagates(self):
        # defense in depth: even a backend that RAISES darkens this leg, never crashes the server (C1)
        def boom(*a, **k):
            raise RuntimeError("graph exploded mid-query")
        srv = _server(recall_fn=boom, surf_fn=boom, fold_fn=boom)
        out = _tool(srv, "cortex_recall")
        self.assertTrue(out.get("dark"))


class FixtureSeam(unittest.TestCase):
    """The live fold path honors EDGE_CORTEX_FIXTURE (the existing cortex_fold seam), so the server is
    exercisable end-to-end with no live neo4j — the door reuses cortex_fold, never a forked read (R10)."""

    def test_live_fold_reads_the_cortex_fixture(self):
        import json as _json
        import tempfile
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        tmp.write(_json.dumps(FOLD))
        tmp.close()
        os.environ["EDGE_CORTEX_FIXTURE"] = tmp.name
        try:
            # only the fold backend is live; recall/surf stay injected (their live path needs neo4j)
            srv = cortex_mcp.CortexServer(group="edge-test",
                                          recall_fn=lambda group=None: dict(RECALL_SUBGRAPH),
                                          surf_fn=lambda seeds, group=None: [])
            out = _tool(srv, "cortex_node", {"ref": "a1"})
            self.assertEqual(out["node"]["ref"], "a1")
        finally:
            os.environ.pop("EDGE_CORTEX_FIXTURE", None)
            os.unlink(tmp.name)


class BoundedLatencyFailDark(unittest.TestCase):
    """N1/R3 — every cortex_* call is latency-bounded: a slow/absent graph darkens within a budget,
    never blocks the beat. The shared neo4j seams open the driver with explicit connection timeouts
    (the dark marker IS the timeout's value), and the MCP tool wrappers turn None into the dark marker."""

    def test_shared_session_driver_sets_an_explicit_connection_timeout(self):
        # the reused _session seam (R7) — and so every tool that rides it — must bound the connect,
        # or a slow TCP/pool-acquire hangs the standing server. The timeouts come from _driver_kwargs;
        # assert the seam carries a bounded budget AND _session opens the driver with it.
        import inspect
        import recall
        kw = recall._driver_kwargs()
        self.assertIn("connection_acquisition_timeout", kw,
                      "the shared driver must bound connection acquisition (N1/R3), not block forever")
        self.assertIn("connection_timeout", kw, "and bound the TCP connect")
        self.assertGreater(kw["connection_acquisition_timeout"], 0)
        self.assertIn("_driver_kwargs()", inspect.getsource(recall._session),
                      "_session must open the driver with the bounded budget")

    def test_cortex_fold_live_driver_sets_an_explicit_connection_timeout(self):
        # cortex_node/cortex_search ride cortex_fold's live driver — it too must bound the connect.
        import inspect
        sys.path.insert(0, str(REPO / "blog"))
        import server
        src = inspect.getsource(server._cortex_live)
        self.assertIn("connection_acquisition_timeout", src,
                      "the live fold driver must bound connection acquisition (N1/R3)")

    def test_cortex_fold_live_queries_carry_a_server_side_query_timeout(self):
        # the fold queries that back cortex_node/cortex_search must ALSO bound QUERY execution, not
        # only the connect — a connected-but-stalling query must darken within the budget (codex
        # Slice-2 [high]). Pinned on the live path the runtime executes.
        import inspect
        sys.path.insert(0, str(REPO / "blog"))
        import server
        src = inspect.getsource(server._cortex_live)
        self.assertIn("Query(", src, "the fold queries must ride neo4j.Query(..., timeout=budget)")
        self.assertIn("timeout=budget", src,
                      "the fold queries must carry the server-side execution timeout (N1/R3)")

    def test_an_unreachable_graph_darkens_within_a_bounded_budget(self):
        # an unreachable URI must yield the dark marker promptly (the timeout's value), never hang.
        import time
        import recall
        srv = cortex_mcp.CortexServer(
            group="edge-test",
            recall_fn=lambda group=None: recall.recall_subgraph(group, uri="bolt://10.255.255.1:7687"),
            surf_fn=lambda seeds, group=None: [],
            fold_fn=lambda: {"nodes": [], "edges": []})
        t0 = time.time()
        out = _tool(srv, "cortex_recall")
        elapsed = time.time() - t0
        self.assertTrue(out.get("dark"), "an unreachable graph must fail dark, never return live data")
        self.assertLess(elapsed, 20, "the dark must come within a bounded budget, not block the beat")


class UsageSignalWiring(unittest.TestCase):
    """Slice 3 — the four tools record the Usage signal (off-truth-path, F7/N4) and surf/search apply
    the read-time re-rank, all behind EDGE_CORTEX_USAGE. OFF: no write, no re-rank. The current write
    never affects its own ordering (rank before record, N3). Acceptance (d)+(e)."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Path(self.tmp.name) / "usage.jsonl"
        os.environ["EDGE_CORTEX_USAGE_PATH"] = str(self.store)
        os.environ.pop("EDGE_CORTEX_USAGE", None)

    def tearDown(self):
        self.tmp.cleanup()
        for k in ("EDGE_CORTEX_USAGE", "EDGE_CORTEX_USAGE_PATH"):
            os.environ.pop(k, None)

    def test_usage_off_writes_nothing_and_leaves_base_order(self):
        # acceptance (d): OFF == no write AND no re-rank.
        srv = _server()
        out = _tool(srv, "cortex_surf", {"seeds": ["active-recall"]})
        self.assertEqual([n["slug"] for n in out["nodes"]], ["passive-topk", "arxiv-2606"])  # base order
        _tool(srv, "cortex_recall")
        _tool(srv, "cortex_node", {"ref": "a1"})
        _tool(srv, "cortex_search", {"query": "arxiv"})
        self.assertFalse(self.store.exists(), "OFF must write no telemetry on ANY read path")

    def test_usage_on_appends_one_line_per_read(self):
        os.environ["EDGE_CORTEX_USAGE"] = "on"
        srv = _server()
        _tool(srv, "cortex_surf", {"seeds": ["active-recall"]})
        _tool(srv, "cortex_search", {"query": "arxiv"})
        lines = self.store.read_text().strip().splitlines()
        self.assertEqual(len(lines), 2)
        tools = {__import__("json").loads(l)["tool"] for l in lines}
        self.assertEqual(tools, {"cortex_surf", "cortex_search"})

    def test_usage_on_diverges_from_off_once_a_result_has_history(self):
        # acceptance (d): ON re-orders the SAME set by prior usage; here arxiv-2606 has prior history,
        # so it sorts ahead of passive-topk — DIVERGING from the OFF base order.
        import json as _json
        import time as _time
        with self.store.open("w") as f:
            for _ in range(5):
                f.write(_json.dumps({"ts": _time.time(), "tool": "cortex_surf",
                                     "refs": ["arxiv-2606"], "run_id": "prior"}) + "\n")
        os.environ["EDGE_CORTEX_USAGE"] = "on"
        out = _tool(_server(), "cortex_surf", {"seeds": ["active-recall"]})
        self.assertEqual(out["nodes"][0]["slug"], "arxiv-2606",
                         "ON must promote a ref with prior usage ahead of the base hops/slug order")

    def test_a_dark_read_records_nothing(self):
        # a dark leg surfaced no refs — it reinforces nothing (no usage line for an outage).
        os.environ["EDGE_CORTEX_USAGE"] = "on"
        srv = _server(surf_fn=lambda seeds, group=None: None)
        out = _tool(srv, "cortex_surf", {"seeds": ["x"]})
        self.assertTrue(out.get("dark"))
        self.assertFalse(self.store.exists(), "a dark read must not write a usage line")


class ReadOnlyNoWritePath(unittest.TestCase):
    """F5/N4 — the door is read-only: no tool exposes a write, and the server holds no graph-mutating
    method (the boundary is the tool-name set + the absence of any write surface)."""

    def test_no_tool_name_implies_a_write(self):
        resp = _call(_server(), "tools/list")
        names = {t["name"] for t in resp["result"]["tools"]}
        for verb in ("write", "set", "delete", "create", "update", "merge", "fold", "promote"):
            self.assertFalse(any(verb in n for n in names),
                             f"no read-door tool may carry a write verb ({verb})")


if __name__ == "__main__":
    unittest.main()
