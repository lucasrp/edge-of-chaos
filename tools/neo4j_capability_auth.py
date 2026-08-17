"""Hermetic per-dispatch authorization for the local capability broker.

The store retains only SHA-256 digests of high-entropy bearer capabilities.  It binds each grant to
one dispatch, a subset of the closed read operations, expiry, call budget, response-byte budget,
and one-use request IDs.  Persistence and private-FD delivery are intentionally later gates.
"""
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import re
import secrets
import threading
import time

from neo4j_capability_protocol import PROTOCOL_VERSION, operation_names


MAX_TTL_SECONDS = 3600
MAX_CALL_BUDGET = 100
MAX_BYTE_BUDGET = 4 * 1024 * 1024
MAX_DISPATCH_ID = 128
_ENVELOPE_FIELDS = frozenset({"capability", "dispatch_id", "request"})
_SAFE_AUDIT_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class AuthorizationError(RuntimeError):
    """A generic authorization denial; details stay inside the broker boundary."""


@dataclass
class _Grant:
    dispatch_id: str
    operations: frozenset
    expires_at: float
    calls_remaining: int
    bytes_remaining: int
    request_ids: set = field(default_factory=set)
    revoked: bool = False


def _digest(token):
    return hashlib.sha256(token.encode("ascii")).digest()


def _bounded_positive_integer(value, label, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"{label} must be between 1 and {maximum}")
    return value


class CapabilityAuthority:
    """Issue and consume in-memory grants; raw capabilities are never retained."""

    def __init__(self, *, clock=None, token_factory=None):
        self._clock = clock or time.monotonic
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
        self._grants = {}
        self._lock = threading.Lock()

    def issue(self, *, dispatch_id, operations, ttl_seconds, call_budget, byte_budget):
        if not isinstance(dispatch_id, str) or not dispatch_id.strip() or len(dispatch_id) > MAX_DISPATCH_ID:
            raise ValueError("dispatch_id must be a bounded non-empty string")
        requested = frozenset(operations)
        if not requested or not requested <= operation_names():
            raise ValueError("operations must be a non-empty subset of the broker allowlist")
        ttl = _bounded_positive_integer(ttl_seconds, "ttl_seconds", MAX_TTL_SECONDS)
        calls = _bounded_positive_integer(call_budget, "call_budget", MAX_CALL_BUDGET)
        byte_limit = _bounded_positive_integer(byte_budget, "byte_budget", MAX_BYTE_BUDGET)
        token = self._token_factory()
        if not isinstance(token, str) or len(token) < 32 or not token.isascii():
            raise ValueError("token factory returned an invalid capability")
        fingerprint = _digest(token)
        with self._lock:
            if fingerprint in self._grants:
                raise ValueError("token factory produced a duplicate capability")
            self._grants[fingerprint] = _Grant(
                dispatch_id=dispatch_id,
                operations=requested,
                expires_at=self._clock() + ttl,
                calls_remaining=calls,
                bytes_remaining=byte_limit,
            )
        return token

    def begin(self, *, token, dispatch_id, operation, request_id):
        """Authorize and reserve one unique call before any backend work occurs."""
        if not all(isinstance(item, str) and item for item in
                   (token, dispatch_id, operation, request_id)):
            raise AuthorizationError("capability denied")
        fingerprint = _digest(token) if token.isascii() else b""
        with self._lock:
            grant = self._grants.get(fingerprint)
            if grant is None or grant.revoked or self._clock() >= grant.expires_at:
                raise AuthorizationError("capability denied")
            if not hmac.compare_digest(grant.dispatch_id, dispatch_id):
                raise AuthorizationError("capability denied")
            if operation not in grant.operations or request_id in grant.request_ids:
                raise AuthorizationError("capability denied")
            if grant.calls_remaining <= 0 or grant.bytes_remaining <= 0:
                raise AuthorizationError("capability denied")
            grant.calls_remaining -= 1
            grant.request_ids.add(request_id)
        return fingerprint

    def finish(self, fingerprint, *, response_bytes):
        """Charge output bytes; over-budget output is denied and the grant is exhausted."""
        if isinstance(response_bytes, bool) or not isinstance(response_bytes, int) or response_bytes < 0:
            raise ValueError("response_bytes must be a non-negative integer")
        with self._lock:
            grant = self._grants.get(fingerprint)
            if grant is None or grant.revoked or self._clock() >= grant.expires_at:
                raise AuthorizationError("capability denied")
            if response_bytes > grant.bytes_remaining:
                grant.bytes_remaining = 0
                raise AuthorizationError("capability denied")
            grant.bytes_remaining -= response_bytes

    def revoke(self, token):
        if not isinstance(token, str) or not token.isascii():
            return False
        with self._lock:
            grant = self._grants.get(_digest(token))
            if grant is None:
                return False
            grant.revoked = True
            return True

    def snapshot(self, token):
        """Sanitized test/operator metadata; never returns the token or its digest."""
        if not isinstance(token, str) or not token.isascii():
            return None
        with self._lock:
            grant = self._grants.get(_digest(token))
            if grant is None:
                return None
            return {
                "dispatch_id": grant.dispatch_id,
                "operations": sorted(grant.operations),
                "expires_at": grant.expires_at,
                "calls_remaining": grant.calls_remaining,
                "bytes_remaining": grant.bytes_remaining,
                "used_request_count": len(grant.request_ids),
                "revoked": grant.revoked,
            }


def _denied(request_id=None):
    return {
        "version": PROTOCOL_VERSION,
        "request_id": request_id if isinstance(request_id, str) else None,
        "ok": False,
        "error": {"code": "capability_denied", "message": "capability denied"},
    }


class AuthorizedBroker:
    """Authorize an envelope, invoke the bounded core, then charge serialized response bytes."""

    def __init__(self, core, authority, *, audit=None):
        self._core = core
        self._authority = authority
        self._audit = audit or (lambda event: None)

    def handle(self, envelope):
        request = envelope.get("request") if isinstance(envelope, dict) else None
        request_id = request.get("request_id") if isinstance(request, dict) else None
        operation = request.get("operation") if isinstance(request, dict) else None
        dispatch_id = envelope.get("dispatch_id") if isinstance(envelope, dict) else None
        try:
            if not isinstance(envelope, dict) or set(envelope) != _ENVELOPE_FIELDS:
                raise AuthorizationError("capability denied")
            token = envelope.get("capability")
            fingerprint = self._authority.begin(
                token=token,
                dispatch_id=dispatch_id,
                operation=operation,
                request_id=request_id,
            )
            response = self._core.handle(request)
            size = len(json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode())
            self._authority.finish(fingerprint, response_bytes=size)
            self._record(dispatch_id, request_id, operation, "allowed", size)
            return response
        except AuthorizationError:
            response = _denied(request_id)
            self._record(dispatch_id, request_id, operation, "denied", 0)
            return response
        except Exception:
            response = _denied(request_id)
            self._record(dispatch_id, request_id, operation, "denied", 0)
            return response

    def _record(self, dispatch_id, request_id, operation, outcome, response_bytes):
        event = {
            "dispatch_id": dispatch_id if isinstance(dispatch_id, str)
            and _SAFE_AUDIT_ID.fullmatch(dispatch_id) else None,
            "request_id": request_id if isinstance(request_id, str)
            and _SAFE_AUDIT_ID.fullmatch(request_id) else None,
            "operation": operation if operation in operation_names() else None,
            "outcome": outcome,
            "response_bytes": response_bytes,
        }
        try:
            self._audit(event)
        except Exception:
            pass
