"""Cortex dashboard parity + usage heat overlay (Slice 7) — R10 + R11.

R10 — ONE read surface, no divergence: the /cortex page and the MCP read the SAME group-scoped fold
(cortex_fold) AND carry the SAME provenance markers (tier + context_only via cortex_provenance), so the
two reads cannot diverge. When Slice 5 added the markers to the MCP path, the dashboard inherits them
through the shared derivation — never a forked second read path.

R11 — the READ-ONLY usage heat overlay: when EDGE_CORTEX_USAGE=on, /cortex visualizes hot refs from
state/cortex/usage.jsonl (a render of a NON-AUTHORITATIVE store — N4). It carries NO write affordance
and enters NO fold; OFF (default) it is absent entirely (the A/B is legible to the operator).
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

BLOG = Path(__file__).resolve().parent.parent / "blog"
REPO = Path(__file__).resolve().parent.parent

FIXTURE = {
    "nodes": [
        {"id": "g0", "label": "Genesis", "title": "ed"},
        {"id": "o1", "label": "Objective", "title": "the hub"},
        {"id": "a1", "label": "Artefato", "title": "active-recall"},
        {"id": "e1", "label": "Entity", "title": "memory"},
    ],
    "edges": [{"id": "r0", "source": "g0", "target": "o1", "type": "GROUNDS"}],
}


def _load_server(env):
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    sys.path.insert(0, str(BLOG))
    import importlib
    import server
    importlib.reload(server)
    return server


class TestProvenanceParity(unittest.TestCase):
    """R10 — the dashboard node mapping carries the SAME orthogonal markers as the MCP, from the ONE
    shared derivation (cortex_provenance). The page can no longer present an extracted/low-tier node
    without the markers the MCP shows."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fix = Path(self.tmp.name) / "c.json"
        self.fix.write_text(json.dumps(FIXTURE))
        self.server = _load_server({"EDGE_CORTEX_FIXTURE": str(self.fix), "EDGE_GROUP": "edge-next",
                                    "EDGE_CORTEX_USAGE": None})

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("EDGE_CORTEX_FIXTURE", None)

    def test_map_node_carries_context_only_alongside_trust(self):
        # an Artefato (asserted spine) is order-bearing → context_only false; an Entity (extracted,
        # unknown Medium) is fail-safe context_only → true. The SAME two axes the MCP returns.
        art = self.server._map_node("4:x:0", "Artefato", {"slug": "active-recall"})
        self.assertIn("context_only", art)
        self.assertFalse(art["context_only"])
        ent = self.server._map_node("4:x:1", "Entity", {"name": "memory"})
        self.assertTrue(ent["context_only"], "an extracted Entity is context_only on the page too (C5)")

    def test_map_node_still_carries_the_trust_tier(self):
        # the existing trust axis is untouched — provenance is ADDITIVE, the page keeps its brightness.
        node = self.server._map_node("4:x:2", "Entity", {"name": "memory"})
        self.assertEqual(node["trust"], "extracted")


class TestUsageHeatOverlayR11(unittest.TestCase):
    """R11 — the read-only usage heat overlay, gated by EDGE_CORTEX_USAGE, a render of usage.jsonl with
    no write affordance and no fold entry (N4)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fix = Path(self.tmp.name) / "c.json"
        self.fix.write_text(json.dumps(FIXTURE))
        self.usage = Path(self.tmp.name) / "usage.jsonl"

    def tearDown(self):
        self.tmp.cleanup()
        for k in ("EDGE_CORTEX_FIXTURE", "EDGE_GROUP", "EDGE_CORTEX_USAGE", "EDGE_CORTEX_USAGE_PATH"):
            os.environ.pop(k, None)

    def _server_with_usage(self, on, refs=None):
        import time
        if refs:
            with self.usage.open("w") as f:
                for r in refs:
                    f.write(json.dumps({"ts": time.time(), "tool": "cortex_surf",
                                        "refs": [r], "run_id": "x"}) + "\n")
        return _load_server({
            "EDGE_CORTEX_FIXTURE": str(self.fix), "EDGE_GROUP": "edge-next",
            "EDGE_CORTEX_USAGE": "on" if on else None,
            "EDGE_CORTEX_USAGE_PATH": str(self.usage),
        })

    def test_overlay_absent_when_usage_off(self):
        server = self._server_with_usage(on=False)
        body = server.app.test_client().get("/cortex").data.decode()
        self.assertNotIn("cortex-usage-heat", body,
                         "the heat overlay must be absent when EDGE_CORTEX_USAGE is off (clean baseline)")

    def test_overlay_present_and_read_only_when_usage_on(self):
        server = self._server_with_usage(on=True, refs=["active-recall", "active-recall", "memory"])
        body = server.app.test_client().get("/cortex").data.decode()
        self.assertIn("cortex-usage-heat", body, "the heat overlay renders when usage is on (R11)")
        # READ-ONLY: the overlay carries no form / write affordance (it is a render of a non-auth store)
        # — assert the overlay block holds no <form> or POST action.
        self.assertNotIn("<form", body.split("cortex-usage-heat", 1)[1][:2000].lower(),
                         "the heat overlay must carry NO write affordance (N4)")

    def test_overlay_data_is_the_usage_counts_not_a_graph_write(self):
        server = self._server_with_usage(on=True, refs=["active-recall", "active-recall", "memory"])
        body = server.app.test_client().get("/cortex").data.decode()
        # the hot ref (active-recall, used twice) appears in the overlay data block.
        self.assertIn("active-recall", body)

    def test_usage_overlay_does_not_enter_the_fold(self):
        # N4 — the fold payload is untouched by usage; the overlay is a SEPARATE render of usage.jsonl.
        server = self._server_with_usage(on=True, refs=["active-recall"])
        payload = server.cortex_fold()
        for n in payload["nodes"]:
            self.assertNotIn("usage", n, "the fold must not carry usage data (off-truth-path, N4)")
            self.assertNotIn("heat", n)


if __name__ == "__main__":
    unittest.main()
