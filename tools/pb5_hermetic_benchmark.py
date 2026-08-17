#!/usr/bin/env python3
"""Small cost probe for PB-5 mechanisms; synthetic and local only."""
import json
from pathlib import Path
import statistics
import tempfile
import time

try:
    from tools import codex_jsonl_gate, heartbeat_sandbox
except ImportError:
    import codex_jsonl_gate
    import heartbeat_sandbox


def _ms(call, n):
    values = []
    for _ in range(n):
        started = time.perf_counter_ns()
        call()
        values.append((time.perf_counter_ns() - started) / 1_000_000)
    return {"runs": n, "median_ms": round(statistics.median(values), 3),
            "max_ms": round(max(values), 3)}


def main():
    owner = "edge-codex-heartbeat"
    directory = {"owner": owner, "group": owner, "mode": "0700"}
    auth = {"owner": owner, "group": owner, "mode": "0600"}

    def policy():
        return heartbeat_sandbox.build_persistent_bridge_policy(
            {"sources": []}, edge_home="/home/operator/edge-install",
            runtime_output_root="/var/lib/edge-codex-heartbeat/runtime-output",
            codex_home="/var/lib/edge-codex-heartbeat/codex-home",
            service_identity=owner, runtime_metadata=directory,
            codex_home_metadata=directory, auth_file_metadata=auth,
            operator_home=Path("/home/operator"), require_sources_exist=False,
        )

    policy_result = policy()
    with tempfile.TemporaryDirectory() as tmp:
        audit = Path(tmp) / "audit"
        audit.mkdir(mode=0o700)
        receipt = codex_jsonl_gate.run_hermetic_fake()
        result = {
            "schema": "edge.pb5-hermetic-cost/v1",
            "policy_validation": _ms(policy, 500),
            "fake_process_start_parse_cleanup": _ms(codex_jsonl_gate.run_hermetic_fake, 10),
            "atomic_terminal_receipt": _ms(
                lambda: codex_jsonl_gate.write_terminal_receipt(
                    receipt, audit_dir=audit, dispatch_id="benchmark-fixed"
                ),
                50,
            ),
            "network_used": False,
            "llm_invoked": False,
            "real_auth_read": False,
        }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
