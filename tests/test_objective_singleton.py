"""#633 — the spine :Objective is a SINGLETON.

The rite promises ONE Objective per group. In the fleet's Bolt, `petertosh` carried **6**
`:Objective` nodes with the IDENTICAL body. The append was NEVER in the eventlog — `objective.set`
is latest-wins and `cortex.objective_at` folds it to one record, so no amount of re-setting the
objective can grow a second node. It was in the **projection**, where two writers shared one label:

  * `publisher.project_lentes` minted one `:Objective` per `operacao` (keyed `{group_id, ref}`) as
    the MARCO_OF hub — an operation is not the group's north, it only borrowed the label; and
  * `publisher._project_backbone` wrote the spine with a bare `MERGE (o:Objective {group_id:$g})`.

A bare MERGE has no discriminating key, so it MATCHED the operation hubs instead of creating the
spine node — and `SET o.body=$b` stamped the SAME body on EVERY one of them. That is the exact
petertosh signature (N nodes, one text), and the `MATCH (a:Artefato),(o:Objective {group_id:$g})
MERGE (a)-[:SERVES]->(o)` fan then hung every Artefato off all N. Recall's "one north" becomes
"aligned with any of them".

The live tests run against the install's own Neo4j in a DISPOSABLE synthetic group (never `ed`,
never `turing`), torn down in tearDown. No graph → skip (the repo's degrade convention).
"""
import inspect
import os
import re
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import eventlog  # noqa: E402
import group_health  # noqa: E402
import publisher  # noqa: E402


def _neo4j_reachable():
    """True iff the install's Neo4j is reachable — gates the live tests (mirrors
    tests/test_recall_surf.py). Offline/CI degrades to skip, never fails."""
    try:
        import _identity
        from neo4j import GraphDatabase
        uri, user, pw = _identity.neo4j_conn()
        drv = GraphDatabase.driver(uri, auth=(user, pw))
        drv.verify_connectivity()
        drv.close()
        return True
    except Exception:  # noqa: BLE001 — no graph → skip the live tests
        return False


_NEO4J = _neo4j_reachable()

# Every disposable group this module mints is `t633…` + a uuid4 slice. No real install carries that
# prefix, so the sweep below can never reach `ed`, `turing` or any fleet group.
_GROUP_PREFIX = "t633"


def tearDownModule():
    """Sweep EVERY `t633…` group off the live Bolt when the module finishes.

    Each test already wipes its own group in tearDown, but a run KILLED between setUp and tearDown
    (crash, Ctrl-C, a harness that reaps the process) strands the fixture in the graph — where a
    passer-by reads six synthetic :Objective as real duplicated memory. Prefix-scoped, so it is
    idempotent and cannot touch a real group."""
    if not _NEO4J:
        return
    try:
        import _identity
        from neo4j import GraphDatabase
        uri, user, pw = _identity.neo4j_conn()
        with GraphDatabase.driver(uri, auth=(user, pw)) as drv:
            with drv.session() as s:
                s.run("MATCH (n) WHERE n.group_id STARTS WITH $p DETACH DELETE n",
                      p=_GROUP_PREFIX)
    except Exception as exc:  # noqa: BLE001 — the sweep is hygiene; it must never fail a green run
        print(f"test_objective_singleton: leftover sweep skipped ({type(exc).__name__}: {exc})")


class SingletonKeyIsAParameter(unittest.TestCase):
    """#578 (corpus N×N, open) pins Genesis/Objective/Direction as `{group_id, agent}`. When it
    lands, unicity becomes per-(group_id, agent) — that must be a PARAMETER, not a rewrite."""

    def test_the_key_is_one_module_level_tuple(self):
        self.assertEqual(publisher.OBJECTIVE_SINGLETON_KEY, ("group_id",))
        self.assertEqual(publisher.spine_objective_key("g"), {"group_id": "g"})

    def test_flipping_the_key_carries_the_agent_with_no_other_edit(self):
        original = publisher.OBJECTIVE_SINGLETON_KEY
        publisher.OBJECTIVE_SINGLETON_KEY = ("group_id", "agent")
        try:
            self.assertEqual(publisher.spine_objective_key("g", agent="ed"),
                             {"group_id": "g", "agent": "ed"})
            self.assertIn("o.agent = $agent",
                          publisher._spine_where(publisher.spine_objective_key("g", "ed")))
        finally:
            publisher.OBJECTIVE_SINGLETON_KEY = original


