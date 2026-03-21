#!/usr/bin/env python3
"""curadoria_compute.py — Corpus curation engine.

Modes:
  --mode stats   Per-doc health metrics from search_events
  --mode lite    Stats + stale candidate identification
  --mode full    Lite + self-probes + nearest-neighbor clustering + classification

Usage:
  curadoria_compute.py --mode stats
  curadoria_compute.py --mode lite
  curadoria_compute.py --mode full --active-threads "thread1,thread2" --recent-gaps "gap1,gap2"
"""

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Add search module to path
SEARCH_DIR = Path.home() / "edge" / "search"
sys.path.insert(0, str(SEARCH_DIR))

from db import ensure_db

OUTPUT_FILE = Path.home() / "edge" / "state" / "curadoria-candidates.json"


# --- Union-Find ---

class UnionFind:
    def __init__(self):
        self.parent = {}
        self.rank = {}

    def find(self, x):
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1

    def clusters(self):
        groups = defaultdict(list)
        for x in self.parent:
            groups[self.find(x)].append(x)
        return list(groups.values())


# --- Doc health metrics ---

def get_doc_health(conn):
    """Per-doc health metrics combining documents and search_events."""
    rows = conn.execute("""
        SELECT d.id, d.path, d.type, d.title, d.created_at,
               COALESCE(se.retrieved_count, 0) AS retrieved_count,
               COALESCE(se.top3_count, 0) AS top3_count,
               se.last_retrieved,
               COALESCE(se.query_diversity, 0) AS query_diversity,
               CAST(julianday('now') - julianday(d.created_at) AS INTEGER) AS age_days,
               COALESCE(se30.retrieved_30d, 0) AS retrieved_30d,
               COALESCE(se30.top3_30d, 0) AS top3_30d
        FROM documents d
        LEFT JOIN (
            SELECT doc_id,
                   COUNT(*) AS retrieved_count,
                   SUM(CASE WHEN rank <= 3 THEN 1 ELSE 0 END) AS top3_count,
                   MAX(ts) AS last_retrieved,
                   COUNT(DISTINCT query_norm) AS query_diversity
            FROM search_events
            GROUP BY doc_id
        ) se ON se.doc_id = d.id
        LEFT JOIN (
            SELECT doc_id,
                   COUNT(*) AS retrieved_30d,
                   SUM(CASE WHEN rank <= 3 THEN 1 ELSE 0 END) AS top3_30d
            FROM search_events
            WHERE ts >= datetime('now', '-30 days')
            GROUP BY doc_id
        ) se30 ON se30.doc_id = d.id
        ORDER BY retrieved_count DESC
    """).fetchall()
    return [dict(r) for r in rows]


def get_stale_candidates(docs):
    """Docs with age > 45 days and no recent retrieval or no top-3 in 30d."""
    stale = []
    for d in docs:
        if d["age_days"] > 45 and (d["retrieved_30d"] == 0 or d["top3_30d"] == 0):
            stale.append(d)
    return stale


# --- Self-probes ---

def extract_rare_terms(title):
    """Extract terms from title for self-probe query."""
    if not title:
        return []
    words = re.findall(r"[a-zA-ZÀ-ú]{4,}", title)
    # Filter common words
    stopwords = {
        "para", "como", "sobre", "entre", "mais", "este", "esta",
        "todo", "toda", "cada", "esse", "essa", "from", "with",
        "that", "this", "have", "been", "some", "what", "when",
    }
    return [w for w in words if w.lower() not in stopwords][:4]


def run_self_probe(title):
    """Run edge-search --no-telemetry with title-based query, return results."""
    terms = extract_rare_terms(title)
    if not terms:
        return None, []

    query = " ".join(terms[:3])
    try:
        result = subprocess.run(
            ["edge-search", "--no-telemetry", "--fts", "-k", "10", query],
            capture_output=True, text=True, timeout=15,
            cwd=str(SEARCH_DIR),
        )
        return query, result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return query, ""


def parse_self_rank(output, doc_id):
    """Parse edge-search output to find rank of doc_id. Returns rank or None."""
    # Output format: "#1   score  type  filename"
    # We can't reliably parse doc_id from CLI output, so return None
    # In full mode, we query the DB directly instead
    return None


def self_probe_via_db(doc, conn):
    """Self-probe by querying FTS directly, returns self_rank."""
    from search import fts_search

    terms = extract_rare_terms(doc["title"])
    if not terms:
        return 99  # No terms = unfindable

    query = " ".join(terms[:3])
    try:
        results = fts_search(query, limit=10, doc_type=doc.get("type"), conn=conn)
        for rank, r in enumerate(results, 1):
            if r["id"] == doc["id"]:
                return rank
        return 99  # Not found in top 10
    except Exception:
        return 99


# --- Nearest-neighbor ---

