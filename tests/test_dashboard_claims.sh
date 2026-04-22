#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="${EDGE_BLOG_VENV:-$EDGE_DIR/blog/.venv/bin/python3}"
if [ ! -x "$VENV_PY" ]; then
    echo "Missing blog venv python: $VENV_PY" >&2
    echo "Set EDGE_BLOG_VENV=/path/to/blog/.venv/bin/python3 when running from a clean worktree." >&2
    exit 2
fi

TMP_BASE="$(mktemp -d /tmp/edge-dashboard-claims-XXXXXX)"
TMP_STATE="$TMP_BASE/state-root"

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p \
    "$TMP_STATE/blog/entries" \
    "$TMP_STATE/threads" \
    "$TMP_STATE/reports" \
    "$TMP_STATE/logs" \
    "$TMP_STATE/state/signals" \
    "$TMP_STATE/state/events" \
    "$TMP_STATE/search"

cat >"$TMP_STATE/blog/entries/2026-04-20-claim-gap.md" <<'MD'
---
title: "Queue close audit"
date: "2026-04-20"
claims:
  - "!Queue close evidence is still missing"
---
body
MD

cat >"$TMP_STATE/blog/entries/2026-04-20-claim-verified-a.md" <<'MD'
---
title: "Operator visibility note"
date: "2026-04-20"
claims:
  - "Operator notes should land in visible tasks"
threads:
  - ops-visibility
report: ops-visible.html
---
body
MD

cat >"$TMP_STATE/blog/entries/2026-04-21-claim-verified-b.md" <<'MD'
---
title: "Follow-up on visible tasks"
date: "2026-04-21"
claims:
  - "Operator notes should land in visible tasks"
threads:
  - ops-visibility
---
body
MD

cat >"$TMP_STATE/threads/ops-visibility.md" <<'MD'
---
id: ops-visibility
title: "Ops visibility"
status: active
owner: ed
goal: "Make queued operator work visible"
---
## Next
Review the next dispatch output.
MD

cat >"$TMP_STATE/reports/ops-visible.html" <<'HTML'
<html><body>report</body></html>
HTML

EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP_STATE" "$VENV_PY" - <<'PY'
import os
import sys

edge_dir = os.environ["EDGE_REPO_DIR"]
sys.path.insert(0, edge_dir)
sys.path.insert(0, os.path.join(edge_dir, "blog"))
os.chdir(os.path.join(edge_dir, "blog"))

from app import app

client = app.test_client()

resp = client.get("/api/dashboard/epistemics")
assert resp.status_code == 200, resp.status_code
data = resp.get_json()

claims = data["ep_claims"]
assert claims["verified_total"] == 1
assert claims["open_total"] == 1
assert claims["attention_count"] == 1
assert claims["unthreaded_count"] == 1
assert claims["no_report_count"] == 1
assert claims["verified_recent"][0]["support_count"] == 2

attention_claim = claims["attention"][0]
assert attention_claim["text"] == "Queue close evidence is still missing"
assert attention_claim["no_thread"] is True
assert attention_claim["no_report"] is True

detail = client.get(f"/claim/{attention_claim['claim_id']}")
assert detail.status_code == 200, detail.status_code
detail_html = detail.get_data(as_text=True)
assert "Current Judgment" in detail_html
assert "Evidence Timeline" in detail_html
assert "Why this is here" in detail_html
assert "Queue close audit" in detail_html

steer = client.post(
    f"/api/steering/claim/{attention_claim['claim_id']}/action",
    json={
        "action": "disputed",
        "reason": "close evidence still has a blind spot",
        "label": attention_claim["text"],
        "reference": attention_claim["reference"],
    },
)
assert steer.status_code == 200, steer.status_code

partial = client.get("/partials/epistemics")
assert partial.status_code == 200, partial.status_code
text = partial.get_data(as_text=True)
assert "claims workbench" in text
assert "needs attention" in text
assert "supported and linked" in text
assert "Operator notes should land in visible tasks" in text
assert "Queued for next dispatch: Mark contested" in text
assert "Turn into proposal" in text
assert "Needs fresh evidence" in text
print("ok")
PY
