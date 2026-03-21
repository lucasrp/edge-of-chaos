"""Find related posts for a blog entry using hybrid search."""

import json
import sys
from pathlib import Path

from db import ensure_db
from search import hybrid_search


def find_related(entry_path: str, limit: int = 5) -> list[dict]:
    """Find posts related to the given entry, excluding self."""
    conn = ensure_db()
    entry_path = str(Path(entry_path).resolve())

    # Get the entry's content for query
    row = conn.execute(
        "SELECT id, title, content FROM documents WHERE path = ?",
        (entry_path,),
    ).fetchone()

    if not row:
        conn.close()
        return []

    doc_id = row["id"]
    # Use title + first 500 chars as query (captures essence without noise)
    query_text = f"{row['title'] or ''} {(row['content'] or '')[:500]}"

    # Search — get extra results to account for self-match
    results = hybrid_search(query_text, limit=limit + 3, conn=conn)

    # Filter out self
    related = [r for r in results if r["id"] != doc_id][:limit]

    # Store in metadata
    existing = conn.execute(
        "SELECT metadata FROM documents WHERE id = ?", (doc_id,)
    ).fetchone()

    meta = json.loads(existing["metadata"]) if existing["metadata"] else {}
    meta["related"] = [
        {"title": r["title"], "path": r["path"], "score": r["score"]}
        for r in related
    ]
    conn.execute(
        "UPDATE documents SET metadata = ? WHERE id = ?",
        (json.dumps(meta, ensure_ascii=False), doc_id),
    )
    conn.commit()
    conn.close()

    return related


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: related.py <entry-path> [limit]")
        sys.exit(1)

    path = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    results = find_related(path, limit)

    if results:
        print(f"Related ({len(results)}):")
        for i, r in enumerate(results, 1):
            name = Path(r["path"]).stem
            print(f"  {i}. {r['title'] or name} ({r['score']:.4f})")
    else:
        print("No related posts found.")
