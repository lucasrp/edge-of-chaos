"""#634 — rename de group_id é FORK; tenant morto sem GC.

`group_id` IS identity. Changing `name`/`codename`/`graph_group` in agent.yaml does NOT migrate
the graph: the `n.group_id = $g` fence simply stops matching the past (the agent "forgets"
without anything being deleted) and the next backbone projection MERGEs a SECOND `:Genesis`
under the new name. That is how `peter tosh` (269 nodes) and `petertosh` (2490) became two
tenants for one agent, and how `edge-next` (476) became a tomb nobody buries.

Three legs, in rising order of blast radius:

  1. `edge-group rename OLD NEW` — one write transaction, plan first, dry-run the DEFAULT. When
     both tenants carry a spine the migration is a MERGE, and the policy (operator, 2026-08-16)
     is that the DESTINATION's spine wins: the source's Genesis/Objective are discarded, printed
     body and all, behind a second `--discard-source-spine` token, with every edge they carried
     rewired to an heir or dropped explicitly. The "one identity root" invariant is additionally
     enforced INSIDE the transaction, so even a doctored plan cannot commit a second root.
  2. the tenant guard — an install whose resolved group holds no `:Genesis` while OTHER groups on
     the same Bolt do is a FORK SUSPECT: refuse, name the candidate, offer the migrate.
  3. `edge-group gc` — LISTS (reusing `group_health.leftovers`, #636) and can bury ONE named
     group. The delete gate is written from an accident (see `GcRefusesToBuryTheLiving`):
     protection is opt-OUT, staleness must be proven rather than assumed, and destroying an
     identity root costs its own separate word.

Every live test writes ONLY into a disposable `fixture-634-*` group and tears it down; the
tenants sharing this Bolt are never touched (asserted, not assumed).
"""
import json
import sys
import unittest
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import group_admin  # noqa: E402


# ---------------------------------------------------------------- offline doubles


class FakeResult:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def data(self):
        return self.rows

    def single(self):
        return self.rows[0] if self.rows else None


class FakeSession:
    """Records every (query, params); serves canned rows keyed by a substring of the query."""

    def __init__(self, rows_by_marker=None):
        self.calls = []
        self.rows_by_marker = rows_by_marker or {}

    def run(self, query, **params):
        flat = " ".join(query.split())
        self.calls.append((flat, params))
        for marker, rows in self.rows_by_marker.items():
            if marker in flat:
                return FakeResult(rows() if callable(rows) else rows)
        return FakeResult()

    def execute_write(self, fn):
        return fn(self)

    def writes(self):
        return [q for q, _ in self.calls if " SET " in q or "DELETE" in q]


def _gc_session(nodes, genesis, last_activity):
    """A session canned to answer everything `gc_plan` asks about one group. Marker order
    matters — the most specific query shapes come first."""
    return FakeSession({
        "RETURN elementId(n) AS id, properties(n) AS props":
            [{"id": "x%d" % i, "props": {}} for i in range(genesis)],
        "RETURN max(toString(coalesce(": [{"n": last_activity}],
        "count(DISTINCT r) AS n": [{"n": 0}],
        "RETURN head(labels(n)) AS label": [{"label": "Entity", "n": nodes}],
        "RETURN count(n) AS n": [{"n": nodes}],
    })


# ---------------------------------------------------------------- the fork, named


class ForkIsNamed(unittest.TestCase):
    """A rename that was never migrated leaves TWO group ids for one agent. The near-twin test is
    what makes `peter tosh` / `petertosh` legible as one fork instead of two tenants."""

    def test_near_twin_group_ids_are_flagged_as_one_fork(self):
        inv = [{"group": "petertosh", "nodes": 2490}, {"group": "peter tosh", "nodes": 269},
               {"group": "edge-next", "nodes": 476}, {"group": "turing", "nodes": 116}]
        self.assertEqual(group_admin.fork_candidates(inv), [("peter tosh", "petertosh")])

    def test_distinct_tenants_are_not_flagged(self):
        inv = [{"group": "ed", "nodes": 21}, {"group": "turing", "nodes": 116}]
        self.assertEqual(group_admin.fork_candidates(inv), [])

    def test_normalization_ignores_case_space_dash_and_underscore(self):
        self.assertEqual(group_admin.normalize_group("Peter Tosh"),
                         group_admin.normalize_group("peter-tosh"))
        self.assertEqual(group_admin.normalize_group("edge_next"),
                         group_admin.normalize_group("edge next"))


