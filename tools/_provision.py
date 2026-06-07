"""_provision — runtime provisioning logic for edge-apply (ADR-0011, #18/#19/#20).

The graph is mandatory on every host. This module builds the runtime — the venv (#20), the
per-host Neo4j via Docker (#18), and the systemd heartbeat timer (#19). It is pure boundary code:
every effectful step goes through an injected ``run`` (defaults to subprocess.run), so the command
construction, password generation, and idempotency are all testable WITHOUT building anything
against the host. Each step **fails loud** — a missing Docker / failed pip / absent systemctl is an
install failure, never a silent degrade.
"""
import secrets
import shutil
import subprocess
import sys
from pathlib import Path


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
        res = run(["docker", "info"])
        return getattr(res, "returncode", 0) == 0
    except Exception:
        return False


def neo4j_run_command(home, password, image=NEO4J_IMAGE, container=NEO4J_CONTAINER):
    """Construct the `docker run` for THIS host's own Neo4j (#18): pinned 5.x, restart
    unless-stopped, data volume under <home>/state/neo4j/, the generated per-host password, and the
    bolt+http ports. No literal password (C4)."""
    data = Path(home) / "state" / "neo4j"
    return [
        "docker", "run", "-d",
        "--name", container,
        "--restart", "unless-stopped",
        "-p", "7474:7474", "-p", "7687:7687",
        "-v", f"{data}:/data",
        "-e", f"NEO4J_AUTH=neo4j/{password}",
        image,
    ]


def container_exists(container, run=subprocess.run) -> bool:
    """Idempotency probe: is a container with this name already present (any state)?"""
    res = run(["docker", "ps", "-aq", "-f", f"name=^{container}$"])
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
