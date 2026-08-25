"""Beat launcher — run the beat as an agent inside Claude Code (ADR-0003).

The launcher does no cognition: it loads the /ed-beat skill body and pipes it into a single
`claude -p -` invocation. Cognition lives in the skill. Interactive dispatch does not use this
at all — the live session runs the skill in-place (never spawns claude -p).
"""
import argparse
import fcntl
import json
import os

import _identity
import random
import shutil
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

import cortex
import eventlog

REPO = Path(__file__).resolve().parent.parent

# Headless beat runtimes. `opus`/`fable` are Anthropic model aliases on the claude CLI
# (`claude --model opus|fable`); there is no separate fable binary on the fleet.
FIXED_HEARTBEAT_CLIS = frozenset({"claude", "grok", "codex", "opus", "fable"})
# Operator mix 2026-07-13: 33% grok · 33% codex · 16.5% opus · 16.5% fable (sum 99).
DEFAULT_HEARTBEAT_CLI_MIX = (
    ("grok", 33.0),
    ("codex", 33.0),
    ("opus", 16.5),
    ("fable", 16.5),
)

# Headless beat runtimes. `opus`/`fable` are Anthropic model aliases on the claude CLI
# (`claude --model opus|fable`); there is no separate fable binary on the fleet.
FIXED_HEARTBEAT_CLIS = frozenset({"claude", "grok", "codex", "opus", "fable"})
# Operator mix 2026-07-13: 33% grok · 33% codex · 16.5% opus · 16.5% fable (sum 99).
DEFAULT_HEARTBEAT_CLI_MIX = (
    ("grok", 33.0),
    ("codex", 33.0),
    ("opus", 16.5),
    ("fable", 16.5),
)

# Ato-1 produce forms (25/08): round-robin among exactly these. No critique, no experiment.
PRODUCE_FORMS = (
    "report", "research", "discovery", "lazer", "map", "plan", "prototype",
)
BEAT_PRODUCE_TYPE = "beat.produce"


