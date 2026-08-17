"""Credential-free MCP adapter for the local capability broker.

The adapter knows only a Unix socket, a dispatch ID, and a low-authority capability.  It imports no
Neo4j, identity, secret-loader, recall, or graph module.  The reviewed design uses pragmatic
environment delivery after the FD experiment proved the parent agent could read either form.  It pops
the capability from its own environment immediately; the grant is revoked by the owning lease.
"""
import json
import os
import sys

from neo4j_capability_protocol import PROTOCOL_VERSION
from neo4j_capability_transport import TransportError, call_unix


MCP_PROTOCOL_VERSION = "2024-11-05"
MAX_CAPABILITY_BYTES = 256

_TOOLS = [
    {"name": "cortex_recall", "description": "Read the bounded salient Cortex seed.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "cortex_surf", "description": "Walk one or two bounded typed hops.",
     "inputSchema": {"type": "object", "properties": {
         "seeds": {"type": "array", "items": {"type": "string"}},
         "hops": {"type": "integer"}}, "required": ["seeds"]}},
    {"name": "cortex_node", "description": "Read one bounded node neighborhood.",
     "inputSchema": {"type": "object", "properties": {"ref": {"type": "string"}},
                     "required": ["ref"]}},
    {"name": "cortex_search", "description": "Run one bounded Cortex text lookup.",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string"}, "limit": {"type": "integer"}},
                     "required": ["query"]}},
    {"name": "cortex_health", "description": "Read boolean broker readiness.",
     "inputSchema": {"type": "object", "properties": {}}},
]
_TOOL_TO_OPERATION = {
    "cortex_recall": "recall", "cortex_surf": "surf", "cortex_node": "node",
    "cortex_search": "search", "cortex_health": "health",
}


def read_capability_fd(fd):
    """Read one bounded ASCII capability, close the descriptor, and never reflect its value."""
    try:
        fd = int(fd)
        if fd < 3:
            raise ValueError
        raw = os.read(fd, MAX_CAPABILITY_BYTES + 1)
    except (OSError, TypeError, ValueError) as exc:
        raise RuntimeError("capability descriptor unavailable") from exc
    finally:
        try:
            if isinstance(fd, int) and fd >= 3:
                os.close(fd)
        except OSError:
            pass
    if len(raw) > MAX_CAPABILITY_BYTES:
        raise RuntimeError("capability descriptor exceeds limit")
    try:
        token = raw.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise RuntimeError("capability descriptor is invalid") from exc
    if len(token) < 32:
        raise RuntimeError("capability descriptor is invalid")
    return token


class CapabilityMCP:
    def __init__(self, *, socket_path, dispatch_id, capability, call=None):
        if not all(isinstance(value, str) and value for value in
                   (socket_path, dispatch_id, capability)):
            raise ValueError("MCP adapter requires socket, dispatch, and capability")
        self.socket_path = str(socket_path)
        self.dispatch_id = dispatch_id
        self.capability = capability
        self._call = call or call_unix
        self._sequence = 0

    def handle(self, message):
        if not isinstance(message, dict):
            return self._error(None, -32600, "invalid request")
        if "id" not in message:
            return None
        mid = message.get("id")
        method = message.get("method")
        if method == "initialize":
            return self._ok(mid, {"protocolVersion": MCP_PROTOCOL_VERSION,
                                  "capabilities": {"tools": {}},
                                  "serverInfo": {"name": "cortex-broker", "version": "1"}})
        if method == "tools/list":
            return self._ok(mid, {"tools": _TOOLS})
        if method != "tools/call":
            return self._error(mid, -32601, "method not found")
        params = message.get("params")
        if not isinstance(params, dict) or params.get("name") not in _TOOL_TO_OPERATION:
            return self._error(mid, -32602, "invalid tool request")
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            return self._error(mid, -32602, "invalid tool arguments")
        self._sequence += 1
        request = {
            "version": PROTOCOL_VERSION,
            # Unique within this per-dispatch adapter. Do not concatenate the dispatch ID: both are
            # independently bounded and a long valid dispatch ID could exceed the protocol's ID cap.
            "request_id": f"mcp-{self._sequence}",
            "operation": _TOOL_TO_OPERATION[params["name"]],
            "arguments": arguments,
        }
        envelope = {"capability": self.capability, "dispatch_id": self.dispatch_id,
                    "request": request}
        try:
            result = self._call(self.socket_path, envelope)
        except TransportError:
            result = {"version": PROTOCOL_VERSION, "request_id": request["request_id"],
                      "ok": False,
                      "error": {"code": "broker_unavailable", "message": "cortex is dark"}}
        domain = result.get("result") if result.get("ok") else {
            "dark": True, "leg": "cortex", "reason": result.get("error", {}).get(
                "code", "broker_unavailable")
        }
        return self._ok(mid, {
            "content": [{"type": "text", "text": json.dumps(domain)}],
            "structuredContent": domain,
            "isError": not bool(result.get("ok")),
        })

    @staticmethod
    def _ok(mid, result):
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    @staticmethod
    def _error(mid, code, message):
        return {"jsonrpc": "2.0", "id": mid,
                "error": {"code": code, "message": message}}


def serve_stdio(adapter):
    for line in sys.stdin:
        try:
            message = json.loads(line)
            response = adapter.handle(message)
        except Exception:
            response = {"jsonrpc": "2.0", "id": None,
                        "error": {"code": -32700, "message": "parse error"}}
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


def main():
    token = os.environ.pop("EDGE_BROKER_CAPABILITY", None)
    if not token:
        raise RuntimeError("broker capability is absent")
    adapter = CapabilityMCP(
        socket_path=os.environ.get("EDGE_BROKER_SOCKET"),
        dispatch_id=os.environ.get("EDGE_DISPATCH_PLAN_ID"),
        capability=token,
    )
    serve_stdio(adapter)


if __name__ == "__main__":
    main()
