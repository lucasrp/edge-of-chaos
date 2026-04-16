#!/usr/bin/env bash
# hold-artifact.sh — move an artifact into the hold queue (BLOCKED state)
#
# Part of the #206 enforcement redesign: when a mandatory pipeline step
# cannot run (missing tool, invalid key, network down), the pipeline
# separates this from FAIL (review found defects) by moving the artifact
# into `holding/<YYYY-MM-DD>/` with a reason JSON. Other artifacts in the
# same beat continue; a single notification fires per (error_class, window).
#
# Usage:
#   hold-artifact <artifact_path> \
#     --step <step_name> \
#     --error-class <transient|operator_fixable|permanent> \
#     --error-detail <text> \
#     [--notify-key <key>] \
#     [--notify-window <duration>]
#
# Example (called by consolidate-state.sh when edge-consult is blocked):
#   hold-artifact blog/entries/2026-04-16-dspy.md \
#     --step adversarial_review \
#     --error-class operator_fixable \
#     --error-detail "edge-consult exit 10 (openai_401_invalid_key)" \
#     --notify-key openai_401 \
#     --notify-window 6h
#
# State written:
#   holding/<date>/<slug>.md           copy of artifact
#   holding/<date>/<slug>.reason.json  {step, error_class, error_detail, attempts, first_held_at}
#   holding/index.json                 rollup: {count, by_reason, oldest, items}

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EDGE_DIR="$(dirname "$SCRIPT_DIR")"

ARTIFACT=""
STEP=""
ERROR_CLASS=""
ERROR_DETAIL=""
NOTIFY_KEY=""
NOTIFY_WINDOW="6h"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --step) STEP="$2"; shift 2 ;;
    --error-class) ERROR_CLASS="$2"; shift 2 ;;
    --error-detail) ERROR_DETAIL="$2"; shift 2 ;;
    --notify-key) NOTIFY_KEY="$2"; shift 2 ;;
    --notify-window) NOTIFY_WINDOW="$2"; shift 2 ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    -*) echo "unknown flag: $1" >&2; exit 2 ;;
    *)
      if [[ -z "$ARTIFACT" ]]; then
        ARTIFACT="$1"
      fi
      shift
      ;;
  esac
done

if [[ -z "$ARTIFACT" || -z "$STEP" || -z "$ERROR_CLASS" ]]; then
  echo "Usage: hold-artifact <artifact> --step <name> --error-class <class> [--error-detail <t>] [--notify-key <k>] [--notify-window <d>]" >&2
  exit 2
fi

case "$ERROR_CLASS" in
  transient|operator_fixable|permanent) ;;
  *) echo "--error-class must be one of: transient, operator_fixable, permanent" >&2; exit 2 ;;
esac

TODAY=$(date -u +%F)
HOLDING_DIR="$EDGE_DIR/holding/$TODAY"
HOLDING_INDEX="$EDGE_DIR/holding/index.json"
mkdir -p "$HOLDING_DIR"

SLUG=$(basename "$ARTIFACT")
TARGET="$HOLDING_DIR/$SLUG"
REASON="$HOLDING_DIR/${SLUG%.*}.reason.json"

# Copy artifact if present (may already be absent for pre-publication holds)
if [[ -f "$ARTIFACT" ]]; then
  cp "$ARTIFACT" "$TARGET"
fi

# Write reason JSON (merge if re-held: bump attempts, keep first_held_at)
python3 - "$REASON" "$STEP" "$ERROR_CLASS" "$ERROR_DETAIL" "$ARTIFACT" <<'PYEOF'
import json, os, sys
from datetime import datetime, timezone

path, step, error_class, error_detail, source = sys.argv[1:]
now = datetime.now(timezone.utc).isoformat()

entry = {}
if os.path.exists(path):
    try:
        entry = json.load(open(path))
    except Exception:
        entry = {}

entry['step'] = step
entry['error_class'] = error_class
entry['error_detail'] = error_detail
entry['source'] = source
entry['attempts'] = int(entry.get('attempts', 0)) + 1
entry.setdefault('first_held_at', now)
entry['last_held_at'] = now

