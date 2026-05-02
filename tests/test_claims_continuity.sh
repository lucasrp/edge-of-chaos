#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-open-gaps-continuity-XXXXXX)"
TMP_STATE="$TMP_BASE/state-root"

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p \
    "$TMP_STATE/blog/entries" \
    "$TMP_STATE/threads" \
    "$TMP_STATE/reports" \
    "$TMP_STATE/state/events" \
    "$TMP_STATE/state/projections/continuity-deltas" \
    "$TMP_STATE/state/audits" \
    "$TMP_STATE/logs" \
    "$TMP_STATE/scratchpads"

cat >"$TMP_STATE/blog/entries/2026-04-21-threaded.md" <<'MD'
---
title: "Threaded continuity note"
date: "2026-04-21"
threads:
  - alpha-thread
open_gaps:
  - "The critical case still lacks a closure argument"
report: alpha.html
---
This artifact advances alpha-thread and records one explicit unresolved gap.
MD

cat >"$TMP_STATE/blog/entries/2026-04-20-orphan-a.md" <<'MD'
---
title: "Orphan continuity A"
date: "2026-04-20"
open_gaps:
  - "Judge calibration drift still appears in multi-turn runs"
---
This artifact mentions judge calibration drift but does not anchor it to a thread.
MD

cat >"$TMP_STATE/blog/entries/2026-04-21-orphan-b.md" <<'MD'
---
title: "Orphan continuity B"
date: "2026-04-21"
open_gaps:
  - "Judge calibration drift still appears in multi-turn runs"
---
Second artifact with the same orphan continuity pressure.
MD

cat >"$TMP_STATE/threads/alpha-thread.md" <<'MD'
---
id: alpha-thread
title: "Alpha Thread"
status: active
owner: ed
created: 2026-04-20
updated: 2026-04-20
---
## Next
Close the critical case.
MD

cat >"$TMP_STATE/reports/alpha.html" <<'HTML'
<html><body>alpha report</body></html>
HTML

cat >"$TMP_STATE/state/current-dispatch.json" <<'JSON'
{
  "cycle_id": "cycle-test-continuity",
  "request": {
    "trigger": "operator",
    "skill": "research",
    "primary_thread_id": "alpha-thread",
    "args": {
      "thread_id": "alpha-thread"
    }
  },
  "state": {
    "active": true
  }
}
JSON

export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_STATE"
export EDGE_CYCLE_ID="cycle-test-continuity"

python3 - <<'PY'
import os
import sys
from pathlib import Path

edge_dir = os.environ["EDGE_REPO_DIR"]
sys.path.insert(0, os.path.join(edge_dir, "tools"))
from _shared.continuity import process_publication_continuity

entry = Path(os.environ["EDGE_STATE_DIR"]) / "blog" / "entries" / "2026-04-21-threaded.md"
result = process_publication_continuity(entry, primary_thread_id="alpha-thread", cycle_id=os.environ["EDGE_CYCLE_ID"])
assert result["delta"]["primary_thread"] == "alpha-thread"
assert result["facts"]["open_gaps_count"] == 1
PY

python3 - <<'PY' "$TMP_STATE"
import json
import sys
from pathlib import Path

state_root = Path(sys.argv[1])
digest = json.loads((state_root / "state" / "projections" / "open-gaps-digest.json").read_text())

assert digest["open_total"] == 3, digest
assert digest["entries_with_gaps"] == 3, digest
assert digest["hot_threads_by_open_gaps"][0]["thread_id"] == "alpha-thread", digest

delta = json.loads((state_root / "state" / "projections" / "continuity-deltas" / "2026-04-21-threaded.json").read_text())
assert delta["primary_thread"] == "alpha-thread", delta
assert delta["open_gaps_total"] == 1, delta
assert "alpha-thread" in delta["summary"], delta

events = [json.loads(line) for line in (state_root / "state" / "events" / "log.jsonl").read_text().splitlines() if line.strip()]
types = {item["type"] for item in events}
for expected in {"ArtifactPublished", "ThreadTouched", "OpenGapObserved"}:
    assert expected in types, types
print("ok")
PY
