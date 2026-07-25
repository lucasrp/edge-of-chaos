"""Narrow graph projection port and its deterministic in-memory test adapter.

The event log remains truth.  This module only defines the navigation-shaped seam used
by best-effort projections; it deliberately has no search/retrieval operation.
"""

from copy import deepcopy
from dataclasses import dataclass
import re
from typing import Iterable, Mapping, Optional, Protocol, runtime_checkable


class GraphUnavailable(RuntimeError):
    """The graph adapter could not complete one projection operation."""


class _GraphContractError(ValueError):
    """A live query completed but violated the GraphStore's structural contract."""


@dataclass(frozen=True)
class ProjectionResult:
    """Outcome of one best-effort projection pass."""

    complete: bool
    incomplete_refs: tuple[str, ...] = ()

    def __post_init__(self):
        refs = []
        for ref in tuple(self.incomplete_refs):
            if not isinstance(ref, str) or not ref.strip():
                raise ValueError("incomplete refs must be non-blank strings")
            if ref not in refs:
                refs.append(ref)
        refs = tuple(refs)
        object.__setattr__(self, "incomplete_refs", refs)
        if self.complete and refs:
            raise ValueError("a complete projection cannot name incomplete refs")
        if not self.complete and not refs:
            raise ValueError("an incomplete projection must name at least one incomplete ref")

    @classmethod
    def success(cls):
        return cls(complete=True)

    @classmethod
    def incomplete(cls, refs: Iterable[str]):
        return cls(complete=False, incomplete_refs=tuple(refs))


@dataclass(frozen=True)
class GraphNeighbor:
    """One typed hop returned by :meth:`GraphStore.neighbors`."""

    ref: str
    label: str
    node_props: Mapping
    edge_kind: str
    edge_props: Mapping
    direction: str


@dataclass(frozen=True)
class EdgeSpec:
    """One desired outgoing edge in a deterministic ``replace_edges`` set."""

    dst_ref: str
    props: Mapping

    def __init__(self, dst_ref: str, props: Optional[Mapping] = None):
        object.__setattr__(self, "dst_ref", dst_ref)
        object.__setattr__(self, "props", deepcopy(dict(props or {})))


@runtime_checkable
class GraphStore(Protocol):
    """Mutation plus neighborhood navigation; intentionally no global search."""

    def merge_node(self, ref: str, label: str, props: Optional[Mapping] = None): ...

    def merge_edge(
        self,
        src_ref: str,
        edge_kind: str,
        dst_ref: str,
        props: Optional[Mapping] = None,
    ): ...

    def replace_edges(
        self,
        owner_ref: str,
        edge_kind: str,
        desired: Iterable,
        as_of=None,
    ): ...

    def invalidate(self, ref: str, as_of=None): ...

    def neighbors(self, ref: str, edge_kind: Optional[str] = None, direction: str = "both"): ...


_CYPHER_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _cypher_identifier(value, field):
    if not isinstance(value, str) or not _CYPHER_IDENTIFIER.fullmatch(value):
        raise ValueError(f"{field} must be a safe Cypher identifier")
    return value


def _edge_properties(props):
    properties = deepcopy(dict(props or {}))
    src_seq = properties.get("src_seq")
    if isinstance(src_seq, bool) or not isinstance(src_seq, int) or src_seq < 1:
        raise ValueError("edge props.src_seq must be a positive integer")
    return properties


def _node_properties(props):
    properties = deepcopy(dict(props or {}))
    protected = sorted({"group_id", "ref"} & set(properties))
    if protected:
        raise ValueError(
            "node props cannot overwrite structural identity: " + ", ".join(protected)
        )
    return properties