class SpineStatementsAreDiscriminated(unittest.TestCase):
    """Hermetic guards (they run with no graph)."""

    def test_no_bare_group_only_objective_match_in_the_write_path(self):
        """No statement that means THE SPINE may address `:Objective` by `group_id` alone — that is
        the bug, and it reads as correct."""
        src = inspect.getsource(publisher)
        for stmt in re.findall(r'"[^"]*:Objective \{group_id:\$g\}[^"]*"(?:\s*"[^"]*")*', src):
            self.assertIn("spine", stmt,
                          f"spine statement addresses :Objective by group alone: {stmt[:120]}")

    def test_the_operacao_hub_no_longer_borrows_the_objective_label(self):
        """`group_health` (#638) counts EVERY `:Objective` in a group and fails at >1 — so the
        per-`operacao` MARCO_OF hub cannot keep sharing the label."""
        self.assertEqual(publisher.OPERACAO_LABEL, "Operacao")
        src = inspect.getsource(publisher.project_lentes)
        self.assertIn("OPERACAO_LABEL", src)
        self.assertNotIn('"Objective"', src,
                         "project_lentes still mints the operation hub as :Objective")


@unittest.skipUnless(_NEO4J, "no Neo4j reachable — live singleton tests skipped")
class _LiveGroup(unittest.TestCase):
    """A disposable synthetic group on the install's own Neo4j. Never `ed`, never `turing`."""

    PREFIX = "t633-"

    def setUp(self):
        import _identity
        from neo4j import GraphDatabase
        uri, user, pw = _identity.neo4j_conn()
        self.g = self.PREFIX + uuid.uuid4().hex[:10]
        self.drv = GraphDatabase.driver(uri, auth=(user, pw))
        self.s = self.drv.session()
        self._wipe()
        self.seed()

    def seed(self):
        pass

    def tearDown(self):
        try:
            self._wipe()
        finally:
            self.s.close()
            self.drv.close()

    def _wipe(self):
        self.s.run("MATCH (n {group_id:$g}) DETACH DELETE n", g=self.g)

    def _objectives(self):
        return [dict(r) for r in self.s.run(
            "MATCH (o:Objective {group_id:$g}) RETURN elementId(o) AS id, o.ref AS ref, "
            "o.body AS body, o.spine AS spine ORDER BY coalesce(o.ref,'')", g=self.g)]


def _lentes_log(tmpdir, operations):
    """A tiny canonical log with one open Atividade per operation — the lentes plane's input."""
    log = Path(tmpdir) / "lentes.jsonl"
    for name in operations:
        eventlog.open_atividade(operacao=name, finalidade=f"trilho {name}", tier="asserted",
                                author="operador", log=log)
    return log


def _live_store(driver, group_id):
    """The live GraphStore port, scoped to the disposable group — what `sweep` hands project_lentes."""
    import graph_store
    return graph_store.Neo4jGraphStore(driver, group_id=group_id)


