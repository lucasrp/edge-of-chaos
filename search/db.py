"""Database schema and connection for agent memory search."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "memory.db"
EMBEDDING_DIM = 1536  # text-embedding-3-small

# Try to load sqlite_vec; degrade gracefully if unavailable
_HAS_SQLITE_VEC = False
try:
    import sqlite_vec
    _HAS_SQLITE_VEC = True
except ImportError:
    pass


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    if _HAS_SQLITE_VEC:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def has_vec() -> bool:
    """Return True if sqlite_vec is available."""
    return _HAS_SQLITE_VEC


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE NOT NULL,
            type TEXT NOT NULL,
            title TEXT,
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            metadata TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(type);
        CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(content_hash);
    """)

    # FTS5 — external content table synced via triggers
    conn.executescript("""
        CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
            title, content,
            content=documents,
            content_rowid=id,
            tokenize='porter unicode61 remove_diacritics 2'
        );

        CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
            INSERT INTO documents_fts(rowid, title, content)
            VALUES (new.id, new.title, new.content);
        END;

        CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
            INSERT INTO documents_fts(documents_fts, rowid, title, content)
            VALUES('delete', old.id, old.title, old.content);
        END;

        CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
            INSERT INTO documents_fts(documents_fts, rowid, title, content)
            VALUES('delete', old.id, old.title, old.content);
            INSERT INTO documents_fts(rowid, title, content)
            VALUES (new.id, new.title, new.content);
        END;
    """)

    # Vec0 for embeddings (only if sqlite_vec is available)
    if _HAS_SQLITE_VEC:
        conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_vec USING vec0(
                document_id INTEGER PRIMARY KEY,
                embedding float[{EMBEDDING_DIM}]
            )
        """)

    # Search telemetry
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS search_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_norm TEXT NOT NULL,
            doc_id INTEGER,
            rank INTEGER,
            score REAL,
            ts TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_search_events_doc_id ON search_events(doc_id);
        CREATE INDEX IF NOT EXISTS idx_search_events_ts ON search_events(ts);
    """)

    # Dashboard: signals and chat
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            doc_path TEXT NOT NULL,
            signal TEXT NOT NULL,
            value TEXT,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(doc_path, signal)
        );
        CREATE INDEX IF NOT EXISTS idx_signals_lookup ON signals(signal, value);

        CREATE TABLE IF NOT EXISTS chat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL,
            text TEXT NOT NULL,
            ts TEXT NOT NULL DEFAULT (datetime('now')),
            processed INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_chat_processed ON chat(processed);
    """)

    conn.commit()


def ensure_db() -> sqlite3.Connection:
    conn = get_connection()
    init_db(conn)
    return conn