class Neo4jGraphStore:
    """Live GraphStore adapter over an injected Neo4j driver.

    Driver/session failures cross one translation seam and become ``GraphUnavailable``;
    callers never need the Neo4j exception hierarchy and tests stay entirely offline.
    """

    def __init__(self, driver, *, group_id):
        self._driver = driver
        if not isinstance(group_id, str) or not group_id.strip():
            raise ValueError("group_id must be a non-blank string")
        self._group_id = group_id.strip()

    def _execute(self, operation, fn):
        try:
            with self._driver.session() as session:
                return fn(session)
        except GraphUnavailable:
            raise
        except _GraphContractError:
            raise
        except Exception as exc:
            raise GraphUnavailable(f"Neo4j graph unavailable during {operation}") from exc

    def merge_node(self, ref, label, props=None):
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError("ref must be a non-blank string")
        label = _cypher_identifier(label, "label")
        properties = _node_properties(props)
        query = (
            f"MERGE (n:`{label}` {{group_id:$group_id, ref:$ref}}) "
            "SET n += $props"
        )
        params = {"group_id": self._group_id, "ref": ref, "props": properties}
        return self._execute("merge_node", lambda session: session.run(query, **params))

    def _edge_statement(self, src_ref, edge_kind, dst_ref, props=None):
        for value, field in ((src_ref, "src_ref"), (dst_ref, "dst_ref")):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be a non-blank string")
        edge_kind = _cypher_identifier(edge_kind, "edge_kind")
        properties = _edge_properties(props)
        src_seq = properties["src_seq"]
        query = (
            "MATCH (src {group_id:$group_id}) "
            "WHERE src.ref=$src_ref OR src.uuid=$src_ref "
            "WITH src MATCH (dst {group_id:$group_id}) "
            "WHERE dst.ref=$dst_ref OR dst.uuid=$dst_ref "
            f"MERGE (src)-[r:`{edge_kind}` {{src_seq:$src_seq}}]->(dst) "
            "SET r += $props RETURN count(r) AS merged"
        )
        params = {
            "group_id": self._group_id,
            "src_ref": src_ref,
            "dst_ref": dst_ref,
            "src_seq": src_seq,
            "props": properties,
        }
        return query, params

    def merge_edge(self, src_ref, edge_kind, dst_ref, props=None):
        query, params = self._edge_statement(src_ref, edge_kind, dst_ref, props)

        def _merge(session):
            row = session.run(query, **params).single()
            merged = row.get("merged") if row is not None else 0
            if merged != 1:
                raise _GraphContractError(
                    "merge_edge requires exactly one source and destination endpoint; "
                    f"observed cardinality {merged}"
                )

        return self._execute("merge_edge", _merge)

    def replace_edges(self, owner_ref, edge_kind, desired, as_of=None):
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ValueError("owner_ref must be a non-blank string")
        edge_kind = _cypher_identifier(edge_kind, "edge_kind")
        statements = []
        for edge in list(desired):
            if not isinstance(edge, EdgeSpec):
                raise TypeError("desired edges must be EdgeSpec values")
            statements.append(
                self._edge_statement(owner_ref, edge_kind, edge.dst_ref, edge.props)
            )
        delete_query = (
            "MATCH (owner {group_id:$group_id}) "
            "WHERE owner.ref=$owner_ref OR owner.uuid=$owner_ref "
            f"OPTIONAL MATCH (owner)-[r:`{edge_kind}`]->() "
            "FOREACH (_ IN CASE WHEN r IS NULL THEN [] ELSE [1] END | DELETE r) "
            "RETURN count(DISTINCT owner) AS owners"
        )
        delete_params = {"group_id": self._group_id, "owner_ref": owner_ref}

        def _transaction(tx):
            owner_row = tx.run(delete_query, **delete_params).single()
            owners = owner_row.get("owners") if owner_row is not None else 0
            if owners != 1:
                raise _GraphContractError(
                    f"replace_edges requires exactly one owner; observed cardinality {owners}"
                )
            for query, params in statements:
                row = tx.run(query, **params).single()
                merged = row.get("merged") if row is not None else 0
                if merged != 1:
                    raise _GraphContractError(
                        "replace_edges requires exactly one source and destination endpoint; "
                        f"observed cardinality {merged}"
                    )

        def _replace(session):
            return session.execute_write(_transaction)

        return self._execute("replace_edges", _replace)

    def invalidate(self, ref, as_of=None):
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError("ref must be a non-blank string")
        invalidated_at = as_of if as_of is not None else True
        query = (
            "MATCH (n {group_id:$group_id}) "
            "WHERE n.ref=$ref OR n.uuid=$ref "
            "SET n.archived=true, n.invalidated_at=$as_of "
            "WITH n OPTIONAL MATCH (n)-[r]-(neighbor {group_id:$group_id}) "
            "FOREACH (_ IN CASE WHEN r IS NULL THEN [] ELSE [1] END | "
            "SET r.invalidated_at=$as_of) RETURN count(DISTINCT n) AS invalidated"
        )
        params = {
            "group_id": self._group_id,
            "ref": ref,
            "as_of": invalidated_at,
        }
        def _invalidate(session):
            row = session.run(query, **params).single()
            cardinality = row.get("invalidated") if row is not None else 0
            if cardinality != 1:
                raise _GraphContractError(
                    "invalidate requires exactly one anchor; "
                    f"observed cardinality {cardinality}"
                )

        return self._execute("invalidate", _invalidate)

    def neighbors(self, ref, edge_kind=None, direction="both"):
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError("ref must be a non-blank string")
        if direction not in {"in", "out", "both"}:
            raise ValueError("direction must be 'in', 'out', or 'both'")
        relation = "[r]" if edge_kind is None else f"[r:`{_cypher_identifier(edge_kind, 'edge_kind')}`]"

        def _arm(hop):
            pattern = (f"(anchor)-{relation}->(neighbor)" if hop == "out"
                       else f"(anchor)<-{relation}-(neighbor)")
            return (
                "MATCH (anchor {group_id:$group_id}) "
                "WHERE anchor.ref=$ref OR anchor.uuid=$ref "
                f"MATCH {pattern} "
                "WHERE coalesce(anchor.archived,false)=false "
                "AND anchor.invalidated_at IS NULL "
                "AND anchor.merged_into IS NULL "
                "AND neighbor.group_id=$group_id "
                "AND r.invalidated_at IS NULL "
                "RETURN coalesce(neighbor.ref, neighbor.uuid) AS ref, "
                "head(labels(neighbor)) AS label, "
                "properties(neighbor) AS node_props, type(r) AS edge_kind, "
                f"properties(r) AS edge_props, '{hop}' AS direction"
            )

        hops = ("out", "in") if direction == "both" else (direction,)
        query = " UNION ALL ".join(_arm(hop) for hop in hops)
        params = {"group_id": self._group_id, "ref": ref}

        def _read(session):
            cardinality_row = session.run(
                "MATCH (anchor {group_id:$group_id}) "
                "WHERE anchor.ref=$ref OR anchor.uuid=$ref "
                "RETURN count(anchor) AS anchors",
                **params,
            ).single()
            cardinality = cardinality_row.get("anchors") if cardinality_row is not None else 0
            if cardinality != 1:
                raise _GraphContractError(
                    "neighbors requires exactly one anchor; "
                    f"observed cardinality {cardinality}"
                )
            rows = session.run(query, **params).data()

            def _canonical(row):
                current = dict(row)
                seen = set()
                while True:
                    props = dict(current.get("node_props") or {})
                    identity = (props.get("uuid") or props.get("ref")
                                or current.get("ref"))
                    if not isinstance(identity, str) or identity in seen:
                        return None
                    seen.add(identity)
                    if (props.get("archived") is True
                            or props.get("invalidated_at") is not None):
                        return None
                    target = props.get("merged_into")
                    if target is None:
                        return current
                    if not isinstance(target, str) or not target.strip():
                        return None
                    matches = session.run(
                        "MATCH (canonical {group_id:$group_id}) "
                        "WHERE canonical.ref=$target OR canonical.uuid=$target "
                        "OR canonical.name=$target OR canonical.curated_name=$target "
                        "RETURN coalesce(canonical.ref, canonical.uuid) AS ref, "
                        "head(labels(canonical)) AS label, "
                        "properties(canonical) AS node_props",
                        group_id=self._group_id,
                        target=target,
                    ).data()
                    if len(matches) != 1:
                        return None
                    resolved = dict(matches[0])
                    current.update(resolved)

            neighbors = []
            for row in rows:
                row = _canonical(row)
                if row is None:
                    continue
                node_props = deepcopy(dict(row.get("node_props") or {}))
                for internal in ("group_id", "ref", "archived", "invalidated_at"):
                    node_props.pop(internal, None)
                neighbors.append(GraphNeighbor(
                    ref=row.get("ref"),
                    label=row.get("label"),
                    node_props=node_props,
                    edge_kind=row.get("edge_kind"),
                    edge_props=deepcopy(dict(row.get("edge_props") or {})),
                    direction=row.get("direction"),
                ))
            return sorted(
                neighbors,
                key=lambda neighbor: (
                    neighbor.edge_kind,
                    neighbor.ref,
                    repr(neighbor.edge_props.get("src_seq")),
                    neighbor.direction,
                ),
            )

        return self._execute("neighbors", _read)