class TenantVerdict(unittest.TestCase):
    """The guard's judgement, on canned graph facts. `fork_suspect` is the verdict that refuses a
    fresh install: my group is EMPTY while other groups on this Bolt already own a `:Genesis`."""

    def _verdict(self, group, genesis_groups, my_nodes, inventory=None):
        s = FakeSession({
            "MATCH (n:Genesis)": [{"group": g, "n": 1} for g in genesis_groups],
            "RETURN count(n) AS n": [{"n": my_nodes}],
            "WHERE n.group_id IS NOT NULL RETURN n.group_id AS group":
                inventory or [{"group": g, "nodes": 1, "genesis": 1, "last_activity": None}
                              for g in genesis_groups],
        })
        return group_admin.tenant_verdict(s, group)

    def test_group_owning_its_genesis_is_the_owner(self):
        v = self._verdict("ed", ["ed", "turing"], 21)
        self.assertEqual(v["status"], "owner")
        self.assertTrue(v["ok"])

    def test_empty_group_beside_a_foreign_genesis_is_a_fork_suspect(self):
        v = self._verdict("petertosh", ["peter tosh"], 0)
        self.assertEqual(v["status"], "fork_suspect")
        self.assertFalse(v["ok"])
        self.assertEqual(v["candidates"], ["peter tosh"])
        self.assertIn("edge-group rename", v["detail"])      # OFFER the migrate, not just complain
        self.assertIn("peter tosh", v["detail"])

    def test_empty_group_on_an_empty_bolt_is_a_fresh_install(self):
        v = self._verdict("ed", [], 0, inventory=[])
        self.assertEqual(v["status"], "fresh")
        self.assertIsNone(v["ok"])                           # advisory: nothing to fork from

    def test_populated_group_without_a_spine_yet_is_advisory_not_a_refusal(self):
        v = self._verdict("ed", ["turing"], 12)
        self.assertEqual(v["status"], "unrooted")
        self.assertIsNone(v["ok"])

    def test_a_near_twin_of_my_own_group_is_a_refusal(self):
        v = self._verdict("petertosh", ["petertosh", "peter tosh"], 2490,
                          inventory=[{"group": "petertosh", "nodes": 2490, "genesis": 1,
                                      "last_activity": None},
                                     {"group": "peter tosh", "nodes": 269, "genesis": 1,
                                      "last_activity": None}])
        self.assertEqual(v["status"], "forked")
        self.assertFalse(v["ok"])
        self.assertIn("peter tosh", v["detail"])


class GuardRefusesInInstallValidation(unittest.TestCase):
    """Leg 2 of the issue: the guard has to reach `edge-apply`. A fork suspect is a FAILED install
    check (apply exits nonzero), never a silent second Genesis."""

    def test_validate_exposes_a_tenant_check(self):
        import _validate
        self.assertTrue(hasattr(_validate, "check_tenant"))
        names = [c[0] for c in _validate.validate_install(
            REPO, {}, REPO, provisioned=True, repo_tools=REPO / "tools",
            agent_yaml=REPO / "nope.yaml")]
        self.assertIn("tenant", names)

    def test_fork_suspect_probe_output_is_a_failed_check(self):
        import _validate
        name, ok, detail = _validate._tenant_from_probe(json.dumps({
            "status": "fork_suspect", "ok": False, "group": "petertosh",
            "candidates": ["peter tosh"],
            "detail": "group 'petertosh' is empty while 'peter tosh' owns a :Genesis — "
                      "run `edge-group rename 'peter tosh' petertosh` to migrate"}))
        self.assertEqual(name, "tenant")
        self.assertIs(ok, False)
        self.assertIn("edge-group rename", detail)

    def test_declared_new_tenant_downgrades_to_advisory_but_stays_loud(self):
        import _validate
        name, ok, detail = _validate._tenant_from_probe(json.dumps({
            "status": "fork_suspect", "ok": False, "group": "petertosh",
            "candidates": ["peter tosh"], "detail": "…", "new_tenant_declared": True}))
        self.assertIsNone(ok)                     # declared → does not block the install
        self.assertIn("peter tosh", detail)       # but the foreign tenant is still NAMED


class ConfirmationIsNotOptional(unittest.TestCase):
    """Dry-run is the DEFAULT for both verbs; every write needs the destination retyped."""

    def test_rename_without_apply_is_a_dry_run(self):
        s = FakeSession({"RETURN count(n) AS n": [{"n": 3}]})
        self.assertEqual(group_admin.main(["rename", "old", "new"], session=s), 0)
        self.assertEqual(s.writes(), [], "a default rename must not write")

    def test_rename_apply_without_confirm_refuses(self):
        s = FakeSession({"RETURN count(n) AS n": [{"n": 3}]})
        self.assertEqual(group_admin.main(["rename", "old", "new", "--apply"], session=s), 2)
        self.assertEqual(s.writes(), [])

    def test_rename_apply_with_a_mismatched_confirm_refuses(self):
        s = FakeSession({"RETURN count(n) AS n": [{"n": 3}]})
        self.assertEqual(group_admin.main(
            ["rename", "old", "new", "--apply", "--confirm", "nwe"], session=s), 2)
        self.assertEqual(s.writes(), [])

    def test_rename_onto_itself_is_refused(self):
        s = FakeSession({"RETURN count(n) AS n": [{"n": 3}]})
        self.assertEqual(group_admin.main(
            ["rename", "ed", "ed", "--apply", "--confirm", "ed"], session=s), 2)
        self.assertEqual(s.writes(), [])

    def test_renaming_an_empty_group_is_refused(self):
        s = FakeSession({"RETURN count(n) AS n": [{"n": 0}]})
        self.assertEqual(group_admin.main(
            ["rename", "ghost", "new", "--apply", "--confirm", "new"], session=s), 2)
        self.assertEqual(s.writes(), [])

    def test_gc_delete_without_confirm_refuses(self):
        s = _gc_session(nodes=476, genesis=0, last_activity="2026-01-01T00:00:00Z")
        self.assertEqual(group_admin.main(
            ["gc", "--delete", "edge-next", "--stale-since", "2026-06-01"], session=s), 2)
        self.assertEqual(s.writes(), [])

    def test_gc_refuses_to_delete_the_live_group(self):
        s = _gc_session(nodes=21, genesis=0, last_activity="2026-01-01T00:00:00Z")
        self.assertEqual(group_admin.main(
            ["gc", "--delete", "ed", "--confirm", "ed", "--stale-since", "2026-06-01"],
            session=s, live_group="ed"), 2)
        self.assertEqual(s.writes(), [])

    def test_gc_refuses_to_delete_a_group_named_by_keep(self):
        s = _gc_session(nodes=116, genesis=0, last_activity="2026-01-01T00:00:00Z")
        self.assertEqual(group_admin.main(
            ["gc", "--delete", "turing", "--confirm", "turing", "--keep", "turing",
             "--stale-since", "2026-06-01"], session=s, live_group="ed"), 2)
        self.assertEqual(s.writes(), [])


