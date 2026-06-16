"""Cortex-v1 (brick-1) — recall-surf-query: the ASSOCIATIVE-ONLY, HUB-EXCLUDED, bounded recall
traversal (schema report `the-graph-you-filled-like-a-list`, move 2: "surf associative edges only;
exclude SERVES/Direction/Entity; bound hops *1..2").

`surf_subgraph` is the topology read a SELECT cannot do: from a seed Artefato it walks the typed
peer web (BUILDS_ON|SUPERSEDES|CONTRADICTS|RELATES_TO|CITES, *1..2 hops, direction-agnostic) and
returns the reachable Artefatos/Sources. SERVES — the degree-44 classification spine — is excluded
STRUCTURALLY, by omission from the allowlist: the hub that "reaches everything and therefore
discriminates nothing" is never a pass-through hop.

The seam (research `cosine-nominates-the-author-disposes`, R1): surf_subgraph also OFFERS candidate
priors for the producer to author typed lineage FROM — "recall surfs candidate priors and the
producer authors+types FROM them." Wiring it into the authoring context is the L6 doc instruction,
not this code change.

Degrade contract is recall_subgraph's, verbatim (CONTRACT C1, ADR-0011): a dark graph yields None,
NEVER a crash. No ranking weight in v1 (ORDER BY hops, slug only; the 1/|P| hub-damping rank is OUT).
"""
import inspect
import os
import re
import sys
import unittest
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import recall  # noqa: E402


def _neo4j_reachable():
    """True iff the install's Neo4j is reachable — gates the live surf test. Offline/CI degrades to
    skip, never fails (mirrors tests/test_publisher.py)."""
    try:
        import _identity
        from neo4j import GraphDatabase
        uri, user, pw = _identity.neo4j_conn()
        _identity.require_group()
        drv = GraphDatabase.driver(uri, auth=(user, pw))
        drv.verify_connectivity()
        drv.close()
        return True
    except Exception:  # noqa: BLE001 — no graph → skip the live test
        return False


_NEO4J = _neo4j_reachable()


class SurfQueryIsAssociativeOnly(unittest.TestCase):
    """The SURF_QUERY constant is the associative-only, hub-excluded allowlist — asserted on the
    QUERY the runtime executes, not on function source (review-proven: a comment once satisfied a
    substring while the live query regressed)."""

    def test_surf_query_is_associative_only(self):
        q = recall.SURF_QUERY
        # the allowlist is PINNED EXACTLY — extract the rel-type alternation the runtime walks
        # ([:A|B|C*1..2]) and assert the set equals the five associative types and nothing else.
        # A bare assertIn loop would silently pass a smuggled sixth (non-SERVES) relation; the
        # set-equality closes the allowlist so any addition/removal trips this test (review FIX-1).
        m = re.search(r"\[:([A-Z_|]+)\*1\.\.2\]", q)
        self.assertIsNotNone(m, "the surf must walk a bounded typed-relation alternation [:..*1..2]")
        rels = set(m.group(1).split("|"))
        self.assertEqual(
            rels, {"BUILDS_ON", "SUPERSEDES", "CONTRADICTS", "RELATES_TO", "CITES"},
            "the surf allowlist must be EXACTLY the five associative types — no more, no fewer")
        # bounded hops *1..2 (a multi-hop reach, not the whole graph)
        self.assertIn("*1..2", q, "the surf must bound the walk to *1..2 hops")
        # the hub is excluded STRUCTURALLY, by omission — SERVES is never a pass-through hop
        self.assertNotIn("SERVES", q,
                         "SERVES (the degree-44 hub) must be excluded from the surf allowlist")
        # no ranking weight in v1 — ORDER BY hops, slug only (the 1/|P| hub-damping rank is OUT)
        self.assertIn("ORDER BY hops", q, "v1 orders by hops, slug only — no ranking weight")
        # surf_subgraph executes the guarded constant, not an inline copy
        src = inspect.getsource(recall.surf_subgraph)
        self.assertIn("s.run(_q(SURF_QUERY)", src,
                      "surf_subgraph must execute SURF_QUERY (timeout-wrapped, N1/R3), "
                      "not an inline copy")

    def test_surf_query_scopes_the_path_wide_not_just_endpoints(self):
        # R7b / GitHub #41 — the variable-length *1..2 walk must constrain EVERY node on the path
        # to the group, not only `seed` and the terminal `n`. On the SHARED neo4j a foreign
        # INTERMEDIATE bridge node could route which same-group peers surface — a cross-install
        # topology leak that looks scoped (rows same-group) while the traversal was contaminated.
        # Pinned on the QUERY constant the runtime executes (review-proven: a comment is not the query).
        q = recall.SURF_QUERY
        self.assertIn("all(x IN nodes(p) WHERE x.group_id=$g)", q,
                      "the surf must constrain EVERY node on the *1..2 path to the group (R7b/#41), "
                      "not only the seed and the terminal node")

    def test_surf_does_not_touch_the_recall_spine_constants(self):
        # surgical: the surf is ADDITIVE — the existing recall constants are untouched.
        self.assertIn("SERVES", recall.ARTEFATOS_QUERY,
                      "the existing recall spine (ARTEFATOS_QUERY) still reaches via SERVES")
        self.assertIn(":Genesis", recall.SPINE_QUERY)
        self.assertIn("DISTILLS", recall.CLUSTERS_QUERY)


