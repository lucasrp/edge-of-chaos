#!/usr/bin/env python3
"""Audit CQRS/event-sourced enforcement migration coverage."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent


@dataclass
class Check:
    check_id: str
    status: str
    detail: str
    artifact: str

    def as_dict(self) -> dict[str, str]:
        return {
            "check_id": self.check_id,
            "status": self.status,
            "detail": self.detail,
            "artifact": self.artifact,
        }


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _check_contains(check_id: str, path: Path, needles: list[str], detail: str) -> Check:
    content = _read(path)
    missing = [needle for needle in needles if needle not in content]
    if missing:
        return Check(check_id, "fail", f"missing: {', '.join(missing)}", str(path.relative_to(REPO_ROOT)))
    return Check(check_id, "ok", detail, str(path.relative_to(REPO_ROOT)))


def _run_projection() -> Check:
    tool = SCRIPT_DIR / "rollup-pipeline-state.py"
    result = subprocess.run(
        [sys.executable, str(tool), "--json", "--no-write"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode != 0:
        return Check("projection:pipeline-state-replay", "fail", result.stderr.strip() or result.stdout.strip(), str(tool.relative_to(REPO_ROOT)))
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        return Check("projection:pipeline-state-replay", "fail", f"invalid JSON: {exc}", str(tool.relative_to(REPO_ROOT)))
    summary = payload.get("summary") or {}
    counts = summary.get("counts_by_status") or {}
    detail = (
        f"artifacts={summary.get('artifacts_total', 0)} "
        f"attention={summary.get('artifacts_attention', 0)} "
        f"complete={counts.get('complete', 0)} "
        f"blocked={counts.get('blocked', 0)} "
        f"failed={counts.get('failed', 0)} "
        f"orphaned_publish={counts.get('orphaned_publish', 0)}"
    )
    if counts.get("blocked", 0) or counts.get("failed", 0):
        return Check("projection:pipeline-state-replay", "fail", detail, str(tool.relative_to(REPO_ROOT)))
    if summary.get("artifacts_attention", 0):
        return Check("projection:pipeline-state-replay", "warn", detail, str(tool.relative_to(REPO_ROOT)))
    return Check("projection:pipeline-state-replay", "ok", detail, str(tool.relative_to(REPO_ROOT)))


def _run_operator_pressure_projection() -> Check:
    tool = SCRIPT_DIR / "rollup-operator-pressure.py"
    env = dict(os.environ)
    env["EDGE_OPERATOR_PRESSURE_DISABLE_LLM"] = "1"
    result = subprocess.run(
        [sys.executable, str(tool), "--json", "--no-write"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode != 0:
        return Check("projection:operator-pressure", "fail", result.stderr.strip() or result.stdout.strip(), str(tool.relative_to(REPO_ROOT)))
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        return Check("projection:operator-pressure", "fail", f"invalid JSON: {exc}", str(tool.relative_to(REPO_ROOT)))
    summary = payload.get("summary") or {}
    detail = (
        f"status={payload.get('status')} "
        f"items={summary.get('item_total', 0)} "
        f"sessions={summary.get('session_total', 0)} "
        f"messages={summary.get('message_total', 0)} "
        f"render={summary.get('render_mode', '')}"
    )
    if payload.get("status") != "ok":
        return Check("projection:operator-pressure", "fail", detail, str(tool.relative_to(REPO_ROOT)))
    return Check("projection:operator-pressure", "ok", detail, str(tool.relative_to(REPO_ROOT)))


def _fleet_canonical_check() -> Check:
    path = REPO_ROOT / "observability" / "fleet"
    if path.exists():
        return Check("repo:fleet-grafana-absent", "fail", "canonical repo still contains observability/fleet", str(path.relative_to(REPO_ROOT)))
    return Check("repo:fleet-grafana-absent", "ok", "Grafana fleet overlay is absent from canonical repo", "observability/fleet")


def _legacy_residuals() -> list[dict[str, str]]:
    patterns = {
        "write-guard": "legacy hook remains as edge-cmd shim",
        "heartbeat-dispatch-guard": "legacy heartbeat hook remains as edge-cmd shim/fallback",
        "current-beat.json": "legacy beat sentinel remains as compatibility fallback",
        "EDGE_CONSOLIDATE_ACTIVE": "legacy env authorization remains as adapter into command boundary",
    }
    scan_paths = [
        REPO_ROOT / "bin",
        REPO_ROOT / "hooks",
        REPO_ROOT / "tools",
        REPO_ROOT / "docs",
        REPO_ROOT / "config",
    ]
    residuals: list[dict[str, str]] = []
    for root in scan_paths:
        if not root.exists():
            continue
        for file_path in root.rglob("*"):
            if not file_path.is_file() or file_path.suffix in {".pyc", ".png", ".jpg", ".db"}:
                continue
            text = _read(file_path)
            for pattern, interpretation in patterns.items():
                if pattern in text:
                    residuals.append(
                        {
                            "pattern": pattern,
                            "artifact": str(file_path.relative_to(REPO_ROOT)),
                            "interpretation": interpretation,
                        }
                    )
                    break
    return residuals


def build_audit() -> dict[str, Any]:
    checks = [
        _check_contains(
            "publisher:phase-completed",
            REPO_ROOT / "blog" / "consolidate-state.sh",
            ["PhaseCompleted", "emit_shadow_event"],
            "consolidate-state emits canonical PhaseCompleted facts",
        ),
        _check_contains(
            "command-boundary:edge-cmd",
            REPO_ROOT / "tools" / "edge-cmd",
            ["validate-write", "ArtifactWriteRejected", "ArtifactWriteAuthorized"],
            "edge-cmd validates protected writes and emits command-boundary facts",
        ),
        _check_contains(
            "hook:write-guard-shim",
            REPO_ROOT / "hooks" / "write-guard.sh",
            ["edge-cmd", "validate-write"],
            "write-guard delegates protected writes to edge-cmd",
        ),
        _check_contains(
            "hook:heartbeat-guard-shim",
            REPO_ROOT / "bin" / "heartbeat-dispatch-guard.sh",
            ["edge-cmd", "--require-dispatched-heartbeat", "--heartbeat-only"],
            "heartbeat dispatch guard delegates heartbeat invariant to edge-cmd",
        ),
        _check_contains(
            "postflight:pipeline-state",
            REPO_ROOT / "tools" / "edge-postflight",
            ["pipeline_state.refresh", "refresh_pipeline_state"],
            "postflight consults pipeline-state projection",
        ),
        _check_contains(
            "protocol:pipeline-state",
            REPO_ROOT / "tools" / "_shared" / "protocol_runtime.py",
            ["pipeline_state.refresh"],
            "runtime protocol compiler accepts pipeline-state postflight step",
        ),
        _check_contains(
            "doctor:pipeline-state",
            REPO_ROOT / "tools" / "edge-doctor",
            ["projection:pipeline-state", "check_pipeline_state"],
            "edge-doctor exposes pipeline-state projection health",
        ),
        _check_contains(
            "backfill:pipeline-phase-events",
            REPO_ROOT / "tools" / "backfill-pipeline-phase-events.py",
            ["orphaned_publish", "PhaseCompleted"],
            "legacy ArtifactPublished facts have an idempotent PhaseCompleted backfill path",
        ),
        _check_contains(
            "config:pipeline-state",
            REPO_ROOT / "config" / "postflight.yaml",
            ["pipeline_state.refresh"],
            "default postflight protocol includes pipeline-state refresh",
        ),
        _check_contains(
            "runtime:operator-pressure-projection",
            REPO_ROOT / "tools" / "_shared" / "dispatch_runtime.py",
            ["read_or_refresh_operator_pressure_projection", "projection_status"],
            "preflight consumes operator pressure through a projection refresh boundary",
        ),
        _check_contains(
            "replay:operator-pressure",
            REPO_ROOT / "tools" / "edge-replay",
            ["operator-pressure", "write_operator_pressure_projection"],
            "edge-replay exposes the operator-pressure projection",
        ),
        _run_projection(),
        _run_operator_pressure_projection(),
        _fleet_canonical_check(),
    ]
    return {
        "ok": all(check.status != "fail" for check in checks),
        "checks": [check.as_dict() for check in checks],
        "legacy_residuals": _legacy_residuals(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit CQRS/event-sourced enforcement migration coverage")
    parser.add_argument("--json", action="store_true", help="Print JSON")
    parser.add_argument("--strict-residuals", action="store_true", help="Treat legacy shim/fallback residuals as failures")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = build_audit()
    if args.strict_residuals and payload["legacy_residuals"]:
        payload["ok"] = False

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for check in payload["checks"]:
            label = "OK" if check["status"] == "ok" else "FAIL"
            print(f"{label}: {check['check_id']} — {check['detail']} ({check['artifact']})")
        if payload["legacy_residuals"]:
            print("")
            print("Legacy residuals still present as shims/fallbacks:")
            for item in payload["legacy_residuals"][:20]:
                print(f"- {item['pattern']} in {item['artifact']}: {item['interpretation']}")
            if len(payload["legacy_residuals"]) > 20:
                print(f"- ... {len(payload['legacy_residuals']) - 20} more")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
