"""Ingest documents into agent memory."""

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from db import ensure_db, has_vec
from embed import embed_batch, embed_text


# --- Parsers ---


def _extract_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML-like frontmatter from markdown. Returns (meta, body)."""
    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    meta = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            # Handle lists like [tag1, tag2]
            if val.startswith("[") and val.endswith("]"):
                val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(",")]
            meta[key] = val

    return meta, parts[2].strip()


class _HTMLTextExtractor(HTMLParser):
    """Extract visible text from HTML, skipping scripts/styles/SVG."""

    SKIP_TAGS = {"script", "style", "svg", "head"}

    def __init__(self):
        super().__init__()
        self._result = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self._result.append(text)

    def get_text(self) -> str:
        return "\n".join(self._result)


def _extract_html_text(html: str) -> tuple[str | None, str]:
    """Extract title and body text from HTML."""
    title = None
    m = re.search(r"<title>(.*?)</title>", html, re.DOTALL)
    if m:
        title = m.group(1).strip()

    parser = _HTMLTextExtractor()
    parser.feed(html)
    return title, parser.get_text()


def _detect_type(path: Path) -> str:
    """Detect document type from path."""
    s = str(path)
    if "/notes/" in s:
        return "note"
    if "/reports/" in s:
        return "report"
    if "/blog/entries/" in s or "/entries/" in s:
        return "blog"
    if "archive" in s:
        return "archive"
    return "other"


def _split_archive_entries(content: str) -> list[tuple[str, str]]:
    """Split archive markdown into individual entries."""
    entries = []
    current_title = None
    current_lines = []

    for line in content.splitlines():
        if line.startswith("## ["):
            if current_title and current_lines:
                entries.append((current_title, "\n".join(current_lines)))
            current_title = line.lstrip("# ").strip()
            current_lines = [line]
        elif current_title:
            current_lines.append(line)

    if current_title and current_lines:
        entries.append((current_title, "\n".join(current_lines)))

    return entries


# --- Core ---


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def ingest_file(
    path: Path,
    conn=None,
    skip_embedding: bool = False,
    verbose: bool = True,
) -> str:
    """Ingest a single file. Returns 'new', 'updated', 'unchanged', or 'error'."""
    own_conn = conn is None
    if own_conn:
        conn = ensure_db()

    try:
        path = path.resolve()
        if not path.exists():
            if verbose:
                print(f"  SKIP (not found): {path}")
            return "error"

        raw = path.read_text(errors="replace")
        if not raw.strip():
            if verbose:
                print(f"  SKIP (empty): {path.name}")
            return "error"

        h = content_hash(raw)
        doc_type = _detect_type(path)

        # Check if unchanged
        existing = conn.execute(
            "SELECT id, content_hash FROM documents WHERE path = ?", (str(path),)
        ).fetchone()

        if existing and existing["content_hash"] == h:
            if verbose:
                print(f"  unchanged: {path.name}")
            return "unchanged"

        # Parse content
        meta = {}
        if path.suffix == ".html":
            title, body = _extract_html_text(raw)
        elif path.suffix == ".md":
            meta, body = _extract_frontmatter(raw)
            title = meta.get("title", path.stem)
        else:
            title = path.stem
            body = raw

        meta_json = json.dumps(meta, ensure_ascii=False) if meta else None
        now = datetime.now(timezone.utc).isoformat()

        if existing:
            conn.execute(
                """UPDATE documents SET type=?, title=?, content=?,
                   content_hash=?, metadata=?, updated_at=? WHERE id=?""",
                (doc_type, title, body, h, meta_json, now, existing["id"]),
            )
            doc_id = existing["id"]
            status = "updated"
        else:
            cur = conn.execute(
                """INSERT INTO documents (path, type, title, content, content_hash,
                   metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(path), doc_type, title, body, h, meta_json, now, now),
            )
            doc_id = cur.lastrowid
            status = "new"

        # Embedding
        if not skip_embedding and has_vec():
            try:
                emb_text = f"{title or ''}\n{body}"
                embedding = embed_text(emb_text)
                # Delete old embedding if exists
                conn.execute(
                    "DELETE FROM documents_vec WHERE document_id = ?", (doc_id,)
                )
                conn.execute(
                    "INSERT INTO documents_vec (document_id, embedding) VALUES (?, ?)",
                    (doc_id, json.dumps(embedding)),
                )
            except Exception as e:
                if verbose:
                    print(f"  WARNING: embedding failed for {path.name}: {e}")

        conn.commit()
        if verbose:
            print(f"  {status}: {path.name} ({doc_type})")
        return status

    except Exception as e:
        if verbose:
            print(f"  ERROR: {path.name}: {e}")
        return "error"
    finally:
        if own_conn:
            conn.close()


def ingest_directory(
    directory: Path,
    pattern: str = "*.md",
    skip_embedding: bool = False,
    verbose: bool = True,
) -> dict:
    """Ingest all matching files in a directory."""
    conn = ensure_db()
    stats = {"new": 0, "updated": 0, "unchanged": 0, "error": 0}

    files = sorted(directory.glob(pattern))
    if verbose:
        print(f"Found {len(files)} files in {directory}")

    for f in files:
        if f.is_file():
            result = ingest_file(f, conn=conn, skip_embedding=skip_embedding, verbose=verbose)
            stats[result] = stats.get(result, 0) + 1

    conn.close()
    return stats