class ObjectiveWriteIsIdempotent(_LiveGroup):
    BODY = "invariante ATENDENTE: lead -> consulta -> receita -> laudo"

    def seed(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / "log.jsonl"
        eventlog.set_objective(self.BODY, log=self.log)

    def _legacy_hub(self, name):
        """What project_lentes used to write — the hub, wearing the :Objective label."""
        self.s.run("MERGE (o:Objective {group_id:$g, ref:$r}) SET o.operacao=$n",
                   g=self.g, r=f"operacao:{name}", n=name)

    def _backbone(self):
        publisher._project_backbone(self.s, self.g, self.log)

    # --- the criteria ----------------------------------------------------------------------
    def test_writing_the_same_body_twice_yields_one_node(self):
        """The issue's literal acceptance criterion."""
        self._backbone()
        self._backbone()
        self.assertEqual(len(self._objectives()), 1)

    def test_the_spine_write_never_stamps_the_operacao_hubs(self):
        """THE #633 REPRODUCTION: with the lentes plane present, the bare spine MERGE matched the
        operation hubs and stamped every one with the identical body — petertosh's 6 copies."""
        for name in ("closavo", "blog", "frota", "cortex", "rito", "frontier"):
            self._legacy_hub(name)
        self._backbone()
        carrying = [r for r in self._objectives() if r["body"]]
        self.assertEqual(len(carrying), 1,
                         f"{len(carrying)} :Objective carry the spine body (expected exactly 1)")
        self.assertIsNone(carrying[0]["ref"], "the spine body landed on an operacao hub")
        self.assertEqual(
            self.s.run("MATCH (o:Objective {group_id:$g}) WHERE o.ref IS NOT NULL "
                       "RETURN count(*) AS n", g=self.g).single()["n"], 6,
            "the pre-rename hubs must survive untouched (MARCO_OF depends on them)")

    def test_group_health_stops_reporting_duplicate_objectives(self):
        """#638's `group_health` is the acceptance criterion written from outside: it counts EVERY
        :Objective in the group and fails at >1. A freshly projected group must pass it."""
        publisher.project_lentes(_lentes_log(self.tmp.name, ("closavo", "blog", "frota")),
                                 _live_store(self.drv, self.g))
        self._backbone()
        card = group_health.health(self.s, self.g)
        self.assertEqual(card["objectives"], 1, "group_health still counts duplicate Objectives")
        self.assertEqual([m for _sev, m in group_health.verdicts(card) if "#633" in m], [],
                         "group_health still fails this group on the #633 criterion")

    def test_a_legacy_unstamped_objective_is_ADOPTED_not_forked(self):
        """Compat (BRIEF #4): every install alive today carries an :Objective written BEFORE the
        `spine` stamp existed (`ed` and `turing` both do). The new keyed write must ADOPT it — if it
        forked instead, the fix would hand every install in the fleet a second copy."""
        legacy = self.s.run(
            "CREATE (o:Objective {group_id:$g, body:'um norte antigo, sem carimbo'}) "
            "RETURN elementId(o) AS id", g=self.g).single()["id"]
        self._backbone()
        rows = self._objectives()
        self.assertEqual(len(rows), 1, "the legacy Objective was forked, not adopted")
        self.assertEqual(rows[0]["id"], legacy)
        self.assertEqual(rows[0]["body"], self.BODY)
        self.assertTrue(rows[0]["spine"], "the adopted node was not stamped")

    def test_a_new_body_supersedes_in_place_it_does_not_create(self):
        self._backbone()
        first = self._objectives()
        eventlog.set_objective("um norte novo, abduzido da conduta", log=self.log)
        self._backbone()
        rows = self._objectives()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], first[0]["id"],
                         "a new body forked the node instead of superseding it")
        self.assertEqual(rows[0]["body"], "um norte novo, abduzido da conduta")

    def test_serves_and_grounds_target_only_the_spine(self):
        """Six hubs must not each collect a SERVES star — the hub that reaches everything
        discriminates nothing, and six of them make 'aligned' meaningless."""
        for name in ("closavo", "blog", "frota"):
            self._legacy_hub(name)
        self.s.run("MERGE (a:Artefato {group_id:$g, slug:'a-1'})", g=self.g)
        self._backbone()
        served = self.s.run(
            "MATCH (:Artefato {group_id:$g})-[:SERVES]->(o:Objective {group_id:$g}) "
            "RETURN count(DISTINCT o) AS n", g=self.g).single()["n"]
        self.assertEqual(served, 1, f"the artefato SERVES {served} objectives")
        grounded = self.s.run(
            "MATCH (:Genesis {group_id:$g})-[:GROUNDS]->(o:Objective {group_id:$g}) "
            "RETURN count(DISTINCT o) AS n", g=self.g).single()["n"]
        self.assertEqual(grounded, 1, f"Genesis GROUNDS {grounded} objectives")

    def test_the_guard_reports_a_second_live_objective_without_deleting_it(self):
        """The guard REPORTS; it never deletes on the write path (deletion is the migration's job,
        behind --dry-run). An install that already duplicated must keep sweeping."""
        self._backbone()
        self.s.run("CREATE (o:Objective {group_id:$g, body:'copia', spine:true})", g=self.g)
        self.assertEqual(len(publisher.objective_singleton_violation(self.s, self.g)), 1)
        self._backbone()  # must not raise
        self.assertEqual(len(self._objectives()), 2, "the write path deleted a node")


