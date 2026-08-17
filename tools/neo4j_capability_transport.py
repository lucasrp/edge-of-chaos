"""Bounded Unix-domain transport for the local capability broker.

The transport is deliberately credential-agnostic.  Filesystem mode and SO_PEERCRED restrict the
socket to the owning OS user, but they do not authorize individual agent dispatches.  Dispatch
capabilities are a later work package and remain a required gate before deployment.
"""
import json
import os
from pathlib import Path
import socket
import stat
import struct

from neo4j_capability_protocol import PROTOCOL_VERSION


MAX_FRAME_BYTES = 128 * 1024
DEFAULT_TIMEOUT_SECONDS = 2.0


class TransportError(RuntimeError):
    """A local transport failure that never triggers a direct-Neo4j fallback."""


def _error(code, message):
    return {
        "version": PROTOCOL_VERSION,
        "request_id": None,
        "ok": False,
        "error": {"code": code, "message": message},
    }


def _receive_frame(conn, maximum=MAX_FRAME_BYTES):
    chunks = []
    size = 0
    while True:
        chunk = conn.recv(min(4096, maximum + 1 - size))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        if size > maximum:
            raise TransportError("frame exceeds byte limit")
        if b"\n" in chunk:
            break
    raw = b"".join(chunks)
    if not raw:
        raise TransportError("empty frame")
    line, separator, trailing = raw.partition(b"\n")
    if not separator:
        raise TransportError("unterminated frame")
    if trailing.strip():
        raise TransportError("multiple frames are not allowed per connection")
    return line


def _send_frame(conn, value):
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
    if len(raw) > MAX_FRAME_BYTES:
        raw = json.dumps(
            _error("response_too_large", "broker response unavailable"), separators=(",", ":")
        ).encode() + b"\n"
    conn.sendall(raw)


def _peer_uid(conn):
    if not hasattr(socket, "SO_PEERCRED"):
        raise TransportError("peer credential checks are unavailable")
    raw = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    _pid, uid, _gid = struct.unpack("3i", raw)
    return uid


class UnixBrokerServer:
    """Bind a private Unix socket and serve bounded one-request connections."""

    def __init__(self, socket_path, handler, *, timeout=DEFAULT_TIMEOUT_SECONDS, owner_uid=None):
        self.path = Path(socket_path)
        self.handler = handler
        self.timeout = float(timeout)
        self.owner_uid = os.getuid() if owner_uid is None else int(owner_uid)
        self._socket = None

    def bind(self):
        parent = self.path.parent
        if not parent.exists() or not parent.is_dir() or parent.is_symlink():
            raise TransportError("socket directory must be an existing real directory")
        parent_stat = parent.stat()
        if parent_stat.st_uid != self.owner_uid:
            raise TransportError("socket directory has the wrong owner")
        if stat.S_IMODE(parent_stat.st_mode) & 0o077:
            raise TransportError("socket directory must not grant group or other access")
        if self.path.exists() or self.path.is_symlink():
            raise TransportError("socket path already exists")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.settimeout(self.timeout)
            server.bind(str(self.path))
            os.chmod(self.path, 0o600)
            server.listen(4)
        except Exception:
            server.close()
            try:
                if self.path.is_socket():
                    self.path.unlink()
            except OSError:
                pass
            raise
        self._socket = server
        return self

    def serve_once(self):
        if self._socket is None:
            raise TransportError("server is not bound")
        conn, _address = self._socket.accept()
        with conn:
            conn.settimeout(self.timeout)
            if _peer_uid(conn) != self.owner_uid:
                _send_frame(conn, _error("peer_denied", "peer is not allowed"))
                return
            try:
                raw = _receive_frame(conn)
                request = json.loads(raw)
                if not isinstance(request, dict):
                    raise TransportError("request must be an object")
                response = self.handler(request)
            except (UnicodeDecodeError, json.JSONDecodeError, TransportError):
                response = _error("invalid_frame", "invalid local broker frame")
            except Exception:
                response = _error("handler_unavailable", "broker handler unavailable")
            _send_frame(conn, response)

    def close(self):
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        try:
            if self.path.is_socket():
                self.path.unlink()
        except OSError:
            pass

    def __enter__(self):
        return self.bind()

    def __exit__(self, _kind, _value, _traceback):
        self.close()


def call_unix(socket_path, request, *, timeout=DEFAULT_TIMEOUT_SECONDS):
    """Make one bounded call; outage raises TransportError and has no fallback path."""
    path = Path(socket_path)
    raw = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
    if len(raw) > MAX_FRAME_BYTES:
        raise TransportError("request exceeds byte limit")
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.settimeout(float(timeout))
        client.connect(str(path))
        client.sendall(raw)
        line = _receive_frame(client)
        value = json.loads(line)
        if not isinstance(value, dict):
            raise TransportError("response must be an object")
        return value
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TransportError) as exc:
        raise TransportError("local capability broker unavailable") from exc
    finally:
        client.close()
