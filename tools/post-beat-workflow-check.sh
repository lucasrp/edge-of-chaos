#!/usr/bin/env bash
# post-beat-workflow-check.sh — verify workflow search was performed during the beat
# Exit 0 = at least one workflow search logged → OK
# Exit 1 = no workflow search detected → beat incomplete
#
# Checks edge-search telemetry (SQLite search_events) for searches that
# returned workflow-type documents within the time window.
# Usage is NOT enforced — only the search. Creates a paper trail.

EDGE_DIR="${EDGE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
SEARCH_DB="$EDGE_DIR/search/edge-memory.db"
WINDOW_MIN="${1:-120}"

if [ ! -f "$SEARCH_DB" ]; then
  echo "WORKFLOW_CHECK FAIL — search database not found."
  echo "Run: edge-search \"test\" to initialize."
  exit 1
fi

RESULT=$(python3 -c "
import sqlite3
from datetime import datetime, timedelta, timezone

db = '$SEARCH_DB'
window = int('$WINDOW_MIN')
cutoff = datetime.now(timezone.utc) - timedelta(minutes=window)
cutoff_str = cutoff.strftime('%Y-%m-%d %H:%M:%S')

conn = sqlite3.connect(db)
try:
    # Join search_events with documents to find searches that hit workflow docs
    cur = conn.execute('''
        SELECT COUNT(DISTINCT se.query_norm) as queries,
               COUNT(*) as hits
        FROM search_events se
        JOIN documents d ON se.doc_id = d.id
        WHERE se.ts >= ?
          AND d.type = 'workflow'
    ''', (cutoff_str,))
    row = cur.fetchone()
    queries = row[0] if row else 0
    hits = row[1] if row else 0
    print(f'{queries}|{hits}')
except Exception as e:
    print(f'0|0|{e}')
finally:
    conn.close()
" 2>/dev/null)

QUERIES=$(echo "$RESULT" | cut -d'|' -f1)
HITS=$(echo "$RESULT" | cut -d'|' -f2)

if [ "${QUERIES:-0}" -eq 0 ]; then
  echo "WORKFLOW_CHECK FAIL — no workflow search in the last ${WINDOW_MIN}min."
  echo "Run: edge-search \"<topic>\" --type workflow -k 3"
  exit 1
fi

echo "WORKFLOW_CHECK OK — ${QUERIES} queries returned workflow results (${HITS} hits)"
exit 0
