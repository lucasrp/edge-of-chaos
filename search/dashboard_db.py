"""Dashboard DB operations: signals and chat."""
from db import ensure_db


def set_signal(doc_path: str, signal: str, value: str | None, conn=None):
    """Set or update a signal for a document. If value is None, delete the signal."""
    own = conn is None
    if own: conn = ensure_db()
    try:
        if value is None:
            conn.execute("DELETE FROM signals WHERE doc_path=? AND signal=?", (doc_path, signal))
        else:
            conn.execute(
                "INSERT OR REPLACE INTO signals(doc_path, signal, value, updated_at) VALUES(?, ?, ?, datetime('now'))",
                (doc_path, signal, value))
        conn.commit()
    finally:
        if own: conn.close()


def get_signals(signal: str | None = None, value: str | None = None, conn=None) -> list[dict]:
    """Get signals, optionally filtered by signal name and/or value."""
    own = conn is None
    if own: conn = ensure_db()
    try:
        sql = "SELECT doc_path, signal, value, updated_at FROM signals WHERE 1=1"
        params = []
        if signal:
            sql += " AND signal=?"
            params.append(signal)
        if value:
            sql += " AND value=?"
            params.append(value)
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        if own: conn.close()


def add_chat(author: str, text: str, conn=None) -> int:
    """Add a chat message. Returns the message id."""
    own = conn is None
    if own: conn = ensure_db()
    try:
        cur = conn.execute(
            "INSERT INTO chat(author, text, ts) VALUES(?, ?, datetime('now'))",
            (author, text))
        conn.commit()
        return cur.lastrowid
    finally:
        if own: conn.close()


def get_chats(unprocessed_only: bool = False, pinned_only: bool = False,
              limit: int = 100, conn=None) -> list[dict]:
    """Get chat messages, optionally filtered by processed/pinned status."""
    own = conn is None
    if own: conn = ensure_db()
    try:
        sql = "SELECT id, author, text, ts, processed, pinned FROM chat"
        clauses = []
        if unprocessed_only:
            clauses.append("processed=0")
        if pinned_only:
            clauses.append("pinned=1")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY ts ASC, id ASC LIMIT ?"
        return [dict(r) for r in conn.execute(sql, (limit,)).fetchall()]
    finally:
        if own: conn.close()


def mark_chat_processed(chat_id: int, conn=None):
    """Mark a chat message as processed."""
    own = conn is None
    if own: conn = ensure_db()
    try:
        conn.execute("UPDATE chat SET processed=1 WHERE id=?", (chat_id,))
        conn.commit()
    finally:
        if own: conn.close()


def pin_chat(chat_id: int, conn=None):
    """Pin a chat message. Pinned messages persist as direction to the agent."""
    own = conn is None
    if own: conn = ensure_db()
    try:
        conn.execute("UPDATE chat SET pinned=1 WHERE id=?", (chat_id,))
        conn.commit()
    finally:
        if own: conn.close()


def unpin_chat(chat_id: int, conn=None):
    """Unpin a chat message."""
    own = conn is None
    if own: conn = ensure_db()
    try:
        conn.execute("UPDATE chat SET pinned=0 WHERE id=?", (chat_id,))
        conn.commit()
    finally:
        if own: conn.close()
