"""_validate — install validation (the substrate check, made first-class).

Reports an install's health so the operator/user is NOTIFIED of a broken install up front, instead of
discovering it mid-beat — a missing venv, an unresolved secret, an empty/orphaned graph group: the
exact faults that left this host's graph dark. Each check is a (name, ok, detail) triple — ok is
True (pass) / False (fail) / None (advisory: couldn't determine, not counted against health). It
NEVER raises: a broken substrate is a reported FAIL, not a crash. `format_report` renders the checks
and returns (text, healthy), healthy False iff any check failed.
"""
import subprocess
from pathlib import Path

LAYOUT_DIRS = ("blog/entries", "state", "memory", "threads", "secrets")


def _venv_python(home):
    return Path(home) / ".venv" / "bin" / "python"


def check_layout(home):
    home = Path(home)
    missing = [d for d in LAYOUT_DIRS if not (home / d).is_dir()]
    return ("layout", not missing,
            "all install dirs present" if not missing else "missing dirs: " + ", ".join(missing))


def check_genotype(home):
    home = Path(home)
    ok = (home / "skills").is_dir() and (home / "blog" / "server.py").exists()
    return ("genotype", ok,
            "skills/ + blog/server.py in place" if ok else "skills/ or blog/server.py absent")


def _resolve_secret(env_dir, ref):
    """ref = '<file>:<VAR>' resolved against env_dir (same semantics as the installer, C4). Self-
    contained so the validator never couples to the installer script's internals."""
    fn, _, var = ref.partition(":")
    if not fn or not var:                                   # keyless ref → nothing to resolve
        return None
    p = Path(env_dir) / fn
    if not p.exists() or p.is_dir():
        return None
    for line in p.read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):]
        if line.startswith(var + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def _required_refs(cfg):
    refs = [r["secret_ref"] for r in (cfg.get("routers") or {}).values() if r.get("secret_ref")]
    refs += [s["secret_ref"] for s in (cfg.get("sources") or [])
             if s.get("kind") == "api" and s.get("secret_ref")]
    return refs


def check_secrets(home, cfg, env_dir):
    try:
        missing = [r for r in _required_refs(cfg) if not _resolve_secret(env_dir, r)]
    except Exception as e:                                   # never raise — report it
        return ("secrets", None, "could not check: " + str(e)[:60])
    return ("secrets", not missing,
            "all required keys present" if not missing else "missing: " + ", ".join(missing))


def check_venv(home):
    py = _venv_python(home)
    if not py.exists():
        return ("venv", False, "missing — run edge-apply --provision-runtime")
    try:
        res = subprocess.run([str(py), "-c", "import neo4j, graphiti_core, openai, yaml"],
                             capture_output=True, text=True, timeout=60)
    except Exception as e:
        return ("venv", None, "could not probe: " + str(e)[:60])
    if res.returncode == 0:
        return ("venv", True, "core deps import OK")
    tail = (res.stderr.strip().splitlines() or ["import failed"])[-1]
    return ("venv", False, "deps broken: " + tail[:80])


def check_graph(home, repo_tools):
    """Best-effort: the graph the RUNTIME sees — neo4j reachable with the env creds AND the resolved
    group populated (catches the orphan where the group resolves to an empty name). Runs under the
    venv python (it has the neo4j driver); reflects env, not env_dir — a password that exists in
    secrets/ but never reaches the env is a real runtime fault, and this surfaces it."""
    py = _venv_python(home)
    if not py.exists():
        return ("graph", None, "skipped — no venv")
    probe = (
        "import sys; sys.path.insert(0, %r)\n"
        "import _identity\n"
        "from neo4j import GraphDatabase\n"
        "uri, user, pw = _identity.neo4j_conn(); g = _identity.group()\n"
        "if not pw: print('NOPW'); raise SystemExit\n"
        "if not g: print('NOGROUP'); raise SystemExit\n"
        "d = GraphDatabase.driver(uri, auth=(user, pw))\n"
        "n = d.session().run('MATCH (e:Entity {group_id:$g}) RETURN count(e) AS n', g=g).single()['n']\n"
        "print(('OK ' if n>0 else 'EMPTY ')+g+' '+str(n))\n"
    ) % str(repo_tools)
    try:
        res = subprocess.run([str(py), "-c", probe], capture_output=True, text=True, timeout=30)
    except Exception as e:
        return ("graph", None, "could not probe: " + str(e)[:60])
    out = (res.stdout or res.stderr).strip().splitlines()
    line = out[-1] if out else "no output"
    if line.startswith("OK "):
        _, grp, n = line.split()
        return ("graph", True, "group '%s': %s entities" % (grp, n))
    if line.startswith("EMPTY "):
        _, grp, n = line.split()
        return ("graph", False, "group '%s' EMPTY (%s entities) — orphaned; set EDGE_GROUP" % (grp, n))
    if line == "NOPW":
        return ("graph", False, "EDGE_NEO4J_PASSWORD not in env (secrets not loaded into the runtime)")
    if line == "NOGROUP":
        return ("graph", False, "no group resolves (set EDGE_GROUP or agent.yaml name/codename)")
    return ("graph", False, "unreachable: " + line[:70])


def validate_install(home, cfg, env_dir, provisioned=True, repo_tools=None):
    """Run the substrate checks. `provisioned`=False skips the venv/graph checks (a files-only apply
    legitimately has no venv yet). Returns a list of (name, ok, detail)."""
    checks = [check_layout(home), check_genotype(home), check_secrets(home, cfg, env_dir)]
    if provisioned:
        checks.append(check_venv(home))
        checks.append(check_graph(home, repo_tools or (Path(home) / "tools")))
    return checks


def format_report(checks):
    mark = {True: "OK", False: "XX", None: ".."}
    lines = ["install validation:"]
    healthy = True
    for name, ok, detail in checks:
        lines.append("  [%s] %-9s %s" % (mark.get(ok, ".."), name + ":", detail))
        if ok is False:
            healthy = False
    lines.append("  => " + ("INSTALL HEALTHY"
                            if healthy else "INSTALL INCOMPLETE — fix the [XX] checks above"))
    return "\n".join(lines), healthy
