"""Fail-closed compatibility gate for bounded ``codex exec --json`` output.

The official documentation establishes JSON Lines output but does not publish a normative event
schema on that page.  This parser therefore names an observed compatibility profile and rejects
every unknown top-level or item type until it is reviewed.  It never returns raw event text,
reasoning, model output, or secret material.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time
import re


PROFILE = "codex-jsonl-observed-0.147.0/v1"
ALLOWED_EVENTS = frozenset({"thread.started", "turn.started", "item.completed", "turn.completed"})
ALLOWED_ITEMS = frozenset({"reasoning", "agent_message"})
TOOL_ITEMS = frozenset({
    "command_execution", "file_change", "mcp_tool_call", "web_search",
    "computer", "function_call", "tool_call",
})
MAX_LINE_BYTES = 64 * 1024
MAX_TOTAL_BYTES = 512 * 1024
MAX_STDERR_BYTES = 64 * 1024
_ROOT = Path(__file__).resolve().parent.parent
_FAKE = _ROOT / "tests" / "fixtures" / "fake_codex_jsonl.py"
_SYNTHETIC_CANARY = "EDGE_SYNTHETIC_JSONL_SECRET_CANARY"
_SYNTHETIC_PROMPT = "EDGE_SYNTHETIC_SUPERVISED_PROMPT"
_BEHAVIORS = frozenset({
    "success", "tool", "unknown-event", "unknown-item", "malformed", "overflow",
    "stderr-overflow", "secret", "nonzero", "missing-terminal", "hang",
})


class JsonlGateError(RuntimeError):
    """The stream did not satisfy the closed compatibility profile."""


def build_supervised_codex_command(policy: dict, *, codex_bin, dispatch_id: str) -> list[str]:
    """Build, but never execute, the fixed PB-4 Codex command."""
    if not isinstance(policy, dict) or policy.get("schema") != "edge.persistent-auth-bridge/v1":
        raise JsonlGateError("supervised command requires persistent bridge policy v1")
    if (policy.get("cadence") or {}).get("may_enable_timer") is not False:
        raise JsonlGateError("supervised command requires timer prohibition")
    if not isinstance(dispatch_id, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", dispatch_id):
        raise JsonlGateError("supervised command requires a fixed safe dispatch id")
    executable = Path(codex_bin)
    if not executable.is_absolute() or executable.name != "codex":
        raise JsonlGateError("codex_bin must be an absolute Codex executable path")
    immutable = Path(str(policy.get("immutable_input_root") or ""))
    runtime = Path(str(policy.get("runtime_output_root") or ""))
    codex_home = Path(str(policy.get("codex_home") or ""))
    if not all(path.is_absolute() for path in (immutable, runtime, codex_home)):
        raise JsonlGateError("supervised roots must be absolute")
    if any(a == b or a in b.parents or b in a.parents
           for i, a in enumerate((immutable, runtime, codex_home))
           for b in (immutable, runtime, codex_home)[i + 1:]):
        raise JsonlGateError("supervised roots must not overlap")
    return [
        str(executable), "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--sandbox", "workspace-write",
        "--json",
        "--color", "never",
        "-C", str(immutable),
        "--add-dir", str(runtime),
        "-",
    ]


def write_terminal_receipt(receipt: dict, *, audit_dir, dispatch_id: str) -> Path:
    """Atomically persist only the allowlisted sanitized terminal receipt."""
    if not isinstance(dispatch_id, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", dispatch_id):
        raise JsonlGateError("receipt requires a fixed safe dispatch id")
    required = {
        "schema", "compatibility_profile", "passed", "event_counts", "item_counts",
        "tool_items", "unknown_events", "terminal", "raw_output_persisted",
        "reasoning_persisted", "model_output_persisted", "secret_occurrences",
        "bytes_inspected", "process_group_terminal", "stderr_persisted", "llm_invoked",
        "network_used",
    }
    if not isinstance(receipt, dict) or set(receipt) != required:
        raise JsonlGateError("terminal receipt shape is not allowlisted")
    if receipt.get("schema") != "edge.codex-jsonl-terminal-gate/v1" \
            or receipt.get("passed") is not True or receipt.get("terminal") is not True \
            or receipt.get("process_group_terminal") is not True:
        raise JsonlGateError("terminal receipt is not a successful closed run")
    if any(receipt.get(name) is not False for name in (
            "raw_output_persisted", "reasoning_persisted", "model_output_persisted",
            "stderr_persisted", "llm_invoked", "network_used")):
        raise JsonlGateError("terminal receipt claims a forbidden side effect")
    if receipt.get("secret_occurrences") != 0 or receipt.get("tool_items") != 0 \
            or receipt.get("unknown_events") != 0:
        raise JsonlGateError("terminal receipt contains a failed security count")

    directory = Path(audit_dir)
    if not directory.is_absolute() or not directory.is_dir() or directory.is_symlink():
        raise JsonlGateError("audit_dir must be an existing absolute regular directory")
    body = json.dumps(
        {**receipt, "dispatch_id": dispatch_id}, ensure_ascii=True, sort_keys=True,
        separators=(",", ":"),
    ).encode() + b"\n"
    lowered = body.lower()
    if any(marker in lowered for marker in (
            b"authorization", b"api_key", b"access_token", b"refresh_token", b"auth.json")):
        raise JsonlGateError("terminal receipt contains forbidden credential-shaped material")
    temp = directory / f".{dispatch_id}.json.tmp-{os.getpid()}-{time.monotonic_ns()}"
    target = directory / f"{dispatch_id}.json"
    fd = None
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        view = memoryview(body)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise JsonlGateError("terminal receipt write made no progress")
            view = view[written:]
        os.fsync(fd)
        os.close(fd)
        fd = None
        os.replace(temp, target)
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        if target.stat().st_mode & 0o777 != 0o600 or target.stat().st_nlink != 1:
            raise JsonlGateError("terminal receipt metadata verification failed")
        return target
    finally:
        if fd is not None:
            os.close(fd)
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def inspect_jsonl(lines: list[bytes], *, secret_needles=()) -> dict:
    """Validate a complete bounded stream and return only sanitized structural evidence."""
    if not isinstance(lines, list):
        raise JsonlGateError("JSONL input must be a list of byte lines")
    needles = []
    for needle in secret_needles:
        if not isinstance(needle, (bytes, str)):
            raise JsonlGateError("secret needles must be bytes or strings")
        encoded = needle.encode() if isinstance(needle, str) else needle
        if encoded:
            needles.append(encoded)

    total = 0
    state = "new"
    event_counts = {}
    item_counts = {}
    agent_messages = 0
    for raw in lines:
        if not isinstance(raw, bytes):
            raise JsonlGateError("JSONL lines must be bytes")
        total += len(raw)
        if len(raw) > MAX_LINE_BYTES or total > MAX_TOTAL_BYTES:
            raise JsonlGateError("JSONL output exceeded the configured bound")
        if any(needle in raw for needle in needles):
            raise JsonlGateError("secret canary occurred in JSONL output")
        try:
            event = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise JsonlGateError("JSONL output is malformed") from exc
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise JsonlGateError("JSONL event envelope is invalid")
        event_type = event["type"]
        if event_type not in ALLOWED_EVENTS:
            raise JsonlGateError("JSONL event type is not allowlisted")
        event_counts[event_type] = event_counts.get(event_type, 0) + 1

        if state == "new" and event_type == "thread.started":
            state = "thread"
        elif state == "thread" and event_type == "turn.started":
            state = "turn"
        elif state == "turn" and event_type == "item.completed":
            item = event.get("item")
            if not isinstance(item, dict) or not isinstance(item.get("type"), str):
                raise JsonlGateError("completed item envelope is invalid")
            item_type = item["type"]
            if item_type in TOOL_ITEMS:
                raise JsonlGateError("tool item is forbidden")
            if item_type not in ALLOWED_ITEMS:
                raise JsonlGateError("item type is not allowlisted")
            item_counts[item_type] = item_counts.get(item_type, 0) + 1
            if item_type == "agent_message":
                agent_messages += 1
        elif state == "turn" and event_type == "turn.completed":
            state = "terminal"
        else:
            raise JsonlGateError("JSONL event order is invalid")

    if state != "terminal":
        raise JsonlGateError("JSONL stream has no successful terminal turn")
    if agent_messages != 1:
        raise JsonlGateError("JSONL stream must contain exactly one final agent message")
    return {
        "schema": "edge.codex-jsonl-terminal-gate/v1",
        "compatibility_profile": PROFILE,
        "passed": True,
        "event_counts": event_counts,
        "item_counts": item_counts,
        "tool_items": 0,
        "unknown_events": 0,
        "terminal": True,
        "raw_output_persisted": False,
        "reasoning_persisted": False,
        "model_output_persisted": False,
        "secret_occurrences": 0,
        "bytes_inspected": total,
    }


def _terminate_group(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=0.5)
    except (OSError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            pass


def run_hermetic_fake(*, behavior="success", timeout_seconds=1.0) -> dict:
    """Exercise the supervisor against the repository-owned fake process only."""
    if behavior not in _BEHAVIORS:
        raise ValueError("unsupported fake JSONL behavior")
    if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) \
            or not 0.05 <= float(timeout_seconds) <= 3.0:
        raise ValueError("fake timeout must be between 0.05 and 3 seconds")
    if not _FAKE.is_file():
        raise JsonlGateError("repository fake JSONL process is unavailable")

    process = subprocess.Popen(
        [sys.executable, str(_FAKE), behavior],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"},
        start_new_session=True,
    )
    selector = selectors.DefaultSelector()
    lines = []
    stdout_buffer = bytearray()
    stdout_total = 0
    stderr = bytearray()
    started = time.monotonic()
    try:
        process.stdin.write((_SYNTHETIC_PROMPT + "\n").encode())
        process.stdin.close()
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        while selector.get_map():
            remaining = float(timeout_seconds) - (time.monotonic() - started)
            if remaining <= 0:
                raise JsonlGateError("fake JSONL process timed out")
            ready = selector.select(remaining)
            if not ready:
                raise JsonlGateError("fake JSONL process timed out")
            for key, _ in ready:
                chunk = os.read(key.fileobj.fileno(), 4096)
                if not chunk:
                    if key.data == "stdout" and stdout_buffer:
                        lines.append(bytes(stdout_buffer))
                        stdout_buffer.clear()
                    selector.unregister(key.fileobj)
                    continue
                if key.data == "stdout":
                    stdout_total += len(chunk)
                    if stdout_total > MAX_TOTAL_BYTES:
                        raise JsonlGateError("JSONL output exceeded the configured bound")
                    stdout_buffer.extend(chunk)
                    while b"\n" in stdout_buffer:
                        line, _, rest = stdout_buffer.partition(b"\n")
                        lines.append(bytes(line) + b"\n")
                        stdout_buffer = bytearray(rest)
                    if len(stdout_buffer) > MAX_LINE_BYTES:
                        raise JsonlGateError("JSONL line exceeded the configured bound")
                else:
                    stderr.extend(chunk)
                    if len(stderr) > MAX_STDERR_BYTES:
                        raise JsonlGateError("stderr exceeded the configured bound")
                if _SYNTHETIC_CANARY.encode() in chunk:
                    raise JsonlGateError("secret canary occurred in child output")
        returncode = process.wait(timeout=max(0.05, float(timeout_seconds)))
        if returncode != 0:
            raise JsonlGateError("fake JSONL process exited nonzero")
        receipt = inspect_jsonl(lines, secret_needles=[_SYNTHETIC_CANARY])
        receipt["process_group_terminal"] = process.poll() is not None
        receipt["stderr_persisted"] = False
        receipt["llm_invoked"] = False
        receipt["network_used"] = False
        return receipt
    except subprocess.TimeoutExpired as exc:
        raise JsonlGateError("fake JSONL process failed to terminate") from exc
    finally:
        selector.close()
        _terminate_group(process)
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()


def run_hermetic_bridge(*, audit_dir, dispatch_id="fake-bridge-01", behavior="success") -> Path:
    """Wire fake subprocess → bounded parser → atomic sanitized receipt, and nothing else."""
    receipt = run_hermetic_fake(behavior=behavior)
    return write_terminal_receipt(
        receipt, audit_dir=audit_dir, dispatch_id=dispatch_id
    )