class GcRefusesToBuryTheLiving(unittest.TestCase):
    """REGRESSION, written from an accident of mine (2026-08-16).

    The first cut of this CLI protected only `_identity.group()` — THIS install's own tenant —
    plus whatever `--keep` named. On a shared Bolt that is backwards: the tenants you can least
    afford to destroy are precisely the ones belonging to OTHER unix users, whose installs this
    process cannot see, and they were one correctly-typed command away from deletion. I typed
    that command against `turing` while probing what I believed was the refusal path, and deleted
    a live agent's memory (141 nodes) in one round trip.

    Burying a tenant IS supported — `edge-next` is meant to be buried — but every assertion is
    now separate and none of them defaults to yes:
      - the group named in `--delete`, RETYPED in `--confirm`;
      - a `--stale-since` date the group's own last activity must predate (no timestamp at all =
        no evidence of death = refused);
      - `--bury-rooted` on top of all that when the group holds a `:Genesis`, because an identity
        root means an install claimed the tenant.
    The command that destroyed `turing` is refused by three of those rows at once, and the
    refusals live in the PLAN, so a caller who skips the CLI still cannot get past them.
    """

    STALE = ["--stale-since", "2026-06-01"]

    def test_the_command_that_destroyed_turing_is_now_refused(self):
        # verbatim: `gc --delete turing --confirm turing`, against turing's shape
        s = _gc_session(nodes=141, genesis=1, last_activity="2026-01-01T00:00:00Z")
        rc = group_admin.main(["gc", "--delete", "turing", "--confirm", "turing"],
                              session=s, live_group="ed")
        self.assertEqual(rc, 2)
        self.assertEqual(s.writes(), [], "the accident must not be reproducible")

    def test_a_rooted_group_needs_bury_rooted_on_top_of_everything_else(self):
        s = _gc_session(nodes=141, genesis=1, last_activity="2026-01-01T00:00:00Z")
        rc = group_admin.main(["gc", "--delete", "turing", "--confirm", "turing"] + self.STALE,
                              session=s, live_group="ed")
        self.assertEqual(rc, 2)
        self.assertEqual(s.writes(), [],
                         "an identity root means an install claimed this tenant")

    def test_the_plan_itself_blocks_a_rooted_group_until_the_burial_is_declared(self):
        s = _gc_session(nodes=141, genesis=1, last_activity="2026-01-01T00:00:00Z")
        plan = group_admin.gc_plan(s, "turing", stale_since="2026-06-01")
        self.assertTrue(any(group_admin.SPINE_ROOT in b for b in plan["blockers"]),
                        plan["blockers"])
        with self.assertRaises(group_admin.GroupAdminError):
            group_admin.gc_apply(s, plan)
        self.assertEqual(s.writes(), [])
        declared = group_admin.gc_plan(s, "turing", stale_since="2026-06-01", bury_rooted=True)
        self.assertEqual(declared["blockers"], [],
                         "a declared burial of a stale rooted tenant is allowed — that is the "
                         "edge-next case; what is forbidden is doing it by default")

    def test_delete_without_a_staleness_date_is_refused(self):
        s = _gc_session(nodes=476, genesis=0, last_activity="2026-01-01T00:00:00Z")
        rc = group_admin.main(["gc", "--delete", "edge-next", "--confirm", "edge-next"],
                              session=s, live_group="ed")
        self.assertEqual(rc, 2)
        self.assertEqual(s.writes(), [])

    def test_a_group_that_moved_after_the_staleness_date_is_refused(self):
        s = _gc_session(nodes=476, genesis=0, last_activity="2026-08-15T10:00:00Z")
        rc = group_admin.main(["gc", "--delete", "edge-next", "--confirm", "edge-next"]
                              + self.STALE, session=s, live_group="ed")
        self.assertEqual(rc, 2)
        self.assertEqual(s.writes(), [])

    def test_a_group_with_no_activity_timestamp_is_refused(self):
        """No evidence of death is not evidence of death.

        The REASON matters as much as the refusal: an undated group must be refused for being
        undated, not by falling through a date comparison that happens to come out the right way
        on the string `None`. An operator who reads "moved at None, not older than …" cannot
        tell whether the tool checked anything."""
        s = _gc_session(nodes=9, genesis=0, last_activity=None)
        rc = group_admin.main(["gc", "--delete", "mystery", "--confirm", "mystery"]
                              + self.STALE, session=s, live_group="ed")
        self.assertEqual(rc, 2)
        self.assertEqual(s.writes(), [])
        plan = group_admin.gc_plan(_gc_session(9, 0, None), "mystery",
                                   stale_since="2026-06-01")
        self.assertTrue(any("no activity timestamp" in b for b in plan["blockers"]),
                        plan["blockers"])

    def test_every_token_is_load_bearing(self):
        """The whole gate read as one table. Drop any token and the plan blocks again; only the
        two cleared rows below are deletable — unrooted-and-stale, or rooted-stale-and-declared
        (the `edge-next` burial the operator asked for)."""
        blocked = {
            "rooted, not declared": group_admin.gc_plan(
                _gc_session(141, 1, "2026-01-01T00:00:00Z"), "turing",
                stale_since="2026-06-01"),
            "moved after the date": group_admin.gc_plan(
                _gc_session(476, 0, "2026-08-15T10:00:00Z"), "edge-next",
                stale_since="2026-06-01"),
            "no timestamp at all": group_admin.gc_plan(
                _gc_session(9, 0, None), "mystery", stale_since="2026-06-01"),
            "no staleness date": group_admin.gc_plan(
                _gc_session(12, 0, "2026-01-01T00:00:00Z"), "debris", stale_since=None),
            "rooted, declared, but recent": group_admin.gc_plan(
                _gc_session(476, 1, "2026-08-15T10:00:00Z"), "edge-next",
                stale_since="2026-06-01", bury_rooted=True),
        }
        for why, plan in blocked.items():
            self.assertTrue(plan["blockers"], why)
        for why, plan in {
            "unrooted and stale": group_admin.gc_plan(
                _gc_session(12, 0, "2026-01-01T00:00:00Z"), "debris",
                stale_since="2026-06-01"),
            "rooted, stale, declared": group_admin.gc_plan(
                _gc_session(476, 1, "2026-01-01T00:00:00Z"), "edge-next",
                stale_since="2026-06-01", bury_rooted=True),
        }.items():
            self.assertEqual(plan["blockers"], [], why)


