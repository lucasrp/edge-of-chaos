"""quente — o 4º brief do wake (o SENTIR passivo): o construtor do insumo de dois trilhos.

Pins the PURE CORE of the input builder (bare python): ordinal-K selection of substantial
sessions (E1: turnos-op >=5 E chars-op >=1k), operator-prompt extraction (verbatim, cap 500c,
scaffolding filtered — trilho voz), and the two-rail bundle assembly (voz + âncoras mecânicas
injetadas). O leitor é um subagente (skills/quente); aqui só a máquina de preparar o insumo.
Proposta: docs/agencia/proposta-novo-wake.md (16k default, K=3 ordinal, dois trilhos).
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import quente  # noqa: E402


META = [  # (id, op_turns, op_chars, last_ts) — mais recente primeiro após seleção
    {"id": "s-novo", "op_turns": 20, "op_chars": 9000, "last": "2026-07-05T01:00:00Z"},
    {"id": "s-agente", "op_turns": 0, "op_chars": 0, "last": "2026-07-05T00:00:00Z"},
    {"id": "s-medio", "op_turns": 8, "op_chars": 2000, "last": "2026-07-03T10:00:00Z"},
    {"id": "s-raso", "op_turns": 2, "op_chars": 100, "last": "2026-07-02T10:00:00Z"},
    {"id": "s-velho", "op_turns": 30, "op_chars": 15000, "last": "2026-06-20T10:00:00Z"},
]


class TestOrdinalSelection(unittest.TestCase):
    def test_last_k_substantial_ordinal(self):
        """K=2: pega as 2 substanciais MAIS RECENTES; agente-only e rasa ficam fora."""
        sel = quente.select_sessions(META, k=2)
        self.assertEqual([s["id"] for s in sel], ["s-novo", "s-medio"])

    def test_wallclock_is_ceiling_not_ruler(self):
        """Teto wall-clock: sessão substancial FORA do teto não entra mesmo com K sobrando."""
        sel = quente.select_sessions(META, k=5, max_age_days=7,
                                     now="2026-07-05T02:00:00Z")
        self.assertNotIn("s-velho", [s["id"] for s in sel])
        self.assertEqual([s["id"] for s in sel], ["s-novo", "s-medio", "s-raso"][:2] if False
                         else ["s-novo", "s-medio"])  # só as substanciais dentro do teto


class TestVozRail(unittest.TestCase):
    TURNS = [
        ("user", "faz o X direito"),
        ("assistant", "feito"),
        ("user", "<system-reminder>lixo injetado</system-reminder>"),
        ("user", "heartbeat keep-warm: reporte"),
        ("user", "b" * 900),
    ]

    def test_prompts_verbatim_cap_and_filter(self):
        out = quente.operator_prompts(self.TURNS, cap=500)
        self.assertEqual(out[0], "faz o X direito")     # verbatim
        self.assertEqual(len(out), 2)                    # scaffolding/heartbeat fora
        self.assertEqual(len(out[1]), 500)               # cap aplicado


class TestBundle(unittest.TestCase):
    def test_two_rails_assembled(self):
        """O insumo carrega os DOIS trilhos rotulados — voz e âncoras — e nada de prosa nossa."""
        bundle = quente.build_input(
            sessions=[{"id": "s1", "prompts": ["oi", "faz Y"]}],
            anchors="## git log\nabc123 feat: x")
        self.assertIn("TRILHO VOZ", bundle)
        self.assertIn("faz Y", bundle)
        self.assertIn("ÂNCORAS MECÂNICAS", bundle)
        self.assertIn("abc123", bundle)


def _ts(hours_ago):
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


def _write_session(store, stem, n_user_turns, chars_per_turn, hours_ago):
    """Uma sessão jsonl no formato do store Claude: N turnos-user de M chars, último ts relativo."""
    lines = []
    for i in range(n_user_turns):
        lines.append(json.dumps({"type": "user", "timestamp": _ts(hours_ago + n_user_turns - i),
                                 "message": {"content": f"turno {i} " + "x" * chars_per_turn}}))
        lines.append(json.dumps({"type": "assistant", "timestamp": _ts(hours_ago + n_user_turns - i),
                                 "message": {"content": [{"type": "text", "text": "feito"}]}}))
    # o último evento define `last`
    lines[-1] = json.dumps({"type": "assistant", "timestamp": _ts(hours_ago),
                            "message": {"content": [{"type": "text", "text": "fim"}]}})
    (Path(store) / f"{stem}.jsonl").write_text("\n".join(lines) + "\n")


def _write_codex_session(store, stem, n_user_turns, chars_per_turn, hours_ago):
    lines = [json.dumps({"type": "session_meta", "timestamp": _ts(hours_ago + n_user_turns + 1),
                         "payload": {"id": stem, "thread_source": "user"}})]
    for i in range(n_user_turns):
        lines.append(json.dumps({"type": "response_item", "timestamp": _ts(hours_ago + n_user_turns - i),
                                 "payload": {"type": "message", "role": "user",
                                             "content": [{"type": "input_text",
                                                          "text": f"codex turno {i} " + "c" * chars_per_turn}]}}))
        lines.append(json.dumps({"type": "response_item", "timestamp": _ts(hours_ago + n_user_turns - i),
                                 "payload": {"type": "message", "role": "assistant",
                                             "content": [{"type": "output_text", "text": "feito"}]}}))
    lines[-1] = json.dumps({"type": "response_item", "timestamp": _ts(hours_ago),
                            "payload": {"type": "message", "role": "assistant",
                                        "content": [{"type": "output_text", "text": "fim"}]}})
    (Path(store) / f"{stem}.jsonl").write_text("\n".join(lines) + "\n")


def _write_grok_session(store, stem, n_user_turns, chars_per_turn, hours_ago,
                       session_kind=None):
    root = Path(store) / "%2Ftmp" / stem
    root.mkdir(parents=True, exist_ok=True)
    lines = []
    for i in range(n_user_turns):
        text = f"grok turno {i} " + "c" * chars_per_turn
        lines.append(json.dumps({
            "type": "user",
            "content": [{"type": "text", "text": f"<user_query>\n{text}\n</user_query>"}],
        }))
        lines.append(json.dumps({
            "type": "assistant",
            "content": [{"type": "text", "text": "feito"}],
        }))
    (root / "chat_history.jsonl").write_text("\n".join(lines) + "\n")
    summary = {
        "info": {"id": stem},
        "last_active_at": _ts(hours_ago),
        "updated_at": _ts(hours_ago),
    }
    if session_kind is not None:
        summary["session_kind"] = session_kind
    (root / "summary.json").write_text(json.dumps(summary))


class TestSelectWindow(unittest.TestCase):
    """select_window — o scan barato de metadata que predispatch e build_bundle COMPARTILHAM
    (invariante de coerência: o hot_cutoff do briefing ≡ a janela que o leitor quente cobre)."""

    def _store(self, tmp):
        _write_session(tmp, "s-novo", n_user_turns=8, chars_per_turn=300, hours_ago=2)
        _write_session(tmp, "s-medio", n_user_turns=6, chars_per_turn=300, hours_ago=30)
        _write_session(tmp, "s-raso", n_user_turns=2, chars_per_turn=20, hours_ago=1)
        _write_session(tmp, "s-velho", n_user_turns=9, chars_per_turn=300, hours_ago=24 * 30)

    def test_window_start_is_the_oldest_selected_last(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._store(tmp)
            sel, window_start = quente.select_window(store_dir=tmp, k=2, max_age_days=7,
                                                     exclude=())
            self.assertEqual([m["id"] for m in sel], ["s-novo", "s-medio"])
            self.assertEqual(window_start, sel[-1]["last"])

    def test_store_dir_none_resolves_host_agnostic_via_identity(self):
        """store_dir omitido → _identity.project_dir() (EDGE_PROJECT_DIR → convenção do $HOME);
        nunca um path do ed hard-coded."""
        with tempfile.TemporaryDirectory() as tmp:
            self._store(tmp)
            old = os.environ.get("EDGE_PROJECT_DIR")
            os.environ["EDGE_PROJECT_DIR"] = tmp
            try:
                sel, window_start = quente.select_window(k=1, exclude=(), codex_dir=False)
            finally:
                if old is None:
                    del os.environ["EDGE_PROJECT_DIR"]
                else:
                    os.environ["EDGE_PROJECT_DIR"] = old
            self.assertEqual([m["id"] for m in sel], ["s-novo"])

    def test_exclude_defaults_to_the_session_in_course(self):
        """exclude=None → CLAUDE_CODE_SESSION_ID (a sessão em curso nunca entra na própria janela);
        exclude=() explícito desliga."""
        with tempfile.TemporaryDirectory() as tmp:
            self._store(tmp)
            old = os.environ.get("CLAUDE_CODE_SESSION_ID")
            os.environ["CLAUDE_CODE_SESSION_ID"] = "s-novo"
            try:
                sel, _ = quente.select_window(store_dir=tmp, k=2)
                self.assertNotIn("s-novo", [m["id"] for m in sel])
                sel_all, _ = quente.select_window(store_dir=tmp, k=2, exclude=())
                self.assertIn("s-novo", [m["id"] for m in sel_all])
            finally:
                if old is None:
                    del os.environ["CLAUDE_CODE_SESSION_ID"]
                else:
                    os.environ["CLAUDE_CODE_SESSION_ID"] = old

    def test_codex_sessions_join_the_same_hot_window(self):
        with tempfile.TemporaryDirectory() as claude, tempfile.TemporaryDirectory() as codex:
            _write_session(claude, "s-claude", n_user_turns=8, chars_per_turn=300, hours_ago=3)
            _write_codex_session(codex, "s-codex", n_user_turns=8, chars_per_turn=300, hours_ago=1)
            sel, _ = quente.select_window(store_dir=claude, codex_dir=codex, k=2,
                                          max_age_days=7, exclude=())
            self.assertEqual([m["id"] for m in sel], ["codex:s-codex", "s-claude"])
            self.assertEqual(sel[0]["surface"], "codex")

    def test_build_bundle_carries_codex_operator_prompts(self):
        with tempfile.TemporaryDirectory() as claude, tempfile.TemporaryDirectory() as codex:
            _write_session(claude, "s-claude", n_user_turns=8, chars_per_turn=300, hours_ago=3)
            _write_codex_session(codex, "s-codex", n_user_turns=8, chars_per_turn=300, hours_ago=1)
            bundle, _ = quente.build_bundle(store_dir=claude, codex_dir=codex, repos=(),
                                            exclude=(), eventlog_path=Path(claude) / "none.jsonl")
            self.assertIn("Sessão codex:s", bundle)
            self.assertIn("codex turno", bundle)

    def test_grok_sessions_join_the_same_hot_window(self):
        with tempfile.TemporaryDirectory() as claude, tempfile.TemporaryDirectory() as grok:
            _write_session(claude, "s-claude", n_user_turns=8, chars_per_turn=300, hours_ago=3)
            _write_grok_session(grok, "s-grok", n_user_turns=8, chars_per_turn=300, hours_ago=1)
            sel, _ = quente.select_window(store_dir=claude, grok_dir=grok, codex_dir=False, k=2,
                                          max_age_days=7, exclude=())
            self.assertEqual([m["id"] for m in sel], ["grok:s-grok", "s-claude"])
            self.assertEqual(sel[0]["surface"], "grok")

    def test_build_bundle_carries_grok_operator_prompts(self):
        with tempfile.TemporaryDirectory() as claude, tempfile.TemporaryDirectory() as grok:
            _write_session(claude, "s-claude", n_user_turns=8, chars_per_turn=300, hours_ago=3)
            _write_grok_session(grok, "s-grok", n_user_turns=8, chars_per_turn=300, hours_ago=1)
            bundle, _ = quente.build_bundle(store_dir=claude, grok_dir=grok, codex_dir=False,
                                            repos=(), exclude=(),
                                            eventlog_path=Path(claude) / "none.jsonl")
            self.assertIn("Sessão grok:s", bundle)
            self.assertIn("grok turno", bundle)


    def test_grok_subagent_sessions_are_filtered_from_window(self):
        """Optional surfaces use is_user_session — Grok workers must not pollute hot window."""
        with tempfile.TemporaryDirectory() as claude, tempfile.TemporaryDirectory() as grok:
            _write_session(claude, "s-claude", n_user_turns=8, chars_per_turn=300, hours_ago=3)
            _write_grok_session(grok, "s-worker", n_user_turns=8, chars_per_turn=300, hours_ago=1,
                                session_kind="subagent")
            _write_grok_session(grok, "s-op", n_user_turns=8, chars_per_turn=300, hours_ago=2)
            sel, _ = quente.select_window(store_dir=claude, grok_dir=grok, codex_dir=False, k=3,
                                          max_age_days=7, exclude=())
            ids = [m["id"] for m in sel]
            self.assertIn("grok:s-op", ids)
            self.assertNotIn("grok:s-worker", ids)

    def test_exclude_defaults_to_active_grok_session_when_env_unset(self):
        """GROK_SESSION_ID is not exported by real CLI; live id comes from active_sessions.json."""
        import sessions
        with tempfile.TemporaryDirectory() as claude, tempfile.TemporaryDirectory() as grok, \
                tempfile.TemporaryDirectory() as act:
            _write_session(claude, "s-claude", n_user_turns=8, chars_per_turn=300, hours_ago=3)
            _write_grok_session(grok, "s-live", n_user_turns=8, chars_per_turn=300, hours_ago=1)
            _write_grok_session(grok, "s-other", n_user_turns=8, chars_per_turn=300, hours_ago=2)
            active = Path(act) / "active_sessions.json"
            active.write_text(json.dumps([{
                "session_id": "s-live",
                "pid": os.getpid(),
                "cwd": "/tmp",
                "opened_at": "2026-07-11T00:00:00Z",
            }]))
            keys = ("CLAUDE_CODE_SESSION_ID", "CODEX_SESSION_ID", "CODEX_THREAD_ID",
                    "GROK_SESSION_ID", "EDGE_GROK_ACTIVE_SESSIONS", "GROK_HOME")
            old = {k: os.environ.get(k) for k in keys}
            for k in keys:
                os.environ.pop(k, None)
            os.environ["EDGE_GROK_ACTIVE_SESSIONS"] = str(active)
            try:
                self.assertEqual(sessions.current_session_anchor(), "grok:s-live")
                sel, _ = quente.select_window(store_dir=claude, grok_dir=grok, codex_dir=False,
                                              k=3, max_age_days=7)
                ids = [m["id"] for m in sel]
                self.assertNotIn("grok:s-live", ids)
                self.assertNotIn("s-live", ids)
                self.assertIn("grok:s-other", ids)
            finally:
                for k, v in old.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v


class TestAnchorsRail(unittest.TestCase):
    """Trilho EXECUTADO honesto (codex-adversarial 7/8, gate=SINAL): o bundle entrega git log
    E eventlog-tail (o contrato do leitor: 'fato executado vem SÓ daqui'); erro de git vira
    marcador dark, nunca a afirmação falsa '(sem commits)'."""

    def test_bundle_carries_the_eventlog_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_session(tmp, "s-novo", n_user_turns=8, chars_per_turn=300, hours_ago=2)
            ev = Path(tmp) / "log.jsonl"
            ev.write_text(json.dumps({"seq": 1, "ts": _ts(1), "type": "artefato.published",
                                      "subject": "close", "payload": {}}) + "\n")
            bundle, _ = quente.build_bundle(store_dir=tmp, repos=(), exclude=(),
                                            eventlog_path=ev)
            self.assertIn("eventlog", bundle)
            self.assertIn("artefato.published", bundle)

    def test_git_failure_is_dark_never_sem_commits(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_session(tmp, "s-novo", n_user_turns=8, chars_per_turn=300, hours_ago=2)
            bundle, _ = quente.build_bundle(store_dir=tmp, repos=(Path(tmp) / "nao-e-repo",),
                                            exclude=(), eventlog_path=Path(tmp) / "nada.jsonl")
            self.assertIn("git indisponível", bundle)
            self.assertNotIn("(sem commits)", bundle)


if __name__ == "__main__":
    unittest.main()
