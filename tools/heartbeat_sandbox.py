"""Pure policy model for a future OS-sandboxed heartbeat.

This module does not install, start, or enable a service.  It turns one phenotype's
declared paths into a small, auditable policy that a later renderer can consume.
Filesystem enforcement belongs to that later systemd boundary; this module's job is to
fail closed before a broad or ambiguous path reaches it.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any, Iterable

import yaml


POLICY_SCHEMA = "edge.heartbeat-sandbox/v1"
PERSISTENT_BRIDGE_SCHEMA = "edge.persistent-auth-bridge/v1"

# These roots would turn a write allowlist into ambient authority.  Resolve first, then
# compare exactly; descendants such as /home/operator/edge-install remain valid.
_FORBIDDEN_WRITABLE_ROOTS = frozenset({
    Path("/"),
    Path("/home"),
    Path("/mnt"),
    Path("/mnt/c"),
    Path("/tmp"),
    Path("/var"),
})

_FORBIDDEN_PRIVATE_ROOTS = _FORBIDDEN_WRITABLE_ROOTS | frozenset({
    Path("/run"),
    Path("/var/lib"),
})

UNSET_ENVIRONMENT = (
    "SSH_AUTH_SOCK",
    "SSH_AGENT_PID",
    "GIT_SSH",
    "GIT_SSH_COMMAND",
    "OP_SERVICE_ACCOUNT_TOKEN",
    "OP_CONNECT_HOST",
    "OP_CONNECT_TOKEN",
)


class SandboxPolicyError(ValueError):
    """A phenotype cannot be narrowed into a safe filesystem policy."""


def _resolved_absolute(value: str | os.PathLike[str], *, field: str) -> Path:
    if not isinstance(value, (str, os.PathLike)) or not str(value).strip():
        raise SandboxPolicyError(f"{field} must be a non-empty absolute path")
    raw = Path(os.path.expanduser(str(value).strip()))
    if not raw.is_absolute():
        raise SandboxPolicyError(f"{field} must be absolute, got {value!r}")
    return raw.resolve(strict=False)


def validate_writable_root(edge_home: str | os.PathLike[str]) -> Path:
    """Return a canonical install root, rejecting broad or home-level authority."""
    root = _resolved_absolute(edge_home, field="edge_home")
    user_home = Path.home().resolve(strict=False)
    forbidden = _FORBIDDEN_WRITABLE_ROOTS | frozenset({user_home})
    if root in forbidden:
        raise SandboxPolicyError(f"edge_home is too broad for sandbox writes: {root}")
    # Require an install below a stable parent, not a top-level mount or shallow alias.
    if len(root.parts) < 4:
        raise SandboxPolicyError(f"edge_home is too shallow for sandbox writes: {root}")
    return root


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _validate_private_service_path(
    value: str | os.PathLike[str],
    *,
    field: str,
    operator_home: Path,
) -> Path:
    """Validate a narrow service-owned path without creating or inspecting it."""
    if not isinstance(value, (str, os.PathLike)) or not str(value).strip():
        raise SandboxPolicyError(f"{field} must be a non-empty absolute path")
    lexical = Path(os.path.expanduser(str(value).strip()))
    if not lexical.is_absolute():
        raise SandboxPolicyError(f"{field} must be absolute, got {value!r}")
    # Check every existing lexical component before resolve(): resolve would otherwise erase
    # the evidence that a parent redirected the supposedly private boundary elsewhere.
    current = Path(lexical.anchor)
    for part in lexical.parts[1:]:
        current /= part
        if current.is_symlink():
            raise SandboxPolicyError(f"{field} may not contain a symlink: {current}")
    path = lexical.resolve(strict=False)
    if path in _FORBIDDEN_PRIVATE_ROOTS or path == operator_home:
        raise SandboxPolicyError(f"{field} is too broad: {path}")
    if len(path.parts) < 4:
        raise SandboxPolicyError(f"{field} is too shallow: {path}")
    if _is_within(path, Path("/tmp")) or _is_within(path, Path("/mnt")):
        raise SandboxPolicyError(f"{field} may not live in a temporary or mounted tree: {path}")
    return path


def _validate_identity_metadata(metadata: dict[str, Any], *, field: str) -> dict[str, Any]:
    """Validate content-free expected ownership metadata for a future provisioner."""
    if not isinstance(metadata, dict):
        raise SandboxPolicyError(f"{field} metadata must be a mapping")
    owner = metadata.get("owner")
    group = metadata.get("group")
    mode = metadata.get("mode")
    if not isinstance(owner, str) or not owner.strip():
        raise SandboxPolicyError(f"{field} owner must be explicit")
    if not isinstance(group, str) or not group.strip():
        raise SandboxPolicyError(f"{field} group must be explicit")
    if mode not in {"0700", "0600"}:
        raise SandboxPolicyError(f"{field} mode must be 0700 or 0600")
    return {"owner": owner.strip(), "group": group.strip(), "mode": mode}


def build_persistent_bridge_policy(
    cfg: dict[str, Any],
    *,
    edge_home: str | os.PathLike[str],
    runtime_output_root: str | os.PathLike[str],
    codex_home: str | os.PathLike[str],
    service_identity: str,
    runtime_metadata: dict[str, Any],
    codex_home_metadata: dict[str, Any],
    auth_file_metadata: dict[str, Any],
    operator_home: Path | None = None,
    require_sources_exist: bool = True,
) -> dict[str, Any]:
    """Build the pure split-root contract for a future persistent-auth bridge.

    This function performs no provisioning and reads no credential.  It describes the
    immutable phenotype input, the independently writable runtime output, and the private
    Codex home as non-overlapping authorities.  A later work package may render or enforce
    this policy only after the runtime has a supported way to consume the split roots.
    """
    if not isinstance(cfg, dict):
        raise SandboxPolicyError("agent configuration must be a mapping")
    if not isinstance(service_identity, str) or not re.fullmatch(
            r"[a-z_][a-z0-9_-]{0,31}", service_identity):
        raise SandboxPolicyError("service_identity must be a fixed local account name")

    install = validate_writable_root(edge_home)
    home = (operator_home or Path.home()).resolve(strict=False)
    runtime = _validate_private_service_path(
        runtime_output_root, field="runtime_output_root", operator_home=home
    )
    credential_home = _validate_private_service_path(
        codex_home, field="codex_home", operator_home=home
    )

    for field, path in (("runtime_output_root", runtime), ("codex_home", credential_home)):
        if _is_within(path, install) or _is_within(install, path):
            raise SandboxPolicyError(f"{field} overlaps immutable edge_home: {path}")
    if _is_within(runtime, credential_home) or _is_within(credential_home, runtime):
        raise SandboxPolicyError("runtime_output_root and codex_home must not overlap")

    read_only = declared_read_only_roots(
        cfg, writable_root=install, require_exists=require_sources_exist
    )
    for row in read_only:
        source = Path(row["path"])
        for field, private in (
            ("runtime_output_root", runtime), ("codex_home", credential_home)
        ):
            if _is_within(private, source) or _is_within(source, private):
                raise SandboxPolicyError(f"{field} overlaps declared source: {source}")

    runtime_meta = _validate_identity_metadata(runtime_metadata, field="runtime_output_root")
    codex_meta = _validate_identity_metadata(codex_home_metadata, field="codex_home")
    auth_meta = _validate_identity_metadata(auth_file_metadata, field="auth_file")
    for field, meta in (
        ("runtime_output_root", runtime_meta),
        ("codex_home", codex_meta),
        ("auth_file", auth_meta),
    ):
        if meta["owner"] != service_identity or meta["group"] != service_identity:
            raise SandboxPolicyError(f"{field} must belong only to service_identity")
    if runtime_meta["mode"] != "0700" or codex_meta["mode"] != "0700":
        raise SandboxPolicyError("service directories must have mode 0700")
    if auth_meta["mode"] != "0600":
        raise SandboxPolicyError("auth_file must have mode 0600")

    return {
        "schema": PERSISTENT_BRIDGE_SCHEMA,
        "service_identity": service_identity,
        "immutable_input_root": str(install),
        "runtime_output_root": str(runtime),
        "codex_home": str(credential_home),
        "auth_file": str(credential_home / "auth.json"),
        "read_only_roots": read_only,
        "inaccessible_paths": sensitive_paths(
            operator_home=home,
            declared_paths=(row["path"] for row in read_only),
        ),
        "ownership": {
            "runtime_output_root": runtime_meta,
            "codex_home": codex_meta,
            "auth_file": auth_meta,
        },
        "cadence": {"may_install_test_unit": False, "may_enable_timer": False},
        "enforcement": {"implemented": False, "credential_content_present": False},
    }


def _path_interfaces(cfg: dict[str, Any]) -> Iterable[tuple[str, str]]:
    for source in cfg.get("sources") or []:
        if not isinstance(source, dict):
            continue
        source_name = str(source.get("name") or "unnamed-source")
        direct = source.get("path")
        if isinstance(direct, str) and direct.strip():
            yield source_name, direct
        for interface in source.get("interfaces") or []:
            if not isinstance(interface, dict):
                continue
            via = interface.get("via")
            if isinstance(via, str) and via.startswith("path:"):
                yield source_name, via.removeprefix("path:")


def declared_read_only_roots(
    cfg: dict[str, Any],
    *,
    writable_root: Path,
    require_exists: bool = True,
) -> list[dict[str, str]]:
    """Canonicalize path sources and ensure none overlaps the writable install."""
    by_path: dict[Path, set[str]] = {}
    for source_name, value in _path_interfaces(cfg):
        path = _resolved_absolute(value, field=f"source {source_name!r} path")
        if require_exists and not path.exists():
            raise SandboxPolicyError(f"declared source path does not exist: {path}")
        if path == writable_root or writable_root in path.parents or path in writable_root.parents:
            raise SandboxPolicyError(
                f"declared read-only source overlaps writable edge_home: {path}"
            )
        by_path.setdefault(path, set()).add(source_name)
    return [
        {"path": str(path), "sources": ",".join(sorted(names))}
        for path, names in sorted(by_path.items(), key=lambda item: str(item[0]))
    ]


def _windows_user_home(value: str | os.PathLike[str]) -> Path | None:
    """Return the WSL Windows-user home containing one declared path, if any."""
    path = _resolved_absolute(value, field="declared_path")
    parts = path.parts
    if (len(parts) >= 5 and parts[1] == "mnt"
            and re.fullmatch(r"[A-Za-z]", parts[2])
            and parts[3].casefold() == "users" and parts[4]):
        return Path(*parts[:5])
    return None


def sensitive_paths(
    *,
    operator_home: Path | None = None,
    declared_paths: Iterable[str | os.PathLike[str]] = (),
) -> list[str]:
    """Named credential and control paths that the heartbeat never needs directly.

    Nonexistent paths are retained intentionally: systemd can prefix them with ``-`` so
    absence is harmless while a future appearance does not silently gain authority.
    """
    home = (operator_home or Path.home()).resolve(strict=False)
    candidates = {
        home / ".ssh",
        home / ".config" / "1Password",
        home / ".op",
        Path("/run/docker.sock"),
        Path("/var/run/docker.sock"),
        Path("/run") / "user" / str(os.getuid()) / "docker.sock",
        Path("/run") / "user" / str(os.getuid()) / "gnupg",
    }
    # The common WSL mapping uses the same account name on Linux and Windows.  Declared
    # Windows sources also reveal the authoritative Windows home when the names differ.
    if home.name:
        candidates.add(Path("/mnt/c/Users") / home.name / ".ssh")
    for value in declared_paths:
        windows_home = _windows_user_home(value)
        if windows_home is not None:
            candidates.add(windows_home / ".ssh")
    return [str(path) for path in sorted(candidates, key=str)]


def build_policy(
    cfg: dict[str, Any],
    *,
    edge_home: str | os.PathLike[str],
    require_sources_exist: bool = True,
    operator_home: Path | None = None,
) -> dict[str, Any]:
    """Build a deterministic, JSON-serializable sandbox policy."""
    if not isinstance(cfg, dict):
        raise SandboxPolicyError("agent configuration must be a mapping")
    writable = validate_writable_root(edge_home)
    read_only = declared_read_only_roots(
        cfg, writable_root=writable, require_exists=require_sources_exist
    )
    return {
        "schema": POLICY_SCHEMA,
        "writable_root": str(writable),
        "read_only_roots": read_only,
        "inaccessible_paths": sensitive_paths(
            operator_home=operator_home,
            declared_paths=(row["path"] for row in read_only),
        ),
        "unset_environment": list(UNSET_ENVIRONMENT),
        "network": {
            "mode": "loopback-and-https-residual",
            "allowed_address_families": ["AF_UNIX", "AF_INET", "AF_INET6"],
            "complete_egress_isolation": False,
        },
        "cadence": {"may_install_test_unit": True, "may_enable_timer": False},
    }


def load_policy(
    agent_yaml: str | os.PathLike[str],
    *,
    require_sources_exist: bool = True,
) -> dict[str, Any]:
    """Load one phenotype and build its policy without causing side effects."""
    path = _resolved_absolute(agent_yaml, field="agent_yaml")
    try:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise SandboxPolicyError(f"cannot read agent configuration {path}: {exc}") from exc
    declared_home = cfg.get("edge_home")
    if not isinstance(declared_home, str) or not declared_home.strip():
        raise SandboxPolicyError("agent.yaml must declare edge_home")
    expanded = _resolved_absolute(declared_home, field="agent.yaml edge_home")
    # A phenotype may use ~/edge-install.  Its agent.yaml is authoritative only when it
    # resolves to the directory that owns that file.
    owner = path.parent.resolve(strict=False)
    if expanded != owner:
        raise SandboxPolicyError(
            f"agent.yaml edge_home {expanded} does not match owning install {owner}"
        )
    return build_policy(
        cfg, edge_home=expanded, require_sources_exist=require_sources_exist
    )


def _systemd_quote(value: str | os.PathLike[str]) -> str:
    """Quote one systemd word and neutralize specifier expansion."""
    text = str(value).replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
    if "\n" in text or "\r" in text or "\x00" in text:
        raise SandboxPolicyError("systemd values may not contain control-line characters")
    return f'"{text}"'


def _systemd_path(value: str | os.PathLike[str]) -> str:
    """Escape one path for non-command systemd directives.

    Settings such as ``WorkingDirectory=`` do not use ExecStart's command-line
    quoting rules.  Encode whitespace/control bytes and escape percent specifiers.
    """
    text = str(value).replace("%", "%%").replace("\\", "\\x5c")
    out = []
    for char in text:
        code = ord(char)
        if char.isspace() or code < 0x20 or code == 0x7F:
            out.append(f"\\x{code:02x}")
        else:
            out.append(char)
    return "".join(out)


def render_test_service(
    policy: dict[str, Any],
    *,
    heartbeat_bin: str | os.PathLike[str],
    unit_description: str = "edge heartbeat sandbox — render-only test",
) -> str:
    """Render a parallel, non-LLM systemd unit from a validated policy.

    The command deliberately includes ``--dry-run``.  WP2 can therefore validate or even
    install this test unit later without accidentally launching an autonomous beat.  WP3
    will replace the command with a deterministic negative preflight after that checker
    exists and has its own tests.
    """
    if not isinstance(policy, dict) or policy.get("schema") != POLICY_SCHEMA:
        raise SandboxPolicyError("unsupported or missing sandbox policy schema")
    if (policy.get("cadence") or {}).get("may_enable_timer") is not False:
        raise SandboxPolicyError("test service requires an explicit timer prohibition")
    writable = validate_writable_root(policy.get("writable_root"))
    executable = _resolved_absolute(heartbeat_bin, field="heartbeat_bin")
    read_only = policy.get("read_only_roots")
    inaccessible = policy.get("inaccessible_paths")
    unset = policy.get("unset_environment")
    families = (policy.get("network") or {}).get("allowed_address_families")
    if not isinstance(read_only, list) or not isinstance(inaccessible, list):
        raise SandboxPolicyError("policy paths must be lists")
    if not isinstance(unset, list) or not all(isinstance(v, str) and v for v in unset):
        raise SandboxPolicyError("unset_environment must be a list of variable names")
    if not isinstance(families, list) or not families:
        raise SandboxPolicyError("allowed_address_families must be a non-empty list")

    ro_paths: list[Path] = []
    for row in read_only:
        if not isinstance(row, dict):
            raise SandboxPolicyError("each read_only_roots entry must be a mapping")
        path = _resolved_absolute(row.get("path"), field="read_only_root.path")
        if path == writable or writable in path.parents or path in writable.parents:
            raise SandboxPolicyError(f"read-only path overlaps writable root: {path}")
        ro_paths.append(path)
    hidden = [_resolved_absolute(path, field="inaccessible_path") for path in inaccessible]

    lines = [
        "[Unit]",
        f"Description={unit_description}",
        "After=network-online.target",
        "",
        "[Service]",
        "Type=oneshot",
        "# WP2 safety latch: this unit cannot invoke an LLM.",
        "ExecStart=" + " ".join([
            _systemd_quote(executable), "--home", _systemd_quote(writable), "--dry-run"
        ]),
        f"WorkingDirectory={_systemd_path(writable)}",
        "TimeoutStartSec=2min",
        "KillMode=control-group",
        "UMask=0077",
        "NoNewPrivileges=true",
        "CapabilityBoundingSet=",
        "AmbientCapabilities=",
        "PrivateTmp=true",
        "PrivateDevices=true",
        "ProtectSystem=strict",
        "ProtectHome=read-only",
        "ProtectControlGroups=true",
        "ProtectKernelModules=true",
        "ProtectKernelTunables=true",
        "ProtectKernelLogs=true",
        "ProtectClock=true",
        "ProtectHostname=true",
        "ProtectProc=invisible",
        "ProcSubset=pid",
        "RestrictSUIDSGID=true",
        "RestrictRealtime=true",
        "LockPersonality=true",
        "SystemCallArchitectures=native",
        "RestrictAddressFamilies=" + " ".join(families),
        "ReadWritePaths=" + _systemd_path(writable),
    ]
    lines.extend("ReadOnlyPaths=" + _systemd_path(path) for path in sorted(set(ro_paths), key=str))
    # A leading '-' makes a currently absent sensitive path harmless while keeping the
    # denial in the unit if that path appears later.
    lines.extend(
        "InaccessiblePaths=-" + _systemd_path(path)
        for path in sorted(set(hidden), key=str)
    )
    lines.append("UnsetEnvironment=" + " ".join(sorted(set(unset))))
    lines += [
        "Environment=EDGE_HEARTBEAT_SANDBOX=render-only",
        "",
        "# Deliberately no [Install] section: WP2 cannot enable a timer or standing unit.",
        "",
    ]
    rendered = "\n".join(lines)
    if "{{" in rendered or "}}" in rendered:
        raise SandboxPolicyError("unresolved template token")
    return rendered


def render_preflight_service(
    policy: dict[str, Any],
    *,
    preflight_bin: str | os.PathLike[str],
    fixture: str | os.PathLike[str],
    unit_description: str = "edge heartbeat sandbox — deterministic preflight",
) -> str:
    """Render the WP3 non-LLM preflight unit from the same WP2 boundary."""
    # Reuse every hardening directive from the proven render-only unit, then replace
    # only its safe command and marker.  The replacement is exact and fails closed.
    rendered = render_test_service(
        policy,
        heartbeat_bin=preflight_bin,
        unit_description=unit_description,
    )
    writable = validate_writable_root(policy["writable_root"])
    executable = _resolved_absolute(preflight_bin, field="preflight_bin")
    fixture_path = _resolved_absolute(fixture, field="fixture")
    old = "ExecStart=" + " ".join([
        _systemd_quote(executable), "--home", _systemd_quote(writable), "--dry-run"
    ])
    new = "ExecStart=" + " ".join([
        _systemd_quote(executable), "--home", _systemd_quote(writable),
        "--fixture", _systemd_quote(fixture_path),
    ])
    if rendered.count(old) != 1:
        raise SandboxPolicyError("render-only safety command was not uniquely present")
    rendered = rendered.replace(old, new)
    rendered = rendered.replace(
        "Environment=EDGE_HEARTBEAT_SANDBOX=render-only",
        "Environment=EDGE_HEARTBEAT_SANDBOX=preflight",
    )
    anchor = "ReadWritePaths=" + _systemd_path(writable)
    if rendered.count(anchor) != 1:
        raise SandboxPolicyError("writable-root directive was not uniquely present")
    # A more specific read-only bind below edge_home is the disposable negative
    # fixture. Real source trees are never used for write attempts.
    rendered = rendered.replace(
        anchor, anchor + "\nReadOnlyPaths=" + _systemd_path(fixture_path)
    )
    rendered = rendered.replace(
        "# WP2 safety latch: this unit cannot invoke an LLM.",
        "# WP3 deterministic preflight: this command contains no LLM path.",
    )
    return rendered


def render_pilot_service(
    policy: dict[str, Any],
    *,
    heartbeat_bin: str | os.PathLike[str],
    cli: str = "codex",
    timeout_seconds: int = 600,
    codex_home: str | os.PathLike[str] | None = None,
    dispatch_id: str | None = None,
    unit_description: str = "edge heartbeat sandbox — supervised pilot",
) -> str:
    """Render a fixed-runtime, manually invoked pilot with no install section."""
    if cli not in {"codex", "claude", "grok", "opus", "fable"}:
        raise SandboxPolicyError(f"unsupported fixed pilot runtime: {cli}")
    if not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool):
        raise SandboxPolicyError("pilot timeout_seconds must be an integer")
    if not 1 <= timeout_seconds <= 600:
        raise SandboxPolicyError("pilot timeout_seconds must be between 1 and 600")
    if not isinstance(dispatch_id, str) or not re.fullmatch(
            r"[A-Za-z0-9._:-]{1,128}", dispatch_id):
        raise SandboxPolicyError("pilot dispatch_id must be fixed and safe")
    writable = validate_writable_root(policy["writable_root"])
    pilot_codex_home = None
    if cli == "codex":
        if codex_home is None:
            raise SandboxPolicyError("a Codex pilot requires a dedicated codex_home")
        pilot_codex_home = _resolved_absolute(codex_home, field="codex_home")
        if writable not in pilot_codex_home.parents:
            raise SandboxPolicyError("codex_home must live below the writable edge_home")
    rendered = render_test_service(
        policy,
        heartbeat_bin=heartbeat_bin,
        unit_description=unit_description,
    )
    executable = _resolved_absolute(heartbeat_bin, field="heartbeat_bin")
    old = "ExecStart=" + " ".join([
        _systemd_quote(executable), "--home", _systemd_quote(writable), "--dry-run"
    ])
    new = "ExecStart=" + " ".join([
        _systemd_quote(executable), "--home", _systemd_quote(writable),
        "--cli", cli,
        *(["--supervised-cortex-broker"] if cli == "codex" else []),
        "--dispatch-id", dispatch_id,
        "--timeout-seconds", str(timeout_seconds),
    ])
    if rendered.count(old) != 1:
        raise SandboxPolicyError("render-only safety command was not uniquely present")
    rendered = rendered.replace(old, new)
    rendered = rendered.replace("TimeoutStartSec=2min", "TimeoutStartSec=11min")
    rendered = rendered.replace(
        "Environment=EDGE_HEARTBEAT_SANDBOX=render-only",
        "Environment=EDGE_HEARTBEAT_SANDBOX=supervised-pilot",
    )
    if pilot_codex_home is not None:
        rendered = rendered.replace(
            "Environment=EDGE_HEARTBEAT_SANDBOX=supervised-pilot",
            "Environment=EDGE_HEARTBEAT_SANDBOX=supervised-pilot\n"
            "Environment=CODEX_HOME=" + _systemd_path(pilot_codex_home),
        )
    rendered = rendered.replace(
        "# WP2 safety latch: this unit cannot invoke an LLM.",
        "# WP4 supervised pilot: fixed runtime, bounded timeout, no cadence.",
    )
    return rendered


def render_persistent_bridge_candidate(
    policy: dict[str, Any],
    *,
    fail_closed_bin: str | os.PathLike[str] = "/usr/bin/false",
    unit_description: str = "edge persistent-auth bridge — inert candidate",
) -> str:
    """Render an inert system-service candidate from the PB-1 split-root policy.

    The candidate cannot invoke the heartbeat or an LLM: its only command must be an explicit
    absolute fail-closed executable.  PB-4 may later replace that command after a separate audit.
    """
    if not isinstance(policy, dict) or policy.get("schema") != PERSISTENT_BRIDGE_SCHEMA:
        raise SandboxPolicyError("persistent bridge candidate requires the split-root policy")
    if (policy.get("cadence") or {}).get("may_enable_timer") is not False:
        raise SandboxPolicyError("persistent bridge candidate requires a timer prohibition")
    if (policy.get("enforcement") or {}).get("implemented") is not False:
        raise SandboxPolicyError("candidate expects an explicitly non-enforced design policy")
    service = policy.get("service_identity")
    if not isinstance(service, str) or not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", service):
        raise SandboxPolicyError("candidate has an invalid service identity")
    immutable = _resolved_absolute(policy.get("immutable_input_root"), field="immutable_input_root")
    runtime = _resolved_absolute(policy.get("runtime_output_root"), field="runtime_output_root")
    codex_home = _resolved_absolute(policy.get("codex_home"), field="codex_home")
    auth_file = _resolved_absolute(policy.get("auth_file"), field="auth_file")
    if auth_file != codex_home / "auth.json":
        raise SandboxPolicyError("auth_file must be the fixed file below codex_home")
    executable = _resolved_absolute(fail_closed_bin, field="fail_closed_bin")
    if executable.name not in {"false", "false.exe"}:
        raise SandboxPolicyError("inert candidate command must be a fail-closed false executable")

    roots = [immutable, runtime, codex_home]
    if any(_is_within(a, b) or _is_within(b, a)
           for i, a in enumerate(roots) for b in roots[i + 1:]):
        raise SandboxPolicyError("candidate roots must remain non-overlapping")
    read_only = [immutable]
    for row in policy.get("read_only_roots") or []:
        if not isinstance(row, dict):
            raise SandboxPolicyError("candidate read-only roots must be mappings")
        read_only.append(_resolved_absolute(row.get("path"), field="read_only_root.path"))

    hidden_rows = policy.get("inaccessible_paths")
    if not isinstance(hidden_rows, list):
        raise SandboxPolicyError("candidate inaccessible paths must be a list")
    hidden = [_resolved_absolute(path, field="inaccessible_path") for path in hidden_rows]
    lines = [
        "[Unit]",
        f"Description={unit_description}",
        "After=network-online.target",
        "",
        "[Service]",
        "Type=oneshot",
        f"User={service}",
        f"Group={service}",
        "SupplementaryGroups=",
        "ExecStart=" + _systemd_quote(executable),
        f"WorkingDirectory={_systemd_path(immutable)}",
        "TimeoutStartSec=30s",
        "KillMode=control-group",
        "UMask=0077",
        "NoNewPrivileges=true",
        "CapabilityBoundingSet=",
        "AmbientCapabilities=",
        "PrivateTmp=true",
        "PrivateDevices=true",
        "ProtectSystem=strict",
        "ProtectHome=read-only",
        "ProtectControlGroups=true",
        "ProtectKernelModules=true",
        "ProtectKernelTunables=true",
        "ProtectKernelLogs=true",
        "ProtectClock=true",
        "ProtectHostname=true",
        "ProtectProc=invisible",
        "ProcSubset=pid",
        "RestrictSUIDSGID=true",
        "RestrictRealtime=true",
        "LockPersonality=true",
        "SystemCallArchitectures=native",
        "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
        "ReadWritePaths=" + _systemd_path(runtime),
        "ReadWritePaths=" + _systemd_path(codex_home),
    ]
    lines.extend(
        "ReadOnlyPaths=" + _systemd_path(path)
        for path in sorted(set(read_only), key=str)
    )
    lines.extend(
        "InaccessiblePaths=-" + _systemd_path(path)
        for path in sorted(set(hidden), key=str)
    )
    lines += [
        "UnsetEnvironment=" + " ".join(sorted(set(UNSET_ENVIRONMENT))),
        "Environment=HOME=" + _systemd_path(codex_home),
        "Environment=CODEX_HOME=" + _systemd_path(codex_home),
        "Environment=EDGE_HOME=" + _systemd_path(immutable),
        "Environment=EDGE_RUNTIME_ROOT=" + _systemd_path(runtime),
        "Environment=EDGE_HEARTBEAT_SANDBOX=persistent-bridge-inert",
        "",
        "# Deliberately no [Install]: inert candidate, no cadence and no LLM command.",
        "",
    ]
    rendered = "\n".join(lines)
    forbidden = ("auth.json", "OPENAI_API_KEY", "OP_SERVICE_ACCOUNT_TOKEN=", "WantedBy=")
    if any(value in rendered for value in forbidden):
        raise SandboxPolicyError("candidate rendered forbidden credential or activation material")
    return rendered