def ingest_bulk_with_batch_embeddings(
    paths: list[Path],
    verbose: bool = True,
) -> dict:
    """Ingest multiple files with batched embedding calls for efficiency."""
    conn = ensure_db()
    stats = {"new": 0, "updated": 0, "unchanged": 0, "error": 0}

    # Phase 1: Insert/update documents without embeddings
    docs_needing_embedding = []  # (doc_id, text_for_embedding)

    for path in paths:
        path = path.resolve()
        if not path.exists() or not path.is_file():
            stats["error"] += 1
            continue

        raw = path.read_text(errors="replace")
        if not raw.strip():
            stats["error"] += 1
            continue

        h = content_hash(raw)
        doc_type = _detect_type(path)

        existing = conn.execute(
            "SELECT id, content_hash FROM documents WHERE path = ?", (str(path),)
        ).fetchone()

        if existing and existing["content_hash"] == h:
            stats["unchanged"] += 1
            continue

        meta = {}
        if path.suffix == ".html":
            title, body = _extract_html_text(raw)
        elif path.suffix == ".md":
            meta, body = _extract_frontmatter(raw)
            title = meta.get("title", path.stem)
        else:
            title = path.stem
            body = raw

        meta_json = json.dumps(meta, ensure_ascii=False) if meta else None
        now = datetime.now(timezone.utc).isoformat()

        if existing:
            conn.execute(
                """UPDATE documents SET type=?, title=?, content=?,
                   content_hash=?, metadata=?, updated_at=? WHERE id=?""",
                (doc_type, title, body, h, meta_json, now, existing["id"]),
            )
            doc_id = existing["id"]
            stats["updated"] += 1
        else:
            cur = conn.execute(
                """INSERT INTO documents (path, type, title, content, content_hash,
                   metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(path), doc_type, title, body, h, meta_json, now, now),
            )
            doc_id = cur.lastrowid
            stats["new"] += 1

        docs_needing_embedding.append((doc_id, f"{title or ''}\n{body}"))

        if verbose and (stats["new"] + stats["updated"]) % 50 == 0:
            print(f"  ... {stats['new'] + stats['updated']} docs processed")

    conn.commit()

    # Phase 2: Batch embed (only if sqlite_vec available)
    if docs_needing_embedding and has_vec():
        if verbose:
            print(f"\nEmbedding {len(docs_needing_embedding)} documents...")

        doc_ids = [d[0] for d in docs_needing_embedding]
        texts = [d[1] for d in docs_needing_embedding]

        try:
            embeddings = embed_batch(texts, batch_size=100)

            for doc_id, embedding in zip(doc_ids, embeddings):
                conn.execute(
                    "DELETE FROM documents_vec WHERE document_id = ?", (doc_id,)
                )
                conn.execute(
                    "INSERT INTO documents_vec (document_id, embedding) VALUES (?, ?)",
                    (doc_id, json.dumps(embedding)),
                )

            conn.commit()
            if verbose:
                print(f"  Embedded {len(embeddings)} documents")
        except Exception as e:
            if verbose:
                print(f"  WARNING: batch embedding failed: {e}")
                print("  Documents are indexed in FTS5 but without embeddings")
    elif docs_needing_embedding and not has_vec():
        if verbose:
            print("  NOTE: sqlite_vec not installed — skipping embeddings (FTS5 only)")

    conn.close()
    return stats


# --- CLI ---


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Ingest documents into agent memory")
    parser.add_argument("paths", nargs="+", help="Files or directories to ingest")
    parser.add_argument(
        "--pattern", default="*.md", help="Glob pattern for directories (default: *.md)"
    )
    parser.add_argument(
        "--no-embed", action="store_true", help="Skip embedding generation"
    )
    parser.add_argument("--quiet", action="store_true", help="Minimal output")
    parser.add_argument(
        "--reindex", action="store_true", help="Force reindex (ignore hash cache)"
    )
    args = parser.parse_args()

    verbose = not args.quiet
    total_stats = {"new": 0, "updated": 0, "unchanged": 0, "error": 0}

    all_files = []
    for p in args.paths:
        path = Path(p).expanduser().resolve()
        if path.is_dir():
            all_files.extend(sorted(path.glob(args.pattern)))
            # Also grab HTML in reports
            if args.pattern == "*.md":
                all_files.extend(sorted(path.glob("*.html")))
        elif path.is_file():
            all_files.append(path)
        else:
            if verbose:
                print(f"SKIP: {p} (not found)")

    if not all_files:
        print("No files to ingest")
        sys.exit(1)

    if verbose:
        print(f"Ingesting {len(all_files)} files...")

    if args.reindex:
        # Clear all hashes to force re-processing
        conn = ensure_db()
        conn.execute("UPDATE documents SET content_hash = ''")
        conn.commit()
        conn.close()

    if args.no_embed:
        conn = ensure_db()
        for f in all_files:
            result = ingest_file(f, conn=conn, skip_embedding=True, verbose=verbose)
            total_stats[result] = total_stats.get(result, 0) + 1
        conn.close()
    else:
        total_stats = ingest_bulk_with_batch_embeddings(all_files, verbose=verbose)

    if verbose:
        print(f"\nDone: {total_stats['new']} new, {total_stats['updated']} updated, "
              f"{total_stats['unchanged']} unchanged, {total_stats['error']} errors")


if __name__ == "__main__":
    main()