# ---------------------------------------------------------------- live fixture proof


def _live_driver():
    try:
        import _identity
        from neo4j import GraphDatabase
        uri, user, pw = _identity.neo4j_conn()
        if not pw:
            return None
        drv = GraphDatabase.driver(uri, auth=(user, pw), connection_timeout=3,
                                   max_transaction_retry_time=3)
        drv.verify_connectivity()
        return drv
    except Exception:                                    # noqa: BLE001 — no graph → skip
        return None


class LiveFixtureCase(unittest.TestCase):
    """Base for the live legs: every write lands in a disposable `fixture-634-*` group, and the
    teardown proves no neighbouring tenant lost a node."""

    FIXTURE_PREFIX = "fixture-634-"

    @classmethod
    def setUpClass(cls):
        cls.driver = _live_driver()
        if cls.driver is None:
            raise unittest.SkipTest("no reachable Neo4j — live group surgery skipped")
        cls._sweep_fixtures()

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "driver", None) is not None:
            cls._sweep_fixtures()
            cls.driver.close()

    @classmethod
    def _sweep_fixtures(cls):
        """Clear any `fixture-634-*` group a CRASHED earlier run left behind. Prefix-guarded in
        the Cypher itself, so this can only ever reach groups this file minted."""
        with cls.driver.session() as s:
            s.run("MATCH (n) WHERE n.group_id STARTS WITH $p DETACH DELETE n",
                  p=cls.FIXTURE_PREFIX)

    def _tenants(self, s):
        """The census of REAL tenants — fixture groups excluded, because they are ours to create
        and destroy and their disappearance is the expected outcome, not a leak."""
        return {r["g"]: r["n"] for r in s.run(
            "MATCH (n) WHERE n.group_id IS NOT NULL AND NOT n.group_id STARTS WITH $p "
            "RETURN n.group_id AS g, count(n) AS n", p=self.FIXTURE_PREFIX).data()}

    def setUp(self):
        self.groups = []
        with self.driver.session() as s:
            self.before = self._tenants(s)

    def tearDown(self):
        with self.driver.session() as s:
            for g in self.groups:
                assert g.startswith(self.FIXTURE_PREFIX)     # never a real tenant
                s.run("MATCH (n) WHERE n.group_id=$g DETACH DELETE n", g=g)
            after = self._tenants(s)
            survivors = [g for g in self.groups if s.run(
                "MATCH (n) WHERE n.group_id=$g RETURN count(n) AS n", g=g).single()["n"]]
        # This Bolt is SHARED — the installs on it may write while the suite runs, so a tenant
        # that GREW proves nothing about us. What must hold is that no REAL tenant LOST nodes (a
        # rename would move them out, a gc would delete them) and that this test's own fixture
        # groups are gone.
        for g, n in self.before.items():
            self.assertGreaterEqual(after.get(g, 0), n,
                                    "tenant %r lost nodes — a live test leaked" % g)
        self.assertEqual(survivors, [], "a fixture group survived its test")

    def _fixture(self, tag):
        g = self.FIXTURE_PREFIX + tag + "-" + uuid.uuid4().hex[:8]
        self.groups.append(g)
        return g

    def _seed(self, group, *, entities=0, spine=True, objective="norte"):
        """Seed a tenant shaped like a real one: a :Genesis spine root, an :Objective it GROUNDS,
        and graphiti-shaped :Entity/:Episodic nodes joined by group-STAMPED edges."""
        with self.driver.session() as s:
            if spine:
                s.run("CREATE (g:Genesis {group_id:$g, space:0, codename:$g})", g=group)
                s.run("CREATE (o:Objective {group_id:$g, body:$b})", g=group, b=objective)
                s.run("MATCH (g:Genesis {group_id:$g}),(o:Objective {group_id:$g}) "
                      "MERGE (g)-[:GROUNDS]->(o)", g=group)
            for i in range(entities):
                s.run("CREATE (e:Entity {group_id:$g, uuid:$u, name:$n, created_at:$t})",
                      g=group, u=f"{group}-e{i}", n=f"ent-{i}", t="2026-01-01T00:00:00Z")
                s.run("CREATE (ep:Episodic {group_id:$g, uuid:$u, name:$n, created_at:$t})",
                      g=group, u=f"{group}-ep{i}", n=f"epi-{i}", t="2026-01-01T00:00:00Z")
                s.run("MATCH (ep:Episodic {group_id:$g, uuid:$u}),"
                      "(e:Entity {group_id:$g, uuid:$v}) "
                      "MERGE (ep)-[:MENTIONS {group_id:$g, uuid:$r}]->(e)",
                      g=group, u=f"{group}-ep{i}", v=f"{group}-e{i}", r=f"{group}-r{i}")

    def _count(self, group, label=None):
        pat = f"(n:{label})" if label else "(n)"
        with self.driver.session() as s:
            return s.run(f"MATCH {pat} WHERE n.group_id=$g RETURN count(n) AS n",
                         g=group).single()["n"]

    def _rels(self, group):
        with self.driver.session() as s:
            return s.run("MATCH ()-[r]->() WHERE r.group_id=$g RETURN count(r) AS n",
                         g=group).single()["n"]