class SurfDegradesToNoneOffline(unittest.TestCase):
    """surf_subgraph reuses recall_subgraph's degrade scaffolding verbatim (CONTRACT C1): no group,
    no driver, or an unreachable graph all yield None — it NEVER raises."""

    def test_surf_degrades_to_none_offline(self):
        # unreachable URI -> None, no raise (the genuine dark-graph path)
        self.assertIsNone(recall.surf_subgraph(["A"], uri="bolt://127.0.0.1:1"))

    def test_surf_degrades_to_none_without_seeds(self):
        self.assertIsNone(recall.surf_subgraph([]))
        self.assertIsNone(recall.surf_subgraph(None))

    def test_surf_degrades_to_none_when_identity_resolution_raises(self):
        # Identity/credential resolution is INSIDE the guard (review FIX-2): a misconfigured install
        # where _identity.group() (or neo4j_password()) raises must darken this leg, never propagate.
        # The fallbacks only fire when the arg AND the env are empty, so clear the env to force them.
        def _boom():
            raise RuntimeError("no identity here")
        cases = {"group": "EDGE_GROUP", "neo4j_password": "EDGE_NEO4J_PASSWORD"}
        for attr, env in cases.items():
            with self.subTest(attr=attr):
                orig = getattr(recall._identity, attr)
                saved_env = os.environ.pop(env, None)
                setattr(recall._identity, attr, _boom)
                try:
                    # group=None forces _identity.group(); password=None forces neo4j_password()
                    self.assertIsNone(recall.surf_subgraph(["A"]))
                finally:
                    setattr(recall._identity, attr, orig)
                    if saved_env is not None:
                        os.environ[env] = saved_env


