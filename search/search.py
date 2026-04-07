"""Search edge-memory database: FTS5, vector, or hybrid."""

import json
import re
import struct
import sys
from pathlib import Path

import yaml

from db import EMBEDDING_DIM, ensure_db
from embed import embed_text

EDGE_HOME = Path.home() / "edge"
NOTES_DIR = EDGE_HOME / "notes"


def _parse_frontmatter_note(filepath: Path) -> str | None:
    """Extract the 'note' field from YAML frontmatter. Returns None on any failure."""
    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
        if not text.startswith("---"):
            return None
        end = text.index("---", 3)
        fm = yaml.safe_load(text[3:end])
        if isinstance(fm, dict):
            return fm.get("note")
    except Exception:
        return None
    return None


def _enrich_with_notes(results: list[dict]) -> list[dict]:
    """Enrich blog results with linked note content when available.

    For each result where type == "blog", reads the entry file, parses its
    frontmatter for a ``note:`` field, and if present reads the note file
    from ~/edge/notes/{note_filename}.  Adds ``note_path`` (str) and
    ``note_content`` (first 2000 chars) to the result dict.

    Fault-tolerant: any failure is silently skipped.
    """
    for result in results:
        if result.get("type") != "blog":
            continue
        try:
            entry_path = EDGE_HOME / result["path"]
            note_filename = _parse_frontmatter_note(entry_path)
            if not note_filename:
                continue
            note_path = NOTES_DIR / note_filename
            if not note_path.is_file():
                continue
            note_text = note_path.read_text(encoding="utf-8", errors="replace")
            result["note_path"] = str(note_path)
            result["note_content"] = note_text[:2000]
        except Exception:
            continue
    return results


def _serialize_f32(vec: list[float]) -> bytes:
    """Serialize float list to bytes for vec0 query."""
    return struct.pack(f"{len(vec)}f", *vec)


def fts_search(
    query: str,
    limit: int = 10,
    doc_type: str | None = None,
    conn=None,
) -> list[dict]:
    """Full-text search using FTS5 BM25 ranking."""
    own_conn = conn is None
    if own_conn:
        conn = ensure_db()

    try:
        # Escape FTS5 special chars
        safe_query = query.replace('"', '""')
        # Use simple query — each word is OR'd
        terms = safe_query.split()
        fts_query = " OR ".join(f'"{t}"' for t in terms if t)

        if not fts_query:
            return []

        sql = """
            SELECT d.id, d.path, d.type, d.title,
                   rank AS score,
                   snippet(documents_fts, 1, '>>>', '<<<', '...', 30) AS snippet
            FROM documents_fts
            JOIN documents d ON d.id = documents_fts.rowid
            WHERE documents_fts MATCH ?
        """
        params = [fts_query]

        if doc_type:
            sql += " AND d.type = ?"
            params.append(doc_type)

        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own_conn:
            conn.close()


def vec_search(
    query_embedding: list[float],
    limit: int = 10,
    doc_type: str | None = None,
    conn=None,
) -> list[dict]:
    """Vector similarity search using sqlite-vec."""
    own_conn = conn is None
    if own_conn:
        conn = ensure_db()

    try:
        query_bytes = _serialize_f32(query_embedding)

        if doc_type:
            sql = """
                SELECT v.document_id, v.distance,
                       d.path, d.type, d.title
                FROM documents_vec v
                JOIN documents d ON d.id = v.document_id
                WHERE v.embedding MATCH ?
                  AND k = ?
                  AND d.type = ?
                ORDER BY v.distance
            """
            rows = conn.execute(sql, (query_bytes, limit * 2, doc_type)).fetchall()
        else:
            sql = """
                SELECT v.document_id, v.distance,
                       d.path, d.type, d.title
                FROM documents_vec v
                JOIN documents d ON d.id = v.document_id
                WHERE v.embedding MATCH ?
                  AND k = ?
                ORDER BY v.distance
            """
            rows = conn.execute(sql, (query_bytes, limit * 2)).fetchall()

        results = []
        for r in rows[:limit]:
            results.append({
                "id": r["document_id"],
                "path": r["path"],
                "type": r["type"],
                "title": r["title"],
                "score": 1 - r["distance"],  # Convert distance to similarity
                "snippet": None,
            })
        return results
    finally:
        if own_conn:
            conn.close()


