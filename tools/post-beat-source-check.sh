#!/usr/bin/env bash
# post-beat-source-check.sh — verify source primitives were used during the beat
# Exit 0 = at least one primitive invoked → OK
# Exit 1 = no usage detected → beat incomplete

EDGE_DIR="${EDGE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
USAGE_LOG="$EDGE_DIR/state/source-usage.jsonl"
WINDOW_MIN="${1:-120}"

if [ ! -f "$USAGE_LOG" ]; then
  echo "SOURCE_CHECK FAIL — no primitives have ever been called."
  echo "Use: edge-source <primitive> [args...]"
  exit 1
fi

RESULT=$(python3 -c "
import json
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(minutes=$WINDOW_MIN)
total = 0
sources = set()
stubs = set()

with open('$USAGE_LOG') as f:
    for line in f:
        line = line.strip()
        if not line: continue
        try:
            e = json.loads(line)
            ts = datetime.fromisoformat(e['ts'].replace('Z', '+00:00'))
            if ts < cutoff: continue
            if e.get('phase') != 'end': continue
            total += 1
            sources.add(e.get('source', '?'))
            if e.get('exit_code') == 127:
                stubs.add(e.get('source', '?'))
        except: pass

stubs_str = ','.join(sorted(stubs)) if stubs else ''
sources_str = ','.join(sorted(sources)) if sources else ''
print(f'{total}|{sources_str}|{stubs_str}')
" 2>/dev/null)

TOTAL=$(echo "$RESULT" | cut -d'|' -f1)
SOURCES=$(echo "$RESULT" | cut -d'|' -f2)
STUBS=$(echo "$RESULT" | cut -d'|' -f3)

if [ "${TOTAL:-0}" -eq 0 ]; then
  echo "SOURCE_CHECK FAIL — no primitive usage in the last ${WINDOW_MIN}min."
  echo "Source operations MUST go through: edge-source <primitive>"
  exit 1
fi

echo "SOURCE_CHECK OK — ${TOTAL} calls (${SOURCES})"
if [ -n "$STUBS" ]; then
  echo "STUBS HIT (exit 127): ${STUBS} — implement before next beat"
fi
exit 0
