#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_BASE="$(mktemp -d /tmp/edge-dashboard-chat-XXXXXX)"
TMP_EDGE="$TMP_BASE/edge"

cleanup() {
    rm -rf "$TMP_BASE"
}
trap cleanup EXIT

mkdir -p "$TMP_EDGE/state" "$TMP_EDGE/logs" "$TMP_EDGE/search"

export EDGE_REPO_DIR="$EDGE_DIR"
export EDGE_STATE_DIR="$TMP_EDGE"
export EDGE_CODENAME="test-agent"

python3 - <<'PY' "$EDGE_DIR"
import sys

edge_dir = sys.argv[1]
sys.path.insert(0, edge_dir + "/search")

from dashboard_db import add_chat, get_chats, mark_chat_processed

first_id = add_chat("user", "oldest visible only if limit is wrong")
mark_chat_processed(first_id)

for index in range(120):
    chat_id = add_chat("user", f"filler {index:03d}")
    mark_chat_processed(chat_id)

latest_id = add_chat("user", "latest operator message")
latest_system_id = add_chat("system", "latest system acknowledgement")
mark_chat_processed(latest_system_id)

messages = get_chats(limit=100)
ids = [item["id"] for item in messages]

assert latest_id in ids, "latest user message must remain visible in chat history"
assert latest_system_id in ids, "latest system reply must remain visible in chat history"
assert first_id not in ids, "chat history limit must drop oldest messages first"
assert ids == sorted(ids), "selected latest messages must render chronologically"

pending = get_chats(unprocessed_only=True, limit=10)
assert [item["id"] for item in pending] == [latest_id], pending

print("ok")
PY
