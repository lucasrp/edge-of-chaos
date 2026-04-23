#!/usr/bin/env python3
"""rollup-render-install-drift — compare rendered intent with installed state.

Reads canonical shadow facts from `state/events/log.jsonl` and writes
`state/render-install-drift.json`.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "config"))
from paths import RENDER_INSTALL_DRIFT_FILE, STATE_EVENTS_FILE  # noqa: E402


def _iter_jsonl(path: Path):
    if not path.exists():
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _parse_ts(value: str | None) -> str:
    return value or ""


def _latest_by_key(existing: dict, key: str, event: dict) -> None:
    if not key:
        return
    current = existing.get(key)
    if current is None or _parse_ts(event.get("ts")) >= _parse_ts(current.get("ts")):
        existing[key] = event


def build_projection(limit: int = 20) -> dict:
    render_by_output: dict[str, dict] = {}
    install_by_artifact: dict[str, dict] = {}
    removed_by_artifact: dict[str, dict] = {}
    checks_by_id: dict[str, dict] = {}

    for event in _iter_jsonl(STATE_EVENTS_FILE) or []:
        etype = event.get("type")
        payload = event.get("payload") or {}
        if etype == "RenderProduced":
            output_path = str(payload.get("output_path") or event.get("artifact") or "")
            _latest_by_key(render_by_output, output_path, event)
        elif etype == "InstallApplied":
            artifact = str(event.get("artifact") or "")
            _latest_by_key(install_by_artifact, artifact, event)
        elif etype == "InstallRemoved":
            artifact = str(event.get("artifact") or "")
            _latest_by_key(removed_by_artifact, artifact, event)
        elif etype == "InstallCheckObserved":
            check_id = str(payload.get("check_id") or "")
            _latest_by_key(checks_by_id, check_id, event)

    active_installs: dict[str, dict] = {}
    for artifact, install_event in install_by_artifact.items():
        removed_event = removed_by_artifact.get(artifact)
        if removed_event and _parse_ts(removed_event.get("ts")) >= _parse_ts(install_event.get("ts")):
            continue
        active_installs[artifact] = install_event

    installs_by_source: dict[str, list[dict]] = {}
    for event in active_installs.values():
        source_template = str((event.get("payload") or {}).get("source_template") or "")
        installs_by_source.setdefault(source_template, []).append(event)

    rendered_without_install = []
    hash_mismatches = []
    linked_installs = 0
    for output_path, render_event in render_by_output.items():
        installs = installs_by_source.get(output_path, [])
        if not installs:
            rendered_without_install.append(
                {
                    "output_path": output_path,
                    "artifact": render_event.get("artifact"),
                    "source_template": (render_event.get("payload") or {}).get("source_template"),
                }
            )
            continue
        linked_installs += len(installs)
        render_hash = (render_event.get("payload") or {}).get("hash")
        for install_event in installs:
            install_hash = (install_event.get("payload") or {}).get("hash")
            if render_hash and install_hash and render_hash != install_hash:
                hash_mismatches.append(
                    {
                        "output_path": output_path,
                        "render_hash": render_hash,
                        "install_hash": install_hash,
                        "artifact": install_event.get("artifact"),
                    }
                )

    install_without_render = []
    missing_on_disk = []
    for artifact, install_event in active_installs.items():
        payload = install_event.get("payload") or {}
        source_template = str(payload.get("source_template") or "")
        if source_template and source_template not in render_by_output and not source_template.startswith(("generated:", "command:")):
            install_without_render.append(
                {
                    "artifact": artifact,
                    "source_template": source_template,
                    "kind": payload.get("kind"),
                    "action": payload.get("action"),
                }
            )
        if artifact and not Path(artifact).exists():
            missing_on_disk.append(
                {
                    "artifact": artifact,
                    "source_template": source_template,
                    "kind": payload.get("kind"),
                }
            )

    doctor_failures = []
    doctor_warnings = []
    for event in checks_by_id.values():
        payload = event.get("payload") or {}
        entry = {
            "check_id": payload.get("check_id"),
            "status": payload.get("status"),
            "detail": payload.get("detail"),
            "artifact": event.get("artifact"),
        }
        if payload.get("status") == "fail":
            doctor_failures.append(entry)
        elif payload.get("status") == "warn":
            doctor_warnings.append(entry)

    projection = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_path": str(RENDER_INSTALL_DRIFT_FILE),
        "state_events_path": str(STATE_EVENTS_FILE),
        "summary": {
            "rendered_outputs": len(render_by_output),
            "installed_artifacts": len(active_installs),
            "render_linked_installs": linked_installs,
            "rendered_without_install": len(rendered_without_install),
            "install_without_render": len(install_without_render),
            "hash_mismatches": len(hash_mismatches),
            "missing_on_disk": len(missing_on_disk),
            "doctor_warn": len(doctor_warnings),
            "doctor_fail": len(doctor_failures),
        },
        "rendered_without_install": rendered_without_install[:limit],
        "install_without_render": install_without_render[:limit],
        "hash_mismatches": hash_mismatches[:limit],
        "missing_on_disk": missing_on_disk[:limit],
        "doctor_failures": doctor_failures[:limit],
        "doctor_warnings": doctor_warnings[:limit],
    }
    return projection


def main() -> int:
    json_only = "--json" in sys.argv[1:]
    limit = 20
    if "--limit" in sys.argv[1:]:
        idx = sys.argv.index("--limit")
        try:
            limit = max(1, int(sys.argv[idx + 1]))
        except (IndexError, ValueError):
            print("invalid --limit", file=sys.stderr)
            return 2

    payload = build_projection(limit=limit)
    RENDER_INSTALL_DRIFT_FILE.parent.mkdir(parents=True, exist_ok=True)
    RENDER_INSTALL_DRIFT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if json_only:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        summary = payload["summary"]
        print(
            "OK: "
            f"{RENDER_INSTALL_DRIFT_FILE} "
            f"(rendered={summary['rendered_outputs']} "
            f"installed={summary['installed_artifacts']} "
            f"missing={summary['rendered_without_install']} "
            f"mismatch={summary['hash_mismatches']} "
            f"doctor_fail={summary['doctor_fail']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
