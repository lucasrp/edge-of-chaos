"""Hermetic, synthetic-only experiment for a pre-prompt credential closure gate.

This module cannot accept a credential, auth path, executable, home, or prompt from its caller.
It proves only our lifecycle state machine with repository-owned fake processes.  It does not invoke
Codex, OpenAI, a network, a live phenotype, systemd, or the heartbeat.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import selectors
import signal
import subprocess
import sys
import tempfile
import time


_ROOT = Path(__file__).resolve().parent.parent
_FAKE_CLI = _ROOT / "tests" / "fixtures" / "fake_credential_cli.py"
_FAKE_TOOL = _ROOT / "tests" / "fixtures" / "fake_credential_tool.py"
_BEHAVIORS = frozenset({"normal", "ready-before-read", "malformed-ready",
                        "crash-before-ready", "delay-ready"})
_PROMPT = "EDGE_SYNTHETIC_PROMPT_GATE_OPEN"
_CANARY_PREFIX = "EDGE_SYNTHETIC_AUTH_"


class AntechamberError(RuntimeError):
    """The synthetic lifecycle could not prove safe prompt release."""


def _readline(process, timeout_seconds):
    selector = selectors.DefaultSelector()
    try:
        selector.register(process.stdout, selectors.EVENT_READ)
        if not selector.select(timeout_seconds):
            raise AntechamberError("synthetic child timed out")
        line = process.stdout.readline()
    finally:
        selector.close()
    if not line:
        raise AntechamberError("synthetic child closed before terminal frame")
    return line


def _stop_group(process):
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass


def _frame(line, expected_event):
    try:
        value = json.loads(line)
    except (TypeError, ValueError) as exc:
        raise AntechamberError("synthetic child returned malformed frame") from exc
    if not isinstance(value, dict) or value.get("event") != expected_event:
        raise AntechamberError("synthetic child returned unexpected frame")
    return value


def run_hermetic_antechamber(*, behavior="normal", timeout_seconds=2.0):
    """Run one fake lifecycle and return content-free, JSON-serializable evidence.

    The deliberately narrow signature is a safety boundary: callers can vary only a closed fake
    behavior and a small timeout.  All paths, prompt bytes, and canary material are internal.
    """
    if behavior not in _BEHAVIORS:
        raise ValueError("unsupported synthetic behavior")
    if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) \
            or not 0.05 <= float(timeout_seconds) <= 5.0:
        raise ValueError("synthetic timeout must be between 0.05 and 5 seconds")
    if not _FAKE_CLI.is_file() or not _FAKE_TOOL.is_file():
        raise AntechamberError("repository fake boundary is unavailable")

    canary = _CANARY_PREFIX + secrets.token_hex(24)
    started = time.monotonic()
    transitions = ["runtime_created"]
    process = None
    with tempfile.TemporaryDirectory(prefix="edge-auth-antechamber-") as tmp:
        runtime = Path(tmp)
        os.chmod(runtime, 0o700)
        credential = runtime / "synthetic-auth"
        descriptor = os.open(credential, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(descriptor, canary.encode("ascii"))
        finally:
            os.close(descriptor)
        transitions.append("synthetic_credential_staged")
        command = [sys.executable, str(_FAKE_CLI), "--auth-path", str(credential),
                   "--tool-path", str(_FAKE_TOOL), "--behavior", behavior]
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
        }
        try:
            process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, env=environment, start_new_session=True, bufsize=1,
            )
            transitions.append("fake_cli_started")
            ready_line = _readline(process, float(timeout_seconds))
            if canary in ready_line:
                raise AntechamberError("synthetic child reflected credential material")
            ready = _frame(ready_line, "ready")
            if set(ready) != {"event", "credential_loaded"} \
                    or ready.get("credential_loaded") is not True:
                raise AntechamberError("credential load readiness is unproven")
            transitions.append("credential_load_proven")

            credential.unlink()
            if credential.exists():
                raise AntechamberError("credential closure is unproven")
            transitions.append("credential_path_closed")

            process.stdin.write(json.dumps({"event": "prompt", "text": _PROMPT}) + "\n")
            process.stdin.flush()
            transitions.append("prompt_released")
            result_line = _readline(process, float(timeout_seconds))
            if canary in result_line:
                raise AntechamberError("synthetic result reflected credential material")
            result = _frame(result_line, "result")
            expected_fields = {"event", "prompt_received", "cli_rereadable", "tool_rereadable",
                               "tool_process", "credential_value_returned"}
            if set(result) != expected_fields:
                raise AntechamberError("synthetic result shape is invalid")
            if result != {
                    "event": "result", "prompt_received": True, "cli_rereadable": False,
                    "tool_rereadable": False, "tool_process": True,
                    "credential_value_returned": False}:
                raise AntechamberError("credential remained reachable after prompt gate")
            transitions.append("child_read_denied")
            process.stdin.close()
            returncode = process.wait(timeout=float(timeout_seconds))
            if returncode != 0:
                raise AntechamberError("synthetic child exited nonzero")
            stderr = process.stderr.read()
            if canary in stderr:
                raise AntechamberError("synthetic child reflected credential to stderr")
            transitions.append("fake_cli_terminal")
            summary = {
                "schema": "edge.credential-antechamber-hermetic/v1",
                "behavior": behavior,
                "passed": True,
                "runtime_mode": oct(runtime.stat().st_mode & 0o777),
                "credential_mode": "0o600",
                "prompt_released_after_closure": True,
                "cli_rereadable_after_gate": False,
                "tool_rereadable_after_gate": False,
                "separate_tool_process": True,
                "credential_value_returned": False,
                "network_used": False,
                "llm_invoked": False,
                "real_auth_read": False,
                "transitions": transitions,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            }
            if canary in json.dumps(summary, sort_keys=True):
                raise AntechamberError("synthetic credential reached returned evidence")
            return summary
        except (BrokenPipeError, subprocess.TimeoutExpired) as exc:
            raise AntechamberError("synthetic lifecycle failed closed") from exc
        finally:
            if process is not None:
                _stop_group(process)
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None and not stream.closed:
                        stream.close()
            if credential.exists():
                credential.unlink()
            canary = None
