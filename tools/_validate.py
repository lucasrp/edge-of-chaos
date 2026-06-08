"""_validate — install validation (the substrate check, made first-class).

Reports an install's health so the operator/user is NOTIFIED of a broken install up front, instead of
discovering it mid-beat — a missing venv, an unresolved secret, an empty/orphaned graph group: the
exact faults that left this host's graph dark. Each check is a (name, ok, detail) triple — ok is
True (pass) / False (fail) / None (advisory: couldn't determine, not counted against health). It
NEVER raises: a broken substrate is a reported FAIL, not a crash. `format_report` renders the checks
and returns (text, healthy), healthy False iff any check failed.
"""
import subprocess
import sys
from pathlib import Path

LAYOUT_DIRS = ("blog/entries", "state", "memory", "threads", "secrets")

# Stage-(i) REQUIRED briefing sections (briefing-lifecycle audit): HEALTHY must imply the edge has
# its initial tattoos, the Idiom glossary floor, and the REAL declared source roster. Each is the
# section header `compose_briefing` emits; a composed text missing any is a lobotomy the gate fails.
REQUIRED_SECTIONS = ("### Personality", "### Method", "## Idiom", "## 4. Source orientation")
# The log-fed sections must render their HONEST empty markers on a fresh log (present, not crashed) —
# the gate confirms compose did not blank/crash them (the empty-is-correct stage-(i) distinction).
EMPTY_MARKERS = ("no confirmed objective yet", "no direction set yet",
                 "no direcionamento report yet", "no corpus yet")


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


def _classify_graph(group, mine, total):
    """Classify the graph leg from entity counts. A fresh install has an empty-but-reachable graph
    (populates on the first sweep) — that is NOT a failure; only an empty group while OTHER groups
    hold data is the real orphan."""
    if mine > 0:
        return (True, "group '%s': %d entities" % (group, mine))
    if total > 0:
        return (False, "group '%s' empty but %d entities under other groups — orphaned "
                       "(check graph_group / EDGE_GROUP)" % (group, total))
    return (None, "group '%s' reachable, empty — fresh install (populates on first sweep)" % group)


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
        "s = d.session()\n"
        "n = s.run('MATCH (e:Entity {group_id:$g}) RETURN count(e) AS n', g=g).single()['n']\n"
        "t = s.run('MATCH (e:Entity) RETURN count(e) AS n').single()['n']\n"
        "print('COUNTS '+g+' '+str(n)+' '+str(t))\n"
    ) % str(repo_tools)
    try:
        res = subprocess.run([str(py), "-c", probe], capture_output=True, text=True, timeout=30)
    except Exception as e:
        return ("graph", None, "could not probe: " + str(e)[:60])
    out = (res.stdout or res.stderr).strip().splitlines()
    line = out[-1] if out else "no output"
    if line.startswith("COUNTS "):
        _, grp, n, t = line.split()
        ok, detail = _classify_graph(grp, int(n), int(t))
        return ("graph", ok, detail)
    if line == "NOPW":
        return ("graph", False, "EDGE_NEO4J_PASSWORD not in env (secrets not loaded into the runtime)")
    if line == "NOGROUP":
        return ("graph", False, "no group resolves (set EDGE_GROUP or agent.yaml name/codename)")
    return ("graph", False, "unreachable: " + line[:70])


def _assert_identity_sections(text):
    """The assert leg of the identity gate: a composed briefing that DID NOT raise must still carry
    the stage-(i) REQUIRED genotype-identity sections (Personality, Method, the Idiom glossary floor,
    and the real declared Source roster). Returns ("identity", ok, detail) — a missing section is a
    FAIL even when the composer was silent. The log-fed sections (Objective/Direction/Direcionamento/
    Corpus) are checked SEPARATELY against a fresh log (they are correctly populated on a live
    install), so this leg is log-independent — it asserts only the genotype-identity head."""
    missing = [s for s in REQUIRED_SECTIONS if s not in text]
    if missing:
        return ("identity", False,
                "briefing composed but REQUIRED section(s) missing: " + ", ".join(missing))
    return ("identity", True,
            "identity composed — Personality + Method + Idiom floor + real Source roster present")


