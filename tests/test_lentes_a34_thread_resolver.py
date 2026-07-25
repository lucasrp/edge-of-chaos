"""A34 (pen-edge half) — resolução label→UUID de thread na borda do open_map.

O eventlog nunca importa Graphiti/OpenAI (A21): o resolver é um callable INJETADO. Um label
resolve para EXATAMENTE um candidato vivo {uuid, display}; zero ou múltiplos → recusa loud e
ZERO bytes escritos. Caller nenhum pode forjar o snapshot resolvido."""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402


class ThreadResolverPenEdge(unittest.TestCase):
    def _open(self, log, **kw):
        return eventlog.open_map(
            operacao="edge", titulo="A34", rationale="thread estável",
            dispatch_id=eventlog.test_dispatch_id(), author="operador", log=log, **kw,
        )

    def test_label_resolves_to_the_single_live_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"

            def resolve(ref):
                self.assertEqual(ref, "V10")
                return [{"uuid": "thread-canonical", "display": "Consolidação V10"}]

            event = self._open(log, thread="V10", resolve_thread_fn=resolve)
            self.assertEqual(
                event["payload"]["thread"],
                {"uuid": "thread-canonical", "display": "Consolidação V10"},
            )

    def test_zero_candidates_refuses_loud_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaisesRegex(ValueError, "thread"):
                self._open(log, thread="fantasma", resolve_thread_fn=lambda ref: [])
            self.assertEqual(eventlog.read(log=log), [])

    def test_multiple_candidates_refuses_loud_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"

            def resolve(ref):
                return [
                    {"uuid": "thread-a", "display": "A"},
                    {"uuid": "thread-b", "display": "B"},
                ]

            with self.assertRaisesRegex(ValueError, "thread"):
                self._open(log, thread="ambíguo", resolve_thread_fn=resolve)
            self.assertEqual(eventlog.read(log=log), [])

    def test_label_without_resolver_refuses_loud(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaisesRegex(ValueError, "resolve"):
                self._open(log, thread="V10")
            self.assertEqual(eventlog.read(log=log), [])

    def test_pre_resolved_dict_is_rejected_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaisesRegex(ValueError, "label"):
                self._open(
                    log, thread={"uuid": "thread-old", "display": "snapshot forjado"},
                )
            self.assertEqual(eventlog.read(log=log), [])

    def test_no_thread_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            event = self._open(log)
            self.assertIsNone(event["payload"]["thread"])


if __name__ == "__main__":
    unittest.main()
