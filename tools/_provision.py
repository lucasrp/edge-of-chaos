"""_provision — runtime provisioning logic for edge-apply (ADR-0011, #18/#19/#20).

The graph is mandatory on every host. This module builds the runtime — the venv (#20), the
per-host Neo4j via Docker (#18), and the systemd heartbeat timer (#19). It is pure boundary code:
every effectful step goes through an injected ``run`` (defaults to subprocess.run), so the command
construction, password generation, and idempotency are all testable WITHOUT building anything
against the host. Each step **fails loud** — a missing Docker / failed pip / absent systemctl is an
install failure, never a silent degrade.
"""
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEMPLATES = REPO / "templates"


def _run(run, cmd, what):
    """Invoke `cmd` through the injected runner; raise loud on a non-zero exit."""
    res = run(cmd)
    rc = getattr(res, "returncode", 0)
    if rc != 0:
        raise RuntimeError(f"{what} failed (exit {rc}): {' '.join(map(str, cmd))}")
    return res


def venv_python(home: Path) -> Path:
    return Path(home) / ".venv" / "bin" / "python"


def venv_pip(home: Path) -> Path:
    return Path(home) / ".venv" / "bin" / "pip"


def venv_exists(home: Path) -> bool:
    """A venv is 'present' when its python interpreter exists (the resolver's contract)."""
    return venv_python(home).exists()


def build_venv(home, requirements, run=subprocess.run):
    """Build <home>/.venv from a pinned requirements.txt, idempotently (#20).

    Create the venv only if absent (idempotent — no rebuild churn), then pip-install the pins into
    the venv's own pip. Fails loud if the create or the install fails. Returns the venv python path.
    """
    home = Path(home)
    requirements = Path(requirements)
    if not venv_exists(home):
        _run(run, [sys.executable, "-m", "venv", str(home / ".venv")], "venv create")
    _run(run, [str(venv_pip(home)), "install", "--upgrade", "pip"], "pip upgrade")
    _run(run, [str(venv_pip(home)), "install", "-r", str(requirements)], "pip install -r requirements")
    return venv_python(home)


def place_file(src, dst):
    """Copy a genotype file into the install home, skipping when src and dst are the SAME path — the
    REPO == edge_home topology, where the genotype checkout IS the home. Returns True iff copied."""
    src, dst = Path(src), Path(dst)
    if src.resolve() == dst.resolve():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dst)
    return True


def place_tree(src, dst):
    """copytree a genotype dir into the install home, skipping when src == dst (REPO == edge_home).
    Returns True iff copied."""
    src, dst = Path(src), Path(dst)
    if src.resolve() == dst.resolve():
        return False
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return True


# --- Neo4j via Docker (#18) ---------------------------------------------------------------------
NEO4J_IMAGE = "neo4j:5.26"            # pinned 5.x — required for the vector index (ADR-0011)
NEO4J_CONTAINER = "edge-neo4j"


def generate_neo4j_password(nbytes=24):
    """A generated per-host Neo4j password — never a baked-in literal (CONTRACT C4)."""
    return secrets.token_urlsafe(nbytes)


def write_neo4j_secret(env_dir, password):
    """Persist the generated password to the secrets dir as neo4j.env (mode 600). Returns the path."""
    env_dir = Path(env_dir)
    env_dir.mkdir(parents=True, exist_ok=True)
    path = env_dir / "neo4j.env"
    path.write_text(f"EDGE_NEO4J_PASSWORD={password}\n")
    path.chmod(0o600)
    return path


def docker_present(run=subprocess.run) -> bool:
    """True iff a docker CLI is reachable. Pure check via the injected runner / PATH."""
    if shutil.which("docker") is None:
        return False
    try:
        res = run(["docker", "info"], capture_output=True, text=True)
        return getattr(res, "returncode", 0) == 0
    except Exception:
        return False


def neo4j_run_command(home, password, image=NEO4J_IMAGE, container=NEO4J_CONTAINER):
    """Construct the `docker run` for THIS host's own Neo4j (#18): pinned 5.x, restart unless-stopped,
    the generated per-host password, the bolt+http ports, and an ANONYMOUS docker volume for /data —
    never a bind mount under <home>. The container writes its store as root; a bind mount under <home>
    left those files un-removable, so `rm -rf <home>` failed and a clean reinstall broke (bug #5).
    With an anonymous volume the graph lives in docker's store: `rm -rf <home>` stays clean and
    `docker rm -fv <container>` tears the volume down with the container. No literal password (C4).
    `home` is kept for signature stability; the data location no longer depends on it."""
    return [
        "docker", "run", "-d",
        "--name", container,
        "--restart", "unless-stopped",
        "-p", "7474:7474", "-p", "7687:7687",
        "-v", "/data",
        "-e", f"NEO4J_AUTH=neo4j/{password}",
        image,
    ]


