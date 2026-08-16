"""Issue #632 — a Direction needs a HANDLE and an END.

The fleet read of 2026-08-16 found 788 `:Direction` nodes in `roberto`, 577 in `petertosh`,
each carrying only a `body`. The question "what is this agent working on?" had no answer short
of opening eight hundred paragraphs, and `consolidate` had nothing to merge on — so every beat
just appended one more.

Two defects, one root: a Direction has no SHORT NAME and no END.

  (1) HANDLE — the write path accepted a body-only steer. These tests pin the contract: a NEW
      `direction.proposed` / `direction.set` requires a `title` of <= 80 chars, on one line, or
      the write FAILS. Nothing lands.

  (2) END — the live counterexample is this host's own graph. Group `ed` holds exactly ONE
      Direction, and it is the WELL-WRITTEN one: it names its own deadline in the body,
      "PRAZO EXPLICITO: esta Direction expira no nascimento de ed". The agent.yaml was emitted
      the same day, so the deadline PASSED — and nothing in the system can tell, because the
      deadline is PROSE, not a field. `expires_at` makes the fold able to read it.

Compatibility (BRIEF rule 4): the contract binds NEW writes. Legacy events with no title/expiry
must keep folding and rendering exactly as before — `LegacyDirectionsKeepReading` pins that.
"""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)
TITLE = "audit the install path"


