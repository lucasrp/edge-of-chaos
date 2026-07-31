"""_hermes_provision - render Hermes skill wrappers for an Edge install.

Hermes (Nous Research) é a 4ª CLI padrão do edge (operador 2026-07-25). Ele descobre
user-skills de HERMES_HOME/skills/<name>/SKILL.md — a MESMA convenção SKILL.md dos
outros harnesses. Os arquivos aqui são wrappers finos que apontam de volta pro contrato
canônico do install (mesmo shape dos wrappers Grok/Codex). Genérico por construção:
nenhum nome de install hardcoded — qualquer usuário do hermes com o edge provisiona igual.
"""
from pathlib import Path
import shutil

import yaml

def _write_if_changed(path: Path, content: str) -> None:
    """Write only when content differs, keeping repeated apply runs idempotent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() == content:
        return
    path.write_text(content)


def hermes_prefixes(cfg: dict) -> list:
    """Expose only the install-specific alias; duplicate families add no capability."""
    prefix = cfg.get("skill_prefix") or cfg.get("codename") or cfg.get("name") or "edge"
    return [str(prefix).strip()]

_OBSOLETE_RENDERER = r'''
def _render_hermes_skill_old(slug: str, prefix: str, canonical_skill: Path, edge_group=None) -> str:
    """Render a global Hermes wrapper for one canonical Edge skill."""
    name = f"{prefix}-{slug}"
    canonical = str(Path(canonical_skill).expanduser())
    wake_terminal = (
        "5. WAKE TERMINAL INVARIANT: after all four briefs complete, render the canonical "
        "human-facing orientation (do not dump or merely summarize the briefs), then halt and "
        "ask what the operator wants to work on. Do not start work before their reply.\n"
        if slug == "wake" else ""
    )
    mentor_invariant = (
        "0. HERMES PREFLIGHT SHORT-CIRCUIT: when `EOC MENTOR PREFLIGHT` is present, answer directly "
        "from that payload before any tool call. Do not reload the skill, memory, portfolio, history, "
        "or Cortex. State level/stage; compare three work fronts; cite one supplied community; name "
        "the cross-front pattern; choose one justified priority; prescribe one executable next step; "
        "do not end with a topic-selection question. Only use the remaining steps when the preflight "
        "is absent.\n"
        "5. MENTOR CONTRACT INVARIANT: observe leveling-state and the operator's work first; cite "
        "one state line before any residual question. Render the contract's opt-in portfolio "
        "orientation and use the lint agenda as evidence, not as an opening script. Ask at most one "
        "free-prose residual question, never a menu. After the operator answers, process all "
        "applicable persona writeback, steers, synthesis, and traceable inscription in the same "
        "turn; advice alone is not completion. Do not stop and ask them to say continue. Do not "
        "force a closing question when the path is clear, and never invent a writeback or "
        "inscription merely to satisfy this wrapper.\n"
        "6. HERMES MEMORY ADAPTER (mandatory, provider-agnostic): use the standing memory context "
        "injected by Hermes' configured memory provider (local, Honcho, Mem0, Hindsight, Holographic, "
        "or another supported provider) and combine it with canonical leveling, portfolio recall, "
        "and Cortex communities. Before the first user-facing mentor response — including orientation, "
        "status, disclaimer, or question — use any available provider-native profile/context capability "
        "for a compact peer snapshot. If the request depends on prior "
        "statements, preferences, relationships, or cross-session patterns, use the available "
        "provider-native search/reasoning capability; Honcho tools are one implementation, not a "
        "requirement. If it names or depends on a specific Hermes conversation, decision, or where "
        "work stopped, call `session_search` and inspect that original session before concluding. "
        "Do not require tools the configured provider does not expose, do not call expensive retrieval "
        "without its trigger, do not treat one memory system as a substitute for another, and never "
        "persist inferred facts without evidence. HERMES HARD GATE: before any user-facing mentor "
        "response, evidence must include current conversation + injected/provider memory context (or "
        "explicit unavailable marker). Then run exactly `$EDGE_HOME/tools/edge-python "
        "$EDGE_HOME/tools/mentor_preflight.py`; its JSON is the single mandatory read door for "
        "canonical leveling + portfolio recall + Cortex communities. Do not replace it with manual "
        "file inspection or prose. Evidence must therefore include canonical leveling + portfolio recall + Cortex communities "
        "(or explicit DARK marker), plus any retrieval triggered by the request. If any leg lacks an "
        "actual attempt, emit no mentor response and ask no question; continue the reads first. The "
        "generic orientation rule does not apply to mentor until these reads complete. Missing evidence "
        "is an instruction to keep reading, not a valid final answer or a reason to ask the operator "
        "to continue.\n"
        if slug == "mentor" else ""
    )
    return (
        "---\n"
        f"name: {name}\n"
        canonical_steps = (
            f"1. Read `{canonical}` completely (canonical contract).\n"
            f"2. Follow the active skill — do not re-interpret it from this wrapper.\n"
            f"3. Work from the live install at `{canonical}`; the install's edge_home owns the skills/ tree.\n"
            if slug != "mentor" else ""
        )
        return (
            f"---\nname: {name}\ndescription: Edge `{slug}` skill (`/{name}`). Use when the user "
            f"invokes `/{name}`, `@{name}`, or asks for Edge of Chaos {slug}.\n---\n"
            f"You are running the Edge of Chaos skill **{name}**.\n\n"
            + mentor_invariant
            + canonical_steps
            + (f"4. Set `EDGE_GROUP={edge_group}` for every EoC tool command.\n" if edge_group else "")
            + wake_terminal
        )


'''


def render_hermes_skill(slug: str, prefix: str, canonical_skill: Path, edge_group=None) -> str:
    """Render a Hermes wrapper; mentor consumes the native preflight without re-reading."""
    name = f"{prefix}-{slug}"
    canonical_path = Path(canonical_skill).expanduser()
    canonical = str(canonical_path)
    edge_home = str(canonical_path.parent.parent.parent)
    header = (
        f"---\nname: {name}\ndescription: Edge `{slug}` skill (`/{name}`). Use when invoked. "
        f"Canonical contract: {canonical}.\n---\n"
        f"You are running the Edge of Chaos skill **{name}**.\n\n"
    )
    if slug == "mentor":
        return header + (
            "HERMES PREFLIGHT SHORT-CIRCUIT: `EOC MENTOR PREFLIGHT` is the completed native "
            "mentor read produced by `$EDGE_HOME/tools/mentor_preflight.py`, the single mandatory read door. Use it before any user-facing mentor content: the first user-facing mentor response must answer directly from it before any tool call. State level/stage; compare "
            "at least three concrete work fronts; cite one supplied Cortex community; name the "
            "cross-front pattern; choose one priority and justify it; prescribe one executable next "
            "step; do not end with a question. The payload already combines the configured memory provider "
            "through a provider-agnostic adapter; Honcho tools are one implementation, not a requirement. "
            "It includes recent session history, local leveling, portfolio, and "
            "Cortex communities and the lint agenda as evidence. If that read door fails, emit no mentor response and ask no question. The supplied portfolio is the opt-in portfolio orientation; the response "
            "itself must provide persona synthesis, steers, and a concrete intervention, never a menu; "
            "advice alone is not completion; after intervention, preserve persona writeback, steers, synthesis, and traceable inscription. "
            "The generic orientation rule does not apply to mentor. "
            "Do not stop and ask them to say continue. Do not force a closing question. never invent a writeback or inscription. Do not emit an instruction to keep reading, reload the skill, or repeat any preflight.\n"
        )
    return header + (
        f"1. Read `{canonical}` completely (canonical contract).\n"
        "2. Follow the active skill without re-interpreting it from this wrapper.\n"
        f"3. Work from the live install at `{canonical}`.\n"
        f"4. For every EoC tool command, set `EDGE_HOME={edge_home}` and run with working "
        f"directory `{edge_home}` so canonical relative paths resolve against the live install.\n"
        + (f"5. Set `EDGE_GROUP={edge_group}` for every EoC tool command.\n" if edge_group else "")
        + ("6. WAKE TERMINAL INVARIANT: render the canonical human-facing orientation, then halt and ask what the operator wants to work on. Do not start work before their reply.\n" if slug == "wake" else "")
    )


def provision_hermes(cfg: dict, repo: Path, edge_home: Path, hermes_home: Path,
                     edge_group=None) -> list:
    """Idempotently provision HERMES_HOME/skills with prefixed EoC wrappers."""
    repo = Path(repo)
    edge_home = Path(edge_home).expanduser()
    hermes_home = Path(hermes_home).expanduser()
    prefixes = hermes_prefixes(cfg)
    rows = []
    installed = 0

    skills_src = repo / "skills"
    if skills_src.exists():
        skill_dirs = [p for p in sorted(skills_src.iterdir())
                      if p.is_dir() and not p.name.startswith(".")
                      and p.name != "_shared" and (p / "SKILL.md").exists()]
        desired = {f"{prefix}-{skill_dir.name}"
                   for prefix in prefixes for skill_dir in skill_dirs}
        installed_skills = hermes_home / "skills"
        if installed_skills.is_dir():
            for path in installed_skills.iterdir():
                if path.name not in desired and path.is_dir() \
                        and _managed_wrapper(path, repo, edge_home):
                    shutil.rmtree(path)
        for skill_dir in skill_dirs:
            canonical = edge_home / "skills" / skill_dir.name / "SKILL.md"
            for prefix in prefixes:
                dst = hermes_home / "skills" / f"{prefix}-{skill_dir.name}" / "SKILL.md"
                _write_if_changed(
                    dst,
                    render_hermes_skill(
                        slug=skill_dir.name, prefix=prefix, canonical_skill=canonical,
                        edge_group=edge_group),
                )
                installed += 1
    rows.append(f"hermes skills: {installed} wrappers em {hermes_home / 'skills'}")
    return rows


def _managed_wrapper(path, repo, edge_home=None):
    try:
        body = (path / "SKILL.md").read_text()
    except OSError:
        return False
    roots = [Path(repo).resolve() / "skills"]
    if edge_home is not None:
        roots.append(Path(edge_home).resolve() / "skills")
    marker = any(text in body for text in ("Canonical implementation:", "Read the full contract at", "Canonical contract:"))
    return marker and any(str(root) in body for root in roots)

def reconcile_hermes_profiles(cfg, repo, edge_home, hermes_root):
    import hermes_profiles

    root = Path(hermes_root)
    homes = [("default", root)]
    profiles = root / "profiles"
    if profiles.is_dir():
        homes.extend((p.name, p) for p in profiles.iterdir() if p.is_dir())
    result = {}
    for name, home in homes:
        member = hermes_profiles.membership(root, name)
        if member.enabled:
            result[name] = provision_hermes(
                cfg, repo, edge_home, home, edge_group=member.edge_group)
            continue
        removed = []
        skills = home / "skills"
        if skills.is_dir():
            for path in skills.iterdir():
                if path.is_dir() and _managed_wrapper(path, repo, edge_home):
                    shutil.rmtree(path)
                    removed.append(path.name)
        result[name] = {"skills_removed": removed}
    return result


def configure_hermes_group(hermes_root, edge_group):
    """Seed the EoC group unless Hermes already has an explicit policy."""
    path = Path(hermes_root) / "config.yaml"
    try:
        cfg = yaml.safe_load(path.read_text()) or {}
    except FileNotFoundError:
        cfg = {}
    if not isinstance(cfg, dict):
        raise ValueError(f"Hermes config must be a mapping: {path}")
    if "edge_group" in cfg:
        return False
    cfg["edge_group"] = edge_group
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))
    tmp.replace(path)
    return True


def install_hermes_plugin(cfg, repo, edge_home, hermes_root):
    """Install the startup reconciler as a normal Hermes user plugin."""
    explorer_path = Path(repo) / ".claude" / "agents" / "explorer.md"
    plugin = Path(hermes_root) / "plugins" / "edge-of-chaos"
    plugin.mkdir(parents=True, exist_ok=True)
    (plugin / "plugin.yaml").write_text(
        "name: edge-of-chaos\nversion: 1.0.0\ndescription: Reconcile Edge skills across Hermes profiles\n"
    )
    (plugin / "__init__.py").write_text(
        "from pathlib import Path\nimport sys\n\n"
        f"REPO = Path({str(Path(repo))!r})\n"
        f"EDGE_HOME = Path({str(Path(edge_home))!r})\n"
        f"HERMES_ROOT = Path({str(Path(hermes_root))!r})\n"
        f"EXPLORER_CONTRACT_PATH = Path({str(explorer_path)!r})\n"
        "sys.path.insert(0, str(REPO / 'tools'))\n"
        "import sources\n"
        "def mark_session_active(session_id='', **_):\n"
        "    if session_id:\n"
        "        from sessions import mark_hermes_session_active\n"
        "        mark_hermes_session_active(session_id, env={'EDGE_HOME': str(EDGE_HOME)})\n"
        "def mark_session_inactive(session_id='', **_):\n"
        "    if session_id:\n"
        "        from sessions import mark_hermes_session_inactive\n"
        "        mark_hermes_session_inactive(session_id, env={'EDGE_HOME': str(EDGE_HOME)})\n"
        "def _active_edge_group():\n"
        "    from hermes_cli.profiles import get_active_profile_name\n"
        "    from hermes_profiles import membership\n"
        "    profile_name = get_active_profile_name()\n"
        "    resolved = membership(HERMES_ROOT, profile_name)\n"
        "    if not resolved.enabled or not resolved.edge_group:\n"
        "        raise RuntimeError(f'active Hermes profile {profile_name!r} has no Edge group')\n"
        "    return resolved.edge_group\n"
        "def _invokes(text, slug):\n"
        "    text = (text or '').lstrip()\n"
        "    command = f'/Steve-{slug}'\n"
        "    if text == command or text.startswith(command + ' ') or text.startswith(command + '\\n'):\n"
        "        return True\n"
        "    prefixes = (f'Steve-{slug}: Edge `{slug}` skill', f'[IMPORTANT: The user has invoked the \\\"Steve-{slug}\\\" skill')\n"
        "    return any(text == prefix or text.startswith(prefix + ' ') or text.startswith(prefix + '\\n') for prefix in prefixes)\n"
        "def _release_lease_on_error(callback):\n"
        "    def guarded(*args, **kwargs):\n"
        "        try:\n"
        "            return callback(*args, **kwargs)\n"
        "        except BaseException:\n"
        "            mark_session_inactive(session_id=kwargs.get('session_id', ''))\n"
        "            raise\n"
        "    return guarded\n"
        "@_release_lease_on_error\n"
        "def mentor_preflight(user_message='', session_id='', **_):\n"
        "    if not _invokes(user_message, 'mentor'):\n"
        "        return None\n"
        "    import json, os, subprocess\n"
        "    env = os.environ.copy()\n"
        "    env.update(EDGE_HOME=str(EDGE_HOME), EDGE_GROUP=_active_edge_group(), HERMES_SESSION_ID=session_id)\n"
        "    raw = subprocess.run([str(EDGE_HOME / 'tools' / 'edge-python'), str(REPO / 'tools' / 'mentor_preflight.py')], cwd=str(EDGE_HOME), env=env, capture_output=True, text=True, check=True, timeout=180).stdout\n"
        "    payload = json.loads(raw)\n"
        "    return {'context': 'EOC MENTOR PREFLIGHT — FIRST RESPONSE ACCEPTANCE CONTRACT: synthesize all four sources: canonical leveling, portfolio, recent Hermes work, and Cortex communities. Explicitly state the current level/stage and quote at least one exact `communities[].name` value from the supplied Cortex payload as evidence; saying only `Cortex`, inventing a name, or proceeding when `communities` is null does not satisfy this. Write a `Frentes comparadas` section with at least three separately labeled bullets; every bullet must name a distinct supplied recent work front and state its user_goal -> outcome; name concrete accomplishments, unresolved gaps, a cross-front pattern, one justified priority, and one actionable next step. Do not anchor on the newest item. Do not return a title-only inventory, disclaimer, status update, or generic question. The preflight already contains the required evidence: do not call tools before the first user-facing response. The first response itself must complete this analysis before inviting dialogue):\\n' + "
        "json.dumps(payload, ensure_ascii=False, default=str)}\n"
        "@_release_lease_on_error\n"
        "def dig_preflight(user_message='', session_id='', **_):\n"
        "    if not _invokes(user_message, 'dig'):\n"
        "        return None\n"
        "    import os, subprocess\n"
        "    if not EXPLORER_CONTRACT_PATH.is_file():\n"
        "        raise RuntimeError('Steve-dig requires the canonical explorer contract')\n"
        "    group = _active_edge_group()\n"
        "    roadmap = sources.render_source_roadmap(EDGE_HOME / 'agent.yaml')\n"
        "    env = {**os.environ, 'EDGE_HOME': str(EDGE_HOME), 'EDGE_GROUP': group, 'HERMES_SESSION_ID': session_id}\n"
        "    result = subprocess.run([str(EDGE_HOME / 'tools' / 'edge-python'), str(EDGE_HOME / 'tools' / 'predispatch.py')], cwd=str(EDGE_HOME), env=env, capture_output=True, text=True, check=True, timeout=180)\n"
        "    import json\n"
        "    briefing = result.stdout[:1200]\n"
        "    roster, findings = sources.load_sources(EDGE_HOME / 'agent.yaml')\n"
        "    plan = json.dumps({'sources': roster, 'findings': findings}, ensure_ascii=False, separators=(',', ':'))\n"
        "    paths = {'edge_home': str(EDGE_HOME), 'roadmap': str(roadmap), 'explorer_contract': str(EXPLORER_CONTRACT_PATH), 'memory_dir': str(EDGE_HOME / 'memory'), 'memory_index': str(EDGE_HOME / 'memory' / 'MEMORY.md'), 'event_log': str(EDGE_HOME / 'state' / 'events' / 'log.jsonl')}\n"
        "    signal = \"EDGE_HOME=%s EDGE_GROUP=%s %s -c \\\"import sys;sys.path.insert(0,'tools');import eventlog;eventlog.source_signal(SLUG, REF, KIND, SIMILARITY)\\\"\" % (EDGE_HOME, group, EDGE_HOME / 'tools' / 'edge-python')\n"
        "    return {'context': 'EOC DIG PREFLIGHT READY. The canonical Steve-dig skill is already loaded: do not call skill_view/read_file/headroom_retrieve for it or this preflight. Fan world reads with delegate_task. Each child must receive its literal source/interface/query plus the explorer invariants: WORLD only; no Cortex, memory, or writes; compact evidence with URLs/snippets. The canonical explorer contract path is supplied for authority; do not paste its body. Account for every source/interface and every paid modality as queried, not applicable, or dark with a specific reason. Before answering, write the topic file and MEMORY index using the ABSOLUTE paths below, emit source.signal only for cited evidence using the exact command template, and include the PRISMA receipt.\\nPATHS=' + json.dumps(paths, ensure_ascii=False, separators=(',', ':')) + '\\nSOURCE_SIGNAL_TEMPLATE=' + signal + '\\nBRIEFING=' + briefing + '\\nSOURCE_ROSTER=' + plan}\n\n"
        "@_release_lease_on_error\n"
        "def recall_preflight(user_message='', session_id='', **_):\n"
        "    if not _invokes(user_message, 'recall'):\n"
        "        return None\n"
        "    import os, subprocess\n"
        "    env = os.environ.copy()\n"
        "    env.update(EDGE_HOME=str(EDGE_HOME), EDGE_GROUP=_active_edge_group(), HERMES_SESSION_ID=session_id)\n"
        "    code = 'import sys; sys.path.insert(0, %r); import recall; print(recall.compose_recall_brief())' % str(REPO / 'tools')\n"
        "    brief = subprocess.run([str(EDGE_HOME / 'tools' / 'edge-python'), '-c', code], cwd=str(EDGE_HOME), env=env, capture_output=True, text=True, check=True, timeout=180).stdout\n"
        "    return {'context': 'EOC RECALL PREFLIGHT — READ-ONLY SHORT-CIRCUIT: The complete canonical recall brief is supplied below. Return that brief verbatim as the first user-facing response. Do not call tools, search files, reload skills, reinterpret, summarize, add advice, ask a question, or mutate state before returning it.\\n' + brief}\n"
        "@_release_lease_on_error\n"
        "def wake_preflight(user_message='', session_id='', **_):\n"
        "    if not _invokes(user_message, 'wake'):\n"
        "        return None\n"
        "    import os, subprocess\n"
        "    env = os.environ.copy()\n"
        "    env.update(EDGE_HOME=str(EDGE_HOME), EDGE_GROUP=_active_edge_group(), HERMES_SESSION_ID=session_id)\n"
        "    result = subprocess.run([str(EDGE_HOME / 'tools' / 'edge-python'), str(REPO / 'tools' / 'predispatch.py'), '--origin', 'user_requested'], cwd=str(EDGE_HOME), env=env, capture_output=True, text=True, check=True, timeout=180)\n"
        "    lines = result.stdout.splitlines()\n"
        "    dispatch_id = next((line for line in lines if line.startswith('DISPATCH_ID=')), '')\n"
        "    recall_at = result.stdout.find('\\n# Recall')\n"
        "    if not dispatch_id or recall_at < 0:\n"
        "        raise RuntimeError('wake preflight missing DISPATCH_ID or Recall section')\n"
        "    compact = dispatch_id + '\\n\\n[BRIEFING PROJECTION]\\n' + result.stdout[:6000] + '\\n\\n[RECALL PROJECTION]\\n' + result.stdout[recall_at:recall_at + 6000] + '\\n\\n' + dispatch_id + '\\n[Canonical Wake payload compacted deterministically for the Hermes first-response context.]'\n"
        "    return {'context': 'EOC WAKE PREFLIGHT — FIRST RESPONSE TERMINAL CONTRACT: the canonical mechanical Wake has completed and a bounded canonical projection follows. Render a concise human-facing orientation grounded only in this payload: current identity/stage, active Direction, Recall/portfolio signal, and the hottest recent work. Then halt and ask what the operator wants to work on. Do not call tools, reload skills, rerun predispatch, start Beat, or begin work before that reply. Preserve the DISPATCH_ID in the response. The projection marker is intentional and is not missing context.\\n' + compact}\n"
        "def register(ctx):\n"
        "    from _hermes_provision import reconcile_hermes_profiles\n"
        f"    reconcile_hermes_profiles({cfg!r}, REPO, EDGE_HOME, HERMES_ROOT)\n"
        "    ctx.register_hook('pre_llm_call', mark_session_active)\n"
        "    ctx.register_hook('pre_llm_call', mentor_preflight)\n"
        "    ctx.register_hook('pre_llm_call', dig_preflight)\n"
        "    ctx.register_hook('pre_llm_call', recall_preflight)\n"
        "    ctx.register_hook('pre_llm_call', wake_preflight)\n"
        "    ctx.register_hook('post_llm_call', mark_session_inactive)\n"
        "    ctx.register_hook('pre_tool_call', mark_session_active)\n"
        "    ctx.register_hook('post_tool_call', mark_session_inactive)\n"
    )
    return plugin
