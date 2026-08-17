"""Transport-free core of the local, read-only Neo4j capability broker.

The core owns a fixed group and an injected backend.  Production credential loading, Unix socket
transport, dispatch capabilities, and systemd lifecycle are intentionally absent from this package.
That makes the first security proof hermetic and prevents this module from being mistaken for a
deployable service before later gates pass.
"""
import json
import re
import time

from neo4j_capability_protocol import PROTOCOL_VERSION, ProtocolError, validate_request


MAX_DEPTH = 8
MAX_CONTAINER_ITEMS = 100
MAX_STRING_LENGTH = 4096
MAX_RESPONSE_BYTES = 64 * 1024

_SENSITIVE_KEY = re.compile(
    r"(?:password|passwd|secret|token|credential|authorization|api[_-]?key|private[_-]?key)",
    re.IGNORECASE,
)
_SENSITIVE_VALUE = re.compile(
    r"(?:EDGE_NEO4J_PASSWORD\s*=|neo4j(?:\+s|\+ssc|\+bolt)?://[^\s]*@|"
    r"(?:password|passwd|secret|token|api[_-]?key)\s*[:=]\s*\S+)",
    re.IGNORECASE,
)
_PRIVATE_PATH = re.compile(
    r"(?:^|\s)/home/[^/\s]+/(?:[^\s]*/)?(?:\.ssh|\.config/op|secrets)(?:/\S*)?"
)


class BrokerError(RuntimeError):
    """A bounded broker failure that does not expose backend exception text."""


def _sanitize(value, depth=0):
    if depth > MAX_DEPTH:
        return "[TRUNCATED_DEPTH]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        text = value[:MAX_STRING_LENGTH]
        if _SENSITIVE_VALUE.search(text) or _PRIVATE_PATH.search(text):
            return "[REDACTED]"
        return text
    if isinstance(value, dict):
        out = {}
        for key, item in list(value.items())[:MAX_CONTAINER_ITEMS]:
            safe_key = str(key)[:128]
            if _SENSITIVE_KEY.search(safe_key):
                continue
            out[safe_key] = _sanitize(item, depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [_sanitize(item, depth + 1) for item in list(value)[:MAX_CONTAINER_ITEMS]]
    return str(value)[:MAX_STRING_LENGTH]


class CapabilityBroker:
    """Execute a closed read operation against a backend under one immutable graph group."""

    def __init__(self, *, group, backend, audit=None, clock=None):
        if not isinstance(group, str) or not group.strip():
            raise ValueError("broker requires a fixed non-empty group")
        self._group = group
        self._backend = backend
        self._audit = audit or (lambda event: None)
        self._clock = clock or time.monotonic

    def handle(self, raw_request):
        started = self._clock()
        request_id = raw_request.get("request_id") if isinstance(raw_request, dict) else None
        operation = raw_request.get("operation") if isinstance(raw_request, dict) else None
        try:
            request = validate_request(raw_request)
            payload = self._execute(request.operation, request.arguments)
            safe_payload = _sanitize(payload)
            response = {
                "version": PROTOCOL_VERSION,
                "request_id": request.request_id,
                "ok": True,
                "result": safe_payload,
            }
            encoded = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode()
            if len(encoded) > MAX_RESPONSE_BYTES:
                raise BrokerError("response exceeds broker byte limit")
            self._record(request.request_id, request.operation, "ok", started, len(encoded))
            return response
        except ProtocolError as exc:
            response = self._error(request_id, "invalid_request", str(exc))
            self._record(request_id, operation, "invalid_request", started, self._size(response))
            return response
        except BrokerError:
            response = self._error(request_id, "bounded_failure", "broker result unavailable")
            self._record(request_id, operation, "bounded_failure", started, self._size(response))
            return response
        except Exception as exc:  # backend details must not cross the boundary
            response = self._error(request_id, "backend_unavailable", "graph memory is dark")
            self._record(request_id, operation, "backend_unavailable", started,
                         self._size(response), error_type=type(exc).__name__)
            return response

    def _execute(self, operation, arguments):
        if operation == "health":
            return {"ready": bool(self._backend.health(group=self._group)),
                    "protocol": PROTOCOL_VERSION}
        if operation == "recall":
            return self._backend.recall(group=self._group)
        if operation == "surf":
            return self._backend.surf(group=self._group, **arguments)
        if operation == "node":
            return self._backend.node(group=self._group, **arguments)
        if operation == "search":
            return self._backend.search(group=self._group, **arguments)
        raise BrokerError("unreachable operation")

    @staticmethod
    def _error(request_id, code, message):
        return {
            "version": PROTOCOL_VERSION,
            "request_id": request_id if isinstance(request_id, str) else None,
            "ok": False,
            "error": {"code": code, "message": message},
        }

    @staticmethod
    def _size(value):
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())

    def _record(self, request_id, operation, outcome, started, response_bytes, error_type=None):
        event = {
            "request_id": request_id if isinstance(request_id, str) else None,
            "operation": operation if operation in {"health", "recall", "surf", "node", "search"}
            else None,
            "outcome": outcome,
            "duration_ms": max(0, round((self._clock() - started) * 1000, 3)),
            "response_bytes": response_bytes,
        }
        if error_type:
            event["error_type"] = error_type
        try:
            self._audit(event)
        except Exception:
            # Audit is metadata-only and best-effort in this transport-free core. A later service
            # wrapper will own durable receipts; its outage must not expose backend details here.
            pass
