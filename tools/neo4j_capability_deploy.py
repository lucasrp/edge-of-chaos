"""Pure deployment rendering and one-shot bootstrap for the local broker."""
from pathlib import Path
import re

from neo4j_capability_protocol import PROTOCOL_VERSION, operation_names
from neo4j_capability_transport import TransportError, call_unix


BOOTSTRAP_VERSION = "edge.neo4j-capability-bootstrap/v1"
DEFAULT_OPERATIONS = frozenset(operation_names())
DEFAULT_TTL_SECONDS = 600
DEFAULT_CALL_BUDGET = 40
DEFAULT_BYTE_BUDGET = 512 * 1024
_SAFE_DISPATCH = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class OneShotBootstrap:
    """Issue exactly one bounded grant, then remain permanently closed."""

    def __init__(self, authority):
        self.authority = authority
        self.closed = False

    def handle(self, request):
        if self.closed:
            return _bootstrap_error("bootstrap_closed")
        if not isinstance(request, dict) or set(request) != {"version", "dispatch_id"}:
            return _bootstrap_error("invalid_bootstrap")
        dispatch_id = request.get("dispatch_id")
        if request.get("version") != BOOTSTRAP_VERSION or not isinstance(dispatch_id, str) \
                or not _SAFE_DISPATCH.fullmatch(dispatch_id):
            return _bootstrap_error("invalid_bootstrap")
        # Close before issuing: even an unexpected issuance failure cannot reopen this process.
        self.closed = True
        try:
            token = self.authority.issue(
                dispatch_id=dispatch_id,
                operations=DEFAULT_OPERATIONS,
                ttl_seconds=DEFAULT_TTL_SECONDS,
                call_budget=DEFAULT_CALL_BUDGET,
                byte_budget=DEFAULT_BYTE_BUDGET,
            )
        except Exception:
            return _bootstrap_error("bootstrap_failed")
        return {
            "version": BOOTSTRAP_VERSION,
            "ok": True,
            "dispatch_id": dispatch_id,
            "capability": token,
            "broker_protocol": PROTOCOL_VERSION,
            "limits": {"ttl_seconds": DEFAULT_TTL_SECONDS,
                       "call_budget": DEFAULT_CALL_BUDGET,
                       "byte_budget": DEFAULT_BYTE_BUDGET,
                       "operations": sorted(DEFAULT_OPERATIONS)},
        }


def _bootstrap_error(code):
    return {"version": BOOTSTRAP_VERSION, "ok": False,
            "error": {"code": code, "message": "bootstrap unavailable"}}


def bootstrap_once(socket_path, dispatch_id, *, call=call_unix):
    """Obtain the one grant without printing or persisting it."""
    if not isinstance(dispatch_id, str) or not _SAFE_DISPATCH.fullmatch(dispatch_id):
        raise ValueError("dispatch_id is invalid")
    try:
        response = call(socket_path, {"version": BOOTSTRAP_VERSION,
                                      "dispatch_id": dispatch_id})
    except TransportError as exc:
        raise RuntimeError("broker bootstrap unavailable") from exc
    if not isinstance(response, dict) or not response.get("ok") \
            or response.get("dispatch_id") != dispatch_id \
            or not isinstance(response.get("capability"), str):
        raise RuntimeError("broker bootstrap denied")
    return response["capability"], dict(response.get("limits") or {})


def render_broker_service(*, edge_home, runtime_name="edge-neo4j-capability-broker"):
    """Render a static user service. No [Install], timer, or heartbeat dependency."""
    home = Path(edge_home)
    if not home.is_absolute() or len(home.parts) < 4:
        raise ValueError("edge_home must be a narrow absolute install path")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", runtime_name):
        raise ValueError("runtime_name contains unsupported characters")
    edge_python = home / "tools" / "edge-python"
    entrypoint = home / "tools" / "edge-neo4j-capability-broker"
    return f"""[Unit]
Description=edge Neo4j read capability broker (static, manual)
After=network.target

[Service]
Type=simple
ExecStart={edge_python} {entrypoint} --home {home} --runtime-dir %t/{runtime_name}
WorkingDirectory={home}
RuntimeDirectory={runtime_name}
RuntimeDirectoryMode=0700
UMask=0077
Restart=no
TimeoutStartSec=30s
TimeoutStopSec=10s
KillMode=control-group
NoNewPrivileges=true
CapabilityBoundingSet=
PrivateTmp=true
PrivateDevices=true
ProtectProc=invisible
ProcSubset=pid
MemoryDenyWriteExecute=true
ProtectSystem=strict
ProtectHome=read-only
ProtectControlGroups=true
ProtectKernelModules=true
ProtectKernelTunables=true
ProtectKernelLogs=true
ProtectClock=true
ProtectHostname=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictRealtime=true
RestrictNamespaces=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
IPAddressDeny=any
IPAddressAllow=localhost
SystemCallArchitectures=native
"""
