"""Sync, group-scoped Graphiti thread label resolver for the ``open_map`` pen seam.

The eventlog owns persistence but never imports a graph provider (A21).  Callers construct this
adapter with the already-open sync Neo4j driver and install group, then inject it as
``resolve_thread_fn``.  The callable returns the one-candidate iterable expected by the pen.
"""

import inspect


def _nonblank(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-blank string")
    return value.strip()


class ThreadResolver:
    """Resolve a human label through ``merged_into`` to one live terminal Entity."""

    def __init__(self, driver, *, group_id):
        self._driver = driver
        self._group_id = _nonblank(group_id, "group_id")

    @staticmethod
    def _rows(result):
        if inspect.isawaitable(result):
            close = getattr(result, "close", None)
            if callable(close):
                close()
            raise TypeError("thread resolver requires a sync Neo4j driver")
        rows = result.data()
        if inspect.isawaitable(rows):
            close = getattr(rows, "close", None)
            if callable(close):
                close()
            raise TypeError("thread resolver requires a sync Neo4j driver")
        return [dict(row) for row in rows]

    def _lookup_label(self, session, label):
        return self._rows(session.run(
            "MATCH (e:Entity {group_id:$group_id}) "
            "WHERE e.name=$label OR e.curated_name=$label "
            "RETURN e.ref AS ref, e.uuid AS uuid, e.name AS name, "
            "e.curated_name AS curated_name, e.merged_into AS merged_into, "
            "coalesce(e.archived,false) AS archived",
            group_id=self._group_id,
            label=label,
        ))

    def _lookup_target(self, session, target):
        return self._rows(session.run(
            "MATCH (e:Entity {group_id:$group_id}) "
            "WHERE e.ref=$target OR e.uuid=$target OR e.name=$target "
            "OR e.curated_name=$target "
            "RETURN e.ref AS ref, e.uuid AS uuid, e.name AS name, "
            "e.curated_name AS curated_name, e.merged_into AS merged_into, "
            "coalesce(e.archived,false) AS archived",
            group_id=self._group_id,
            target=target,
        ))

    def _terminal(self, session, node):
        seen = set()
        while True:
            identity = node.get("uuid") or node.get("ref") or node.get("name")
            identity = _nonblank(identity, "thread identity")
            if identity in seen:
                raise ValueError("thread merge cycle detected")
            seen.add(identity)
            if node.get("archived") is True:
                raise ValueError("thread resolves to an archived entity")
            target = node.get("merged_into")
            if target is None:
                uuid = _nonblank(node.get("uuid"), "thread.uuid")
                display = node.get("curated_name") or node.get("name")
                return {"uuid": uuid, "display": _nonblank(display, "thread.display")}
            target = _nonblank(target, "thread.merged_into")
            matches = self._lookup_target(session, target)
            if not matches:
                raise ValueError(f"thread merge is dangling at {target!r}")
            if len(matches) != 1:
                raise ValueError(f"thread merge target {target!r} is ambiguous")
            node = matches[0]

    def __call__(self, label):
        label = _nonblank(label, "thread label")
        session = self._driver.session()
        if inspect.isawaitable(session):
            close = getattr(session, "close", None)
            if callable(close):
                close()
            raise TypeError("thread resolver requires a sync Neo4j driver")
        with session:
            candidates = self._lookup_label(session, label)
            if not candidates:
                raise ValueError(f"thread label {label!r} was not found")
            terminals = {}
            for candidate in candidates:
                terminal = self._terminal(session, candidate)
                terminals[terminal["uuid"]] = terminal
            if len(terminals) != 1:
                raise ValueError(f"thread label {label!r} is ambiguous")
            return [next(iter(terminals.values()))]


def resolve_for_install(label, *, driver_factory=None, identity=None):
    """Resolve one label against this install, owning the short-lived driver lifecycle.

    Provider and identity imports stay lazy so importing the ledger/portfolio path remains A21
    provider-free. Tests may inject both seams; production derives connection and group solely
    from ``_identity``.
    """
    if identity is None:
        import _identity as identity
    if driver_factory is None:
        from neo4j import GraphDatabase
        driver_factory = GraphDatabase.driver
    group_id = identity.require_group()
    uri, user, password = identity.neo4j_conn()
    driver = driver_factory(uri, auth=(user, password))
    try:
        return ThreadResolver(driver, group_id=group_id)(label)
    finally:
        driver.close()