class ANewDirectionRequiresATitle(unittest.TestCase):
    """Part 1 of #632: 'toda Direction nova exige titulo curto (<=80) + body. Sem titulo, a
    escrita FALHA (nao "body-only ok")'. The gate is on the WRITE, not on a linter downstream:
    a steer with no handle must never reach the log in the first place."""

    def test_propose_without_a_title_fails_and_nothing_lands(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaises(ValueError):
                eventlog.propose("d1", "a long steer body", log=log)
            self.assertEqual(eventlog.read(log=log), [], "no title must mean no write")

    def test_set_direction_without_a_title_fails_and_nothing_lands(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaises(ValueError):
                eventlog.set_direction("d1", "a long steer body", log=log)
            self.assertEqual(eventlog.read(log=log), [], "no title must mean no write")

    def test_blank_and_overlong_and_multiline_titles_all_fail(self):
        # A whitespace title is no title; >80 chars is a paragraph wearing a handle's name; a
        # newline turns the "short handle" back into the body it was supposed to replace.
        bad = ["", "   ", "\n\t ", "x" * (eventlog.DIRECTION_TITLE_MAX + 1),
               "two\nlines", 123, ["a"]]
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            for t in bad:
                with self.subTest(title=t):
                    with self.assertRaises(ValueError):
                        eventlog.propose("d1", "body", title=t, log=log)
                    with self.assertRaises(ValueError):
                        eventlog.set_direction("d1", "body", title=t, log=log)
            self.assertEqual(eventlog.read(log=log), [])

    def test_a_title_at_the_limit_writes_and_is_stripped(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            edge = "x" * eventlog.DIRECTION_TITLE_MAX
            eventlog.propose("d1", "body", title=f"  {edge}  ", log=log)
            self.assertEqual(eventlog.read(log=log)[0]["payload"]["title"], edge)

    def test_the_title_folds_through_to_both_tiers(self):
        # The handle is useless if the fold drops it: recall/briefing read the FOLD, not the log.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.propose("d1", "long body one", title="close the grill", log=log)
            eventlog.set_direction("d2", "long body two", title=TITLE, log=log)
            d = eventlog.direction_at(log=log)
            self.assertEqual(d["proposed"][0]["title"], "close the grill")
            self.assertEqual(d["set"][0]["title"], TITLE)

    def test_the_body_is_still_required(self):
        # The title does not BUY OFF the body — a handle with nothing behind it is worse than
        # a body with no handle (it reads as substance in every list).
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaises(ValueError):
                eventlog.set_direction("d1", "   ", title=TITLE, log=log)
            self.assertEqual(eventlog.read(log=log), [])


class ADirectionCanDeclareItsEnd(unittest.TestCase):
    """Part 2 of #632: lifecycle. `supersedes` was ALREADY honored by the fold (a set retires the
    id it supersedes), so the missing half is the CALENDAR one — a steer that dies on a date with
    nobody there to retire it. The live counterexample is group `ed` on this host: one Direction,
    well written, whose deadline is a sentence in the body and therefore unreadable by anything."""

    def test_an_expired_direction_leaves_the_live_fold(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_direction("dead", "the install-path audit", title="audit install",
                                   expires_at="2026-08-15", log=log)
            eventlog.set_direction("live", "the next steer", title="next steer",
                                   expires_at="2026-12-31", log=log)
            d = eventlog.direction_at(now=NOW, log=log)
            self.assertEqual([i["id"] for i in d["set"]], ["live"])

    def test_expiry_is_inclusive_of_its_own_day(self):
        # "expires 2026-08-16" must still be live DURING 2026-08-16 — a date-only expiry names
        # the last day the steer holds, not the first day it is gone.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_direction("d1", "body", title=TITLE, expires_at="2026-08-16", log=log)
            self.assertEqual([i["id"] for i in eventlog.direction_at(now=NOW, log=log)["set"]],
                             ["d1"])
            later = NOW + timedelta(days=1)
            self.assertEqual(eventlog.direction_at(now=later, log=log)["set"], [])

    def test_expired_directions_are_listed_not_silently_gone(self):
        # Leaving the live fold must not mean vanishing: an expired steer is still readable, so a
        # beat can see WHAT ran out and write the successor (#632: "sucessora e buraco aberto no
        # mapa, nao silencio").
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_direction("dead", "body", title="audit install",
                                   expires_at="2026-08-15", log=log)
            gone = eventlog.expired_directions(now=NOW, log=log)
            self.assertEqual([i["id"] for i in gone], ["dead"])
            self.assertEqual(gone[0]["title"], "audit install")

    def test_a_dropped_direction_does_not_resurface_as_expired(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_direction("d1", "body", title=TITLE, expires_at="2026-08-15", log=log)
            eventlog.drop("d1", "retired by hand", log=log)
            self.assertEqual(eventlog.expired_directions(now=NOW, log=log), [])

    def test_a_ts_cursor_is_its_own_clock_not_the_wall_clock(self):
        # `direction_at` promises that replaying to a cursor reconstructs the world AT that cursor.
        # Expiry must therefore be read against the CURSOR, not against wall-clock: the same steer
        # is live at a cursor inside its window and gone at one past it, and neither answer moves
        # when the machine's clock does.
        far = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
        inside = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        outside = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_direction("d1", "body", title=TITLE, expires_at=far, log=log)
            self.assertEqual([i["id"] for i in eventlog.direction_at(ts=inside, log=log)["set"]],
                             ["d1"], "a cursor inside the window must see the steer live")
            self.assertEqual(eventlog.direction_at(ts=outside, log=log)["set"], [],
                             "a cursor past the window must see it retired")

    def test_a_seq_cursor_still_answers_to_now(self):
        # A seq cursor carries no clock of its own, so the live read decides: the wall clock is the
        # only thing that can notice a deadline passing with no beat present to retire the steer.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            ev = eventlog.set_direction("d1", "body", title=TITLE,
                                        expires_at="2026-08-15", log=log)
            self.assertEqual(eventlog.direction_at(seq=ev["seq"], now=NOW, log=log)["set"], [])

    def test_a_garbage_expiry_fails_the_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            for bad in ("someday", "2026-13-40", "", 20260816, []):
                with self.subTest(expires_at=bad):
                    with self.assertRaises(ValueError):
                        eventlog.set_direction("d1", "body", title=TITLE,
                                               expires_at=bad, log=log)
            self.assertEqual(eventlog.read(log=log), [])

    def test_supersedes_is_honored_not_a_dead_field(self):
        # Pinned here because #632 asked whether `supersedes` was live: it IS (fold_direction
        # pops the superseded id). This test is the receipt, so the answer survives the issue.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.propose("old", "the prior steer", title="prior", log=log)
            eventlog.set_direction("new", "the successor", title="successor",
                                   supersedes="old", log=log)
            d = eventlog.direction_at(log=log)
            self.assertEqual([i["id"] for i in d["set"]], ["new"])
            self.assertEqual(d["proposed"], [])


class LegacyDirectionsKeepReading(unittest.TestCase):
    """BRIEF rule 4: the new contract binds NEW writes; the 788 nodes already in the fleet have
    no title and no expiry, and every read path over them must keep working unchanged."""

    def test_a_title_less_legacy_event_still_folds(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.append("direction.set", "direction",
                            {"id": "legacy", "body": "the old steer"}, log=log)
            d = eventlog.direction_at(now=NOW, log=log)
            self.assertEqual([i["id"] for i in d["set"]], ["legacy"])
            self.assertIsNone(d["set"][0]["title"])

    def test_a_corrupt_expiry_in_a_legacy_event_does_not_crash_the_fold(self):
        # Fail-dark, as the fold already does for a corrupt id: an unparseable expiry on a
        # historical event means "no declared end", never a crashed briefing.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.append("direction.set", "direction",
                            {"id": "legacy", "body": "old", "expires_at": ["nonsense"]}, log=log)
            d = eventlog.direction_at(now=NOW, log=log)
            self.assertEqual([i["id"] for i in d["set"]], ["legacy"])


class TheHandleReachesTheReader(unittest.TestCase):
    """Acceptance criterion 3 of #632: 'Recall/briefing lista Directions por titulo, nao por
    truncagem de body.' A title that only lives in the log is not a fix."""

    def test_the_direction_page_leads_with_the_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            out = Path(tmp) / "direction.md"
            eventlog.set_direction("d1", "a very long steer body that nobody wants in a list",
                                   title=TITLE, log=log)
            text = eventlog.project_direction(log=log, out=out)
            self.assertIn(TITLE, text)
            self.assertLess(text.index(TITLE), text.index("a very long steer body"),
                            "the handle must come before the paragraph")

    def test_the_briefing_section_leads_with_the_title(self):
        import briefing
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_direction("d1", "a very long steer body that nobody wants in a list",
                                   title=TITLE, log=log)
            text = briefing._section_direction(log, None, None)
            self.assertIn(TITLE, text)
            self.assertLess(text.index(TITLE), text.index("a very long steer body"))

    def test_a_legacy_title_less_item_still_renders_its_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            out = Path(tmp) / "direction.md"
            eventlog.append("direction.set", "direction",
                            {"id": "legacy", "body": "the old steer"}, log=log)
            self.assertIn("the old steer", eventlog.project_direction(log=log, out=out))


class TheProjectionCarriesTheHandleToTheGraph(unittest.TestCase):
    """A title that stops at the log is not a fix: `group_health` (#636) counts a Direction as
    handled only when the NODE carries `coalesce(title, name)`, and as having lifecycle only when
    the NODE carries `expires_at` or `supersedes`. This pins the projection that feeds it.

    The bug underneath: the node was MERGE'd by body alone and SET nothing, so even the fold's `id`
    never reached the graph — this host's one :Direction has keys ['body','group_id'] and no id.
    Body-as-only-key is exactly how a group accumulates 788 of them."""

    class _Rec(list):
        def single(self):
            return self[0] if self else None

    class _Session:
        def __init__(self):
            self.calls = []

        def run(self, cypher, **kw):
            self.calls.append((cypher, kw))
            # O dublê tem que RESPONDER as consultas que o código faz, não só registrá-las.
            # `merge_spine_objective` (#633) faz `.single()["id"]` sobre o MERGE da espinha; um
            # dublê que devolve vazio ali quebra com TypeError — e, pior, um que devolvesse algo
            # genérico esconderia a dependência. Responder só ao que é pedido mantém o dublê
            # honesto: se a projeção passar a exigir outra coluna, isto quebra em vez de mentir.
            if cypher.startswith("MERGE (o:Objective") and "elementId(o) AS id" in cypher:
                return TheProjectionCarriesTheHandleToTheGraph._Rec([{"id": "e-spine-1"}])
            return TheProjectionCarriesTheHandleToTheGraph._Rec()

    def _project(self, log):
        import publisher
        s = self._Session()
        publisher._project_backbone(s, "ed", log)
        return s

    def _direction_writes(self, s):
        return [(c, kw) for c, kw in s.calls if "MERGE (d:Direction" in c]

    def test_a_new_direction_lands_with_its_handle_and_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_objective("ship the handle", log=log)
            eventlog.set_direction("d1", "the long steer body", title=TITLE, log=log)
            writes = self._direction_writes(self._project(log))
            self.assertEqual(len(writes), 1)
            cypher, params = writes[0]
            self.assertEqual(params["t"], TITLE, "the handle must reach the node")
            self.assertEqual(params["id"], "d1", "the fold's id must reach the node")
            self.assertIn("d.title=", cypher)

    def test_a_declared_end_reaches_the_node_so_health_can_see_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_objective("ship the handle", log=log)
            eventlog.set_direction("d1", "body", title=TITLE, expires_at="2099-01-01", log=log)
            _cypher, params = self._direction_writes(self._project(log))[0]
            self.assertTrue(params["x"], "expires_at must reach the node, not stay in the log")

    def test_the_projection_never_wipes_a_backfilled_title_with_a_null(self):
        # A legacy (title-less) steer re-projects every canonical sweep. If the SET were
        # unconditional it would null out the handle the backfill just wrote, and the fleet would
        # silently regress to 788 unreadable nodes on the next wake.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_objective("ship the handle", log=log)
            eventlog.append("direction.set", "direction",
                            {"id": "legacy", "body": "the old steer"}, log=log)
            cypher, params = self._direction_writes(self._project(log))[0]
            self.assertIsNone(params["t"])
            self.assertIn("coalesce($t,d.title)", cypher)


class TheDrainParksRatherThanBlocks(unittest.TestCase):
    """The one place the title contract could hurt: the Voz rail. A standing Directive whose plan
    carries no handle must NOT crash the drain (a blocked rail) and must NOT quietly close as a
    plain reply (a lost steer, ADR-0017). It PARKS — the module's existing fail-safe — and asks the
    mentee to name the steer, so the chat stays open and nothing is lost."""

    def _drain(self):
        sys.path.insert(0, str(REPO / "blog"))
        import grill_drain
        return grill_drain

    def test_a_titleless_directive_parks_instead_of_raising(self):
        drain = self._drain()
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.append("voz.comment", "chat",
                            {"comment_id": "c1", "body": "always cite a benchmark"}, log=log)
            drain.drain(log, lambda c: {"reply": "r", "directive": True,
                                        "direction_body": "always cite a benchmark"},
                        grill_run_id="g1")
            types = [e["type"] for e in eventlog.read(log=log)]
            self.assertIn("voz.clarify", types, "no handle → park, never crash the rail")
            self.assertNotIn("direction.set", types, "a body-only steer must not land")
            self.assertNotIn("voz.resolved", types, "parking is non-terminal — the chat stays open")


class RecallReadsTheHandle(unittest.TestCase):
    """The graph read path: the spine query must return a handle, falling back to the body for a
    node the backfill has not reached yet."""

    def test_the_spine_query_prefers_the_title_over_the_body(self):
        import recall
        self.assertIn("d.title", recall.SPINE_QUERY)
        self.assertIn("d.body", recall.SPINE_QUERY,
                      "a legacy node with no title must still yield its body")


if __name__ == "__main__":
    unittest.main()
