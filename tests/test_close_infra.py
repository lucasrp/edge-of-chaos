"""Close × falha de transporte do completer (issue #55).

Quota morta / auth quebrada / CLI ausente é INFRA, não um juízo sobre o conteúdo: um
LLMTransportError vindo do completer do revisor deve SUBIR de run_close (com um evento
`llm.infra_error` no log) — nunca virar strike/reprovação silenciosa que manda o produtor
diagnosticar "defeito de conteúdo" que era bilhetagem. Exceção genérica do revisor segue
fail-closed como sempre (verdito reprovado bounded) — regressão pinada aqui.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import _llm      # noqa: E402
import close     # noqa: E402
import eventlog  # noqa: E402


def _conformant_artefato(slug="infra-artefato"):
    return {
        "slug": slug,
        "content": {"sections": [{"title": "Body", "blocks": [
            {"type": "paragraph", "text": "the proof is bound to this exact payload."},
        ]}]},
        "cites": [{"ref": "github:abc", "kind": "atividade", "relevant": True,
                   "snippet": "the cursor became a watermark"}],
        "proposes": [{"body": "name the budget", "kind": "constraint"}],
        "intent": "open: x; bet: y",
    }


class TransportErrorIsInfraNotVerdict(unittest.TestCase):
    def setUp(self):
        self._old_log = eventlog.LOG
        self._tmp = Path(tempfile.mkdtemp())
        eventlog.LOG = self._tmp / "log.jsonl"

    def tearDown(self):
        eventlog.LOG = self._old_log

    def _events(self):
        if not eventlog.LOG.exists():
            return []
        return [json.loads(l) for l in eventlog.LOG.read_text().splitlines() if l.strip()]

    def test_transport_error_raises_out_of_run_close(self):
        def dead_quota_completer(prompt):
            raise _llm.LLMTransportError("insufficient_quota", status=429)

        art = _conformant_artefato()
        with self.assertRaises(_llm.LLMTransportError):
            close.run_close(art, produce_fn=lambda: art,
                            complete_fn=dead_quota_completer)

    def test_transport_error_is_logged_as_infra_event(self):
        def dead_quota_completer(prompt):
            raise _llm.LLMTransportError("insufficient_quota", status=429)

        art = _conformant_artefato()
        try:
            close.run_close(art, produce_fn=lambda: art,
                            complete_fn=dead_quota_completer)
        except _llm.LLMTransportError:
            pass
        infra = [e for e in self._events() if e["type"] == "llm.infra_error"]
        self.assertEqual(len(infra), 1)
        self.assertEqual(infra[0]["payload"]["status"], 429)
        self.assertIn("insufficient_quota", infra[0]["payload"]["detail"])

    def test_generic_reviewer_exception_still_fails_closed_bounded(self):
        """Regressão: uma exceção NÃO-transporte segue virando veredito reprovado
        (bounce bounded), nunca um raise — o fail-closed de sempre."""
        def broken_completer(prompt):
            raise RuntimeError("schema drift")

        art = _conformant_artefato()
        result = close.run_close(art, produce_fn=lambda: art,
                                 complete_fn=broken_completer)
        self.assertFalse(result["pass"])
        self.assertEqual(self._events(), [])   # nada de evento de infra


if __name__ == "__main__":
    unittest.main()
