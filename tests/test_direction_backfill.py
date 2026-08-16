"""The #632 backfill — give the Directions already in the fleet a handle, MARKED AS GENERATED.

The contract in `eventlog` binds NEW writes. It does nothing for the 788 nodes already in
`roberto` or the 577 in `petertosh`: those were written body-only and cannot be re-authored. This
migration derives a handle from the first sentence of each body so `group_health` can count them
and `recall` can list them — and stamps `title_generated` on every one, because a derived handle
is a legible placeholder, never a claim that somebody named the steer.

Hermetic, like test_group_health: no Neo4j is opened. The double answers by query signature, so a
changed query goes RED instead of silently matching nothing.

BRIEF rule 3 (migration): dry-run is the DEFAULT and shows the plan; writing takes an explicit
flag, and this file pins that with a WRITE LEDGER rather than by reading the source.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import direction_backfill  # noqa: E402
import eventlog  # noqa: E402


class _Result(list):
    def single(self):
        return self[0] if self else None


class FakeSession:
    """A handful of :Direction rows, and a ledger of every write attempted."""

    def __init__(self, rows):
        self.rows = rows
        self.writes = []

    def run(self, cypher, **kw):
        if "SET " in cypher or "DELETE" in cypher or "MERGE" in cypher:
            self.writes.append((cypher, kw))
            # the guard in BACKFILL_QUERY: only a still-untitled node comes back
            hit = [r for r in self.rows
                   if r["body"] == kw.get("node_id") and not r.get("title")]
            return _Result({"node_id": kw.get("node_id")} for _ in hit)
        if "count(d)" in cypher:
            return _Result([{
                "total": len(self.rows),
                "titled": sum(1 for r in self.rows if r.get("title")),
                "derived": sum(1 for r in self.rows if r.get("title_generated")),
                "with_expiry": sum(1 for r in self.rows if r.get("expires_at")),
            }])
        if ":Direction" in cypher:
            return _Result({"node_id": r["body"], "direction_id": r.get("id"), "body": r["body"]}
                           for r in self.rows if not r.get("title"))
        raise AssertionError(f"query not recognised by the double: {cypher[:70]}")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeDriver:
    def __init__(self, rows):
        self.fake = FakeSession(rows)

    def session(self):
        return self.fake

    @property
    def writes(self):
        return self.fake.writes


UNTITLED = {"body": "Fechar o rito de onboarding antes de qualquer outra coisa. O resto espera.",
            "id": "d1", "title": None}
TITLED = {"body": "ja tem handle", "id": "d2", "title": "handle existente"}
DERIVED_TITLE = "Fechar o rito de onboarding antes de qualquer outra coisa"


class ThePlanIsReadOnlyAndNamesEveryChange(unittest.TestCase):

    def test_planning_writes_nothing(self):
        d = FakeDriver([UNTITLED, TITLED])
        direction_backfill.plan(group="roberto", driver=d)
        self.assertEqual(d.writes, [], "planning must not touch the graph")

    def test_only_the_handle_less_nodes_are_planned(self):
        d = FakeDriver([UNTITLED, TITLED])
        rows = direction_backfill.plan(group="roberto", driver=d)
        self.assertEqual([r["direction_id"] for r in rows], ["d1"],
                         "a node that already has a handle is left alone")

    def test_the_derived_title_is_the_first_sentence(self):
        d = FakeDriver([UNTITLED])
        self.assertEqual(direction_backfill.plan(group="g", driver=d)[0]["title"], DERIVED_TITLE)

    def test_a_long_first_sentence_is_cut_to_the_handle_budget(self):
        d = FakeDriver([{"body": "palavra " * 60, "id": "d9", "title": None}])
        title = direction_backfill.plan(group="g", driver=d)[0]["title"]
        self.assertLessEqual(len(title), eventlog.DIRECTION_TITLE_MAX)
        self.assertTrue(title.endswith("…"), "a cut handle must show that it was cut")

    def test_a_body_with_nothing_to_derive_from_is_reported_not_invented(self):
        # An empty body has no first sentence. Inventing a handle would be fabricating data about
        # a steer nobody can read — the row is reported with title=None and skipped at write time.
        d = FakeDriver([{"body": "   ", "id": "d0", "title": None}])
        rows = direction_backfill.plan(group="g", driver=d)
        self.assertEqual([r["title"] for r in rows], [None])


class ApplyingIsExplicitAndAlwaysMarksTheTitleGenerated(unittest.TestCase):

    def test_apply_stamps_title_generated_on_every_row(self):
        d = FakeDriver([UNTITLED])
        written = direction_backfill.apply(group="roberto", driver=d)
        self.assertEqual(written, 1)
        cypher, params = d.writes[0]
        self.assertIn("d.title_generated = true", cypher)
        self.assertEqual(params["title"], DERIVED_TITLE)

    def test_a_row_with_no_derivable_title_is_skipped_not_written(self):
        d = FakeDriver([{"body": "   ", "id": "d0", "title": None}])
        self.assertEqual(direction_backfill.apply(group="g", driver=d), 0)
        self.assertEqual(d.writes, [], "an empty handle is worse than none — never write it")

    def test_apply_never_deletes_or_rewrites_a_body(self):
        d = FakeDriver([UNTITLED])
        direction_backfill.apply(group="roberto", driver=d)
        for cypher, _ in d.writes:
            self.assertNotIn("DELETE", cypher.upper())
            self.assertNotIn("d.body =", cypher)

    def test_apply_reguards_against_a_handle_that_appeared_meanwhile(self):
        # The plan is read before the write; in between, a beat may have authored a real title.
        # The write re-checks emptiness so a derived handle never clobbers an authored one.
        d = FakeDriver([UNTITLED])
        direction_backfill.apply(group="roberto", driver=d)
        cypher, _ = d.writes[0]
        self.assertIn("coalesce(d.title,'') = ''", cypher)

    def test_a_second_run_is_a_no_op(self):
        # Idempotence: after the first pass the nodes carry titles, so the untitled query returns
        # nothing and the tool writes nothing. Safe to re-run on the fleet.
        rows = [dict(UNTITLED)]
        d = FakeDriver(rows)
        direction_backfill.apply(group="roberto", driver=d)
        rows[0]["title"] = DERIVED_TITLE  # the graph now reflects the first pass
        d2 = FakeDriver(rows)
        self.assertEqual(direction_backfill.apply(group="roberto", driver=d2), 0)
        self.assertEqual(d2.writes, [])


class TheCommandLineIsDryRunByDefault(unittest.TestCase):

    def _run(self, argv, rows):
        d = FakeDriver(rows)
        out = []
        direction_backfill.main(argv + ["--group", "roberto"], driver=d, echo=out.append)
        return d, "\n".join(str(x) for x in out)

    def test_default_run_prints_the_plan_and_writes_nothing(self):
        d, out = self._run([], [UNTITLED, TITLED])
        self.assertEqual(d.writes, [], "a bare run must never write (BRIEF rule 3)")
        self.assertIn("DRY-RUN", out)
        self.assertIn(DERIVED_TITLE, out)

    def test_the_plan_reports_the_census_before_and_the_count_to_change(self):
        d, out = self._run([], [UNTITLED, TITLED])
        self.assertIn("2 Direction(s)", out)
        self.assertIn("1 with a handle", out)
        self.assertIn("1 without a handle", out)

    def test_apply_flag_writes(self):
        d, out = self._run(["--apply"], [UNTITLED])
        self.assertEqual(len(d.writes), 1)
        self.assertIn("applied: 1", out)

    def test_a_graph_with_nothing_to_do_writes_nothing(self):
        d, out = self._run([], [TITLED])
        self.assertEqual(d.writes, [])
        self.assertIn("0 without a handle", out)


if __name__ == "__main__":
    unittest.main()