def get_nearest_neighbors(doc_id, doc_type, conn, limit=3):
    """Get nearest neighbors for a doc from documents_vec."""
    import struct

    try:
        # Get embedding for this doc
        row = conn.execute(
            "SELECT embedding FROM documents_vec WHERE document_id = ?",
            (doc_id,),
        ).fetchone()
        if not row:
            return []

        embedding_bytes = row[0]

        # Query neighbors of same type
        sql = """
            SELECT v.document_id, v.distance,
                   d.title, d.path, d.type
            FROM documents_vec v
            JOIN documents d ON d.id = v.document_id
            WHERE v.embedding MATCH ?
              AND k = ?
              AND d.type = ?
              AND v.document_id != ?
            ORDER BY v.distance
        """
        rows = conn.execute(
            sql, (embedding_bytes, limit + 1, doc_type, doc_id)
        ).fetchall()

        neighbors = []
        for r in rows[:limit]:
            neighbors.append({
                "doc_id": r["document_id"],
                "title": r["title"],
                "similarity": round(1 - r["distance"], 4),
            })
        return neighbors
    except Exception:
        return []


def title_overlap(t1, t2):
    """Jaccard similarity between title word sets."""
    if not t1 or not t2:
        return 0.0
    s1 = set(re.findall(r"[a-zA-ZÀ-ú]{3,}", t1.lower()))
    s2 = set(re.findall(r"[a-zA-ZÀ-ú]{3,}", t2.lower()))
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)


# --- Classification ---

