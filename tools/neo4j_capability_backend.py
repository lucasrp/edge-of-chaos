"""Adapter from the broker's five capabilities to existing Cortex read seams.

Tests inject every callable.  ``build_existing_cortex_backend`` is construction-only: importing this
module does not import Neo4j, identity, secrets, recall, or the blog server.  Those dependencies are
resolved lazily only inside the future credential-owning broker process.
"""


class CortexReadBackend:
    def __init__(self, *, health_fn, recall_fn, surf_fn, fold_fn):
        self._health_fn = health_fn
        self._recall_fn = recall_fn
        self._surf_fn = surf_fn
        self._fold_fn = fold_fn

    def health(self, *, group):
        return bool(self._health_fn(group))

    def recall(self, *, group):
        return self._recall_fn(group)

    def surf(self, *, group, seeds, hops):
        rows = self._surf_fn(seeds, group)
        if rows is None:
            return None
        return {
            "nodes": [row for row in rows if row.get("hops") is None or row.get("hops") <= hops],
            "hops": hops,
        }

    def node(self, *, group, ref):
        fold = self._fold_fn(group)
        if fold is None:
            return None
        nodes = fold.get("nodes") or []
        node = next((item for item in nodes if ref in {
            item.get("ref"), item.get("id"), item.get("slug"), item.get("key"), item.get("title")
        }), None)
        if node is None:
            return {"node": None, "neighbors": []}
        canonical = node.get("ref") or node.get("id")
        ids = {node.get("id"), canonical}
        adjacent = set()
        for edge in fold.get("edges") or []:
            source, target = edge.get("source"), edge.get("target")
            if source in ids:
                adjacent.add(target)
            elif target in ids:
                adjacent.add(source)
        neighbors = [item for item in nodes if item.get("id") in adjacent or item.get("ref") in adjacent]
        return {"node": node, "neighbors": neighbors}

    def search(self, *, group, query, limit):
        fold = self._fold_fn(group)
        if fold is None:
            return None
        needle = query.casefold()
        rows = []
        for node in fold.get("nodes") or []:
            haystack = " ".join(str(node.get(field) or "") for field in ("label", "title", "slug"))
            if needle in haystack.casefold():
                rows.append(node)
                if len(rows) >= limit:
                    break
        return {"results": rows, "limit": limit}


def build_existing_cortex_backend():
    """Wire existing group-scoped reads; call only inside the future privileged broker service."""
    import recall
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo / "blog"))
    import server

    return CortexReadBackend(
        health_fn=lambda group: recall.recall_subgraph(group) is not None,
        recall_fn=lambda group: recall.recall_subgraph(group),
        surf_fn=lambda seeds, group: recall.surf_subgraph(seeds, group=group),
        fold_fn=lambda group: server.cortex_fold(group),
    )
