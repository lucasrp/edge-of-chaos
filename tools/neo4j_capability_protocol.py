"""Closed protocol for the local Neo4j capability broker.

This module is deliberately pure: it imports no graph, identity, secret, socket, or agent code.
The agent can request named reads; it cannot submit Cypher, choose a group, name a path, or request
a mutation.  Live transport and credential ownership belong to later work packages.
"""
from dataclasses import dataclass
import re


PROTOCOL_VERSION = "edge.neo4j-capability/v1"
MAX_REQUEST_ID = 128
MAX_SEEDS = 8
MAX_SEED_LENGTH = 128
MAX_REF_LENGTH = 256
MAX_QUERY_LENGTH = 256
MAX_SEARCH_RESULTS = 25


class ProtocolError(ValueError):
    """A fail-closed request validation error safe to return to a local client."""


@dataclass(frozen=True)
class CapabilityRequest:
    request_id: str
    operation: str
    arguments: dict


_OPERATIONS = frozenset({"health", "recall", "surf", "node", "search"})
_REQUEST_FIELDS = frozenset({"version", "request_id", "operation", "arguments"})
_ARG_FIELDS = {
    "health": frozenset(),
    "recall": frozenset(),
    "surf": frozenset({"seeds", "hops"}),
    "node": frozenset({"ref"}),
    "search": frozenset({"query", "limit"}),
}
_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]+$")


def operation_names():
    """Return the immutable public operation allowlist."""
    return _OPERATIONS


def _exact_fields(value, allowed, label):
    unknown = set(value) - set(allowed)
    if unknown:
        # Do not reflect model-controlled field names: a malicious key could itself carry a secret.
        raise ProtocolError(f"{label} contains unknown fields")


def _bounded_string(value, label, maximum, *, nonempty=True):
    if not isinstance(value, str):
        raise ProtocolError(f"{label} must be a string")
    if nonempty and not value.strip():
        raise ProtocolError(f"{label} must not be empty")
    if len(value) > maximum:
        raise ProtocolError(f"{label} exceeds {maximum} characters")
    return value


def validate_request(value):
    """Validate and normalize one request without accepting ambient authority fields."""
    if not isinstance(value, dict):
        raise ProtocolError("request must be an object")
    _exact_fields(value, _REQUEST_FIELDS, "request")
    if set(value) != _REQUEST_FIELDS:
        missing = _REQUEST_FIELDS - set(value)
        raise ProtocolError(f"request missing fields: {', '.join(sorted(missing))}")
    if value["version"] != PROTOCOL_VERSION:
        raise ProtocolError("unsupported protocol version")

    request_id = _bounded_string(value["request_id"], "request_id", MAX_REQUEST_ID)
    if not _SAFE_ID.fullmatch(request_id):
        raise ProtocolError("request_id contains unsupported characters")
    operation = value["operation"]
    if operation not in _OPERATIONS:
        raise ProtocolError("operation is not allowed")
    arguments = value["arguments"]
    if not isinstance(arguments, dict):
        raise ProtocolError("arguments must be an object")
    _exact_fields(arguments, _ARG_FIELDS[operation], "arguments")

    normalized = {}
    if operation == "surf":
        seeds = arguments.get("seeds")
        if not isinstance(seeds, list) or not seeds or len(seeds) > MAX_SEEDS:
            raise ProtocolError(f"seeds must contain between 1 and {MAX_SEEDS} strings")
        normalized["seeds"] = [
            _bounded_string(seed, "seed", MAX_SEED_LENGTH) for seed in seeds
        ]
        hops = arguments.get("hops", 2)
        if isinstance(hops, bool) or not isinstance(hops, int) or hops not in (1, 2):
            raise ProtocolError("hops must be 1 or 2")
        normalized["hops"] = hops
    elif operation == "node":
        normalized["ref"] = _bounded_string(arguments.get("ref"), "ref", MAX_REF_LENGTH)
    elif operation == "search":
        normalized["query"] = _bounded_string(
            arguments.get("query"), "query", MAX_QUERY_LENGTH
        )
        limit = arguments.get("limit", 12)
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ProtocolError("limit must be an integer")
        if not 1 <= limit <= MAX_SEARCH_RESULTS:
            raise ProtocolError(f"limit must be between 1 and {MAX_SEARCH_RESULTS}")
        normalized["limit"] = limit

    return CapabilityRequest(request_id=request_id, operation=operation, arguments=normalized)