@unittest.skipUnless(_NEO4J, "no Neo4j reachable — live migration tests skipped")
class MigrationCollapsesAndRewires(_LiveGroup):
    """`tools/migrate_objective_singleton.py` — dry-run by default; the SERVES edges that pointed at
    the collapsed copies must SURVIVE on the survivor (else duplication becomes orphanhood)."""

    PREFIX = "t633m-"
    TOOL = REPO / "tools" / "migrate_objective_singleton.py"

    def seed(self):
        # the petertosh shape: 1 keyless spine + 1 extra copy + 1 stamped operation hub, each with
        # its own slice of the SERVES star, plus a MARCO_OF that only the hub carries.
        self.s.run(
            "CREATE (o:Objective {group_id:$g, body:$b, created_at:'2026-01-01'}) "
            "CREATE (d1:Objective {group_id:$g, body:$b, created_at:'2026-02-01'}) "
            "CREATE (h:Objective {group_id:$g, ref:'operacao:closavo', operacao:'closavo', body:$b}) "
            "CREATE (a1:Artefato {group_id:$g, slug:'art-1'}) "
            "CREATE (a2:Artefato {group_id:$g, slug:'art-2'}) "
            "CREATE (m:Artefato {group_id:$g, slug:'marco-1'}) "
            "CREATE (a1)-[:SERVES]->(o) CREATE (a1)-[:SERVES]->(d1) CREATE (a1)-[:SERVES]->(h) "
            "CREATE (a2)-[:SERVES]->(d1) "
            "CREATE (m)-[:MARCO_OF]->(h)", g=self.g, b="o norte")

    def _run(self, *args):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO / "tools")
        return subprocess.run([sys.executable, str(self.TOOL), "--group", self.g, *args],
                              capture_output=True, text=True, env=env, cwd=str(REPO))

    def _counts(self):
        objs = self.s.run("MATCH (o:Objective {group_id:$g}) RETURN count(*) AS n",
                          g=self.g).single()["n"]
        serves = self.s.run(
            "MATCH (a:Artefato {group_id:$g})-[:SERVES]->(o:Objective {group_id:$g}) "
            "RETURN collect(DISTINCT a.slug) AS slugs", g=self.g).single()["slugs"]
        return objs, sorted(serves)

    def test_dry_run_is_the_default_and_changes_nothing(self):
        before = self._counts()
        out = self._run()
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("dry-run", out.stdout)
        self.assertEqual(self._counts(), before, "the DEFAULT invocation mutated the graph")

    def test_apply_without_confirmation_refuses(self):
        before = self._counts()
        out = self._run("--apply")
        self.assertNotEqual(out.returncode, 0)
        self.assertEqual(self._counts(), before)

    def test_apply_collapses_to_one_and_the_serves_edges_survive(self):
        out = self._run("--apply", "--yes")
        self.assertEqual(out.returncode, 0, out.stderr)
        objs, serves = self._counts()
        self.assertEqual(objs, 1, "the group still carries more than one :Objective")
        # both artefatos still SERVE a north — the edges were RELINKED, not dropped
        self.assertEqual(serves, ["art-1", "art-2"])
        # the operation hub survives, relabelled, with its own topology and no stamped body
        hub = self.s.run(f"MATCH (o:`{publisher.OPERACAO_LABEL}` {{group_id:$g}}) "
                         "RETURN o.ref AS ref, o.body AS body", g=self.g).single()
        self.assertEqual(hub["ref"], "operacao:closavo")
        self.assertIsNone(hub["body"], "the operation hub kept the stamped spine body")
        marco = self.s.run("MATCH (:Artefato {group_id:$g})-[:MARCO_OF]->() RETURN count(*) AS n",
                           g=self.g).single()["n"]
        self.assertEqual(marco, 1, "MARCO_OF was collateral damage")

    def test_after_apply_group_health_passes(self):
        self._run("--apply", "--yes")
        card = group_health.health(self.s, self.g)
        self.assertEqual(card["objectives"], 1)
        self.assertEqual([m for _sev, m in group_health.verdicts(card) if "#633" in m], [])