class FakeGraph:
    """Deterministic in-memory adapter used to navigate projection topology in Tier-0."""

    def __init__(self):
        self._nodes = {}
        self._edges = {}
        self._failure_after = None
        self._operations_since_arm = 0

    def fail_after(self, successful_operations):
        """Arm a one-shot outage after ``successful_operations`` more port calls.

        ``fail_after(0)`` fails the next call.  The failure disarms itself so a
        following reprojection can demonstrate convergence without rebuilding the fake.
        """
        if not isinstance(successful_operations, int) or successful_operations < 0:
            raise ValueError("successful_operations must be a non-negative integer")
        self._failure_after = successful_operations
        self._operations_since_arm = 0

    def clear_failure(self):
        self._failure_after = None
        self._operations_since_arm = 0

    def _before_operation(self, operation):
        if (
            self._failure_after is not None
            and self._operations_since_arm >= self._failure_after
        ):
            self.clear_failure()
            raise GraphUnavailable(f"programmed graph failure before {operation}")
        self._operations_since_arm += 1

    @staticmethod
    def _required_name(value, field):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-blank string")
        return value

    def _require_node(self, ref):
        node = self._nodes.get(ref)
        if node is None:
            raise ValueError(f"missing graph node: {ref}")
        return node

    def _canonical_node(self, ref):
        seen = set()
        current_ref = ref
        while True:
            node = self._nodes.get(current_ref)
            if node is None or current_ref in seen:
                return None
            seen.add(current_ref)
            if (node["invalidated_at"] is not None
                    or node["props"].get("archived") is True):
                return None
            target = node["props"].get("merged_into")
            if target is None:
                return current_ref, node
            if not isinstance(target, str) or not target.strip():
                return None
            matches = [
                (candidate_ref, candidate)
                for candidate_ref, candidate in self._nodes.items()
                if target in (
                    candidate_ref,
                    candidate["props"].get("ref"),
                    candidate["props"].get("uuid"),
                    candidate["props"].get("name"),
                    candidate["props"].get("curated_name"),
                )
            ]
            if len(matches) != 1:
                return None
            current_ref, node = matches[0]

    def merge_node(self, ref, label, props=None):
        self._before_operation("merge_node")
        self._required_name(ref, "ref")
        self._required_name(label, "label")
        incoming = _node_properties(props)
        current = self._nodes.get(ref)
        if current is None:
            self._nodes[ref] = {
                "label": label,
                "props": incoming,
                "invalidated_at": None,
            }
            return
        if current["label"] != label:
            raise ValueError(
                f"graph node {ref} already has label {current['label']}, cannot merge {label}"
            )
        current["props"].update(incoming)

    def merge_edge(self, src_ref, edge_kind, dst_ref, props=None):
        self._before_operation("merge_edge")
        self._required_name(src_ref, "src_ref")
        self._required_name(dst_ref, "dst_ref")
        self._required_name(edge_kind, "edge_kind")
        self._require_node(src_ref)
        self._require_node(dst_ref)
        incoming = _edge_properties(props)
        key = (src_ref, edge_kind, dst_ref, incoming.get("src_seq"))
        current = self._edges.get(key)
        if current is None:
            self._edges[key] = {
                "src_ref": src_ref,
                "edge_kind": edge_kind,
                "dst_ref": dst_ref,
                "props": incoming,
                "invalidated_at": None,
            }
            return
        current["props"].update(incoming)

    def replace_edges(self, owner_ref, edge_kind, desired, as_of=None):
        self._before_operation("replace_edges")
        self._required_name(owner_ref, "owner_ref")
        self._required_name(edge_kind, "edge_kind")
        self._require_node(owner_ref)
        raw_wanted = list(desired)
        wanted = []
        for edge in raw_wanted:
            if not isinstance(edge, EdgeSpec):
                raise TypeError("desired edges must be EdgeSpec values")
            self._required_name(edge.dst_ref, "dst_ref")
            self._require_node(edge.dst_ref)
            wanted.append((edge.dst_ref, _edge_properties(edge.props)))

        stale = [
            key
            for key, edge in self._edges.items()
            if edge["src_ref"] == owner_ref and edge["edge_kind"] == edge_kind
        ]
        for key in stale:
            del self._edges[key]
        for dst_ref, incoming in wanted:
            key = (owner_ref, edge_kind, dst_ref, incoming["src_seq"])
            self._edges[key] = {
                "src_ref": owner_ref,
                "edge_kind": edge_kind,
                "dst_ref": dst_ref,
                "props": incoming,
                "invalidated_at": None,
            }

    def invalidate(self, ref, as_of=None):
        self._before_operation("invalidate")
        node = self._require_node(ref)
        invalidated_at = as_of if as_of is not None else True
        node["invalidated_at"] = invalidated_at
        for edge in self._edges.values():
            if edge["src_ref"] == ref or edge["dst_ref"] == ref:
                edge["invalidated_at"] = invalidated_at

    def neighbors(self, ref, edge_kind=None, direction="both"):
        self._before_operation("neighbors")
        anchor = self._require_node(ref)
        if (anchor["invalidated_at"] is not None
                or anchor["props"].get("archived") is True
                or anchor["props"].get("merged_into") is not None):
            return []
        if direction not in {"in", "out", "both"}:
            raise ValueError("direction must be 'in', 'out', or 'both'")
        if edge_kind is not None:
            self._required_name(edge_kind, "edge_kind")

        found = []
        for edge in self._edges.values():
            if edge["invalidated_at"] is not None:
                continue
            if edge_kind is not None and edge["edge_kind"] != edge_kind:
                continue
            hops = []
            if direction in {"out", "both"} and edge["src_ref"] == ref:
                hops.append((edge["dst_ref"], "out"))
            if direction in {"in", "both"} and edge["dst_ref"] == ref:
                hops.append((edge["src_ref"], "in"))
            for neighbor_ref, hop_direction in hops:
                resolved = self._canonical_node(neighbor_ref)
                if resolved is None:
                    continue
                neighbor_ref, node = resolved
                found.append(
                    GraphNeighbor(
                        ref=neighbor_ref,
                        label=node["label"],
                        node_props=deepcopy(node["props"]),
                        edge_kind=edge["edge_kind"],
                        edge_props=deepcopy(edge["props"]),
                        direction=hop_direction,
                    )
                )
        return sorted(
            found,
            key=lambda n: (
                n.edge_kind,
                n.ref,
                repr(n.edge_props.get("src_seq")),
                n.direction,
            ),
        )