def hybrid_search(
    query: str,
    limit: int = 10,
    fts_weight: float = 0.3,
    vec_weight: float = 0.7,
    doc_type: str | None = None,
    conn=None,
    _query_embedding: list[float] | None = None,
) -> list[dict]:
    """Hybrid search combining FTS5 + vector via Reciprocal Rank Fusion."""
    own_conn = conn is None
    if own_conn:
        conn = ensure_db()

    try:
        k = 60  # RRF constant

        # FTS5 results
        fts_results = fts_search(query, limit=limit * 3, doc_type=doc_type, conn=conn)

        # Vector results (reuse embedding if provided)
        try:
            query_embedding = _query_embedding or embed_text(query)
            vec_results = vec_search(
                query_embedding, limit=limit * 3, doc_type=doc_type, conn=conn
            )
        except Exception:
            # If embedding fails, fall back to FTS-only
            query_embedding = None
            vec_results = []

        # RRF merge
        scores = {}
        doc_info = {}

        for rank, doc in enumerate(fts_results):
            doc_id = doc["id"]
            scores[doc_id] = scores.get(doc_id, 0) + fts_weight * (1 / (k + rank))
            doc_info[doc_id] = doc

        for rank, doc in enumerate(vec_results):
            doc_id = doc["id"]
            scores[doc_id] = scores.get(doc_id, 0) + vec_weight * (1 / (k + rank))
            if doc_id not in doc_info:
                doc_info[doc_id] = doc

        # Sort by RRF score
        ranked = sorted(scores.items(), key=lambda x: -x[1])[:limit]

        results = []
        for doc_id, score in ranked:
            info = doc_info[doc_id]
            results.append({
                "id": doc_id,
                "path": info["path"],
                "type": info["type"],
                "title": info["title"],
                "score": round(score, 6),
                "snippet": info.get("snippet"),
            })

        _enrich_with_notes(results)
        return results
    finally:
        if own_conn:
            conn.close()


def search_with_sidecar(
    query: str,
    limit: int = 10,
    doc_type: str | None = None,
    wf_limit: int = 3,
    min_wf_score: float = -0.15,
    conn=None,
) -> tuple[list[dict], list[dict]]:
    """Hybrid search + automatic workflow sidecar.

    Returns (results, workflows). The workflow lookup reuses the same
    embedding — zero extra API cost, ~1ms extra latency.
    """
    own_conn = conn is None
    if own_conn:
        conn = ensure_db()

    try:
        # Compute embedding once
        try:
            query_embedding = embed_text(query)
        except Exception:
            query_embedding = None

        # Main search
        results = hybrid_search(
            query, limit=limit, doc_type=doc_type,
            _query_embedding=query_embedding, conn=conn,
        )

        # Workflow sidecar (skip if already filtering by workflow)
        workflows = []
        if doc_type != "workflow" and query_embedding is not None:
            # IDs already in main results (avoids duplicates)
            main_ids = {r["id"] for r in results}
            wf_raw = vec_search(
                query_embedding, limit=wf_limit + len(main_ids),
                doc_type="workflow", conn=conn,
            )
            workflows = [
                r for r in wf_raw
                if r["score"] > min_wf_score and r["id"] not in main_ids
            ][:wf_limit]

        _enrich_with_notes(results)
        return results, workflows
    finally:
        if own_conn:
            conn.close()


def log_search_telemetry(query: str, results: list[dict], conn=None) -> None:
    """Log search results to search_events table for telemetry."""
    own_conn = conn is None
    if own_conn:
        conn = ensure_db()
    try:
        # Normalize query: lowercase, collapse whitespace
        query_norm = re.sub(r"\s+", " ", query.lower()).strip()
        for rank, r in enumerate(results, 1):
            doc_id = r.get("id")
            score = r.get("score", 0)
            conn.execute(
                "INSERT INTO search_events (query_norm, doc_id, rank, score) VALUES (?, ?, ?, ?)",
                (query_norm, doc_id, rank, score),
            )
        conn.commit()
    except Exception:
        # Telemetry is non-blocking — never break search
        pass
    finally:
        if own_conn:
            conn.close()