class RenameMigratesTheWholeTenant(LiveFixtureCase):
    """The acceptance criterion of #634, against a real Bolt: after a rename, ZERO nodes remain
    under the old id and the destination holds exactly ONE identity root."""

    def test_rename_into_an_empty_group_moves_nodes_and_edges(self):
        old, new = self._fixture("old"), self._fixture("new")
        self._seed(old, entities=3)
        with self.driver.session() as s:
            plan = group_admin.rename_plan(s, old, new)
            self.assertEqual(plan["blockers"], [])
            self.assertEqual(plan["nodes"], self._count(old))
            self.assertEqual(plan["rels"], self._rels(old))
            result = group_admin.rename_apply(s, plan)
        self.assertEqual(self._count(old), 0, "the old group id must be EMPTY after a rename")
        self.assertEqual(self._count(new), plan["nodes"])
        self.assertEqual(self._rels(new), plan["rels"],
                         "graphiti stamps group_id on RELATIONSHIPS too — a rename that only "
                         "moves nodes leaves the edges fenced into a dead tenant")
        self.assertEqual(result["moved_nodes"], plan["nodes"])
        self.assertEqual(self._count(new, "Genesis"), 1, "the spine root must be SINGLE")

    def test_rename_into_a_group_that_has_nodes_but_no_spine_is_a_normal_migration(self):
        """The common recoverable case: the new id already collected some sweep output but never
        got a backbone. Nothing is editorial here, so the migration runs."""
        old, new = self._fixture("old"), self._fixture("partial")
        self._seed(old, entities=2)
        self._seed(new, entities=3, spine=False)
        total = self._count(old) + self._count(new)
        with self.driver.session() as s:
            plan = group_admin.rename_plan(s, old, new)
            self.assertEqual(plan["blockers"], [])
            group_admin.rename_apply(s, plan)
        self.assertEqual(self._count(old), 0)
        self.assertEqual(self._count(new), total)
        self.assertEqual(self._count(new, "Genesis"), 1)

    def test_a_spine_collision_shows_the_discard_before_it_happens(self):
        """The real fleet shape: BOTH ids carry a spine (`peter tosh` and `petertosh` each have a
        Genesis and an Objective). Policy (operator, 2026-08-16): the DESTINATION's spine wins.
        The dry-run must therefore name, verbatim, the norte it is about to destroy — a declared
        direction may be discarded by decision, never in silence."""
        old, new = self._fixture("fork"), self._fixture("main")
        self._seed(old, entities=2, objective="norte antigo")
        self._seed(new, entities=5, objective="norte vivo")
        with self.driver.session() as s:
            plan = group_admin.rename_plan(s, old, new)
            rendered = group_admin._render_rename(plan)
        self.assertIn("Genesis", plan["collisions"])
        self.assertIn("Objective", plan["collisions"])
        self.assertEqual(sorted(d["label"] for d in plan["discards"]), ["Genesis", "Objective"])
        self.assertIn("norte antigo", rendered)          # the body being destroyed, in full
        self.assertIn("norte vivo", rendered)            # the body that survives
        self.assertIn("DISCARD", rendered)
        self.assertIn("KEEP", rendered)

    def test_the_destination_spine_wins_and_the_source_corpus_is_adopted(self):
        old, new = self._fixture("fork"), self._fixture("main")
        self._seed(old, entities=2, objective="norte antigo")
        self._seed(new, entities=5, objective="norte vivo")
        old_nodes, new_nodes = self._count(old), self._count(new)
        with self.driver.session() as s:
            plan = group_admin.rename_plan(s, old, new)
            keep = s.run("MATCH (n:Objective) WHERE n.group_id=$g RETURN n.body AS b",
                         g=new).single()["b"]
            result = group_admin.rename_apply(s, plan)
            bodies = [r["b"] for r in s.run(
                "MATCH (n:Objective) WHERE n.group_id=$g RETURN n.body AS b", g=new).data()]
        self.assertEqual(self._count(old), 0, "the old group id must be EMPTY after a merge")
        self.assertEqual(self._count(new, "Genesis"), 1, "one identity root, always")
        self.assertEqual(bodies, [keep], "the destination's norte is the one that survives")
        # 2 spine nodes discarded; every other node of the source is adopted corpus
        self.assertEqual(self._count(new), old_nodes + new_nodes - 2)
        self.assertEqual(result["discarded"], 2)

    def test_edges_of_a_discarded_spine_node_are_rewired_never_orphaned(self):
        """Trading duplication for orphans is not a fix.

        The source's Objective ANCHORS a Direction that comes along as adopted corpus, and the
        destination has no such edge to fall back on. If the discard simply deleted the source
        Objective, that Direction would arrive unreachable from the surviving spine — memory
        that is present but cannot be walked to. So the edge must land on the heir."""
        old, new = self._fixture("fork"), self._fixture("main")
        self._seed(old, entities=1, objective="norte antigo")
        self._seed(new, entities=1, objective="norte vivo")
        with self.driver.session() as s:
            s.run("CREATE (d:Direction {group_id:$g, body:$b})", g=old, b="rumo adotado")
            s.run("MATCH (o:Objective {group_id:$g}),(d:Direction {group_id:$g}) "
                  "MERGE (o)-[:ANCHORS]->(d)", g=old)
            plan = group_admin.rename_plan(s, old, new)
            incident = sum(len(group_admin._incident_edges(s, d["id"]))
                           for d in plan["discards"])
            group_admin.rename_apply(s, plan)
            anchored = s.run(
                "MATCH (o:Objective)-[:ANCHORS]->(d:Direction) "
                "WHERE o.group_id=$g AND d.body=$b RETURN o.body AS b", g=new,
                b="rumo adotado").data()
            grounds = s.run(
                "MATCH (g:Genesis)-[:GROUNDS]->(o:Objective) "
                "WHERE g.group_id=$g AND o.group_id=$g RETURN count(*) AS n",
                g=new).single()["n"]
            dangling = s.run(
                "MATCH (n) WHERE n.group_id=$g AND NOT (n)--() "
                "AND NOT n:Genesis RETURN count(n) AS n", g=new).single()["n"]
        self.assertEqual(len(plan["rewires"]) + len(plan["dropped"]), incident,
                         "every edge of a discarded node must be accounted for")
        self.assertEqual([r["b"] for r in anchored], ["norte vivo"],
                         "the adopted Direction must hang off the SURVIVING norte")
        self.assertEqual(grounds, 1, "the surviving spine is still connected")
        self.assertEqual(dangling, 0, "no adopted node was left dangling")

    def test_an_ambiguous_heir_drops_edges_explicitly_rather_than_inventing_one(self):
        """`petertosh` carries SIX Objectives: no non-arbitrary heir exists for the edges of the
        discarded one. The plan says so, per edge type, instead of picking a norte nobody chose."""
        old, new = self._fixture("fork"), self._fixture("many")
        self._seed(old, entities=1, objective="norte antigo")
        self._seed(new, entities=1, objective="norte 1")
        with self.driver.session() as s:
            for extra in ("norte 2", "norte 3"):
                s.run("CREATE (o:Objective {group_id:$g, body:$b})", g=new, b=extra)
            plan = group_admin.rename_plan(s, old, new)
            rendered = group_admin._render_rename(plan)
        self.assertIsNone(plan["heirs"]["Objective"], "3 candidates → no unambiguous heir")
        self.assertEqual(plan["heirs"]["Genesis"], plan["collisions"]["Genesis"]["target"][0]["id"])
        self.assertTrue(any(d["label"] == "Objective" for d in plan["dropped"]), plan["dropped"])
        self.assertIn("no unambiguous heir", rendered)
        self.assertIn("DROP", rendered)

    def test_apply_requires_the_discard_token_on_top_of_the_confirm(self):
        """Moving nodes and destroying a declared norte must not be the same keystroke."""
        old, new = self._fixture("fork"), self._fixture("main")
        self._seed(old, entities=1)
        self._seed(new, entities=1)
        with self.driver.session() as s:
            rc = group_admin.main(["rename", old, new, "--apply", "--confirm", new], session=s)
            self.assertEqual(rc, 2)
            self.assertEqual(self._count(old), 4, "a refused merge must move NOTHING")
            rc = group_admin.main(["rename", old, new, "--apply", "--confirm", new,
                                   "--discard-source-spine"], session=s)
        self.assertEqual(rc, 0)
        self.assertEqual(self._count(old), 0)
        self.assertEqual(self._count(new, "Genesis"), 1)

    def test_a_stripped_plan_still_cannot_commit_two_identity_roots(self):
        """Defence in depth for the acceptance criterion. A caller determined to force it — here,
        by deleting the plan's `discards` so the merge would move both spines in — still cannot
        commit: the transaction re-checks the destination and rolls back rather than leave two
        `:Genesis` under one group id."""
        old, new = self._fixture("fork"), self._fixture("main")
        self._seed(old, entities=1)
        self._seed(new, entities=1)
        with self.driver.session() as s:
            plan = dict(group_admin.rename_plan(s, old, new),
                        discards=[], rewires=[], dropped=[])
            with self.assertRaises(group_admin.GroupAdminError):
                group_admin.rename_apply(s, plan)
        self.assertEqual(self._count(new, "Genesis"), 1)
        self.assertEqual(self._count(old, "Genesis"), 1)

    def test_a_drifted_plan_rolls_back_instead_of_half_renaming(self):
        """Atomicity with teeth: if the graph moved under the plan, apply aborts with the OLD
        group intact — never a tenant split across two ids."""
        old, new = self._fixture("drift"), self._fixture("dest")
        self._seed(old, entities=2)
        with self.driver.session() as s:
            plan = group_admin.rename_plan(s, old, new)
            plan = dict(plan, nodes=plan["nodes"] + 7)        # the graph "changed" underneath
            with self.assertRaises(group_admin.GroupAdminError):
                group_admin.rename_apply(s, plan)
        self.assertEqual(self._count(new), 0, "a rolled-back rename must move NOTHING")
        self.assertNotEqual(self._count(old), 0)

    def test_rename_never_touches_a_third_group(self):
        old, new, bystander = self._fixture("a"), self._fixture("b"), self._fixture("c")
        self._seed(old, entities=2)
        self._seed(bystander, entities=4)
        before = self._count(bystander)
        with self.driver.session() as s:
            group_admin.rename_apply(s, group_admin.rename_plan(s, old, new))
        self.assertEqual(self._count(bystander), before)


