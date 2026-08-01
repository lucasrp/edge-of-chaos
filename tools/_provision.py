"""_provision — runtime provisioning logic for edge-apply (ADR-0011, #18/#19/#20).

The graph is mandatory on every host, but Docker is NOT — the edge picks an install mode
(``select_install_mode``): 'docker' when the host can run it, else 'local' (per-host Neo4j
user-space via tarball + a bundled JRE, no root, no docker permission). The onboarding decides the
mode once and persists it (agent.yaml ``install_mode``); ``ensure_neo4j`` reads it. This module also
builds the venv (#20) and the systemd heartbeat timer (#19). Pure boundary code: every effectful
step goes through an injected ``run`` (defaults to subprocess.run), so command construction,
password generation, and idempotency are testable WITHOUT building anything against the host. Steps
fail loud on real failure — but a missing Docker is no longer an install failure, it selects 'local'.
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


def _run(run, cmd, what, **kw):
    """Invoke `cmd` through the injected runner; raise loud on a non-zero exit. Extra kwargs (e.g.
    env=) are forwarded to the runner — the local Neo4j runtime points JAVA_HOME at the bundled JRE."""
    res = run(cmd, **kw)
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


def place_tree(src, dst, replacements=None):
    """copytree a genotype dir into the install home, skipping when src == dst (REPO == edge_home).
    Returns True iff copied."""
    src, dst = Path(src), Path(dst)
    if src.resolve() == dst.resolve():
        return False
    shutil.copytree(src, dst, dirs_exist_ok=True)
    for path in dst.rglob("*") if replacements else ():
        if path.is_file():
            text = path.read_text()
            rendered = text
            for old, new in replacements.items():
                rendered = rendered.replace(old, new)
            if rendered != text:
                path.write_text(rendered)
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


READY_TIMEOUT_S = 120   # 1º boot do neo4j aplica a senha inicial — ~1min típico
READY_POLL_S = 3


def _wait_neo4j_ready(password, run, _sleep, container=NEO4J_CONTAINER):
    """Bloqueia até um RETURN 1 AUTENTICADO responder (docker exec cypher-shell).

    Sem isso, os primeiros cheques do install chegam antes da senha inicial ser aplicada,
    acumulam falhas de auth e disparam AuthenticationRateLimit — envenenando os primeiros
    minutos da instalação (caso edgesandbox 2026-07-25). Fail-loud no timeout."""
    waited = 0
    while waited <= READY_TIMEOUT_S:
        res = run(["docker", "exec", container, "cypher-shell",
                   "-u", "neo4j", "-p", password, "RETURN 1"],
                  capture_output=True, text=True)
        if getattr(res, "returncode", 1) == 0:
            return
        _sleep(READY_POLL_S)
        waited += READY_POLL_S
    raise RuntimeError(
        f"neo4j não ficou pronto em {READY_TIMEOUT_S}s (container {container}) — "
        "veja `docker logs edge-neo4j`; não siga o install com o grafo surdo")


def select_install_mode(caps):
    """The edge's install mode — chosen ONCE for the WHOLE install, not per component: 'docker' when
    this host can run docker, else 'local' (user-space — no docker permission needed). Persisted so
    every containerizable step reads the same mode. This is the seam that inverts the old
    docker-mandatory install: a locked-down host installs 'local' end to end instead of failing."""
    return "docker" if caps.get("docker_present") else "local"


def ensure_neo4j(home, env_dir, run=subprocess.run, mode=None, _password=None, _sleep=None):
    """Provision Neo4j according to the edge-wide install mode — Neo4j reads the mode, never decides
    it. `mode` comes from the persisted phenotype (agent.yaml `install_mode`); when None it is
    detected fresh (docker present → 'docker', else 'local'). 'docker' → the container path; 'local'
    → the user-space runtime (tarball + bundled JRE). A host with no docker permission installs
    'local' instead of the old fail-loud. Returns the secret path (the caller's contract)."""
    mode = mode or select_install_mode({"docker_present": docker_present(run=run)})
    if mode == "docker":
        return provision_neo4j(home, env_dir, run=run, _password=_password, _sleep=_sleep)
    return provision_neo4j_local(home, env_dir, run=run, _password=_password, _sleep=_sleep)


def provision_neo4j(home, env_dir, run=subprocess.run, _password=None, _sleep=None):
    """Provision the per-host Neo4j (#18). Fail loud if Docker is absent. Idempotent: if the
    container already exists AND this install's secret exists, no-op. Container existente
    SEM secret neste home = este install co-habita um neo4j de outro (hosts compartilhados,
    ex. petertosh+roberto) — fail loud com instrução, nunca devolver caminho de arquivo
    inexistente. Otherwise generate a password, write the secret, `docker run` the pinned
    5.x image and WAIT until an authenticated ping succeeds. Returns the secret path."""
    home = Path(home)
    _sleep = _sleep or __import__("time").sleep
    if not docker_present(run=run):
        raise RuntimeError(
            "Docker is absent — the graph is mandatory on every host (ADR-0011); "
            "install Docker before edge-apply (no Tier-0 install target)")
    secret_path = Path(env_dir) / "neo4j.env"
    if container_exists(NEO4J_CONTAINER, run=run):
        if secret_path.is_file():
            return secret_path                       # already provisioned — idempotent no-op
        raise RuntimeError(
            f"container {NEO4J_CONTAINER} já existe mas {secret_path} não — este install "
            "co-habita o neo4j de outro install neste host. Copie o neo4j.env do install "
            "dono do container para os secrets deste home (separação por graph_group), ou "
            "remova o container (`docker rm -fv edge-neo4j` — DESTRÓI o grafo existente)")
    password = _password or generate_neo4j_password()
    secret_path = write_neo4j_secret(env_dir, password)
    _run(run, neo4j_run_command(home, password), "docker run neo4j")
    _wait_neo4j_ready(password, run, _sleep)
    return secret_path


# --- Neo4j local: user-space runtime, no docker (install_mode='local') --------------------------
# The no-docker-permission path. Tarball Neo4j + a bundled JRE (fetch-at-provision) under
# <home>/runtime — runs AS THE USER, so the store is user-owned and `rm -rf <home>` stays clean
# (the inverse of bug #5, which came from a root-writing container). The JRE is bundled so 'local'
# needs NO system Java; without it the barrier would just move from 'docker permission' to 'java'.
NEO4J_LOCAL_VERSION = "5.26.0"          # match the pinned docker image (vector index, ADR-0011)
JRE_VERSION = "21.0.5+11"               # Temurin 21 — bundled JRE for the local runtime


def neo4j_local_home(home):
    return Path(home) / "runtime" / "neo4j"


def jre_local_home(home):
    return Path(home) / "runtime" / "jre"


def neo4j_tarball_url(version=NEO4J_LOCAL_VERSION):
    # ponytail: pinned URL; the real fetch must checksum-verify against a known-good hash (calibration
    # knob — confirm on the first real no-docker host, same as the docker image digest is trusted).
    return f"https://dist.neo4j.org/neo4j-community-{version}-unix.tar.gz"


def jre_tarball_url(version=JRE_VERSION, os_name="linux", arch="x64"):
    v = version.replace("+", "_")
    tag = version.replace("+", "%2B")
    return ("https://github.com/adoptium/temurin21-binaries/releases/download/"
            f"jdk-{tag}/OpenJDK21U-jre_{arch}_{os_name}_hotspot_{v}.tar.gz")


def _fetch_and_extract(url, dest):
    """Real default: stream a .tar.gz and extract it flattened into `dest` (the tarball's single top
    dir is stripped). Injected in tests — nothing hits the network there."""
    import tarfile
    import tempfile as _tf
    import urllib.request
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    with _tf.NamedTemporaryFile(suffix=".tar.gz") as tmp:
        with urllib.request.urlopen(url) as r:      # noqa: S310 — pinned dist host
            shutil.copyfileobj(r, tmp)
        tmp.flush()
        with tarfile.open(tmp.name) as tar:
            top = os.path.commonprefix([m.name for m in tar.getmembers() if m.name]).split("/")[0]
            for m in tar.getmembers():
                if top and m.name.startswith(top + "/"):
                    m.name = m.name[len(top) + 1:]
                if m.name:
                    tar.extract(m, dest)


def _bolt_ready(password, uri="bolt://localhost:7687"):
    """Readiness probe for the local runtime: an authenticated bolt connect (the driver is already a
    dependency). Replaces the docker path's `docker exec cypher-shell` — same 'authenticated ping'."""
    import neo4j
    drv = neo4j.GraphDatabase.driver(uri, auth=("neo4j", password))
    try:
        drv.verify_connectivity()
        return True
    except Exception:
        return False
    finally:
        try:
            drv.close()
        except Exception:
            pass


def _wait_neo4j_ready_local(password, _ready=None, _sleep=None):
    """Block until an authenticated bolt ping succeeds — same fail-loud-on-timeout contract as the
    docker path (never follow the install with a deaf graph)."""
    _ready = _ready or _bolt_ready
    _sleep = _sleep or __import__("time").sleep
    waited = 0
    while waited <= READY_TIMEOUT_S:
        if _ready(password):
            return
        _sleep(READY_POLL_S)
        waited += READY_POLL_S
    raise RuntimeError(
        f"neo4j local não ficou pronto em {READY_TIMEOUT_S}s — veja <home>/runtime/neo4j/logs; "
        "não siga o install com o grafo surdo")


def provision_neo4j_local(home, env_dir, run=subprocess.run, _download=None, _ready=None,
                          _sleep=None, _password=None):
    """Provision Neo4j user-space (install_mode='local') — no docker, no root. Fetch the neo4j tarball
    + a bundled JRE under <home>/runtime (idempotent — skip what's already extracted), write the
    generated secret, set the initial password and start neo4j with JAVA_HOME pinned to the bundled
    JRE. Waits until an authenticated bolt ping answers. Returns the secret path."""
    home = Path(home)
    _download = _download or _fetch_and_extract
    nhome, jhome = neo4j_local_home(home), jre_local_home(home)
    if not (jhome / "bin" / "java").exists():
        _download(jre_tarball_url(), jhome)
    if not (nhome / "bin" / "neo4j").exists():
        _download(neo4j_tarball_url(), nhome)
    password = _password or generate_neo4j_password()
    secret_path = write_neo4j_secret(env_dir, password)
    env = {**os.environ, "JAVA_HOME": str(jhome)}
    _run(run, [str(nhome / "bin" / "neo4j-admin"), "dbms", "set-initial-password", password],
         "neo4j set-initial-password", env=env)
    _run(run, [str(nhome / "bin" / "neo4j"), "start"], "neo4j start", env=env)
    # ponytail: `neo4j start` daemonizes but has no restart-on-logout; upgrade to a systemd --user
    # unit with linger (like the heartbeat timer) if a launch user's graph must survive logout/reboot.
    _wait_neo4j_ready_local(password, _ready=_ready, _sleep=_sleep)
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


def install_heartbeat(cfg, home, unit_dir=None, run=subprocess.run, enable=True):
    """Install the heartbeat timer and static rationalizer worker, idempotently.

    Only the heartbeat has a timer. Rationalization is a oneshot service enqueued after a
    stamped dispatch; it deliberately has no independent cadence.

    ``enable=False`` writes unit files but does **not** enable/start the timer (onboarding
    bootstrap — production ignition is separate after mentor + phenotype).
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
    if enable:
        _run(run, ["systemctl", "--user", "enable", "--now", "edge-heartbeat.timer"],
             "systemctl enable --now timer")
        _run(run, ["loginctl", "enable-linger", os.environ.get("USER", "")], "loginctl enable-linger")


def enable_heartbeat(home=None, run=subprocess.run):
    """Enable+start the heartbeat timer (post-onboarding ignition)."""
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
