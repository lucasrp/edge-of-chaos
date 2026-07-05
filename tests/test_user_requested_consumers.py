"""Consumidores do `origin: user_requested` (follow-up 05 §"hierarquia de ORIGEM").

O schema já carrega a origem (predispatch → dispatch.open → artefato.published). Aqui os
CONSUMIDORES passam a pesar user_requested ≫ beat:
  * quente (tools/quente.py, trilho executado): os artefatos user_requested recentes entram
    nas âncoras mecânicas — o pedido do usuário é exatamente onde está a cognição dele AGORA;
  * beat (skills/beat): o ato-1 LÊ os últimos user_requested como sinal de pauta (goal-level,
    no SKILL.md — testado aqui só na âncora que o alimenta).
"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import quente  # noqa: E402


def _ts(hours_ago):
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


def _write_session(store, stem, hours_ago=2):
    lines = []
    for i in range(8):
        lines.append(json.dumps({"type": "user", "timestamp": _ts(hours_ago + 8 - i),
                                 "message": {"content": f"turno {i} " + "x" * 300}}))
    lines.append(json.dumps({"type": "assistant", "timestamp": _ts(hours_ago),
                             "message": {"content": [{"type": "text", "text": "fim"}]}}))
    (Path(store) / f"{stem}.jsonl").write_text("\n".join(lines) + "\n")


def _published(seq, slug, origin):
    return json.dumps({"seq": seq, "ts": _ts(1), "type": "artefato.published",
                       "subject": f"artefato:{slug}",
                       "payload": {"slug": slug, "origin": origin}})


class UserRequestedAnchor(unittest.TestCase):
    """A âncora user_requested: user_requested entra, beat NÃO (pesar ≫ = só o gradiente é
    âncora; a exploração do próprio beat não vira sinal de pauta). Degrade-honesto como as
    outras âncoras."""

    def test_user_requested_artefatos_anchor_in_the_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_session(tmp, "s-novo")
            ev = Path(tmp) / "log.jsonl"
            ev.write_text(_published(1, "pedido-pelo-op", "user_requested") + "\n"
                          + _published(2, "exploracao-do-beat", "beat") + "\n")
            bundle, _ = quente.build_bundle(store_dir=tmp, repos=(), exclude=(),
                                            eventlog_path=ev)
            self.assertIn("user_requested", bundle)
            self.assertIn("pedido-pelo-op", bundle)
            # beat é exploração — não-distinguível de ruído, não ancora a pauta
            self.assertNotIn("exploracao-do-beat", bundle)

    def test_absence_is_declared_never_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_session(tmp, "s-novo")
            ev = Path(tmp) / "log.jsonl"
            ev.write_text(_published(1, "so-beat", "beat") + "\n")
            bundle, _ = quente.build_bundle(store_dir=tmp, repos=(), exclude=(),
                                            eventlog_path=ev)
            self.assertIn("nenhum artefato user_requested", bundle)

    def test_most_recent_first_and_capped(self):
        slugs = [f"pedido-{i}" for i in range(7)]
        lines = [_published(i + 1, s, "user_requested") for i, s in enumerate(slugs)]
        with tempfile.TemporaryDirectory() as tmp:
            ev = Path(tmp) / "log.jsonl"
            ev.write_text("\n".join(lines) + "\n")
            out = quente._user_requested_anchor(ev, n=5)
            self.assertNotIn("pedido-0", out)   # além do cap
            self.assertNotIn("pedido-1", out)
            self.assertIn("pedido-6", out)
            # mais recente primeiro
            self.assertLess(out.index("pedido-6"), out.index("pedido-2"))

    def test_unavailable_log_degrades_declared(self):
        out = quente._user_requested_anchor(Path("/nao/existe.jsonl"))
        self.assertIn("indisponível", out)

    def test_stale_request_outside_the_window_is_out(self):
        # codex adversarial #2 (SINAL): o quente envelhece em horas — um pedido de meses atrás
        # não é "cognição AGORA"; a âncora respeita o mesmo teto wall-clock do bundle.
        old = json.dumps({"seq": 1, "ts": _ts(24 * 90), "type": "artefato.published",
                          "subject": "artefato:pedido-velho",
                          "payload": {"slug": "pedido-velho", "origin": "user_requested"}})
        with tempfile.TemporaryDirectory() as tmp:
            ev = Path(tmp) / "log.jsonl"
            ev.write_text(old + "\n" + _published(2, "pedido-fresco", "user_requested") + "\n")
            out = quente._user_requested_anchor(ev, since=_ts(24 * 7))
            self.assertIn("pedido-fresco", out)
            self.assertNotIn("pedido-velho", out)

    def test_anchor_carries_the_intent_kernel_as_pauta(self):
        # codex adversarial #3 (SINAL): slug não carrega o pedido — o intent.kernel do mesmo
        # log (obrigatório no publish, C3) é a pauta legível que o beat lê.
        pub = _published(1, "pedido-com-intent", "user_requested")
        kernel = json.dumps({"seq": 2, "ts": _ts(1), "type": "intent.kernel",
                             "subject": "artefato:pedido-com-intent",
                             "payload": {"slug": "pedido-com-intent",
                                         "intent": "open: fio X; bet: aposta Y"}})
        with tempfile.TemporaryDirectory() as tmp:
            ev = Path(tmp) / "log.jsonl"
            ev.write_text(pub + "\n" + kernel + "\n")
            out = quente._user_requested_anchor(ev)
            self.assertIn("open: fio X; bet: aposta Y", out)


class BeatReadsUserRequestedAsPauta(unittest.TestCase):
    """Goal-level no SKILL.md do beat: o ato-1 lê os últimos user_requested como sinal de
    pauta (a instrução existe e aponta pra onde ler — a âncora do quente)."""

    def test_beat_skill_instructs_reading_the_last_user_requested(self):
        skill = (Path(__file__).resolve().parent.parent / "skills" / "beat"
                 / "SKILL.md").read_text()
        self.assertIn("user_requested", skill)
        # a instrução de LER (não só pesar na abstração): o sinal de pauta do ato-1
        self.assertIn("pauta", skill.lower())
        self.assertIn("quente", skill.lower())


if __name__ == "__main__":
    unittest.main()
