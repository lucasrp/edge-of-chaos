"""Tier-0 event log — the append-only source of truth (ADR-0006, issue #9).

The log is truth: `state/events/log.jsonl`, one JSON event per line, never mutated.
`direction_at` folds `direction.set` events to the plan as-of-a-cursor — deterministic
replay IS the strategic-versioning feature. These tests pin the append/read/fold core
(pure Python, no graph).
"""
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402


class AppendThenReadRoundTrips(unittest.TestCase):
    """The tracer bullet: an appended event lands as one JSONL line, stamped with a
    monotonic seq and an ISO ts, and reads back with its type/subject/payload intact."""

    def test_append_returns_and_reads_back_stamped_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "events" / "log.jsonl"
            ev = eventlog.append("direction.set", "direction", {"plan": "X"}, log=log)
            self.assertEqual(ev["seq"], 1)
            self.assertEqual(ev["type"], "direction.set")
            self.assertEqual(ev["subject"], "direction")
            self.assertEqual(ev["payload"], {"plan": "X"})
            self.assertIn("ts", ev)
            self.assertEqual(eventlog.read(log=log), [ev])


class ReadReturnsEventsInSeqOrderFilteredByType(unittest.TestCase):
    """seq is monotonic across appends; read replays in order; `types=` keeps only those
    event types (issue #9 acceptance: read(types=["direction.set"]) returns both, in order)."""

    def test_monotonic_seq_and_type_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.append("direction.set", "direction", {"plan": "X"}, log=log)
            eventlog.append("grill.curated", "term:foo", {"outcome": "renamed"}, log=log)
            eventlog.append("direction.set", "direction", {"plan": "Y"}, log=log)
            self.assertEqual([e["seq"] for e in eventlog.read(log=log)], [1, 2, 3])
            sets = eventlog.read(types=["direction.set"], log=log)
            self.assertEqual([e["payload"]["plan"] for e in sets], ["X", "Y"])
            self.assertEqual([e["seq"] for e in sets], [1, 3])