def doc_stats(conn=None) -> list[dict]:
    """Per-document retrieval stats from search_events."""
    own_conn = conn is None
    if own_conn:
        conn = ensure_db()
    try:
        rows = conn.execute("""
            SELECT doc_id,
                   COUNT(*) as retrieved_count,
                   SUM(CASE WHEN rank<=3 THEN 1 ELSE 0 END) as top3_count,
                   MAX(ts) as last_retrieved,
                   COUNT(DISTINCT query_norm) as query_diversity
            FROM search_events
            GROUP BY doc_id
            ORDER BY retrieved_count DESC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own_conn:
            conn.close()


def _read_workflow_body(path: str) -> str | None:
    """Read a workflow entry and extract the body (after frontmatter)."""
    try:
        filepath = EDGE_HOME / path
        if not filepath.is_file():
            return None
        text = filepath.read_text(encoding="utf-8", errors="replace")
        if text.startswith("---"):
            end = text.index("---", 3)
            body = text[end + 3:].strip()
        else:
            body = text.strip()
        # Cap at 2000 chars to avoid flooding terminal
        if len(body) > 2000:
            body = body[:2000] + "\n[...truncated]"
        return body
    except Exception:
        return None


def format_results(
    results: list[dict],
    mode: str = "hybrid",
    workflows: list[dict] | None = None,
) -> str:
    """Format search results for terminal output.

    Workflow sidecar results are expanded inline — the full body of the
    workflow entry is included so the agent sees procedure steps without
    needing a separate read. This is the mechanism that closes the
    workflow-adoption gap: any search that finds a relevant workflow
    surfaces the procedure in context automatically.
    """
    if not results and not workflows:
        return "No results found."

    lines = []

    # Collect all workflows to expand (from main results + sidecar)
    wf_expanded_ids = set()
    all_workflows_to_expand = list(workflows or [])

    if results:
        # Separate workflows from non-workflows in main results
        regular = [r for r in results if r.get("type") != "workflow"]
        main_workflows = [r for r in results if r.get("type") == "workflow"]
        all_workflows_to_expand = main_workflows + all_workflows_to_expand

        if regular:
            lines.append(f"Results ({mode}, {len(regular)} matches):\n")
            for i, r in enumerate(regular, 1):
                path = Path(r["path"])
                name = path.name
                score = r.get("score", 0)
                doc_type = r.get("type", "?")
                title = r.get("title", "")

                lines.append(f"  #{i:<3} {score:>8.4f}  {doc_type:<8} {name}")
                if title and title != path.stem:
                    lines.append(f"       {' ' * 8}  {' ' * 8} {title[:80]}")
                if r.get("snippet"):
                    snippet = r["snippet"].replace("\n", " ")[:120]
                    lines.append(f"       {' ' * 8}  {' ' * 8} ...{snippet}...")
                lines.append("")

    # Expand all workflows (from main results and sidecar) with full body
    if all_workflows_to_expand:
        sep = "\u2501" * 45
        for r in all_workflows_to_expand:
            wf_id = r.get("id")
            if wf_id in wf_expanded_ids:
                continue
            wf_expanded_ids.add(wf_id)

            title = r.get("title", "")
            score = r.get("score", 0)
            body = _read_workflow_body(r["path"])

            lines.append(f"\u2501\u2501 WORKFLOW FOUND {sep}")
            lines.append(f"{title}  (score: {score:.4f})")
            lines.append("")
            if body:
                lines.append(body)
            else:
                lines.append(f"  [could not read: {r['path']}]")
            lines.append(sep + "\u2501\u2501")
            lines.append("")

    return "\n".join(lines)


def stats(conn=None) -> dict:
    """Get database statistics."""
    own_conn = conn is None
    if own_conn:
        conn = ensure_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        by_type = conn.execute(
            "SELECT type, COUNT(*) as cnt FROM documents GROUP BY type ORDER BY cnt DESC"
        ).fetchall()
        with_vec = conn.execute("SELECT COUNT(*) FROM documents_vec").fetchone()[0]

        return {
            "total": total,
            "by_type": {r["type"]: r["cnt"] for r in by_type},
            "with_embeddings": with_vec,
        }
    finally:
        if own_conn:
            conn.close()


# --- CLI ---


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Search edge-memory")
    parser.add_argument("query", nargs="*", help="Search query")
    parser.add_argument("--fts", action="store_true", help="FTS5 only (no embeddings)")
    parser.add_argument(
        "--semantic", action="store_true", help="Semantic only (embeddings)"
    )
    parser.add_argument(
        "--type", dest="doc_type", help="Filter by type (note, report, blog, etc.)"
    )
    parser.add_argument("-k", type=int, default=10, help="Number of results (default: 10)")
    parser.add_argument("--stats", action="store_true", help="Show database stats")
    parser.add_argument(
        "--no-telemetry", action="store_true", help="Skip search telemetry logging"
    )
    parser.add_argument(
        "--no-sidecar", action="store_true", help="Disable automatic workflow sidecar"
    )
    parser.add_argument(
        "--doc-stats", action="store_true", help="Show per-doc retrieval stats"
    )
    args = parser.parse_args()

    if args.doc_stats:
        ds = doc_stats()
        if not ds:
            print("No search telemetry data yet.")
            return
        print(f"{'doc_id':>8} {'retrieved':>10} {'top3':>6} {'diversity':>10} last_retrieved")
        for r in ds:
            print(
                f"{r['doc_id']:>8} {r['retrieved_count']:>10} "
                f"{r['top3_count']:>6} {r['query_diversity']:>10} "
                f"{r['last_retrieved']}"
            )
        return

    if args.stats:
        s = stats()
        print(f"Total documents: {s['total']}")
        print(f"With embeddings: {s['with_embeddings']}")
        print("By type:")
        for t, c in s["by_type"].items():
            print(f"  {t}: {c}")
        return

    query = " ".join(args.query)
    if not query:
        parser.print_help()
        sys.exit(1)

    conn = ensure_db()
    workflows = []

    if args.fts:
        results = fts_search(query, limit=args.k, doc_type=args.doc_type, conn=conn)
        mode = "fts"
    elif args.semantic:
        query_embedding = embed_text(query)
        results = vec_search(
            query_embedding, limit=args.k, doc_type=args.doc_type, conn=conn
        )
        mode = "semantic"
    elif not args.no_sidecar and args.doc_type != "workflow":
        results, workflows = search_with_sidecar(
            query, limit=args.k, doc_type=args.doc_type, conn=conn
        )
        mode = "hybrid"
    else:
        results = hybrid_search(
            query, limit=args.k, doc_type=args.doc_type, conn=conn
        )
        mode = "hybrid"

    print(format_results(results, mode, workflows=workflows))

    # Log telemetry (includes workflow hits)
    all_results = results + workflows
    if not args.no_telemetry and all_results:
        log_search_telemetry(query, all_results, conn=conn)

    conn.close()


if __name__ == "__main__":
    main()