with open(path + '.tmp', 'w') as f:
    json.dump(entry, f, indent=2, ensure_ascii=False)
os.replace(path + '.tmp', path)
PYEOF

# Rebuild holding/index.json (rollup from all reason files)
python3 - "$EDGE_DIR/holding" "$HOLDING_INDEX" <<'PYEOF'
import json, os, sys
from datetime import datetime, timezone

root, index_path = sys.argv[1], sys.argv[2]
items = []
by_reason = {}
by_class = {}
oldest = None

if os.path.isdir(root):
    for day in sorted(os.listdir(root)):
        day_dir = os.path.join(root, day)
        if not os.path.isdir(day_dir):
            continue
        for f in sorted(os.listdir(day_dir)):
            if not f.endswith('.reason.json'):
                continue
            p = os.path.join(day_dir, f)
            try:
                r = json.load(open(p))
            except Exception:
                continue
            item = {
                'date': day,
                'reason_file': p,
                'step': r.get('step'),
                'error_class': r.get('error_class'),
                'error_detail': r.get('error_detail'),
                'attempts': r.get('attempts', 1),
                'first_held_at': r.get('first_held_at'),
                'source': r.get('source'),
            }
            items.append(item)
            key = f"{r.get('step')}:{r.get('error_class')}"
            by_reason[key] = by_reason.get(key, 0) + 1
            by_class[r.get('error_class', 'unknown')] = by_class.get(r.get('error_class', 'unknown'), 0) + 1
            fh = r.get('first_held_at')
            if fh and (oldest is None or fh < oldest):
                oldest = fh

payload = {
    'updated_at': datetime.now(timezone.utc).isoformat(),
    'count': len(items),
    'by_reason': by_reason,
    'by_class': by_class,
    'oldest': oldest,
    'items': items,
}
os.makedirs(os.path.dirname(index_path), exist_ok=True)
with open(index_path + '.tmp', 'w') as f:
    json.dump(payload, f, indent=2, ensure_ascii=False)
os.replace(index_path + '.tmp', index_path)
print(f"{len(items)} item(s) in hold ({by_class})")
PYEOF

# Tiered escalation: choose notify level by oldest age
NOTIFY_LEVEL="alert"
if [[ "$ERROR_CLASS" == "permanent" ]]; then
  NOTIFY_LEVEL="alert"  # permanent: escalate immediately
fi

# Fire idempotent notification (anti-spam). Key defaults to (step, error_class)
# so N identical blackouts fold into one message per window.
NOTIFY="$SCRIPT_DIR/notify.sh"
if [[ -x "$NOTIFY" ]]; then
  KEY="${NOTIFY_KEY:-${STEP}_${ERROR_CLASS}}"
  COUNT=$(python3 -c "import json; d=json.load(open('$HOLDING_INDEX')); print(d.get('count', 0))" 2>/dev/null || echo 1)
  "$NOTIFY" "$NOTIFY_LEVEL" \
    "[BLOCKED] $STEP: $ERROR_DETAIL (${COUNT} artifact(s) in hold)" \
    --once-per "$KEY" --window "$NOTIFY_WINDOW" >/dev/null 2>&1 || true
fi

# Log to pipeline-failures.jsonl for continuity with existing telemetry
LOG="$EDGE_DIR/logs/pipeline-failures.jsonl"
mkdir -p "$(dirname "$LOG")"
python3 - "$LOG" "$STEP" "$ERROR_CLASS" "$ERROR_DETAIL" "$ARTIFACT" <<'PYEOF'
import json, sys
from datetime import datetime, timezone
path, step, cls, detail, artifact = sys.argv[1:]
entry = {
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'phase': '0.3',
    'operation': 'hold_artifact',
    'step': step,
    'error_class': cls,
    'error_detail': detail,
    'artifact': artifact,
    'state': 'BLOCKED',
}
with open(path, 'a') as f:
    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
PYEOF

echo "HELD: $ARTIFACT → $TARGET (step=$STEP class=$ERROR_CLASS)" >&2
exit 0
