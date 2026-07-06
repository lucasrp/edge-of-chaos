"""cortex_config — the genotype MCP-config + per-cognition allowlist for the standing `cortex` door
(REQUISITES F1/N2/N5/R6). Genotype tool: subject-blind, no identity literals — the group resolves from
_identity (agent.yaml/EDGE_GROUP) at runtime.

The omnipresent door is registered on the parent `claude -p` via `--mcp-config <file>`, a JSON
`{"mcpServers": {"cortex": {...}}}` doc. Claude Code namespaces a server's tools as
`mcp__<server>__<tool>` and lets a subagent's `disallowedTools` REMOVE a server's tools from the
inherited pool. That is the R6 mechanism:
  - the lead beat and its self-reading fan (recall/report/map/plan/...) INHERIT the cortex server;
  - the DELTA/WORLD subagent declares `disallowedTools: mcp__cortex`, so the world-reading subject
    never inherits the self door (ADR-0014's self/world wall, held by subject-scope isolation — a
    read-only door alone does NOT stop the in-context mixing, so the deny is a v1 REQUIREMENT, N5).

Two enforcement layers, BOTH committed: this config-side deny is the PRIMARY wall (a non-granted
subject gets a config with NO cortex server registered, plus the delta skill's disallowed-tools);
the server-side check in cortex_mcp (EDGE_CORTEX_SUBJECT vs GRANTED_SUBJECTS) is secondary defense in
depth, fail-closed — it cannot see a per-caller subject over a shared pipe, so the config-side omission
is the real boundary.
"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

SERVER_NAME = "cortex"
# The server-wide tool glob: the DOCUMENTED `mcp__<server>__*` form (valid in subagent disallowedTools,
# skill disallowed-tools, AND permission rules) — the bare `mcp__<server>` is NOT a server-wide matcher
# in the permission-rule syntax (codex Slice-4 [high]), so always use the explicit `__*`.
SERVER_TOOL_GLOB = f"mcp__{SERVER_NAME}__*"

# R6/N5 — the policy is an ALLOWLIST, not a denylist (codex Slice-4 [high]): the door is GRANTED only
# to an explicit set of self-reading cognitions; an omitted/unknown/typo/new-world-alias subject gets
# NOTHING (fail-closed). The lead beat + its self-reading fan (the producer cognitions + recall +
# assemble/grill/wake/etc.) read the SELF; delta is the WORLD-reading subject and is absent by
# construction. Mirrored in cortex_mcp.GRANTED_SUBJECTS so a directly-launched server is fail-closed too.
GRANTED_SUBJECTS = {
    "lead", "recall", "assemble", "wake", "beat", "consolidate",
    "report", "map", "plan", "research", "critique", "discovery", "mentor", "grill",
    # ticket 05: lazer is a first-class producer (recall/consolidação like every producer).
    "lazer",
    # 04-C follow-up: prototype was the one roster genus missing here (pre-existing gap noted
    # by ticket 05) — same first-class recall/consolidação as every producer.
    "prototype",
}

# Kept for the world-typed config helpers / docs: the explicitly world-reading subjects. The allowlist
# above is authoritative; this names the canonical denied half for clarity (delta = the world door).
DENIED_SUBJECTS = {"delta", "world"}


def _granted(subject):
    """Fail-closed grant test (N5): a subject is granted the self door ONLY if it is an explicit
    self-cognition. Omitted/unknown/typo → NOT granted. (A bare None at the SERVER means the lead's own
    default server — handled in cortex_mcp; here, the config generator requires an explicit subject.)"""
    return (subject or "").lower() in GRANTED_SUBJECTS

# The per-server tool timeout the harness enforces (ms) — N1: a slow tool can't hang the harness even
# before the server's own fail-dark fires. Tracks EDGE_CORTEX_TIMEOUT (s); a small default.
def _timeout_ms():
    try:
        return int(float(os.environ.get("EDGE_CORTEX_TIMEOUT", "5")) * 1000)
    except (TypeError, ValueError):
        return 5000


def tool_name(tool):
    """The MCP-namespaced callable name for a cortex tool: mcp__cortex__<tool>."""
    return f"mcp__{SERVER_NAME}__{tool}"


def _edge_python(home):
    """The edge-python launcher for THIS install (the venv python wrapper). Genotype: derived from the
    install home, never a literal interpreter path."""
    return str(Path(os.path.expanduser(home)) / "tools" / "edge-python") if home else "tools/edge-python"


def _server_script(home):
    """The cortex MCP server script as an ABSOLUTE path from `home` (codex final [P2]): a relative
    `tools/cortex_mcp.py` is cwd-dependent and fails to start when --mcp-config is consumed from any
    other directory. Absolute-from-home is cwd-independent."""
    if home:
        return str(Path(os.path.expanduser(home)) / "tools" / "cortex_mcp.py")
    return "tools/cortex_mcp.py"


def mcp_config(group=None, home=None, subject=None):
    """The {"mcpServers": {"cortex": {...}}} doc registering the stdio cortex server. The group resolves
    from _identity at runtime (no literal); the server env carries EDGE_GROUP so the server resolves the
    SAME identity its parent did. A per-server timeout bounds the harness (N1).

    R6/N5 fail-closed (codex Slice-4 [medium]): a DENIED (delta/world) subject gets a config with NO
    cortex server at all — the strongest deny (nothing to inherit). For a granted subject, the server
    env bakes EDGE_CORTEX_SUBJECT so the SERVER itself enforces the deny even if the client glob is
    bypassed (defense in depth, not glob-only)."""
    # Group resolution is cross-install-safe (codex final [P2] x2). The MCP subprocess INHERITS the
    # launcher's env, and `_identity.group()` prioritizes EDGE_GROUP over agent.yaml — so merely
    # OMITTING EDGE_GROUP does not scrub a STALE inherited one (an `edge-heartbeat --home <other>` would
    # then read the launcher's group). The fix: resolve the group from the TARGET home's agent.yaml and
    # bake it EXPLICITLY, which OVERRIDES any inherited stale EDGE_GROUP. An explicit `group` arg still
    # wins (a genotype install naming its own group).
    if home is None:
        try:
            import _identity
            home = str(_identity.edge_home())
        except Exception:  # noqa: BLE001 — fall back to the repo-relative launcher
            home = None
    if group is None:
        import _identity
        # Precedence matches _identity.group() so the door reads the SAME group as the rest of the beat
        # (codex final [P2]): the intentional EDGE_GROUP env override FIRST, then the TARGET home's
        # agent.yaml (graph_group → name → codename, read straight from the file, never the launcher
        # checkout). The resolved value is BAKED, so it overrides any stale inherited env in the
        # subprocess; an unresolved identity bakes empty (the scrub above) and the server fails loud.
        group = os.environ.get("EDGE_GROUP")
        if not group and home:
            target_yaml = Path(os.path.expanduser(home)) / "agent.yaml"
            if target_yaml.exists():
                cfg = _identity._cfg(target_yaml)
                group = cfg.get("graph_group") or cfg.get("name") or cfg.get("codename")
    if not _granted(subject):
        # FAIL-CLOSED (N5): a delta/world OR omitted/unknown subject gets a config with NO cortex
        # server at all — the strongest deny (nothing to inherit). Only an explicit self-cognition is
        # granted; the door is never registered for anyone else by default.
        return {"mcpServers": {}}
    env = {}
    # ALWAYS set EDGE_GROUP explicitly (codex final [P1]): bake the RESOLVED group (explicit OR
    # target-home-resolved) to OVERRIDE any stale inherited value; when the target identity is
    # UNRESOLVED, set it EMPTY to SCRUB the inherited launcher group (empty is falsy in
    # _identity.group(), so the target server falls through to its own agent.yaml and FAILS LOUD on
    # truly-missing identity — never registers the door against the wrong tenant, ADR-0015). Either
    # way the MCP subprocess can never inherit a foreign group across installs.
    env["EDGE_GROUP"] = group or ""
    env["EDGE_CORTEX_SUBJECT"] = subject    # the server-side deny reads this — fail-closed seam
    return {
        "mcpServers": {
            SERVER_NAME: {
                "command": _edge_python(home),
                "args": [_server_script(home)],
                "env": env,
                "timeout": _timeout_ms(),
            }
        }
    }


def allowed_tools(subject=None):
    """The cortex tools this subject may use — ALLOWLIST, fail-closed (N5): ONLY an explicit
    self-cognition gets the server glob; an omitted/unknown/world subject gets nothing."""
    return [SERVER_TOOL_GLOB] if _granted(subject) else []


def disallowed_tools(subject=None):
    """The cortex tools REMOVED from this subject's inherited pool. A non-granted subject (delta/world
    OR unknown) has the whole cortex server removed (disallowed-tools: mcp__cortex__*) so it never
    inherits the self door."""
    return [] if _granted(subject) else [SERVER_TOOL_GLOB]


def build_beat_command(claude_bin, config_path):
    """The lead beat command WITH the cortex door registered: the base single-shot `claude -p -` plus
    `--mcp-config <config_path>` so the lead AND its self-reading fan can pull cortex_* mid-turn (F1).
    The delta/world subagent the lead fans denies the tool via its own `disallowedTools` (R6)."""
    return [claude_bin, "-p", "-", "--dangerously-skip-permissions", "--mcp-config", config_path]


def write_config(path, subject, group=None, home=None):
    """Render the MCP config for `subject` to `path` (the generated per-install genotype artifact).
    `subject` is REQUIRED (N5 fail-closed, codex Slice-4 [high]): there is no unscoped config — every
    rendered config is for an explicit cognition, so a world/unknown subject yields an empty config
    rather than an accidentally-open one. Returns the path."""
    import json
    import os as _os
    if not subject:
        raise ValueError("write_config requires an explicit subject (N5 fail-closed: no unscoped "
                         "cortex config — name the cognition the door is for)")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(mcp_config(group=group, home=home, subject=subject), indent=2)
    # ATOMIC write (codex final [P2]): two overlapping heartbeats for the same home write the SAME
    # fixed path while another claude may be starting from it — a partial write would launch with a
    # truncated/invalid config. Write to a per-pid temp then os.replace (atomic on POSIX), so a reader
    # always sees either the old or the new whole file, never a half-written one.
    tmp = p.with_name(f".{p.name}.{_os.getpid()}.tmp")
    tmp.write_text(body)
    _os.replace(tmp, p)
    return p
