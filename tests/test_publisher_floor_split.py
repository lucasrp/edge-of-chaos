"""#61 — the S6 grounding floor keeps its TEETH across the producer split.

Under the #61 split the close runs in the PUBLISHER child process: the harness sets
`CLAUDE_CODE_CHILD_SESSION`, and the publisher's own transcript has ZERO source-reads (it does no
grounding — Facet A left that in the MAIN). So the NAIVE floor call — `harvest.close_floor()` — goes
ALWAYS-DARK in the publisher: the very grounding floor the issue leans on loses its teeth.

The cure (design §4) is a one-parameter injection the code already supports: the brief carries
`main_session_id`, and the publisher wires

    floor_fn=lambda: harvest.close_floor(session_id=main_session_id, child_session="")

pointing the floor at the MAIN's transcript (where the reads LIVE) and EXPLICITLY CLEARING the
child-session guard. This test pins that BOTH parameters are LOAD-BEARING: against the SAME MAIN
reality (a themed dispatch with zero recognized reads = a real violation), the WIRED call BITES while
the naive child call DARKS OUT and misses it — and forgetting `child_session=""` alone re-darkens it.

Idiom mirrors tests/test_close_residuals_floor.py `CloseFloorWrapperKnobLogic` (same fixtures).
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tests"))
import harvest    # noqa: E402
import eventlog   # noqa: E402
import predispatch  # noqa: E402


class _Env:
    """Set/clear env vars (EDGE_* knobs + the CLAUDE_CODE_* session vars) and restore them."""
    def __init__(self, **vars):
        self.vars = vars
        self.saved = {}

    def __enter__(self):
        for k, v in self.vars.items():
            self.saved[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = str(v)
        return self

    def __exit__(self, *a):
        for k, old in self.saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


def _log_with_open(tmp, session_id, geometry="themed"):
    log = Path(tmp) / "log.jsonl"
    eventlog.append("dispatch.open", "dispatch",
                    {"session_id": session_id, "dispatch_id": "d1", "geometry": geometry}, log=log)
    return log


def _store_with_transcript(tmp, session_id, *, recognized):
    store = Path(tmp) / "projects"
    if recognized:
        from test_harvest import _tool_pair, _write, X_CMD
        _write(store / "-slug" / f"{session_id}.jsonl",
               _tool_pair(session_id, "t1", "2026-07-01T10:00:00.000Z", X_CMD))
    else:
        line = {"type": "assistant", "sessionId": session_id,
                "timestamp": "2026-07-01T10:00:00.000Z",
                "message": {"role": "assistant",
                            "content": [{"type": "text", "text": "just thinking"}]}}
        p = store / "-slug" / f"{session_id}.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(line) + "\n")
    return store


def _codex_line(ts, payload):
    return json.dumps({"timestamp": ts, "type": "response_item", "payload": payload}) + "\n"


def _write_codex_session(root, session_id, command):
    path = Path(root) / "sessions" / "2026" / "07" / "06" / f"rollout-{session_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"timestamp": "2026-07-06T10:00:00.000Z", "type": "session_meta",
                    "payload": {"id": session_id}}) + "\n"
        + _codex_line("2026-07-06T10:05:00.000Z",
                      {"type": "function_call", "name": "exec_command",
                       "arguments": json.dumps({"cmd": command}),
                       "call_id": "call_1"})
        + _codex_line("2026-07-06T10:05:01.000Z",
                      {"type": "function_call_output", "call_id": "call_1",
                       "output": '{"meta":{"result_count":10}}'})
    )
    return path


def _x_recognizers():
    return harvest.build_recognizers(sources=[{
        "name": "x",
        "description": "X live builder signal. Lens: Mundo.",
        "interfaces": [{
            "interface_id": "v2-recent",
            "via": "GET https://api.twitter.com/2/tweets/search/recent?query=...&max_results=... (Bearer)",
            "hit_count": r'"result_count"\s*:\s*(\d+)',
        }],
    }])


class FloorTeethSurviveTheProducerSplit(unittest.TestCase):
    MAIN = "mainS"           # the MAIN's session — its dispatch.open + its transcript
    PUB = "pubChildS"        # the publisher child's own session

    def test_naive_call_in_publisher_child_goes_dark_and_loses_teeth(self):
        # THE BUG: the publisher runs as a child (CLAUDE_CODE_CHILD_SESSION set) with its own read-less
        # session. The naive close_floor() defaults child_session from the env → dark → [] (no bite),
        # even though the MAIN did a themed dispatch with ZERO reads (a real violation).
        with tempfile.TemporaryDirectory() as tmp, _Env(
                EDGE_GROUNDING_FLOOR=2,
                CLAUDE_CODE_SESSION_ID=self.PUB,
                CLAUDE_CODE_CHILD_SESSION=self.PUB):
            log = _log_with_open(tmp, self.MAIN, "themed")
            store = _store_with_transcript(tmp, self.MAIN, recognized=False)
            out = harvest.close_floor(log=log, store_root=store)   # naive: no session_id, no child clear
            self.assertEqual(out, [])                              # DARK — floor lost its teeth
            self.assertEqual(len(eventlog.read(types=["grounding.floor_dark"], log=log)), 1)

    def test_wired_call_bites_the_same_main_violation_teeth_intact(self):
        # THE CURE: point the floor at the MAIN session and CLEAR the child guard. Same MAIN reality
        # (themed dispatch, zero reads) — now the floor BITES with the named violation.
        with tempfile.TemporaryDirectory() as tmp, _Env(
                EDGE_GROUNDING_FLOOR=2,
                CLAUDE_CODE_SESSION_ID=self.PUB,
                CLAUDE_CODE_CHILD_SESSION=self.PUB):
            log = _log_with_open(tmp, self.MAIN, "themed")
            store = _store_with_transcript(tmp, self.MAIN, recognized=False)
            out = harvest.close_floor(log=log, store_root=store,
                                      session_id=self.MAIN, child_session="")
            self.assertEqual(out, [harvest.FLOOR_VIOLATION])       # TEETH — the violation bit

    def test_wired_call_reaches_the_mains_reads_and_is_satisfied(self):
        # the wiring reaches the MAIN's transcript: a recognized read in the MAIN satisfies the floor
        # (proving session_id=main_session_id targets where the reads LIVE, not the publisher's).
        with tempfile.TemporaryDirectory() as tmp, _Env(
                EDGE_GROUNDING_FLOOR=2,
                CLAUDE_CODE_SESSION_ID=self.PUB,
                CLAUDE_CODE_CHILD_SESSION=self.PUB):
            log = _log_with_open(tmp, self.MAIN, "themed")
            store = _store_with_transcript(tmp, self.MAIN, recognized=True)
            out = harvest.close_floor(log=log, store_root=store,
                                      recognizers=_x_recognizers(),
                                      session_id=self.MAIN, child_session="")
            self.assertEqual(out, [])                              # satisfied — the read counted

    def test_forgetting_child_session_clear_alone_re_darkens_it(self):
        # the SHARPEST pin: even with the RIGHT session_id, omitting child_session="" lets close_floor
        # default it from the child env → set → dark. So child_session="" is independently load-bearing.
        with tempfile.TemporaryDirectory() as tmp, _Env(
                EDGE_GROUNDING_FLOOR=2,
                CLAUDE_CODE_SESSION_ID=self.PUB,
                CLAUDE_CODE_CHILD_SESSION=self.PUB):
            log = _log_with_open(tmp, self.MAIN, "themed")
            store = _store_with_transcript(tmp, self.MAIN, recognized=False)
            out = harvest.close_floor(log=log, store_root=store, session_id=self.MAIN)  # no child clear
            self.assertEqual(out, [])                              # re-darkened — teeth lost again
            self.assertEqual(len(eventlog.read(types=["grounding.floor_dark"], log=log)), 1)


class CodexFloorParity(unittest.TestCase):
    def test_predispatch_stamps_codex_thread_id_when_claude_session_is_absent(self):
        with tempfile.TemporaryDirectory() as tmp, _Env(
                CLAUDE_CODE_SESSION_ID=None,
                CODEX_THREAD_ID="codex-main"):
            log = Path(tmp) / "log.jsonl"
            predispatch.run(sweep_fn=lambda: 0, briefing_fn=lambda: "B",
                            recall_fn=lambda: "R", harvest_fn=lambda: 0,
                            probe_fn=lambda spec: None, log=log, geometry="themed")
            ev = eventlog.read(types=["dispatch.open"], log=log)[0]
            self.assertEqual(ev["payload"]["session_id"], "codex:codex-main")

    def test_close_floor_defaults_to_codex_thread_and_reads_codex_transcript(self):
        from test_harvest import X_CMD
        with tempfile.TemporaryDirectory() as tmp, _Env(
                EDGE_GROUNDING_FLOOR=2,
                CLAUDE_CODE_SESSION_ID=None,
                CLAUDE_CODE_CHILD_SESSION=None,
                CODEX_HOME=Path(tmp) / "codex-home",
                CODEX_THREAD_ID="codex-main"):
            log = Path(tmp) / "log.jsonl"
            eventlog.append("dispatch.open", "dispatch",
                            {"session_id": "codex:codex-main", "dispatch_id": "d1",
                             "geometry": "themed"}, log=log)
            _write_codex_session(Path(tmp) / "codex-home", "codex-main", X_CMD)
            out = harvest.close_floor(log=log, recognizers=_x_recognizers())
            self.assertEqual(out, [])
            self.assertEqual(eventlog.read(types=["grounding.floor_dark"], log=log), [])


if __name__ == "__main__":
    unittest.main()