class LogOnlyEverGrows(unittest.TestCase):
    """Append-only by construction: every append extends the file; earlier bytes are never
    rewritten (issue #9 acceptance: the log file only ever grows)."""

    def test_existing_bytes_are_a_prefix_after_more_appends(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.append("direction.set", "direction", {"plan": "X"}, log=log)
            before = log.read_bytes()
            eventlog.append("direction.set", "direction", {"plan": "Y"}, log=log)
            after = log.read_bytes()
            self.assertTrue(after.startswith(before))
            self.assertGreater(len(after), len(before))


class ReadStopsAtACursor(unittest.TestCase):
    """A cursor bounds the replay: until_seq keeps events with seq<=n; until_ts keeps events
    with ts<=t. This bounded window is what direction_at folds to reconstruct a past state."""

    def test_until_seq_and_until_ts(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            a = eventlog.append("direction.set", "direction", {"plan": "X"}, log=log)
            b = eventlog.append("direction.set", "direction", {"plan": "Y"}, log=log)
            self.assertEqual([e["seq"] for e in eventlog.read(until_seq=1, log=log)], [1])
            self.assertEqual([e["seq"] for e in eventlog.read(until_seq=2, log=log)], [1, 2])
            self.assertEqual([e["seq"] for e in eventlog.read(until_ts=a["ts"], log=log)], [1])
            self.assertEqual([e["seq"] for e in eventlog.read(until_ts=b["ts"], log=log)], [1, 2])


class DirectionFoldsPerIdIntoTwoTiers(unittest.TestCase):
    """ADR-0007: direction.proposed/set/dropped fold per id into two tiers — `set` (curated, Voz)
    and `proposed` (non-curated, grill achados). set outranks proposed for the same id; dropped
    removes it (persist-until-dropped); replay to a past cursor reconstructs both tiers."""

    def test_two_tiers_by_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.propose("a", "explore X", log=log)
            eventlog.set_direction("b", "ship Y", log=log)
            d = eventlog.direction_at(log=log)
            self.assertEqual([i["id"] for i in d["proposed"]], ["a"])
            self.assertEqual([i["id"] for i in d["set"]], ["b"])

    def test_set_outranks_proposed_same_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.propose("a", "maybe X", log=log)
            eventlog.set_direction("a", "X ratified", log=log)
            eventlog.propose("a", "waffle", log=log)  # cannot demote a set id
            d = eventlog.direction_at(log=log)
            self.assertEqual([i["id"] for i in d["set"]], ["a"])
            self.assertEqual(d["proposed"], [])

    def test_dropped_removes_and_stays_gone(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.propose("a", "X", log=log)
            eventlog.drop("a", "noise", log=log)
            self.assertEqual(eventlog.direction_at(log=log), {"set": [], "proposed": []})

    def test_set_carries_origin_comment_id_through_the_fold(self):
        # Slice 4: a Voz `folded-to-direction` writes `direction.set {..., origin_comment_id}`; the
        # fold must CARRY that provenance into the `set` item so the Direction surface can render the
        # steer⇄originating-comment link (SURFACE.md: provenance is tier-disjoint, non-deferred for v1).
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.append("direction.set", "direction",
                            {"id": "d1", "body": "always cite a benchmark",
                             "origin_comment_id": "c-abc123"}, log=log)
            d = eventlog.direction_at(log=log)
            self.assertEqual(d["set"][0]["origin_comment_id"], "c-abc123")

    def test_proposed_never_carries_origin_comment_id(self):
        # Tier-disjoint provenance (ADR-0007 / SURFACE.md): origin_comment_id rides ONLY the curated
        # `set` tier; a proposed item carries from_artefato/relates_to and origin_comment_id is None.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.propose("a", "explore X", from_artefato="alpha-post", log=log)
            d = eventlog.direction_at(log=log)
            self.assertIsNone(d["proposed"][0].get("origin_comment_id"))
            self.assertEqual(d["proposed"][0]["from_artefato"], "alpha-post")

    def test_set_supersedes_a_different_proposed_id(self):
        # ADR-0007: a direction.set that supersedes a DIFFERENT id must RETIRE that id. Codex
        # found supersedes was stored on the item but never honored — fold_direction only
        # dropped via direction.dropped or a same-id set, so the superseded proposal stayed
        # active alongside the new ruling.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.propose("introspection-ratio-watch", "watch recall/research ratio", log=log)
            eventlog.set_direction("worthwhile-test", "ship the worthwhile-test metric",
                                   supersedes="introspection-ratio-watch", log=log)
            d = eventlog.direction_at(log=log)
            self.assertEqual([i["id"] for i in d["set"]], ["worthwhile-test"])
            self.assertEqual(d["proposed"], [],
                             "supersedes must retire the named id, not leave it active")

    def test_supersedes_does_not_drop_its_own_id(self):
        # guard: supersedes pointing at the set's own id must NOT delete the item it just set.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.propose("a", "maybe X", log=log)
            eventlog.set_direction("a", "X ratified", supersedes="a", log=log)
            d = eventlog.direction_at(log=log)
            self.assertEqual([i["id"] for i in d["set"]], ["a"])
            self.assertEqual(d["proposed"], [])

    def test_replay_to_past_cursor(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            p = eventlog.propose("a", "X", log=log)              # seq 1
            eventlog.set_direction("a", "X ratified", log=log)   # seq 2
            past = eventlog.direction_at(seq=p["seq"], log=log)
            self.assertEqual([i["id"] for i in past["proposed"]], ["a"])
            self.assertEqual(past["set"], [])
            self.assertEqual([i["id"] for i in eventlog.direction_at(log=log)["set"]], ["a"])

    def test_empty_log_has_no_direction(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(eventlog.direction_at(log=Path(tmp) / "log.jsonl"))

    def test_fold_tolerates_a_list_valued_id(self):
        # Slice 4 [high]: fold_direction uses direction.set/proposed/dropped `id` AS a dict KEY; a
        # JSON-valid log with a LIST-valued id is unhashable → TypeError in the CANONICAL fold (not
        # just the /direction route). The fold must SKIP the corrupt event and still surface the valid
        # steers — direction_at()/project_direction()/the sweep all flow through here.
        for corrupt in ("direction.set", "direction.proposed", "direction.dropped"):
            with tempfile.TemporaryDirectory() as tmp:
                log = Path(tmp) / "log.jsonl"
                with open(log, "w") as fh:
                    fh.write(json.dumps({"seq": 1, "ts": "t", "type": "direction.set",
                                         "subject": "direction",
                                         "payload": {"id": "good", "body": "a real steer"}}) + "\n")
                    fh.write(json.dumps({"seq": 2, "ts": "t", "type": corrupt, "subject": "direction",
                                         "payload": {"id": ["not", "a", "string"],
                                                     "body": "corrupt"}}) + "\n")
                d = eventlog.direction_at(log=log)  # must not raise
                # the corrupt event is SKIPPED, not folded — only the valid steer survives (fail-dark,
                # never fail-poison: a corrupt id must not land as an active item).
                self.assertEqual([i["id"] for i in d["set"]], ["good"], corrupt)
                self.assertNotIn("corrupt", [i["body"] for i in d["set"] + d["proposed"]], corrupt)

    def test_fold_tolerates_a_truthy_non_dict_payload(self):
        # codex round-3 [medium]: a JSON-valid direction.* with a TRUTHY non-dict payload (a string /
        # non-empty list) passes `p = e.get("payload", {}) or {}` (only falsy → {}) and then
        # `p.get(...)` AttributeErrors the canonical fold — before the id/supersedes tolerance runs.
        # sweep.py calls project_direction() unguarded, so this must normalize, not crash.
        for bad_payload in ('"a string payload"', '[1, 2, 3]'):
            with tempfile.TemporaryDirectory() as tmp:
                log = Path(tmp) / "log.jsonl"
                with open(log, "w") as fh:
                    fh.write(json.dumps({"seq": 1, "ts": "t", "type": "direction.set",
                                         "subject": "direction",
                                         "payload": {"id": "good", "body": "a real steer"}}) + "\n")
                    fh.write('{"seq": 2, "ts": "t", "type": "direction.proposed", '
                             f'"subject": "direction", "payload": {bad_payload}}}\n')
                d = eventlog.direction_at(log=log)  # must not raise
                self.assertEqual([i["id"] for i in d["set"]], ["good"], bad_payload)

    def test_fold_tolerates_a_list_valued_supersedes(self):
        # a direction.set whose `supersedes` is a LIST — fold_direction does `items.pop(sup)`, and
        # pop with an unhashable key TypeErrors the canonical fold. It must skip-or-ignore and render.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with open(log, "w") as fh:
                fh.write(json.dumps({"seq": 1, "ts": "t", "type": "direction.set",
                                     "subject": "direction",
                                     "payload": {"id": "good", "body": "a real steer"}}) + "\n")
                fh.write(json.dumps({"seq": 2, "ts": "t", "type": "direction.set",
                                     "subject": "direction",
                                     "payload": {"id": "other", "body": "another steer",
                                                 "supersedes": ["good"]}}) + "\n")
            d = eventlog.direction_at(log=log)  # must not raise
            self.assertIn("other", [i["id"] for i in d["set"]])

    def test_direction_at_tolerates_a_non_dict_log_line(self):
        # codex round-2 [medium]: a JSON-valid NON-dict line (`[]`, `42`) must not crash the canonical
        # read BEFORE fold_direction's tolerance can apply — read() does e["type"]/e["seq"]/e["ts"]
        # on every parsed value. The typed read must skip non-dict envelopes so direction_at survives
        # (tools/sweep.py calls project_direction() unguarded — the route's private iterator does not
        # protect that path). The valid steer still folds.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with open(log, "w") as fh:
                fh.write(json.dumps({"seq": 1, "ts": "t", "type": "direction.set",
                                     "subject": "direction",
                                     "payload": {"id": "good", "body": "a real steer"}}) + "\n")
                fh.write("[]\n")
                fh.write("42\n")
            d = eventlog.direction_at(log=log)  # must not raise
            self.assertEqual([i["id"] for i in d["set"]], ["good"])

    def test_project_direction_tolerates_a_non_dict_log_line(self):
        # the sweep's projection path (tools.sweep → project_direction) must also survive a non-dict
        # line — it flows through the same read()/fold_direction, so the read-level skip protects it.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            out = Path(tmp) / "DIRECTION.md"
            with open(log, "w") as fh:
                fh.write(json.dumps({"seq": 1, "ts": "t", "type": "direction.set",
                                     "subject": "direction",
                                     "payload": {"id": "good", "body": "a real steer"}}) + "\n")
                fh.write("[]\n")
            text = eventlog.project_direction(log=log, out=out)  # must not raise
            self.assertIn("a real steer", text)

    def test_project_direction_tolerates_a_list_valued_id(self):
        # the projection caller (sweep/reprojection) must also survive a corrupt id — it flows through
        # fold_direction, so hardening the canonical fold protects it too (codex Slice-4 [high]).
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            out = Path(tmp) / "DIRECTION.md"
            with open(log, "w") as fh:
                fh.write(json.dumps({"seq": 1, "ts": "t", "type": "direction.set",
                                     "subject": "direction",
                                     "payload": {"id": "good", "body": "a real steer"}}) + "\n")
                fh.write(json.dumps({"seq": 2, "ts": "t", "type": "direction.set",
                                     "subject": "direction",
                                     "payload": {"id": ["bad"], "body": "corrupt"}}) + "\n")
            text = eventlog.project_direction(log=log, out=out)  # must not raise
            self.assertIn("a real steer", text)


class ProjectDirectionRendersBothTiers(unittest.TestCase):
    """The Direction page is a fold OUTPUT (ADR-0006/0007), banner-marked, with Set and Proposed
    sections; `from_artefato` provenance is shown. Projecting a past cursor writes that past."""

    def test_renders_both_tiers_marked_generated(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            out = Path(tmp) / "direction.md"
            eventlog.set_direction("b", "ship Y", kind="priority", log=log)
            eventlog.propose("c", "name the full-read budget", from_artefato="recall-report", log=log)
            eventlog.project_direction(log=log, out=out)
            text = out.read_text()
            self.assertIn("do not edit", text.lower())
            self.assertIn("## Set", text)
            self.assertIn("ship Y", text)
            self.assertIn("## Proposed", text)
            self.assertIn("name the full-read budget", text)
            self.assertIn("recall-report", text)  # provenance survives

    def test_projects_past_cursor(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            out = Path(tmp) / "direction.md"
            eventlog.propose("a", "alpha", log=log)
            eventlog.set_direction("a", "omega", log=log)
            eventlog.project_direction(seq=1, log=log, out=out)
            text = out.read_text()
            self.assertIn("alpha", text)
            self.assertNotIn("omega", text)


class ArtefatoProposalsConsolidateIntoProposedTier(unittest.TestCase):
    """ADR-0007/#14: artefato.published declares `proposes`; consolidation fans each into the
    non-curated `proposed` tier with from_artefato provenance, idempotently (deterministic id);
    a dropped candidate is never resurrected."""

    def test_candidates_become_proposed_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog._append_orphan_published_for_test("recall-report", proposes=[
                {"body": "name the full-read budget", "kind": "constraint"},
                {"body": "watch read:write ratio"}], log=log)
            self.assertEqual(eventlog.consolidate_artefato_proposals(log=log), 2)
            prop = eventlog.direction_at(log=log)["proposed"]
            self.assertEqual({i["from_artefato"] for i in prop}, {"recall-report"})
            self.assertIn("name the full-read budget", [i["body"] for i in prop])
            self.assertEqual(eventlog.consolidate_artefato_proposals(log=log), 0)  # idempotent

    def test_dropped_candidate_not_resurrected(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog._append_orphan_published_for_test("r", proposes=[{"body": "X"}], log=log)
            eventlog.consolidate_artefato_proposals(log=log)
            eventlog.drop("r:0", "rejected", log=log)
            self.assertEqual(eventlog.consolidate_artefato_proposals(log=log), 0)
            self.assertEqual(eventlog.direction_at(log=log)["proposed"], [])

    def test_consolidation_tolerates_a_corrupt_direction_payload(self):
        # codex Slice-4 round-4 [high]: _direction_ids() (the dedupe set) does
        # `(e.get("payload") or {}).get("id")` — a TRUTHY non-dict direction.* payload (string/list)
        # AttributeErrors it, and sweep.py calls consolidate_artefato_proposals() BEFORE
        # project_direction(), so one corrupt event would stop the sweep from adding proposals even
        # though direction_at() now tolerates it. Consolidation must share the fold's tolerance.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with open(log, "w") as fh:
                fh.write('{"seq": 1, "ts": "t", "type": "direction.set", "subject": "direction", '
                         '"payload": "a corrupt string payload"}\n')
                fh.write('{"seq": 2, "ts": "t", "type": "direction.proposed", "subject": "direction", '
                         '"payload": [1, 2, 3]}\n')
            eventlog._append_orphan_published_for_test("r", proposes=[{"body": "X"}], log=log)
            # must not raise — the valid candidate still consolidates past the corrupt direction events
            self.assertEqual(eventlog.consolidate_artefato_proposals(log=log), 1)
            self.assertIn("X", [i["body"] for i in eventlog.direction_at(log=log)["proposed"]])


class IntentKernelPairsToItsArtefato(unittest.TestCase):
    """CONTRACT C3 / ADR-0009: every dispatch that produces an Artefato emits an `intent.kernel`
    event at close — the durable *why* (what is open, the next bet). It pairs to its Artefato by
    slug (subject `artefato:<slug>`), so the corpus fold can join published + kernel by slug."""

    def test_kernel_appends_intent_kernel_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            ev = eventlog.kernel("recall-report",
                                 "open: read-budget unnamed; bet: name it next beat", log=log)
            self.assertEqual(ev["type"], "intent.kernel")
            self.assertEqual(ev["subject"], "artefato:recall-report")
            self.assertEqual(ev["payload"]["slug"], "recall-report")
            self.assertIn("bet", ev["payload"]["intent"])
            self.assertEqual(eventlog.read(types=["intent.kernel"], log=log), [ev])


class ArtefatosWithoutKernelAreFlagged(unittest.TestCase):
    """The C3 invariant as a pure fold — "no Artefato closes without an intent.kernel" made
    mechanically checkable: `artefatos_without_kernel` returns published slugs that have no
    matching kernel, in publish order. A slug is cleared the moment its kernel is emitted."""

    def test_published_without_kernel_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog._append_orphan_published_for_test("kerneled", log=log)
            eventlog.kernel("kerneled", "why", log=log)
            eventlog._append_orphan_published_for_test("bare", log=log)
            self.assertEqual(eventlog.artefatos_without_kernel(log=log), ["bare"])

    def test_clean_when_every_artefato_has_a_kernel(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog._append_orphan_published_for_test("a", log=log)
            eventlog.kernel("a", "why a", log=log)
            self.assertEqual(eventlog.artefatos_without_kernel(log=log), [])


class KernelDebtRequiresRealContentAfterPublish(unittest.TestCase):
    """Codex gate round-4 [high]: presence of an `intent.kernel` is NOT enough to clear C3 debt — a
    blank/whitespace/None intent, or a kernel that pairs BEFORE its publish (a stale pre-publish
    kernel), must STILL count as debt. Debt clears only when a slug has a kernel whose intent is a
    non-empty stripped string AND that kernel comes at/after the slug's `artefato.published`."""

    def _bare_kernel(self, slug, intent, log):
        # low-level append, bypassing kernel()'s own content guard, to manufacture the bad state
        return eventlog.append("intent.kernel", f"artefato:{slug}",
                               {"slug": slug, "intent": intent}, log=log)

    def test_blank_kernel_does_not_clear_debt(self):
        for bad in ("", "   ", "\n\t ", None):
            with tempfile.TemporaryDirectory() as tmp:
                log = Path(tmp) / "log.jsonl"
                eventlog._append_orphan_published_for_test("bare", log=log)
                self._bare_kernel("bare", bad, log)
                self.assertEqual(eventlog.artefatos_without_kernel(log=log), ["bare"])

    def test_kernel_before_publish_does_not_clear_debt(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.kernel("stale", "open: x; bet: y", log=log)               # kernel FIRST (seq 1)
            eventlog._append_orphan_published_for_test("stale", log=log)        # publish AFTER (seq 2)
            self.assertEqual(eventlog.artefatos_without_kernel(log=log), ["stale"])

    def test_real_kernel_after_publish_clears_debt(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog._append_orphan_published_for_test("ok", log=log)
            eventlog.kernel("ok", "open: x; bet: y", log=log)
            self.assertEqual(eventlog.artefatos_without_kernel(log=log), [])


class KernelRejectsHollowIntent(unittest.TestCase):
    """Codex gate round-4 [high]: `kernel()` is a write helper for the C3 *why* — it must refuse an
    empty/whitespace/non-string intent (raise ValueError, nothing lands) and store the STRIPPED
    intent, mirroring set_objective. A hollow kernel can never be the recorded why."""

    def test_kernel_rejects_empty_and_whitespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            for bad in ("", "   ", "\n\t "):
                with self.assertRaises(ValueError):
                    eventlog.kernel("slug", bad, log=log)
            self.assertEqual(eventlog.read(log=log), [])  # nothing landed

    def test_kernel_rejects_non_string_intent(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            for bad in (None, 7, ["why"], {"why": "x"}):
                with self.assertRaises(ValueError):
                    eventlog.kernel("slug", bad, log=log)
            self.assertEqual(eventlog.read(log=log), [])

    def test_kernel_strips_the_intent(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            ev = eventlog.kernel("slug", "  open: x; bet: y  ", log=log)
            self.assertEqual(ev["payload"]["intent"], "open: x; bet: y")


class CorpusFoldsPublishedArtefatosWithTheirWhy(unittest.TestCase):
    """ADR-0009: the corpus is a pure fold of `{artefato.published, intent.kernel}` paired by slug —
    the edge's own steps + their *why*. Each item carries slug, intent (from its kernel, None if none
    yet), the Artefato's proposes/distills/cites, and its published ts; in publish order. Cursor-aware:
    replaying to a past cursor reconstructs that past corpus (strategic versioning, as direction_at)."""

    def test_kernel_pairs_to_its_artefato_by_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog._append_orphan_published_for_test(
                "recall-report", proposes=[{"body": "name the budget"}],
                distills=["cluster:recall"], cites=["mundo:arxiv"], log=log)
            eventlog.kernel("recall-report", "open: budget unnamed; bet: name it next", log=log)
            corpus = eventlog.corpus_at(log=log)
            self.assertEqual([c["slug"] for c in corpus], ["recall-report"])
            self.assertEqual(corpus[0]["intent"], "open: budget unnamed; bet: name it next")
            self.assertEqual(corpus[0]["proposes"], [{"body": "name the budget"}])
            self.assertEqual(corpus[0]["distills"], ["cluster:recall"])
            self.assertEqual(corpus[0]["cites"], ["mundo:arxiv"])
            self.assertIn("ts", corpus[0])

    def test_artefato_without_kernel_folds_with_intent_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog._append_orphan_published_for_test("bare", log=log)
            corpus = eventlog.corpus_at(log=log)
            self.assertEqual([c["slug"] for c in corpus], ["bare"])
            self.assertIsNone(corpus[0]["intent"])

    def test_blank_kernel_folds_with_intent_none_no_open_bet(self):
        # a hollow kernel must render no open-bet — same content rule as the C3 debt fold
        for bad in ("", "   ", None):
            with tempfile.TemporaryDirectory() as tmp:
                log = Path(tmp) / "log.jsonl"
                eventlog._append_orphan_published_for_test("bare", log=log)
                eventlog.append("intent.kernel", "artefato:bare",
                                {"slug": "bare", "intent": bad}, log=log)
                corpus = eventlog.corpus_at(log=log)
                self.assertEqual([c["slug"] for c in corpus], ["bare"])
                self.assertIsNone(corpus[0]["intent"])

    def test_stale_pre_publish_kernel_folds_with_intent_none(self):
        # a kernel that pairs BEFORE the publish is stale — it does not become the why
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.kernel("stale", "open: x; bet: y", log=log)         # kernel FIRST
            eventlog._append_orphan_published_for_test("stale", log=log)  # publish AFTER
            corpus = eventlog.corpus_at(log=log)
            self.assertEqual([c["slug"] for c in corpus], ["stale"])
            self.assertIsNone(corpus[0]["intent"])

    def test_empty_log_has_empty_corpus(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(eventlog.corpus_at(log=Path(tmp) / "log.jsonl"), [])

    def test_replay_to_past_cursor_reconstructs_past_corpus(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            a = eventlog._append_orphan_published_for_test("first", log=log)  # seq 1
            eventlog.kernel("first", "why first", log=log)                    # seq 2
            eventlog._append_orphan_published_for_test("second", log=log)     # seq 3
            past = eventlog.corpus_at(seq=a["seq"], log=log)
            self.assertEqual([c["slug"] for c in past], ["first"])
            self.assertIsNone(past[0]["intent"])                     # kernel not yet emitted at seq 1
            now = eventlog.corpus_at(log=log)
            self.assertEqual([c["slug"] for c in now], ["first", "second"])
            self.assertEqual(now[0]["intent"], "why first")


class LineageRidesTheAtomicEventIntoTheCorpus(unittest.TestCase):
    """Cortex-v1 (brick-1, slice L2): the authored typed `lineage` (builds_on/supersedes/contradicts)
    rides the atomic `artefato.published` event and folds back onto the corpus item, so a later slice
    (reproject_graph) can replay it as DIRECTED edges. An Artefato with no lineage folds to []."""

    def test_lineage_rides_the_atomic_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            lineage = [{"type": "supersedes", "slug": "x"}]
            eventlog.publish_artefato_atomic(
                "with-lineage", "open: x; bet: y", lineage=lineage, log=log)
            corpus = eventlog.corpus_at(log=log)
            self.assertEqual([c["slug"] for c in corpus], ["with-lineage"])
            self.assertEqual(corpus[0]["lineage"], lineage)

    def test_no_lineage_folds_to_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.publish_artefato_atomic("no-lineage", "open: x; bet: y", log=log)
            corpus = eventlog.corpus_at(log=log)
            self.assertEqual([c["slug"] for c in corpus], ["no-lineage"])
            self.assertEqual(corpus[0]["lineage"], [])


class ProjectCorpusInscribesEachStepsWhy(unittest.TestCase):
    """ADR-0009: state/corpus.md is the corpus projection — part of Memento's tattoo, the zero-memory
    agent reads it to know what it already did and *why*. A fold OUTPUT (banner-marked, never hand-
    edited): each Artefato's slug, its intent (the why), and its proposed steers. Most-recent-first.
    Projecting a past cursor writes that past corpus."""

    def test_renders_banner_marked_with_slug_why_and_proposes(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            out = Path(tmp) / "corpus.md"
            eventlog._append_orphan_published_for_test(
                "recall-report", proposes=[{"body": "name the full-read budget"}], log=log)
            eventlog.kernel("recall-report", "open: budget unnamed; bet: name it next beat", log=log)
            eventlog.project_corpus(log=log, out=out)
            text = out.read_text()
            self.assertIn("do not edit", text.lower())
            self.assertIn("recall-report", text)
            self.assertIn("open: budget unnamed; bet: name it next beat", text)  # the why is inscribed
            self.assertIn("name the full-read budget", text)                     # its proposed steer

    def test_projects_past_cursor(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            out = Path(tmp) / "corpus.md"
            eventlog._append_orphan_published_for_test("alpha", log=log)
            eventlog._append_orphan_published_for_test("omega", log=log)
            eventlog.project_corpus(seq=1, log=log, out=out)
            text = out.read_text()
            self.assertIn("alpha", text)
            self.assertNotIn("omega", text)


class CitesCarryOptionalSnippet(unittest.TestCase):
    """ADR-0009 source-feedback (hypothesis tier): a cite may carry the snippet the agent used —
    `{ref, kind, relevant, snippet}` — so embedding attribution can score snippet-vs-body. Back-
    compatible: a plain string cite (or a cite with no snippet) still round-trips and the corpus
    fold still reads `cites` verbatim — the new fields are never forced."""

    def test_snippetted_and_plain_cites_round_trip_through_corpus(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            cites = [{"ref": "github:abc123", "kind": "atividade", "relevant": True,
                      "snippet": "switched the cursor to a per-session watermark"},
                     "mundo:arxiv"]  # legacy plain cite, no snippet — must still work
            eventlog._append_orphan_published_for_test("recall-report", cites=cites, log=log)
            corpus = eventlog.corpus_at(log=log)
            self.assertEqual(corpus[0]["cites"], cites)
            self.assertEqual(corpus[0]["cites"][0]["snippet"],
                             "switched the cursor to a per-session watermark")


class SourceSignalAppendsTheScore(unittest.TestCase):
    """ADR-0009: the hypothesis tier lands in the Tier-0 log as `source.signal` events — the
    *score* (similarity), never the vectors (no separate DB, no vector store). Payload pins the
    cited source (slug, ref, kind) so the yield fold can aggregate per source."""

    def test_source_signal_appends_event_with_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            ev = eventlog.source_signal("recall-report", "github:abc123", "atividade", 0.81, log=log)
            self.assertEqual(ev["type"], "source.signal")
            self.assertEqual(ev["payload"], {"slug": "recall-report", "ref": "github:abc123",
                                             "kind": "atividade", "similarity": 0.81})
            self.assertEqual(eventlog.read(types=["source.signal"], log=log), [ev])


class SourceYieldFoldsPerSourceCountAndMean(unittest.TestCase):
    """ADR-0009: the source-orientation leg the briefing reads and the grill consults — a pure fold
    of `source.signal` events into **per-source (ref) yield**: count + mean similarity, carrying
    kind. Cursor-aware (replay reconstructs a past yield); empty when there are no signals yet."""

    def test_aggregates_count_and_mean_per_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.source_signal("r1", "github:abc", "atividade", 0.8, log=log)
            eventlog.source_signal("r2", "github:abc", "atividade", 0.6, log=log)
            eventlog.source_signal("r1", "mundo:arxiv", "mundo", 0.4, log=log)
            y = eventlog.source_yield_at(log=log)
            self.assertEqual(y["github:abc"], {"ref": "github:abc", "kind": "atividade",
                                               "count": 2, "mean_similarity": 0.7})
            self.assertEqual(y["mundo:arxiv"], {"ref": "mundo:arxiv", "kind": "mundo",
                                                "count": 1, "mean_similarity": 0.4})

    def test_empty_when_no_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(eventlog.source_yield_at(log=Path(tmp) / "log.jsonl"), {})


class SourceFeedbackFoldsTwoTiersCuratedOverNonCurated(unittest.TestCase):
    """Slice 2 (ADR-0011): source feedback is two-tier, mirroring Direction (set over proposed).
    `source.curated` is the grill-distilled mentee opinion (curated tier); `source.signal` aggregates
    into the non-curated yield. `source_feedback_at` folds both, curated keyed per source, outranking
    the non-curated yield. `source.dropped` removes a curated entry (Voz-only). Cursor-aware: replay
    to a past cursor reconstructs that past — strategic versioning, as direction_at."""

    def test_curated_event_appends_and_folds_into_curated_tier(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            ev = eventlog.source_curated("exa", "values exa for recent-paper recall", log=log)
            self.assertEqual(ev["type"], "source.curated")
            self.assertEqual(ev["payload"]["source"], "exa")
            fb = eventlog.source_feedback_at(log=log)
            self.assertEqual([c["source"] for c in fb["curated"]], ["exa"])
            self.assertEqual(fb["curated"][0]["opinion"], "values exa for recent-paper recall")

    def test_curated_outranks_non_curated_yield_for_same_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.source_signal("r", "exa", "mundo", 0.7, log=log)         # non-curated yield
            eventlog.source_curated("exa", "valued: recent-paper recall", log=log)  # curated opinion
            fb = eventlog.source_feedback_at(log=log)
            self.assertEqual([c["source"] for c in fb["curated"]], ["exa"])
            # the non-curated yield is still folded (a separate event, no promotion) but exa is curated
            self.assertIn("exa", fb["non_curated"])

    def test_dropped_removes_curated_entry_and_stays_gone(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.source_curated("exa", "valued", log=log)
            eventlog.source_dropped("exa", "went cold", log=log)
            fb = eventlog.source_feedback_at(log=log)
            self.assertEqual(fb["curated"], [])

    def test_latest_curated_opinion_wins_per_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.source_curated("exa", "first take", log=log)
            eventlog.source_curated("exa", "sharper take", log=log)
            fb = eventlog.source_feedback_at(log=log)
            self.assertEqual([c["source"] for c in fb["curated"]], ["exa"])
            self.assertEqual(fb["curated"][0]["opinion"], "sharper take")

    def test_replay_to_past_cursor_reconstructs_past_feedback(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            c = eventlog.source_curated("exa", "valued", log=log)        # seq 1
            eventlog.source_dropped("exa", "cold", log=log)              # seq 2
            past = eventlog.source_feedback_at(seq=c["seq"], log=log)
            self.assertEqual([x["source"] for x in past["curated"]], ["exa"])
            now = eventlog.source_feedback_at(log=log)
            self.assertEqual(now["curated"], [])

    def test_empty_log_has_empty_feedback(self):
        with tempfile.TemporaryDirectory() as tmp:
            fb = eventlog.source_feedback_at(log=Path(tmp) / "log.jsonl")
            self.assertEqual(fb, {"curated": [], "non_curated": {}})


class ObjectiveFoldsLatestWins(unittest.TestCase):
    """The grill's anchor as a first-class durable thing: `objective.set` is the mentee's
    **confirmed objective** (abduced from behavior, confirmed by Voz) — it MAY contradict the
    declared agent.yaml mission (this is the *revealed/confirmed* objective). `objective_at` folds
    latest-wins (mirroring set_direction/direction_at), versioned: replay to a past cursor
    reconstructs the past objective. None when no objective has ever been set."""

    def test_set_objective_appends_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            ev = eventlog.set_objective("ship the briefing spine before tuning the grill", log=log)
            self.assertEqual(ev["type"], "objective.set")
            self.assertEqual(ev["subject"], "objective")
            self.assertEqual(ev["payload"]["body"],
                             "ship the briefing spine before tuning the grill")
            self.assertEqual(eventlog.read(types=["objective.set"], log=log), [ev])

    def test_latest_objective_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_objective("first read of the objective", log=log)
            eventlog.set_objective("sharper read after the grill", log=log)
            obj = eventlog.objective_at(log=log)
            self.assertEqual(obj["body"], "sharper read after the grill")

    def test_objective_carries_optional_rationale(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_objective("revealed objective B",
                                   rationale="says mission A, behavior shows B", log=log)
            obj = eventlog.objective_at(log=log)
            self.assertEqual(obj["rationale"], "says mission A, behavior shows B")

    def test_replay_to_past_cursor_reconstructs_past_objective(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            a = eventlog.set_objective("old anchor", log=log)        # seq 1
            eventlog.set_objective("new anchor", log=log)            # seq 2
            self.assertEqual(eventlog.objective_at(seq=a["seq"], log=log)["body"], "old anchor")
            self.assertEqual(eventlog.objective_at(log=log)["body"], "new anchor")

    def test_empty_log_has_no_objective(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(eventlog.objective_at(log=Path(tmp) / "log.jsonl"))


class WriteHelpersRejectEmptyBodies(unittest.TestCase):
    """Codex gate finding [high]: a grill must not be able to land an EMPTY stage-(ii) feeder.
    The write helpers refuse an empty/whitespace body at the source — `set_objective`, `propose`,
    `set_direction`, and `report_direction` raise ValueError before anything lands, so the gate's
    'landed' can never be a hollow event. Non-empty bodies still write. `set_objective` also strips."""

    def test_set_objective_rejects_empty_and_whitespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            for bad in ("", "   ", "\n\t "):
                with self.assertRaises(ValueError):
                    eventlog.set_objective(bad, log=log)
            self.assertEqual(eventlog.read(log=log), [])  # nothing landed

    def test_propose_rejects_empty_and_whitespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            for bad in ("", "   ", "\n\t "):
                with self.assertRaises(ValueError):
                    eventlog.propose("d1", bad, log=log)
            self.assertEqual(eventlog.read(log=log), [])

    def test_set_direction_rejects_empty_and_whitespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            for bad in ("", "   ", "\n\t "):
                with self.assertRaises(ValueError):
                    eventlog.set_direction("d1", bad, log=log)
            self.assertEqual(eventlog.read(log=log), [])

    def test_report_direction_rejects_empty_and_whitespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            for bad in ("", "   ", "\n\t "):
                with self.assertRaises(ValueError):
                    eventlog.report_direction(bad, log=log)
            self.assertEqual(eventlog.read(log=log), [])

    def test_non_empty_bodies_still_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_objective("ship the gate", log=log)
            eventlog.propose("d1", "tighten the close", log=log)
            eventlog.set_direction("d2", "ratify the steer", log=log)
            eventlog.report_direction("the steer prose", log=log)
            self.assertEqual(len(eventlog.read(log=log)), 4)

    def test_set_objective_strips_the_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_objective("  ship the gate  ", log=log)
            self.assertEqual(eventlog.objective_at(log=log)["body"], "ship the gate")


class DirecionamentoReportFoldsLatestAndLineage(unittest.TestCase):
    """The rolling steer ("o direcionamento") as a first-class durable thing: `direction.report`
    carries the **full prose report** (objective + the steer + the live insight). `report_at` folds
    BOTH the **latest** (for injection into the briefing) AND the **lineage** (the priors the grill
    reads to re-derive against — newest-first). Provenance: the report links the threads/sources it
    synthesized from (distills/cites), so the steer is traceable, not pronounced. Cursor-aware:
    replay to a past cursor reconstructs that past report + lineage (versioned, as direction_at)."""

    def test_report_appends_event_with_prose_and_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            ev = eventlog.report_direction("the steer prose body", distills=["cluster:recall"],
                                           cites=[{"ref": "github:abc", "kind": "atividade"}], log=log)
            self.assertEqual(ev["type"], "direction.report")
            self.assertEqual(ev["subject"], "direction")
            self.assertEqual(ev["payload"]["body"], "the steer prose body")
            self.assertEqual(ev["payload"]["distills"], ["cluster:recall"])
            self.assertEqual(ev["payload"]["cites"], [{"ref": "github:abc", "kind": "atividade"}])

    def test_latest_report_is_the_injected_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.report_direction("older steer", log=log)
            eventlog.report_direction("fresher steer", log=log)
            r = eventlog.report_at(log=log)
            self.assertEqual(r["latest"]["body"], "fresher steer")

    def test_lineage_is_the_priors_newest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.report_direction("first", log=log)
            eventlog.report_direction("second", log=log)
            eventlog.report_direction("third", log=log)
            r = eventlog.report_at(log=log)
            self.assertEqual([x["body"] for x in r["lineage"]], ["third", "second", "first"])

    def test_replay_to_past_cursor_reconstructs_past_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            a = eventlog.report_direction("old", log=log)           # seq 1
            eventlog.report_direction("new", log=log)               # seq 2
            past = eventlog.report_at(seq=a["seq"], log=log)
            self.assertEqual(past["latest"]["body"], "old")
            self.assertEqual([x["body"] for x in past["lineage"]], ["old"])
            self.assertEqual(eventlog.report_at(log=log)["latest"]["body"], "new")

    def test_empty_log_has_no_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = eventlog.report_at(log=Path(tmp) / "log.jsonl")
            self.assertIsNone(r["latest"])
            self.assertEqual(r["lineage"], [])


class InsightArtefatoCarriesProvenance(unittest.TestCase):
    """Piece 3: when the grill yields **real** insight, it publishes via the existing publish_artefato
    with **populated provenance** — `distills` = the existing **threads** it draws on (cluster:…),
    `cites` = the **sources** ({ref,kind}). Link only existing threads; if none fits, no link (empty,
    never fabricated — thread maintenance attaches/spawns later). The corpus fold carries both. The
    two-way view (thread →hangs→ Artefatos) is a pure fold: artefatos_for_thread reads the corpus."""

    def test_insight_artefato_folds_with_provenance_when_threads_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog._append_orphan_published_for_test(
                "recall-insight", distills=["cluster:recall", "cluster:cursor"],
                cites=[{"ref": "github:abc", "kind": "atividade"}], log=log)
            eventlog.kernel("recall-insight", "open: …; bet: …", log=log)
            corpus = eventlog.corpus_at(log=log)
            self.assertEqual(corpus[0]["distills"], ["cluster:recall", "cluster:cursor"])
            self.assertEqual(corpus[0]["cites"], [{"ref": "github:abc", "kind": "atividade"}])

    def test_no_fitting_thread_means_empty_distills_never_fabricated(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog._append_orphan_published_for_test(
                "orphan-insight", cites=[{"ref": "mundo:arxiv", "kind": "mundo"}], log=log)
            corpus = eventlog.corpus_at(log=log)
            self.assertEqual(corpus[0]["distills"], [])  # no thread fit → no link, not a fabricated one

    def test_thread_hangs_its_artefatos_two_way(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog._append_orphan_published_for_test("a1", distills=["cluster:recall"], log=log)
            eventlog._append_orphan_published_for_test(
                "a2", distills=["cluster:recall", "cluster:cursor"], log=log)
            eventlog._append_orphan_published_for_test("a3", distills=["cluster:other"], log=log)
            self.assertEqual(eventlog.artefatos_for_thread("cluster:recall", log=log), ["a1", "a2"])
            self.assertEqual(eventlog.artefatos_for_thread("cluster:cursor", log=log), ["a2"])
            self.assertEqual(eventlog.artefatos_for_thread("cluster:none", log=log), [])


class PublishRequiresKernel(unittest.TestCase):
    """CONTRACT C3 enforced at the publish seam: `publish_artefato_atomic` appends the
    `artefato.published` AND its `intent.kernel` in one call — you cannot publish without the
    why (empty/missing intent raises). `require_kernels` is the guard form of the C3 invariant:
    it RAISES listing the offending slugs when any published slug lacks a kernel (vs the
    non-fatal `artefatos_without_kernel` reader the sweep warns with). Additive: the legacy
    publish_artefato + kernel two-call path stays callable."""

    def test_atomic_publish_emits_kernel_so_nothing_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.publish_artefato_atomic("recall-report", intent="open: x; bet: y",
                                             proposes=[{"body": "name the budget"}], log=log)
            self.assertEqual(eventlog.artefatos_without_kernel(log=log), [])

    def test_atomic_publish_without_intent_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaises(ValueError):
                eventlog.publish_artefato_atomic("bare", intent="", log=log)
            self.assertEqual(eventlog.read(log=log), [])  # nothing published without the kernel

    def test_atomic_publish_carries_the_spec_in_the_published_payload(self):
        # Codex round-10 [high]: the page is a PROJECTION (ADR-0006) — for it to be fully
        # regenerable from the log alone, the proof-bound spec (the `content`) must ride the
        # atomic `artefato.published` event, inside the SAME single batch as the kernel.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            spec = {"sections": [{"title": "S", "blocks": [
                {"type": "paragraph", "text": "the body to regenerate"}]}]}
            eventlog.publish_artefato_atomic("recall-report", intent="open: x; bet: y",
                                             spec=spec, log=log)
            published = eventlog.read(types=["artefato.published"], log=log)
            self.assertEqual(len(published), 1)
            self.assertEqual(published[0]["payload"]["spec"], spec)
            # still one indivisible batch with the kernel (C3 holds)
            self.assertEqual(eventlog.artefatos_without_kernel(log=log), [])

    def test_spec_rides_the_same_single_batch_as_the_kernel(self):
        # the spec must NOT be a separate append — it lands in the one batch the published
        # + kernel land in, so there is no window where published-with-spec is missing.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            real_open = Path.open
            writes = {"count": 0}

            def counting_open(self, *a, **k):
                if "a" in (a[0] if a else k.get("mode", "")):
                    writes["count"] += 1
                return real_open(self, *a, **k)

            orig = Path.open
            Path.open = counting_open
            try:
                eventlog.publish_artefato_atomic(
                    "recall-report", intent="open: x; bet: y",
                    spec={"sections": []}, log=log)
            finally:
                Path.open = orig
            self.assertEqual(writes["count"], 1)  # one append carried published(+spec) + kernel

    def test_skill_is_persisted_and_folds_into_the_corpus(self):
        # #30 (Codex P2): the published event carries `skill` so a graph reproject after a
        # publish-time outage can restore the producer identity (the log is the only recovery
        # source). It folds onto the corpus item.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.publish_artefato_atomic("rel-map", intent="open: x; bet: y",
                                             spec={"sections": []}, skill="map", log=log)
            published = eventlog.read(types=["artefato.published"], log=log)
            self.assertEqual(published[0]["payload"]["skill"], "map")
            corpus = eventlog.corpus_at(log=log)
            self.assertEqual(corpus[0]["skill"], "map")

    def test_latest_ts_advances_to_a_kernel_added_later(self):
        # Codex P3: fold_corpus tracks `latest_ts` advancing to a kernel appended AFTER publish, so a
        # legacy C3-debt repair makes the slug stale vs the graph and the graph-recovery freshness
        # check re-projects it. `ts` stays the publish ts (unchanged for existing readers).
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog._append_orphan_published_for_test("legacy-c3", log=log)  # published, no kernel
            item0 = eventlog.corpus_at(log=log)[0]
            self.assertEqual(item0["latest_ts"], item0["ts"])   # no kernel yet → latest == publish
            eventlog.kernel("legacy-c3", "open: repaired; bet: x", log=log)  # kernel ADDED LATER
            item1 = eventlog.corpus_at(log=log)[0]
            self.assertEqual(item1["ts"], item0["ts"])          # publish ts unchanged
            self.assertGreaterEqual(item1["latest_ts"], item0["ts"])
            self.assertNotEqual(item1["latest_ts"], item0["latest_ts"])  # advanced to the kernel ts

    def test_missing_skill_folds_as_none_backward_compatible(self):
        # a legacy published event with no skill folds with skill=None (no crash).
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.publish_artefato_atomic("legacy", intent="open: x; bet: y", log=log)
            self.assertIsNone(eventlog.corpus_at(log=log)[0]["skill"])

    def test_positional_log_call_still_targets_the_given_log(self):
        # Codex P2: `skill` is keyword-ONLY (after log), so the legacy positional form
        # (slug, intent, proposes, distills, cites, spec, log) still binds the custom log — the
        # publish lands in the GIVEN log, never the default, and skill is not the log path.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.publish_artefato_atomic(
                "pos", "open: x; bet: y", [], [], [], {"sections": []}, log)  # all positional
            self.assertEqual([c["slug"] for c in eventlog.corpus_at(log=log)], ["pos"])
            self.assertIsNone(eventlog.corpus_at(log=log)[0]["skill"])  # log not mis-stored as skill

    def test_require_kernels_raises_until_kernel_added(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog._append_orphan_published_for_test("bare", log=log)  # migration debt, no kernel yet
            with self.assertRaises(ValueError):
                eventlog.require_kernels(log=log)
            eventlog.kernel("bare", "open: …; bet: …", log=log)
            eventlog.require_kernels(log=log)  # no raise once the kernel is added


class AtomicPublishHasNoCrashWindow(unittest.TestCase):
    """#3 — the atomic publish is ONE indivisible write, not two appends (published then
    kernel). The two-append form left a crash window: a crash between the appends published an
    Artefato without its kernel (C3 debt). `publish_artefato_atomic` now batches both events
    into a single file write, so there is no ordering window in which `published` exists without
    its `intent.kernel`. Both events still land, stamped with monotonic seqs."""

    def test_atomic_publish_writes_both_events_in_one_file_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            real_open = Path.open
            writes = {"count": 0}

            def counting_open(self, *a, **k):
                if "a" in (a[0] if a else k.get("mode", "")):
                    writes["count"] += 1
                return real_open(self, *a, **k)

            orig = Path.open
            Path.open = counting_open
            try:
                eventlog.publish_artefato_atomic("recall-report", intent="open: x; bet: y",
                                                 log=log)
            finally:
                Path.open = orig
            # ONE append-mode write carried both events — no two-step crash window
            self.assertEqual(writes["count"], 1)
            evs = eventlog.read(log=log)
            self.assertEqual([e["type"] for e in evs],
                             ["artefato.published", "intent.kernel"])
            self.assertEqual([e["seq"] for e in evs], [1, 2])
            self.assertEqual(eventlog.artefatos_without_kernel(log=log), [])


class ProducerFacingPublishPairsItsKernel(unittest.TestCase):
    """Codex re-review C3: when used the producer-facing way — `publish_artefato(slug, intent, …)` —
    the publish path pairs the `intent.kernel` in ONE indivisible write (delegating to
    `publish_artefato_atomic`), so a producer cannot ship a kernel-less `artefato.published`. An
    empty intent raises before anything lands. Manufacturing C3 debt on purpose is reserved to the
    explicitly-named, non-producer-facing `_append_orphan_published_for_test` (the only thing the
    `artefatos_without_kernel`/`require_kernels` detector/migration path should ever use)."""

    def test_publish_artefato_with_intent_emits_its_kernel_so_no_debt(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.publish_artefato("recall-report", intent="open: x; bet: y",
                                      proposes=[{"body": "name the budget"}], log=log)
            # the producer path pairs the kernel atomically — no C3 debt
            self.assertEqual(eventlog.artefatos_without_kernel(log=log), [])
            evs = eventlog.read(log=log)
            self.assertEqual([e["type"] for e in evs],
                             ["artefato.published", "intent.kernel"])

    def test_publish_artefato_with_empty_intent_raises_and_lands_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaises(ValueError):
                eventlog.publish_artefato("bare", intent="", log=log)
            self.assertEqual(eventlog.read(log=log), [])

    def test_publish_artefato_with_missing_intent_raises_no_kernel_less_path(self):
        # intent is positional with no default — a bare producer call cannot manufacture C3 debt
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaises((ValueError, TypeError)):
                eventlog.publish_artefato("bare", log=log)
            self.assertEqual(eventlog.read(log=log), [])

    def test_orphan_helper_is_the_named_unsafe_debt_path_for_detectors(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog._append_orphan_published_for_test("bare", log=log)
            # the migration/detector path still reaches the C3-debt state the detectors check
            self.assertEqual(eventlog.artefatos_without_kernel(log=log), ["bare"])
            with self.assertRaises(ValueError):
                eventlog.require_kernels(log=log)


class AppendBatchIsSerializedAcrossConcurrentWriters(unittest.TestCase):
    """Codex re-review: `append_batch` reads `base = len(read(log))`, stamps seqs, then opens for
    append — with NO lock the read/stamp/write window is racy, so two overlapping writers read the
    same base and append DUPLICATE seq ranges, breaking the cursor/replay invariant the folds
    depend on. The critical section is now guarded by an exclusive flock + fsync before release, so
    concurrent `publish_artefato_atomic` calls produce UNIQUE strictly-monotonic seqs."""

    def test_concurrent_atomic_publishes_yield_unique_monotonic_seqs(self):
        for _ in range(8):  # several iterations — the race is probabilistic
            with tempfile.TemporaryDirectory() as tmp:
                log = Path(tmp) / "log.jsonl"
                n = 12
                barrier = threading.Barrier(n)

                def writer(i):
                    barrier.wait()  # maximize overlap of the read/stamp/write windows
                    eventlog.publish_artefato_atomic(f"a{i}", intent=f"why {i}", log=log)

                threads = [threading.Thread(target=writer, args=(i,)) for i in range(n)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()

                seqs = [e["seq"] for e in eventlog.read(log=log)]
                # each atomic publish lands two events → 2n events, seqs 1..2n with no dupes
                self.assertEqual(len(seqs), 2 * n)
                self.assertEqual(sorted(seqs), list(range(1, 2 * n + 1)))
                self.assertEqual(seqs, sorted(seqs))  # strictly monotonic in file order


class AppendBaseIsPhysicalNotTolerantRead(unittest.TestCase):
    """Codex Slice-4 round-3 [high]: read() now SKIPS a JSON-valid non-dict line, but the append
    base must stay the PHYSICAL line count — else a corrupt non-event line mid-log makes
    len(read()) undercount and the next append stamps a DUPLICATE seq, corrupting the append-only
    source of truth under the very corruption model this slice survives. Strict for writes, tolerant
    only for read-side projections (ADR-0006 deterministic-replay invariant)."""

    def test_append_after_a_mid_log_non_dict_line_does_not_reuse_a_seq(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with open(log, "w") as fh:
                fh.write(json.dumps({"seq": 1, "ts": "t", "type": "direction.set",
                                     "subject": "direction", "payload": {"id": "a", "body": "x"}}) + "\n")
                fh.write("[]\n")  # a corrupt non-dict line read() now skips — but it OCCUPIES seq 2
                fh.write(json.dumps({"seq": 3, "ts": "t", "type": "direction.set",
                                     "subject": "direction", "payload": {"id": "b", "body": "y"}}) + "\n")
            ev = eventlog.append("direction.set", "direction", {"id": "c", "body": "z"}, log=log)
            # the new event must take seq 4 (physical base 3), NOT reuse seq 3 (len(read())==2 → 3)
            self.assertEqual(ev["seq"], 4)

    def test_append_base_ignores_a_whitespace_only_line(self):
        # codex round-5 [high]: _physical_len must use the SAME blank-line semantics as log_is_intact
        # (which skips `not line.strip()`). A whitespace-only line is NOT an event slot — counting it
        # would stamp the next seq one too high, permanently breaking seq contiguity (a harmless blank
        # turned into irreversible source-of-truth corruption). The next append takes seq 2, not 3.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with open(log, "w") as fh:
                fh.write(json.dumps({"seq": 1, "ts": "t", "type": "direction.set",
                                     "subject": "direction", "payload": {"id": "a", "body": "x"}}) + "\n")
                fh.write("   \n")  # whitespace-only — a blank line, NOT an occupied seq slot
            ev = eventlog.append("direction.set", "direction", {"id": "b", "body": "y"}, log=log)
            self.assertEqual(ev["seq"], 2)
            # and the resulting log is seq-contiguous (log_is_intact would accept it)
            seqs = [e["seq"] for e in eventlog.read(log=log)]
            self.assertEqual(seqs, [1, 2])


class CosineIsPureSimilarity(unittest.TestCase):
    """ADR-0009 source-feedback (hypothesis tier): cosine of two equal-length numeric vectors —
    the pure math behind embedding attribution (the actual OpenAI call lives in sweep, never here).
    Orthogonal → 0, identical → 1, a zero vector → 0.0 (no NaN — degrade, never crash)."""

    def test_orthogonal_identical_and_zero_vector(self):
        self.assertAlmostEqual(eventlog.cosine([1, 0], [0, 1]), 0.0)
        self.assertAlmostEqual(eventlog.cosine([1, 2, 3], [1, 2, 3]), 1.0)
        self.assertEqual(eventlog.cosine([0, 0], [1, 1]), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