class GcListsExactlyWhatItWouldDelete(LiveFixtureCase):
    """A gc that deletes by mistake is worse than the tomb it clears. The dry-run plan and the
    delete share ONE derivation, and the delete asserts the match INSIDE the transaction."""

    STALE = "2026-06-01"

    def test_plan_counts_every_node_and_edge_the_delete_removes(self):
        dead = self._fixture("tomb")
        self._seed(dead, entities=4, spine=False)         # unrooted debris: the collectable shape
        with self.driver.session() as s:
            plan = group_admin.gc_plan(s, dead, stale_since=self.STALE)
            self.assertEqual(plan["blockers"], [])
            self.assertEqual(plan["nodes"], self._count(dead))
            self.assertEqual(sum(plan["by_label"].values()), plan["nodes"])
            result = group_admin.gc_apply(s, plan)
        self.assertEqual(result["deleted_nodes"], plan["nodes"])
        self.assertEqual(result["deleted_rels"], plan["rels"])
        self.assertEqual(self._count(dead), 0)

    def test_a_rooted_group_is_not_collected_without_a_declared_burial(self):
        """The incident, reproduced against the real thing: a tenant with an identity root is
        refused by the plan itself, and `gc_apply` on that plan deletes nothing."""
        alive = self._fixture("rooted")
        self._seed(alive, entities=3)                     # spine=True → holds a :Genesis
        before = self._count(alive)
        with self.driver.session() as s:
            plan = group_admin.gc_plan(s, alive, stale_since=self.STALE)
            self.assertTrue(any(group_admin.SPINE_ROOT in b for b in plan["blockers"]),
                            plan["blockers"])
            with self.assertRaises(group_admin.GroupAdminError):
                group_admin.gc_apply(s, plan)
        self.assertEqual(self._count(alive), before)

    def test_a_declared_burial_of_a_stale_rooted_tenant_goes_through(self):
        """The `edge-next` case (476 nodes, abandoned): the operator decided to bury it, so the
        tool has to actually do it — spine and all — once the burial is declared out loud."""
        tomb = self._fixture("edgenext")
        self._seed(tomb, entities=3)                      # rooted, timestamps in 2026-01
        before = self._count(tomb)
        with self.driver.session() as s:
            rc = group_admin.main(
                ["gc", "--delete", tomb, "--confirm", tomb, "--stale-since", self.STALE,
                 "--bury-rooted"], session=s, live_group="ed")
        self.assertEqual(rc, 0)
        self.assertEqual(self._count(tomb), 0, "a declared burial must actually bury")
        self.assertGreater(before, 0)

    def test_a_group_that_moved_recently_cannot_be_collected(self):
        dead = self._fixture("warm")
        self._seed(dead, entities=2, spine=False)
        with self.driver.session() as s:
            plan = group_admin.gc_plan(s, dead, stale_since="2025-01-01")
            self.assertTrue(plan["blockers"])
            with self.assertRaises(group_admin.GroupAdminError):
                group_admin.gc_apply(s, plan)
        self.assertEqual(self._count(dead), 4, "a refused collection must delete NOTHING")

    def test_a_drifted_gc_plan_rolls_back(self):
        dead = self._fixture("tomb")
        self._seed(dead, entities=3, spine=False)
        before = self._count(dead)
        with self.driver.session() as s:
            plan = group_admin.gc_plan(s, dead, stale_since=self.STALE)
            plan = dict(plan, nodes=plan["nodes"] - 1)        # under-counted → must NOT delete
            with self.assertRaises(group_admin.GroupAdminError):
                group_admin.gc_apply(s, plan)
        self.assertEqual(self._count(dead), before, "a drifted gc plan must delete NOTHING")

    def test_inventory_carries_the_evidence_a_delete_decision_needs(self):
        rooted, bare = self._fixture("rooted"), self._fixture("bare")
        self._seed(rooted, entities=1)
        self._seed(bare, entities=1, spine=False)
        with self.driver.session() as s:
            rows = {r["group"]: r for r in group_admin.inventory(s)}
        self.assertEqual(rows[rooted]["genesis"], 1)
        self.assertEqual(rows[bare]["genesis"], 0)
        self.assertEqual(rows[bare]["last_activity"], "2026-01-01T00:00:00Z")
        self.assertGreater(rows[rooted]["rels"], 0)