def classify_docs(stale_with_probes, all_docs, conn):
    """Classify stale docs into archive/merge/strengthen/keep."""
    if not stale_with_probes:
        return [], [], [], []

    # Build union-find clusters
    uf = UnionFind()
    doc_map = {d["id"]: d for d in stale_with_probes}

    for doc in stale_with_probes:
        uf.find(doc["id"])  # ensure registered
        neighbors = get_nearest_neighbors(doc["id"], doc["type"], conn, limit=3)
        doc["neighbors"] = neighbors
        for nb in neighbors:
            sim = nb["similarity"]
            nb_title = nb.get("title", "")
            toverlap = title_overlap(doc.get("title", ""), nb_title)
            if sim >= 0.90 or (sim >= 0.83 and toverlap >= 0.5):
                uf.find(nb["doc_id"])
                uf.union(doc["id"], nb["doc_id"])

    clusters = uf.clusters()

    # Compute p75 of rrf (retrieved_count) across all docs
    rrf_values = sorted(d["retrieved_count"] for d in all_docs if d["retrieved_count"] > 0)
    p75_rrf = rrf_values[int(len(rrf_values) * 0.75)] if rrf_values else 0

    archive_auto = []
    merge_review = []
    strengthen_targets = []
    keep = []

    # Process individual stale docs for archive
    for doc in stale_with_probes:
        if (
            doc["age_days"] > 120
            and doc["retrieved_30d"] == 0
            and doc.get("self_rank", 99) > 5
            and doc.get("neighbors")
            and any(n["similarity"] >= 0.90 for n in doc["neighbors"])
        ):
            best_nb = max(doc["neighbors"], key=lambda n: n["similarity"])
            archive_auto.append({
                "doc_id": doc["id"],
                "title": doc.get("title", ""),
                "age_days": doc["age_days"],
                "self_rank": doc.get("self_rank", 99),
                "nn_sim": best_nb["similarity"],
                "reason": f"Stale {doc['age_days']}d, self_rank={doc.get('self_rank', 99)}, "
                          f"strong neighbor: {best_nb['title']} (sim={best_nb['similarity']})",
            })

    # Process clusters for merge
    for cluster_ids in clusters:
        if len(cluster_ids) < 3:
            continue
        # Compute median similarity within cluster
        sims = []
        for doc_id in cluster_ids:
            if doc_id in doc_map and doc_map[doc_id].get("neighbors"):
                for nb in doc_map[doc_id]["neighbors"]:
                    if nb["doc_id"] in cluster_ids:
                        sims.append(nb["similarity"])
        if not sims:
            continue
        median_sim = sorted(sims)[len(sims) // 2]
        if median_sim >= 0.83:
            cluster_docs = []
            for did in cluster_ids:
                if did in doc_map:
                    cluster_docs.append({
                        "doc_id": did,
                        "title": doc_map[did].get("title", ""),
                    })
                else:
                    cluster_docs.append({"doc_id": did, "title": "?"})
            merge_review.append({
                "cluster_id": len(merge_review) + 1,
                "docs": cluster_docs,
                "median_sim": round(median_sim, 4),
                "suggestion": f"Merge {len(cluster_ids)} docs with median similarity {median_sim:.2f}",
            })

    # Strengthen: clusters with high demand but no consistent top-3
    for cluster_ids in clusters:
        cluster_demand = sum(
            doc_map[did]["retrieved_count"]
            for did in cluster_ids if did in doc_map
        )
        cluster_top3 = max(
            (doc_map[did]["top3_count"] for did in cluster_ids if did in doc_map),
            default=0,
        )
        if cluster_demand > p75_rrf and cluster_top3 == 0:
            best_doc_id = max(
                (did for did in cluster_ids if did in doc_map),
                key=lambda did: doc_map[did]["retrieved_count"],
                default=None,
            )
            if best_doc_id and best_doc_id in doc_map:
                strengthen_targets.append({
                    "doc_id": best_doc_id,
                    "title": doc_map[best_doc_id].get("title", ""),
                    "demand_rrf": cluster_demand,
                    "best_rank": doc_map[best_doc_id].get("self_rank", 99),
                    "suggestion": "Improve title/content of most relevant doc in cluster",
                })

    return archive_auto, merge_review, strengthen_targets, keep


def apply_strategic_veto(archive_auto, strengthen_targets, active_threads, recent_gaps):
    """Suppress archive of docs related to active threads or recent gaps."""
    suppressed = []

    remaining_archive = []
    for doc in archive_auto:
        title_lower = (doc.get("title") or "").lower()
        matched_thread = None
        for thread in active_threads:
            if thread.lower() in title_lower:
                matched_thread = thread
                break
        matched_gap = None
        if not matched_thread:
            for gap in recent_gaps:
                if gap.lower() in title_lower:
                    matched_gap = gap
                    break

        if matched_thread or matched_gap:
            suppressed.append({
                "doc_id": doc["doc_id"],
                "title": doc.get("title", ""),
                "matching_thread": matched_thread or matched_gap,
                "original_action": "ARCHIVE",
            })
        else:
            remaining_archive.append(doc)

    return remaining_archive, suppressed


# --- Main ---

def main():
    parser = argparse.ArgumentParser(
        description="Corpus curation engine: compute doc health, find clusters, classify"
    )
    parser.add_argument(
        "--mode", choices=["stats", "lite", "full"], default="full",
        help="Computation mode (default: full)",
    )
    parser.add_argument(
        "--active-threads", default="",
        help="Comma-separated active thread names (for strategic veto)",
    )
    parser.add_argument(
        "--recent-gaps", default="",
        help="Comma-separated recent gap descriptions (for strategic veto)",
    )
    args = parser.parse_args()

    active_threads = [t.strip() for t in args.active_threads.split(",") if t.strip()]
    recent_gaps = [g.strip() for g in args.recent_gaps.split(",") if g.strip()]

    conn = ensure_db()

    # Stats mode: per-doc health
    docs = get_doc_health(conn)

    if args.mode == "stats":
        output = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "stats",
            "total_docs": len(docs),
            "docs": docs,
        }
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
        print(f"OK: {len(docs)} docs analyzed → {OUTPUT_FILE}")
        conn.close()
        return

    # Lite mode: stats + stale candidates
    stale = get_stale_candidates(docs)

    if args.mode == "lite":
        output = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "lite",
            "total_docs": len(docs),
            "stale_candidates": len(stale),
            "stale": [
                {
                    "doc_id": d["id"],
                    "title": d.get("title", ""),
                    "type": d.get("type", ""),
                    "age_days": d["age_days"],
                    "retrieved_count": d["retrieved_count"],
                    "retrieved_30d": d["retrieved_30d"],
                    "top3_30d": d["top3_30d"],
                }
                for d in stale
            ],
        }
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
        print(f"OK: {len(docs)} docs, {len(stale)} stale → {OUTPUT_FILE}")
        conn.close()
        return

    # Full mode: lite + self-probes + clustering + classification
    # Self-probes
    from search import fts_search  # noqa: delayed import

    for doc in stale:
        doc["self_rank"] = self_probe_via_db(doc, conn)

    # Classification (includes clustering)
    archive_auto, merge_review, strengthen_targets, _ = classify_docs(stale, docs, conn)

    # Strategic veto
    archive_auto, suppressed = apply_strategic_veto(
        archive_auto, strengthen_targets, active_threads, recent_gaps
    )

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "full",
        "total_docs": len(docs),
        "stale_candidates": len(stale),
        "archive_auto": archive_auto,
        "merge_review": merge_review,
        "strengthen_targets": strengthen_targets,
        "suppressed_due_to_active_thread": suppressed,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")

    print(
        f"OK: {len(docs)} docs, {len(stale)} stale, "
        f"{len(archive_auto)} archive, {len(merge_review)} merge, "
        f"{len(strengthen_targets)} strengthen, {len(suppressed)} suppressed → {OUTPUT_FILE}"
    )

    conn.close()


if __name__ == "__main__":
    main()