def container_exists(container, run=subprocess.run) -> bool:
    """Idempotency probe: is a container with this name already present (any state)? Captures stdout
    explicitly — real subprocess.run leaves .stdout None without it, so the probe would never see the
    container id, always report False, and re-`docker run` into a 'name already in use' crash."""
    res = run(["docker", "ps", "-aq", "-f", f"name=^{container}$"],
              capture_output=True, text=True)
    out = getattr(res, "stdout", "") or ""
    return bool(out.strip())


def provision_neo4j(home, env_dir, run=subprocess.run, _password=None):
    """Provision the per-host Neo4j (#18). Fail loud if Docker is absent. Idempotent: if the
    container already exists, do not re-run it (and reuse the existing secret). Otherwise generate a
    password, write the secret, and `docker run` the pinned 5.x image. Returns the secret path."""
    home = Path(home)
    if not docker_present(run=run):
        raise RuntimeError(
            "Docker is absent — the graph is mandatory on every host (ADR-0011); "
            "install Docker before edge-apply (no Tier-0 install target)")
    if container_exists(NEO4J_CONTAINER, run=run):
        return Path(env_dir) / "neo4j.env"          # already provisioned — idempotent no-op
    password = _password or generate_neo4j_password()
    secret_path = write_neo4j_secret(env_dir, password)
    _run(run, neo4j_run_command(home, password), "docker run neo4j")
    return secret_path


# --- systemd background lifecycle: heartbeat timer + static rationalizer worker ----------------
def _render(text, variables):
    """Substitute {{var}} from variables (same convention as tools/edge-render)."""
    return re.sub(r"\{\{\s*(\w+)\s*\}\}",
                  lambda m: str(variables.get(m.group(1), m.group(0))), text)


def _heartbeat_vars(cfg, home):
    return {
        "codename": str(cfg.get("codename", cfg.get("name", "edge"))),
        "heartbeat_interval": str(cfg.get("heartbeat_interval", "3h")),
        "edge_home": str(home),
        "heartbeat_bin": str(REPO / "tools" / "edge-heartbeat"),
    }


def render_heartbeat_service(cfg, home):
    """Render the .service unit from agent.yaml — runs tools/edge-heartbeat --home <edge_home>."""
    tpl = (TEMPLATES / "edge-heartbeat.service.tpl").read_text()
    return _render(tpl, _heartbeat_vars(cfg, home))


def render_heartbeat_timer(cfg, home):
    """Render the .timer unit — OnUnitActiveSec from heartbeat_interval, Persistent=true (#19)."""
    tpl = (TEMPLATES / "edge-heartbeat.timer.tpl").read_text()
    return _render(tpl, _heartbeat_vars(cfg, home))


def render_rationalize_service(cfg, home):
    """Render the bounded static worker enqueued after a dispatch has been stamped."""
    tpl = (TEMPLATES / "edge-rationalize.service.tpl").read_text()
    return _render(tpl, _heartbeat_vars(cfg, home))


def install_heartbeat(cfg, home, unit_dir=None, run=subprocess.run):
    """Install the heartbeat timer and static rationalizer worker, idempotently.

    Only the heartbeat has a timer and is enabled here. Rationalization is a oneshot service
    enqueued after a stamped dispatch; it deliberately has no independent cadence.
    """
    home = Path(home)
    unit_dir = Path(unit_dir) if unit_dir is not None \
        else Path(os.path.expanduser("~/.config/systemd/user"))
    unit_dir.mkdir(parents=True, exist_ok=True)
    (unit_dir / "edge-heartbeat.service").write_text(render_heartbeat_service(cfg, home))
    (unit_dir / "edge-heartbeat.timer").write_text(render_heartbeat_timer(cfg, home))
    (unit_dir / "edge-rationalize.service").write_text(
        render_rationalize_service(cfg, home)
    )
    _run(run, ["systemctl", "--user", "daemon-reload"], "systemctl daemon-reload")
    _run(run, ["systemctl", "--user", "enable", "--now", "edge-heartbeat.timer"],
         "systemctl enable --now timer")
    _run(run, ["loginctl", "enable-linger", os.environ.get("USER", "")], "loginctl enable-linger")


def check_headless_auth(run=subprocess.run):
    """Verify `claude -p` authenticates with NO TTY (#19) — the timer runs headless, and the
    credential the interactive session uses may not be reachable there. Fail loud naming the gap."""
    cmd = ["claude", "-p", "-", "--dangerously-skip-permissions"]
    try:
        res = run(cmd)
    except FileNotFoundError as e:
        raise RuntimeError(f"headless-auth check failed: claude CLI not found ({e})")
    if getattr(res, "returncode", 1) != 0:
        detail = (getattr(res, "stderr", "") or getattr(res, "stdout", "") or "").strip()
        raise RuntimeError(
            "headless-auth check failed: `claude -p` could not authenticate without a TTY "
            f"(the heartbeat timer runs headless) — {detail}")
    return True