class GcBorrowsItsListingFromGroupHealth(LiveFixtureCase):
    """`gc --stale` does not re-decide what #636 already decided. `group_health.leftovers` owns
    "which groups have no install here" and "which nodes carry no group_id"; this module adds
    only the per-group evidence a DELETE needs (identity root, last activity) and the gate."""

    def test_the_listing_is_group_healths_leftovers_verbatim(self):
        import group_health
        orphan = self._fixture("orphan")
        self._seed(orphan, entities=1, spine=False)
        with self.driver.session() as s:
            expected = group_health.leftovers(s, {"ed"})
            printed = group_admin._render_gc(
                group_admin.inventory(s), expected, [], False, "ed")
        self.assertTrue(any(orphan in msg for _sev, msg in expected), expected)
        for _sev, msg in expected:
            self.assertIn(msg, printed)

    def test_ungrouped_nodes_are_diagnosis_and_never_a_delete_target(self):
        """A node written without a tenant stamp is a WRITE-PATH bug — evidence to keep, not
        dirt to sweep. `gc` has no way to aim at them: the target is always a named group."""
        with self.driver.session() as s:
            plan = group_admin.gc_plan(s, None, stale_since="2026-06-01")
            self.assertTrue(plan["blockers"])
            with self.assertRaises(group_admin.GroupAdminError):
                group_admin.gc_apply(s, plan)
            rc = group_admin.main(["gc", "--delete", "", "--confirm", "",
                                   "--stale-since", "2026-06-01"], session=s, live_group="ed")
        self.assertEqual(rc, 2)
        rendered = group_admin._render_gc([], [], [], False, "ed")
        self.assertIn("never garbage", rendered)


class GuardRefusesTheSecondGenesis(LiveFixtureCase):
    """Leg 2 against a real Bolt: an empty group beside a populated tenant is refused, and the
    refusal NAMES the group to migrate from."""

    def test_empty_group_beside_a_live_tenant_is_refused(self):
        live, fresh = self._fixture("live"), self._fixture("fresh")
        self._seed(live, entities=2)
        with self.driver.session() as s:
            v = group_admin.tenant_verdict(s, fresh)
        self.assertEqual(v["status"], "fork_suspect")
        self.assertFalse(v["ok"])
        self.assertIn(live, v["candidates"])
        self.assertIn("edge-group rename", v["detail"])

    def test_after_the_rename_the_guard_is_satisfied(self):
        live, fresh = self._fixture("live"), self._fixture("fresh")
        self._seed(live, entities=2)
        with self.driver.session() as s:
            group_admin.rename_apply(s, group_admin.rename_plan(s, live, fresh))
            v = group_admin.tenant_verdict(s, fresh)
        self.assertEqual(v["status"], "owner")
        self.assertTrue(v["ok"])


if __name__ == "__main__":
    unittest.main()