def check_identity(home, cfg, agent_yaml=None, memory=None, log=None):
    """The install-time identity gate (briefing-lifecycle audit, stage-(i) — gate root-cause #4):
    HEALTHY must imply the edge has an identity and knows its sources, never a lobotomy reporting
    healthy. Composes the briefing (briefing.compose_briefing — the single fail-closed gate); a
    raised BriefingIdentityError (thin agent.yaml identity, absent doctrine, all-missing
    ground_truth, empty/malformed source roster) → ok=False with the message. On a successful
    compose it (1) asserts the stage-(i) REQUIRED genotype-identity sections are present, and (2)
    confirms the log-fed sections render their honest empty markers ON A FRESH LOG (present, not
    crashed) — composed against a throwaway empty log so a live install's populated log is not
    mistaken for a blank. Returns ("identity", ok, detail) like the other checks; NEVER raises, but
    FAILS CLOSED: ANY import/compose exception (typed or not) → ok=False, never a downgrade to
    advisory ok=None (a compose failure is a FAIL, not 'couldn't determine'). `agent_yaml`/`memory`/`log` override the
    genotype inputs for tests; left None they default to this install's own tree (briefing.py reads
    its REPO — the canonical checkout-IS-the-home install). When `log` is passed it is treated as the
    fresh log for the empty-marker leg too (tests hand a fresh log)."""
    try:
        sys.path.insert(0, str(Path(home) / "tools"))
        import briefing
    except Exception as e:                                   # cannot load the composer → FAIL closed
        return ("identity", False, "could not load briefing composer (fail-closed): " + str(e)[:70])
    kw = {"clusters": None, "roster": None}                  # roster None → fail-closed source_roster
    if agent_yaml is not None:
        kw["agent_yaml"] = Path(agent_yaml)
    if memory is not None:
        kw["memory"] = Path(memory)
    try:
        # The genotype-identity leg: compose against the install's own (possibly live) log.
        ident_kw = dict(kw)
        if log is not None:
            ident_kw["log"] = Path(log)
        text = briefing.compose_briefing(**ident_kw)
        # The empty-marker leg: compose against a FRESH log — confirm the log-fed sections render
        # their honest empty markers (present, not crashed). Reuse `log` when given (tests pass a
        # fresh one); otherwise a unique non-existent path, so the eventlog folds read empty.
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            fresh = Path(log) if log is not None else Path(td) / "fresh.jsonl"
            fresh_text = briefing.compose_briefing(**dict(kw, log=fresh))
    except briefing.BriefingIdentityError as e:             # the fail-closed gate fired → lobotomy
        return ("identity", False, "identity gap (briefing fail-closed): " + str(e)[:120])
    except Exception as e:                                   # ANY compose failure is a FAIL, never advisory
        return ("identity", False, "could not compose briefing (fail-closed): " + str(e)[:90])
    name, ok, detail = _assert_identity_sections(text)
    if not ok:
        return (name, ok, detail)
    missing_markers = [m for m in EMPTY_MARKERS if m not in fresh_text]
    if missing_markers:
        return ("identity", False,
                "fresh-log compose did not render the honest empty marker(s) "
                "(crashed/blanked the log-fed sections): " + ", ".join(missing_markers))
    return ("identity", True, detail + "; log-fed sections render honest empty markers on a fresh log")


def validate_install(home, cfg, env_dir, provisioned=True, repo_tools=None,
                     agent_yaml=None, memory=None, log=None):
    """Run the substrate checks. `provisioned`=False skips the venv/graph checks (a files-only apply
    legitimately has no venv yet). The identity gate runs UNCONDITIONALLY (identity is a stage-(i)
    requirement, independent of the runtime — a files-only apply still must not pass a lobotomy).
    `agent_yaml`/`memory`/`log` override the identity gate's genotype inputs (tests); default to the
    install's own tree. Returns a list of (name, ok, detail)."""
    checks = [check_layout(home), check_genotype(home), check_secrets(home, cfg, env_dir),
              check_identity(home, cfg, agent_yaml=agent_yaml, memory=memory, log=log)]
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