@contextmanager
def _produce_lock(log):
    """Serialize pick_produce check+append so one dispatch cannot reroll."""
    lock_path = Path(log).with_name(Path(log).name + ".produce.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def produce_for(dispatch_id, log=eventlog.LOG):
    """The persisted Ato-1 pick for this dispatch, or None. Same beat does not reroll."""
    if not isinstance(dispatch_id, str) or not dispatch_id.strip():
        return None
    live = None
    for e in eventlog.read(types=[BEAT_PRODUCE_TYPE], log=log):
        payload = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        if payload.get("dispatch_id") == dispatch_id:
            live = dict(payload, seq=e.get("seq"))
    if live is not None and live.get("forma") not in PRODUCE_FORMS:
        raise ValueError(
            f"beat.produce forjada/legada: forma {live.get('forma')!r} fora do "
            f"roster {PRODUCE_FORMS} para {dispatch_id!r}")
    return live


def last_produce_forma(log=eventlog.LOG):
    last = None
    for e in eventlog.read(types=[BEAT_PRODUCE_TYPE], log=log):
        payload = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        if payload.get("forma") in PRODUCE_FORMS:
            last = payload["forma"]
    return last


def next_produce_forma(log=eventlog.LOG):
    last = last_produce_forma(log)
    if last is None or last not in PRODUCE_FORMS:
        return PRODUCE_FORMS[0]
    return PRODUCE_FORMS[(PRODUCE_FORMS.index(last) + 1) % len(PRODUCE_FORMS)]


def pick_produce(dispatch_id, *, tema=None, intent=None, faro=None, log=eventlog.LOG):
    """Persist the RR produce form for this dispatch. Re-reading returns the same pick."""
    if not isinstance(dispatch_id, str) or not dispatch_id.strip():
        raise ValueError("dispatch_id must be a non-blank string")
    dispatch_id = dispatch_id.strip()
    tema = (tema or "").strip()
    intent = (intent or "").strip()
    faro = (faro or "").strip()
    with _produce_lock(log):
        existing = produce_for(dispatch_id, log=log)
        if existing is not None:
            return existing
        forma = next_produce_forma(log)
        payload = {
            "dispatch_id": dispatch_id,
            "forma": forma,
            "tema": tema,
            "intent": intent,
            "faro": faro,
        }
        ev = eventlog.append(BEAT_PRODUCE_TYPE, "beat", payload, log=log)
        return dict(payload, seq=ev["seq"])


def require_produce(dispatch_id, log=eventlog.LOG):
    """Ato-2 door: live beat.produce, or leftover live pauta.proposta. RR is the trunk."""
    picked = produce_for(dispatch_id, log=log)
    if picked is not None:
        return picked
    import pauta
    proposta = pauta.proposta_for(dispatch_id, log=log)
    if proposta is not None:
        return proposta
    raise RuntimeError(
        f"o dente: sem beat.produce (nem pauta.proposta leftover) para dispatch "
        f"{dispatch_id!r} — Ato-2 não abre. Rode tools/_beat.py pick-produce "
        "(round-robin among report/research/discovery/lazer/map/plan/prototype). "
        "tools/pauta.py sortear is not the trunk.")



@contextmanager
def heartbeat_lock(home):
    """Serialize the WHOLE heartbeat critical section {capture before_count -> run claude -p ->
    assert_beat_produced} across concurrent heartbeats (Codex gate round-4 [medium]).

    The post-dispatch gate captures a corpus count BEFORE dispatch and accepts ANY increase after
    `claude -p` returns. Under overlap that breaks: two heartbeats (or a heartbeat + another
    producer) let one invocation produce NOTHING yet pass, because another appended a kerneled
    Artefato inside its before/after window — so a corpus increase is no longer attributable to the
    invocation that produced it. Holding an exclusive `fcntl.flock` on a per-install lockfile for the
    full window (the same flock pattern as `append_batch`) means the second heartbeat
    cannot begin its own before/after window until the first's gate completes: no overlap, so any
    increase is attributable to the invocation that produced it. Blocking flock is simplest + correct.
    """
    lock_path = Path(home) / "state" / "beat" / "heartbeat.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def assert_beat_produced(log, before_count, expected_producer=None, dispatch_id=None) -> list:
    """POST-DISPATCH gate: a CLI exit of 0 only proves the subprocess ran.

    A live ``beat.produce`` pick (Ato-1 RR) authorizes production. A leftover
    ``pauta.proposta`` still authorizes (commanded/old road). Beat-origin without
    either is a gap — the happy path must persist the RR pick.
    """
    gaps = []
    corpus = cortex.corpus_at(log=log)
    after_count = len(corpus)
    proposta = None
    produce = None
    silencio = False
    if dispatch_id is not None:
        import pauta
        try:
            produce = produce_for(dispatch_id, log=log)
        except ValueError as forgery:
            gaps.append(f"beat.produce forjada (leitura recusada): {forgery}")
        try:
            proposta = pauta.proposta_for(dispatch_id, log=log)
        except ValueError as forgery:
            gaps.append(f"pauta.proposta forjada (leitura recusada pelo fold): {forgery}")
        silencio = pauta.latest_pauta_state(dispatch_id, log=log) == "silencio"
    if after_count - before_count < 1:
        if not (silencio and proposta is None and produce is None):
            gaps.append(f"no new Artefato: corpus stayed at {after_count} (was {before_count})")
    debt = cortex.artefatos_without_kernel(log=log)
    if debt:
        gaps.append(f"C3 debt — Artefato(s) published without an intent kernel: {debt}")
    new_items = corpus[before_count:]
    if dispatch_id is not None and new_items:
        authority = produce if produce is not None else proposta
        if authority is None:
            gaps.append(
                "the dente: Artefato(s) published with no live beat.produce (nor leftover "
                f"pauta.proposta) for dispatch {dispatch_id!r}: "
                f"{[i.get('slug') for i in new_items]}")
        else:
            expected_producer = authority.get("forma")
            prefix = authority.get("slug_prefix") if produce is None else None
            if prefix:
                wrong_slug = [i.get("slug") for i in new_items
                              if not str(i.get("slug") or "").startswith(prefix)]
                if wrong_slug:
                    gaps.append(
                        f"o nome carrega o setup (spec §3): slug sem o prefixo da célula "
                        f"{prefix!r}: {wrong_slug}")
    if expected_producer is not None:
        wrong = [item.get("slug") for item in new_items
                 if item.get("skill") != expected_producer]
        if wrong:
            gaps.append(
                f"authoritative dispatch producer {expected_producer!r} violated by Artefato(s): "
                f"{wrong}")
    return gaps


def dispatch_plan(subject, dispatch_id, *, runtime_command=None, log=eventlog.LOG,
                  require_pauta=True):
    """Plan one beat dispatch.

    Ato-1 trunk is round-robin ``beat.produce`` among PRODUCE_FORMS. A leftover
    live ``pauta.proposta`` still binds (not the trunk). ``require_pauta`` is the
    Ato-2 door: no pick and no leftover proposta raises. Pre-launch
    (require_pauta=False) leaves producer None until pick-produce runs.
    ``pauta.py sortear`` is not the only Ato-1 and is not the trunk.
    """
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("dispatch subject must be a non-blank string")
    if not isinstance(dispatch_id, str) or not dispatch_id.strip():
        raise ValueError("dispatch_id must be a non-blank string")
    dispatch_id = dispatch_id.strip()
    runtime_command = list(runtime_command or ["claude", "-p", "-"])
    import pauta
    produce = produce_for(dispatch_id, log=log)
    proposta = None
    if produce is None:
        proposta = pauta.proposta_for(dispatch_id, log=log)
    if require_pauta and produce is None and proposta is None:
        require_produce(dispatch_id, log=log)
    if produce is not None:
        decision = {"dispatch_id": dispatch_id, "producer": produce["forma"],
                    "produce_seq": produce.get("seq"), "tema": produce.get("tema"),
                    "intent": produce.get("intent"), "ato1": "round-robin"}
    elif proposta is not None:
        decision = {"dispatch_id": dispatch_id, "producer": proposta["forma"],
                    "pauta_seq": proposta.get("seq"), "tema": proposta.get("tema"),
                    "slug_prefix": proposta.get("slug_prefix")}
    else:
        decision = {"dispatch_id": dispatch_id, "producer": None,
                    "pauta": "pendente — rode tools/_beat.py pick-produce "
                             "(round-robin among report/research/discovery/lazer/"
                             "map/plan/prototype) e re-derive o plano via "
                             "tools/_beat.py dispatch-plan antes de abrir Ato-2. "
                             "tools/pauta.py sortear is not the trunk."}
    import cortex_config
    surface = cortex_config.dispatch_surface(
        subject=subject.strip(), runtime_command=runtime_command,
    )
    return {"decision": decision, "tools": surface["tools"],
            "permissions": surface["permissions"]}


def mint_plan_dispatch_id():
    return f"beat-{uuid.uuid4()}"


def bind_dispatch_plan(prompt, plan):
    """Put the mechanically-authoritative plan before any skill prose/cognition."""
    encoded = json.dumps(plan, ensure_ascii=False, sort_keys=True)
    return ("AUTHORITATIVE DISPATCH PLAN (mechanical; do not override):\n"
            f"{encoded}\nEND AUTHORITATIVE DISPATCH PLAN\n\n{prompt}")


def pick_heartbeat_cli(mix=None, rng=None) -> str:
    """Draw one CLI label from the weighted mix (default operator mix 33/33/16.5/16.5)."""
    pairs = list(mix) if mix is not None else list(DEFAULT_HEARTBEAT_CLI_MIX)
    if not pairs:
        return "claude"
    labels = [p[0] for p in pairs]
    weights = [float(p[1]) for p in pairs]
    chooser = rng if rng is not None else random.Random()
    return chooser.choices(labels, weights=weights, k=1)[0]


def _load_heartbeat_cfg(home=None) -> dict:
    try:
        import yaml
        path = Path(os.path.expanduser(str(home))) / "agent.yaml" if home else None
        if path is None or not path.exists():
            path = _identity.identity_path("agent.yaml")
        cfg = yaml.safe_load(path.read_text()) or {}
        hb = cfg.get("heartbeat") or {}
        return hb if isinstance(hb, dict) else {}
    except Exception:
        return {}


def _cli_mix_from_cfg(hb: dict):
    """Optional ``heartbeat.cli_mix`` override; else the default operator mix."""
    raw = hb.get("cli_mix")
    if isinstance(raw, dict) and raw:
        pairs = []
        for name, w in raw.items():
            label = str(name).strip().lower()
            if label in FIXED_HEARTBEAT_CLIS or label == "claude":
                try:
                    pairs.append((label, float(w)))
                except (TypeError, ValueError):
                    continue
        if pairs:
            return pairs
    return list(DEFAULT_HEARTBEAT_CLI_MIX)


def heartbeat_cli(home=None, rng=None) -> str:
    """Which headless CLI runs the beat.

    Fixed: ``claude`` | ``grok`` | ``codex`` | ``opus`` | ``fable``.
    ``random`` draws from the operator mix (33% grok · 33% codex · 16.5% opus · 16.5% fable).

    Order: ``EDGE_BEAT_CLI`` env → ``agent.yaml`` ``heartbeat.cli`` → ``claude``.
    """
    env = (os.environ.get("EDGE_BEAT_CLI") or "").strip().lower()
    if env in FIXED_HEARTBEAT_CLIS:
        return env
    if env == "random":
        return pick_heartbeat_cli(rng=rng)

    hb = _load_heartbeat_cfg(home)
    cli = str(hb.get("cli") or "claude").strip().lower()
    if cli in FIXED_HEARTBEAT_CLIS:
        return cli
    if cli == "random":
        return pick_heartbeat_cli(mix=_cli_mix_from_cfg(hb), rng=rng)
    return "claude"


def resolve_claude_bin() -> str:
    """Find the claude CLI: env override, then PATH, then common install locations."""
    candidates = []
    env_override = os.environ.get("EDGE_CLAUDE_BIN") or os.environ.get("CLAUDE_BIN")
    if env_override:
        candidates.append(env_override)
    path_hit = shutil.which("claude")
    if path_hit:
        candidates.append(path_hit)
    home = Path.home()
    candidates += [str(home / ".local" / "bin" / "claude"), str(home / "bin" / "claude")]
    for hit in sorted((home / ".nvm" / "versions" / "node").glob("*/bin/claude"), reverse=True):
        candidates.append(str(hit))
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    raise FileNotFoundError("claude CLI not found on PATH or common install locations")


def resolve_grok_bin() -> str:
    """Find the grok CLI: env override, then PATH, then common install locations."""
    candidates = []
    env_override = os.environ.get("EDGE_GROK_BIN") or os.environ.get("GROK_BIN")
    if env_override:
        candidates.append(env_override)
    path_hit = shutil.which("grok")
    if path_hit:
        candidates.append(path_hit)
    home = Path.home()
    candidates += [
        str(home / ".local" / "bin" / "grok"),
        str(home / "bin" / "grok"),
        str(home / ".grok" / "bin" / "grok"),
    ]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    raise FileNotFoundError("grok CLI not found on PATH or common install locations")


def resolve_codex_bin() -> str:
    """Find the codex CLI: env override, then PATH, then common install locations."""
    candidates = []
    env_override = os.environ.get("EDGE_CODEX_BIN") or os.environ.get("CODEX_BIN")
    if env_override:
        candidates.append(env_override)
    path_hit = shutil.which("codex")
    if path_hit:
        candidates.append(path_hit)
    home = Path.home()
    candidates += [
        str(home / ".local" / "bin" / "codex"),
        str(home / "bin" / "codex"),
    ]
    for hit in sorted((home / ".nvm" / "versions" / "node").glob("*/bin/codex"), reverse=True):
        candidates.append(str(hit))
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    raise FileNotFoundError("codex CLI not found on PATH or common install locations")


def build_beat_command(claude_bin: str, mcp_config_path=None, model=None) -> list:
    """One beat = one single-shot `claude -p -`, permissions bypassed. No retry, no envelope.

    When `mcp_config_path` is given (Slice 6, F1), the lead beat is launched with `--mcp-config <path>`
    so the standing `cortex` read door is registered on the parent claude -p — pullable mid-turn by the
    lead AND the self-reading subagents it fans. The world-reading delta subagent is denied via its own
    skill `disallowed-tools: mcp__cortex__*` (Slice 4), so inheriting the parent server is safe. Without
    a path the command is the unchanged base single-shot invocation (backward-compatible).

    ``model`` (optional): Anthropic alias on the claude CLI (``opus``, ``fable``, …).
    """
    cmd = [claude_bin, "-p", "-", "--dangerously-skip-permissions"]
    if mcp_config_path:
        cmd += ["--mcp-config", str(mcp_config_path)]
    if model:
        cmd += ["--model", str(model)]
    return cmd


def build_grok_beat_command(grok_bin: str, prompt_file: Path, cwd: Path) -> list:
    """One beat = one single-shot grok headless run (``--prompt-file`` + ``--always-approve``).

    Grok does not take the skill body on stdin the way ``claude -p -`` does; the launcher writes
    the bound prompt to ``prompt_file`` and points ``--prompt-file`` at it. ``--cwd`` pins the
    install tree so tools/skills resolve under edge_home.
    """
    return [
        grok_bin,
        "--always-approve",
        "--cwd", str(cwd),
        "--prompt-file", str(prompt_file),
    ]


def build_codex_beat_command(codex_bin: str, cwd: Path) -> list:
    """One beat = one single-shot ``codex exec``; prompt on stdin (``-``), approvals bypassed.

    Heartbeat runs non-interactively on a trusted install (same posture as claude
    ``--dangerously-skip-permissions`` / grok ``--always-approve``).
    """
    return [
        codex_bin, "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "-C", str(cwd),
        "-",
    ]


def ensure_cortex_config(home, group=None):
    """Generate (idempotently) the LEAD's cortex --mcp-config for THIS install and return its path
    (Slice 6, F1/N2). A genotype path: the group resolves from identity at runtime (subject=lead, the
    granted self-cognition), so the door deploys to the fleet without an identity literal. The config
    is a RUNTIME artifact under state/cortex/ (gitignored, never committed) — it derives per install."""
    import cortex_config
    # Resolve home to an ABSOLUTE path first (codex final [P2]): the heartbeat runs claude with
    # cwd=home, so a RELATIVE --mcp-config path (and the relative command/script paths inside it) would
    # be re-resolved UNDER home again (home/home/state/...) and the server could not be found. Absolute
    # home makes the config path and its contents cwd-independent.
    home = str(Path(os.path.expanduser(str(home))).resolve())
    path = Path(home) / "state" / "cortex" / "lead.mcp.json"
    cortex_config.write_config(path, subject="lead", group=group, home=home)
    return path


def build_beat_env(home) -> dict:
    """The dispatch env = the launcher env + the install's secrets, so the beat's **agentic** source
    calls (the `via` specs in agent.yaml: exa/x/hn/arxiv/github) AND the graph leg have credentials.
    Without this the `claude -p` child inherits a key-less env and the world-leg darkens — only the
    python tools that touch `_identity` self-load secrets; the agent's own `via`-spec calls do not.
    ADR-0011: never block — a missing secrets dir just returns the base env (the leg darkens, the
    beat still runs)."""
    import _secrets
    try:
        _secrets.load_env(Path(home) / "secrets")
    except Exception:
        pass
    return dict(os.environ)


def load_beat_prompt(home) -> str:
    """The /ed-beat skill body (frontmatter stripped), piped as the prompt. home wins over repo."""
    for base in (Path(home) / "skills", REPO / "skills"):
        p = base / "beat" / "SKILL.md"
        if p.exists():
            text = p.read_text()
            if text.startswith("---"):
                parts = text.split("---", 2)
                text = parts[2] if len(parts) >= 3 else text
            return text.strip()
    raise FileNotFoundError("beat skill not found (skills/beat/SKILL.md)")


def main(argv=None, stdin=None, stdout=None):
    """Interactive fallback: the same authoritative plan seam — the DENTE included
    (no live beat.produce / leftover pauta.proposta → fails loud; Ato-2 never opens)."""
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    plan_parser = sub.add_parser("dispatch-plan")
    plan_parser.add_argument("--home", default=str(REPO))
    plan_parser.add_argument("--group", default=None)
    plan_parser.add_argument("--subject", default="lead")
    plan_parser.add_argument("--dispatch-id", required=True)
    plan_parser.add_argument("--claude-bin", default=None)
    plan_parser.add_argument("--mcp-config", default=None)
    pick = sub.add_parser("pick-produce")
    pick.add_argument("--home", default=str(REPO))
    pick.add_argument("--dispatch-id", required=True)
    pick.add_argument("--tema", default="")
    pick.add_argument("--intent", default="")
    pick.add_argument("--faro", default="")
    pub = sub.add_parser("publish-tetris")
    pub.add_argument("--home", default=str(REPO))
    pub.add_argument("--slug", required=True)
    pub.add_argument("--html", required=True)
    pub.add_argument("--intent", required=True)
    pub.add_argument("--skill", required=True)
    pub.add_argument("--dispatch-id", required=True)
    pub.add_argument("--yaml", default=None)
    pub.add_argument("--blog-dir", default=None)
    args = parser.parse_args(argv)
    stdout = sys.stdout if stdout is None else stdout
    home = Path(os.path.expanduser(args.home)).resolve()
    log = home / "state" / "events" / "log.jsonl"
    if args.command == "pick-produce":
        result = pick_produce(
            args.dispatch_id, tema=args.tema, intent=args.intent,
            faro=args.faro, log=log)
        json.dump(result, stdout, ensure_ascii=False, sort_keys=True)
        stdout.write("\n")
        return result
    if args.command == "publish-tetris":
        import publisher
        blog_dir = Path(args.blog_dir) if args.blog_dir else home / "blog" / "entries"
        result = publisher.publish_tetris(
            args.slug, args.html, intent=args.intent, skill=args.skill,
            dispatch_id=args.dispatch_id, log=log, blog_dir=blog_dir,
            yaml_path=args.yaml)
        json.dump(result, stdout, ensure_ascii=False, sort_keys=True)
        stdout.write("\n")
        return result
    claude_bin = args.claude_bin or resolve_claude_bin()
    config_path = (Path(args.mcp_config).resolve() if args.mcp_config else
                   ensure_cortex_config(home, group=args.group))
    command = build_beat_command(claude_bin, mcp_config_path=config_path)
    result = dispatch_plan(
        args.subject, args.dispatch_id,
        runtime_command=command,
        log=log,
    )
    json.dump(result, stdout, ensure_ascii=False, sort_keys=True)
    stdout.write("\n")
    return result

if __name__ == "__main__":
    main()