@unittest.skipUnless(_NEO4J, "neo4j not reachable (live surf-traversal test)")
class SurfWalksTheAssociativeWebNotTheHub(unittest.TestCase):
    """LIVE: seed A-[:BUILDS_ON]->B-[:RELATES_TO]-C plus a SERVES hub over A,B,C,D. surf_subgraph
    (["A"]) must return {B, C} (reached via the associative web within *1..2) and NEVER D (reachable
    ONLY through the SERVES hub). Uses dedicated `cv1s-*` slugs + a `cv1s-obj` Objective, and
    DETACH-DELETEs them on teardown so it leaves the install graph clean."""

    A, B, C, D = "cv1s-a", "cv1s-b", "cv1s-c", "cv1s-d"
    OBJ = "cv1s-obj"

    def _session(self):
        import _identity
        from neo4j import GraphDatabase
        uri, user, pw = _identity.neo4j_conn()
        self._g = _identity.require_group()
        self._uri, self._user, self._pw = uri, user, pw
        self._drv = GraphDatabase.driver(uri, auth=(user, pw))
        return self._drv.session()

    def _cleanup(self, s):
        s.run("MATCH (a:Artefato {group_id:$g}) WHERE a.slug IN $slugs DETACH DELETE a",
              g=self._g, slugs=[self.A, self.B, self.C, self.D])
        s.run("MATCH (o:Objective {group_id:$g, slug:$slug}) DETACH DELETE o",
              g=self._g, slug=self.OBJ)

    def setUp(self):
        self.s = self._session()
        self._cleanup(self.s)
        # the associative web: A -BUILDS_ON-> B -RELATES_TO- C (1 and 2 hops from A)
        self.s.run(
            "MERGE (a:Artefato {group_id:$g, slug:$A}) "
            "MERGE (b:Artefato {group_id:$g, slug:$B}) "
            "MERGE (c:Artefato {group_id:$g, slug:$C}) "
            "MERGE (a)-[:BUILDS_ON]->(b) "
            "MERGE (b)-[:RELATES_TO]->(c)",
            g=self._g, A=self.A, B=self.B, C=self.C)
        # the hub: a SERVES star over A, B, C AND D — D hangs ONLY off the hub, no peer edge.
        self.s.run(
            "MERGE (o:Objective {group_id:$g, slug:$OBJ}) "
            "MERGE (d:Artefato {group_id:$g, slug:$D}) "
            "WITH o "
            "MATCH (x:Artefato {group_id:$g}) WHERE x.slug IN $slugs "
            "MERGE (x)-[:SERVES]->(o)",
            g=self._g, OBJ=self.OBJ, D=self.D, slugs=[self.A, self.B, self.C, self.D])

    def tearDown(self):
        try:
            self._cleanup(self.s)
        finally:
            self.s.close()
            self._drv.close()

    def test_surf_returns_the_associative_reach_never_the_hub_only_node(self):
        out = recall.surf_subgraph([self.A], group=self._g,
                                   uri=self._uri, user=self._user, password=self._pw)
        self.assertIsNotNone(out, "a reachable graph must surf, not degrade")
        slugs = {n["slug"] for n in out}
        self.assertIn(self.B, slugs, "B is 1 hop via BUILDS_ON — must be surfed")
        self.assertIn(self.C, slugs, "C is 2 hops via BUILDS_ON+RELATES_TO — must be surfed")
        self.assertNotIn(self.D, slugs,
                         "D hangs ONLY off the SERVES hub — must NEVER be surfed (hub excluded)")
        self.assertNotIn(self.A, slugs, "the seed is not its own neighbour")


