"""Proveniência × nascimento do install (caso edgesandbox 2026-07-25: 0 entidades).

A exclusão unknown-provenance existe para não filmar trabalho DELEGADO do edge como
vida do mentee. Mas sessão que PRE-DATA o nascimento do install não pode ser delegada —
o edge nem existia; é a vida pré-edge do mentee, exatamente o que o backfill quer.
Fronteira = install_birth (primeiro evento do log / bootstrap). Pós-nascimento, o
fail-closed continua intacto.
"""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import sessions  # noqa: E402


def _codex_session_no_meta(tmp, age_days):
    p = Path(tmp) / "rollout-2026-06-12T03-14-15-abc.jsonl"
    p.write_text('{"type":"message","role":"user","content":"oi"}\n')
    old = time.time() - age_days * 86400
    os.utime(p, (old, old))
    return sessions.Session(id=p.stem, path=p, surface="codex")


class PreEdgeHistoryIsMenteeLife(unittest.TestCase):
    def test_pre_birth_unknown_codex_is_included(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = _codex_session_no_meta(tmp, age_days=30)
            birth = time.time() - 1 * 86400          # install nasceu ontem
            self.assertIsNone(
                sessions.user_session_exclusion_reason(s, install_birth=birth))

    def test_post_birth_unknown_codex_still_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = _codex_session_no_meta(tmp, age_days=1)
            birth = time.time() - 30 * 86400         # install nasceu há um mês
            self.assertEqual(
                sessions.user_session_exclusion_reason(s, install_birth=birth),
                "codex-unknown-provenance")

    def test_no_birth_keeps_todays_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = _codex_session_no_meta(tmp, age_days=30)
            self.assertEqual(
                sessions.user_session_exclusion_reason(s),
                "codex-unknown-provenance")


class PositiveDelegationMarkerNeverSoftens(unittest.TestCase):
    def test_claude_driven_codex_stays_excluded_even_pre_birth(self):
        """originator='Claude Code' = prova de delegação; os turnos 'user' são o
        agente delegante — pré-nascimento NÃO devolve isso como voz do mentee."""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "rollout-2026-06-11T22-14-00-abc.jsonl"
            meta = ('{"type":"session_meta","payload":{"originator":"Claude Code",'
                    '"thread_source":null,"source":"vscode"}}')
            p.write_text(meta + "\n" + '{"type":"response_item","payload":{"role":"user"}}\n')
            old = time.time() - 40 * 86400
            os.utime(p, (old, old))
            s = sessions.Session(id=p.stem, path=p, surface="codex")
            birth = time.time() - 86400
            self.assertEqual(
                sessions.user_session_exclusion_reason(s, install_birth=birth),
                "codex-originator:claude-code")




class OnboardingExceptionForPoorSubstrate(unittest.TestCase):
    """Operador 2026-07-25: delegada não entra NORMALMENTE (o filtro está certo) —
    MAS no onboarding, com insumo inicial muito ruim, abre-se exceção EXPLÍCITA
    (EDGE_ONBOARD_FILM_DELEGATED=1): obra delegada PRÉ-nascimento vira filme.
    Pós-nascimento nunca — é trabalho do próprio edge."""

    def _delegated(self, tmp, age_days):
        p = Path(tmp) / "rollout-2026-06-11T22-14-00-abc.jsonl"
        meta = ('{"type":"session_meta","payload":{"originator":"Claude Code",'
                '"thread_source":null}}')
        p.write_text(meta + "\n")
        old = time.time() - age_days * 86400
        os.utime(p, (old, old))
        return sessions.Session(id=p.stem, path=p, surface="codex")

    def test_flag_admits_pre_birth_delegated_obra(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            s = self._delegated(tmp, 40)
            with mock.patch.dict(os.environ, {"EDGE_ONBOARD_FILM_DELEGATED": "1"}):
                self.assertIsNone(sessions.user_session_exclusion_reason(
                    s, install_birth=time.time() - 86400))

    def test_flag_never_admits_post_birth(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            s = self._delegated(tmp, 1)
            with mock.patch.dict(os.environ, {"EDGE_ONBOARD_FILM_DELEGATED": "1"}):
                self.assertEqual(sessions.user_session_exclusion_reason(
                    s, install_birth=time.time() - 30 * 86400),
                    "codex-originator:claude-code")

    def test_without_flag_stays_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._delegated(tmp, 40)
            self.assertEqual(sessions.user_session_exclusion_reason(
                s, install_birth=time.time() - 86400),
                "codex-originator:claude-code")


if __name__ == "__main__":
    unittest.main()