@unittest.skipUnless(_NEO4J, "no Neo4j reachable — live migration tests skipped")
class MigrationWhenEveryObjectiveIsAHub(_LiveGroup):
    """The likely petertosh state: `project_lentes` ran BEFORE the first backbone, so the bare
    `MERGE (o:Objective {group_id:$g})` never created a spine node at all — it only ever matched the
    hubs. Every :Objective in the group is an operation hub wearing the same stamped body."""

    PREFIX = "t633h-"
    TOOL = REPO / "tools" / "migrate_objective_singleton.py"
    BODY = "invariante ATENDENTE: lead -> consulta -> receita -> laudo"

    def seed(self):
        for name in ("closavo", "blog", "frota", "cortex", "rito", "frontier"):
            self.s.run("CREATE (o:Objective {group_id:$g, ref:$r, operacao:$n, body:$b})",
                       g=self.g, r=f"operacao:{name}", n=name, b=self.BODY)
        self.s.run("CREATE (a:Artefato {group_id:$g, slug:'art-1'})", g=self.g)
        self.s.run("MATCH (a:Artefato {group_id:$g}) MATCH (o:Objective {group_id:$g}) "
                   "MERGE (a)-[:SERVES]->(o)", g=self.g)

    def _run(self, *args):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO / "tools")
        return subprocess.run([sys.executable, str(self.TOOL), "--group", self.g, *args],
                              capture_output=True, text=True, env=env, cwd=str(REPO))

    def test_the_north_is_rebuilt_from_the_stamped_body_and_the_hubs_survive(self):
        out = self._run("--apply", "--yes")
        self.assertEqual(out.returncode, 0, out.stderr)
        rows = self._objectives()
        self.assertEqual(len(rows), 1, "the group still carries more than one :Objective")
        self.assertEqual(rows[0]["body"], self.BODY, "the rebuilt north lost the text")
        hubs = self.s.run(f"MATCH (o:`{publisher.OPERACAO_LABEL}` {{group_id:$g}}) "
                          "RETURN count(*) AS n, count(o.body) AS stamped", g=self.g).single()
        self.assertEqual(hubs["n"], 6, "the operation hubs were destroyed")
        self.assertEqual(hubs["stamped"], 0, "the hubs kept the stamped spine body")
        served = self.s.run(
            "MATCH (:Artefato {group_id:$g})-[:SERVES]->(o:Objective {group_id:$g}) "
            "RETURN count(DISTINCT o) AS n", g=self.g).single()["n"]
        self.assertEqual(served, 1, "the artefato lost its north, or still serves several")
        card = group_health.health(self.s, self.g)
        self.assertEqual([m for _sev, m in group_health.verdicts(card) if "#633" in m], [])

    def test_it_refuses_to_guess_when_the_hubs_disagree_on_the_north(self):
        """Two different texts and no spine node: there is no evidence which one is the north.
        Refusing beats silently canonising the alphabetically-first body."""
        self.s.run("MATCH (o:Objective {group_id:$g, ref:'operacao:blog'}) SET o.body='outro norte'",
                   g=self.g)
        before = self.s.run("MATCH (o:Objective {group_id:$g}) RETURN count(*) AS n",
                            g=self.g).single()["n"]
        out = self._run("--apply", "--yes")
        self.assertIn("REFUSING", out.stdout)
        self.assertEqual(self.s.run("MATCH (o:Objective {group_id:$g}) RETURN count(*) AS n",
                                    g=self.g).single()["n"], before,
                         "it mutated the graph while refusing")


if __name__ == "__main__":
    unittest.main()