@unittest.skipUnless(_NEO4J, "neo4j not reachable (live foreign-bridge isolation test)")
class SurfPathIsScopedAgainstAForeignBridge(unittest.TestCase):
    """R7b / GitHub #41 — LIVE isolation: a same-group A and C, joined ONLY through a FOREIGN
    intermediate bridge B (a different group_id), via associative edges A-[:RELATES_TO]-B(foreign)
    -[:RELATES_TO]-C. Without path-wide scoping the *1..2 walk routes A→B→C and C surfaces — a
    cross-install topology leak. With `all(x IN nodes(p) WHERE x.group_id=$g)`, B is off-path, so C
    must NOT surface through the foreign bridge.

    Cross-tenant-SAFE on the shared neo4j (codex Slice-1 [medium]): the foreign group AND every node
    carry a UNIQUE per-run marker (`_run`), and cleanup deletes ONLY nodes carrying THIS run's marker
    — never a fixed foreign group id, never an unqualified DELETE of data outside the install. So the
    test that PROVES isolation cannot itself mutate another install's brain."""

    def _session(self):
        import _identity
        from neo4j import GraphDatabase
        uri, user, pw = _identity.neo4j_conn()
        self._g = _identity.require_group()
        self._uri, self._user, self._pw = uri, user, pw
        self._drv = GraphDatabase.driver(uri, auth=(user, pw))
        return self._drv.session()

    def _cleanup(self, s):
        # marker-scoped: delete ONLY this run's synthetic nodes (mine + foreign), never a fixed
        # foreign group — so a collision with real data is impossible (codex Slice-1 [medium]).
        s.run("MATCH (n {test_marker:$m}) DETACH DELETE n", m=self._run)

    def setUp(self):
        self._run = "cv1b-" + uuid.uuid4().hex[:12]          # unique per run
        self._fg = self._run + "-foreign-group"              # a foreign group that exists only now
        self.A, self.C = self._run + "-a", self._run + "-c"
        self.BRIDGE = self._run + "-bridge"
        self.s = self._session()
        self._cleanup(self.s)
        # A (mine) -RELATES_TO- B (FOREIGN) -RELATES_TO- C (mine): C is reachable from A ONLY by
        # passing through the foreign bridge B. Endpoints same-group; the bridge a foreign group.
        # Every node stamps `test_marker` so cleanup is marker-scoped, never group-wide.
        self.s.run(
            "MERGE (a:Artefato {group_id:$g, slug:$A}) SET a.test_marker=$m "
            "MERGE (c:Artefato {group_id:$g, slug:$C}) SET c.test_marker=$m "
            "MERGE (b:Artefato {group_id:$fg, slug:$B}) SET b.test_marker=$m "
            "MERGE (a)-[:RELATES_TO]->(b) "
            "MERGE (b)-[:RELATES_TO]->(c)",
            g=self._g, fg=self._fg, A=self.A, C=self.C, B=self.BRIDGE, m=self._run)

    def tearDown(self):
        try:
            self._cleanup(self.s)
        finally:
            self.s.close()
            self._drv.close()

    def test_a_foreign_bridge_cannot_route_a_same_group_peer_into_surf(self):
        out = recall.surf_subgraph([self.A], group=self._g,
                                   uri=self._uri, user=self._user, password=self._pw)
        self.assertIsNotNone(out, "a reachable graph must surf, not degrade")
        slugs = {n["slug"] for n in out}
        self.assertNotIn(self.C, slugs,
                         "C is reachable ONLY through a FOREIGN intermediate bridge — path-wide "
                         "scoping (R7b/#41) must keep it OUT of the surf")
        self.assertNotIn(self.BRIDGE, slugs, "the foreign bridge itself must never surface")


class SessionHelperGuardsTheConnection(unittest.TestCase):
    """R7 — the open/resolve/fail-dark/close boilerplate that recall_subgraph and surf_subgraph each
    re-implement (and the incoming MCP would copy a third time) is extracted into ONE guarded
    `_session(group)` context helper. It yields a live session, or yields None on every degrade (no
    group, neo4j driver absent, graph unreachable) — NEVER raises (CONTRACT C1) — and always closes
    the driver. Both reused functions execute it, not an inline copy."""

    def test_session_yields_none_without_group(self):
        with recall._session(None) as s:
            self.assertIsNone(s, "no group must yield None (the dark leg), never raise")

    def test_session_yields_none_on_unreachable_graph(self):
        with recall._session("any-group", uri="bolt://127.0.0.1:1") as s:
            self.assertIsNone(s, "an unreachable graph must yield None, never raise")

    def test_reused_functions_go_through_the_helper(self):
        # the de-dup is REAL: both functions execute the shared helper, not an inline driver-open.
        for fn in (recall.recall_subgraph, recall.surf_subgraph):
            src = inspect.getsource(fn)
            self.assertIn("_session(", src,
                          f"{fn.__name__} must open its session through the shared _session helper")


if __name__ == "__main__":
    unittest.main()
