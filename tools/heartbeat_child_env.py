"""Explicit environment allowlist for a future hardened heartbeat child.

This is not wired into ``edge-heartbeat`` yet.  It is a pure builder so the secret-removal contract
can be tested before any live launch or compatibility decision.
"""
import re


_BASE_NAMES = frozenset({
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "TZ", "TERM", "COLORTERM",
    "NO_COLOR", "CODEX_HOME", "XDG_RUNTIME_DIR", "TMPDIR", "SSL_CERT_FILE", "SSL_CERT_DIR",
})
_EDGE_NAMES = frozenset({
    "EDGE_DISPATCH_PLAN", "EDGE_DISPATCH_PLAN_ID", "EDGE_BEAT_CLI",
    "EDGE_BROKER_SOCKET", "EDGE_CAPABILITY_FD", "EDGE_BROKER_CAPABILITY",
    "EDGE_RUNTIME_ROOT",
})
_DENIED_NAME = re.compile(
    r"(?:PASSWORD|PASSWD|SECRET|TOKEN|CREDENTIAL|AUTHORIZATION|API_KEY|PRIVATE_KEY|"
    r"SSH_AUTH_SOCK|DOCKER_HOST|OP_SERVICE_ACCOUNT_TOKEN)", re.IGNORECASE,
)


def _allowed_name(name):
    return name in _BASE_NAMES or name in _EDGE_NAMES or name.startswith("LC_")


def build_hardened_child_env(base=None, *, required=None):
    """Copy only named non-secret process settings and explicit safe dispatch metadata."""
    base = dict(base or {})
    required = dict(required or {})
    output = {}
    for name, value in base.items():
        if _allowed_name(name) and not _DENIED_NAME.search(name) and isinstance(value, str):
            output[name] = value
    for name, value in required.items():
        if not _allowed_name(name) or _DENIED_NAME.search(name):
            raise ValueError(f"required environment name is not allowed: {name}")
        if not isinstance(value, str) or "\x00" in value:
            raise ValueError(f"required environment value is invalid: {name}")
        output[name] = value
    return output
