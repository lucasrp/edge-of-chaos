"""Beat launcher — run the beat as an agent inside Claude Code (ADR-0003).

The launcher does no cognition: it loads the /ed-beat skill body and pipes it into a single
`claude -p -` invocation. Cognition lives in the skill. Interactive dispatch does not use this
at all — the live session runs the skill in-place (never spawns claude -p).
"""
import argparse
import fcntl
import json
import os
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
    """The deterministic POST-DISPATCH gate (Codex gate finding [high]): a `claude -p` exit of 0
    only proves the subprocess ran — NOT that stage-(iii) corpus work happened. Folding the log is
    the only proof. Given the corpus count captured BEFORE the beat, return the list of GAPS — empty
    means the beat produced (or honestly declined); non-empty means the invocation must fail:

      * the corpus did NOT grow by >=1 — UNLESS ``dispatch_id`` is given, the LATEST pauta.*
        event for it is a `pauta.silencio` AND no live `pauta.proposta` stands (spec §4 lei do
        risco: logged silence is the HONEST failure mode, never a punished one; latest-event
        replay, never any-historical, adv r1 #9 — and a LIVE proposta still owes production
        even when a later silêncio landed, because silêncio doesn't kill: exemption inversion,
        adv r2 #2);
      * the live proposta is a FORGERY per `pauta.proposta_for`'s own read-side verification
        (voz without a commanded dispatch.open, or an out-of-roster forma — round 4, Variant A):
        the fold RAISES for every other reader; this gate alone converts the raise into a named
        gap and proceeds with proposta=None, because the post-gate's job is to REPORT, never to
        crash the heartbeat gate;
      * `artefatos_without_kernel(log)` is non-empty (a published Artefato with no intent kernel — C3
        debt), which is a gap even when the corpus grew;
      * THE DENTE (ADR-0024), when ``dispatch_id`` is given: new Artefato(s) with no live
        `pauta.proposta` for this dispatch, whose skill is not the proposta's `forma`, or whose
        slug does not start with the proposta's `slug_prefix` (spec §3 "o nome carrega o setup" —
        enforced mechanically at this gate, never asserted in agent JSON; adv r1 #10).

    ``expected_producer`` remains for callers that already hold a forma. A pure reader over the
    log: edge-heartbeat captures before_count, runs the beat, then calls this; gaps → NONZERO exit."""
    gaps = []
    corpus = cortex.corpus_at(log=log)
    after_count = len(corpus)
    proposta = None
    silencio = False
    if dispatch_id is not None:
        import pauta
        try:
            proposta = pauta.proposta_for(dispatch_id, log=log)
        except ValueError as forgery:
            # round 4 (Variant A): the fold verifies once and raises for every reader;
            # the post-gate alone reports instead — the remaining dente logic then
            # correctly gaps "artefato with no live proposta" / "no new Artefato".
            gaps.append(f"pauta.proposta forjada (leitura recusada pelo fold): {forgery}")
        silencio = pauta.latest_pauta_state(dispatch_id, log=log) == "silencio"
    if after_count - before_count < 1:
        # exemption iff latest==silencio AND no live proposta (adv r2 #2): a proposta
        # viva ainda deve produção mesmo com silêncio posterior (silêncio não mata).
        if not (silencio and proposta is None):
            gaps.append(f"no new Artefato: corpus stayed at {after_count} (was {before_count})")
    debt = cortex.artefatos_without_kernel(log=log)
    if debt:
        gaps.append(f"C3 debt — Artefato(s) published without an intent kernel: {debt}")
    new_items = corpus[before_count:]
    if dispatch_id is not None and new_items:
        if proposta is None:
            gaps.append(
                "the dente (ADR-0024): Artefato(s) published with no live pauta.proposta for "
                f"dispatch {dispatch_id!r}: {[i.get('slug') for i in new_items]}")
        else:
            expected_producer = proposta["forma"]
            prefix = proposta.get("slug_prefix")
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
    """Plan one beat dispatch: the producer IS the Pauta's `forma` (ADR-0024 — the choice left
    the producer/rotation and became a dispatch stage; the rotation cursor road is DEAD).

    THE DENTE: with ``require_pauta`` (the default — the Ato-2 door), no live `pauta.proposta`
    for ``dispatch_id`` raises; the plan's producer is `proposta['forma']`. The heartbeat
    launcher computes a PRE-LAUNCH plan (``require_pauta=False``) before the agent exists:
    producer is explicitly None + `pauta: pendente` — the trunk runs the funnel (sortear →
    catálogo → sugestões → shortlist → grounding → propose) and re-derives the plan through
    this same seam before opening any branch.

    Portfolio is deliberately absent: maps describe the mentee's work and cannot authorize the
    edge. A pure read of the eventlog + the static surface — idempotent by construction
    (ADR-0006: the log is the truth; no cursor state to spend)."""
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("dispatch subject must be a non-blank string")
    if not isinstance(dispatch_id, str) or not dispatch_id.strip():
        raise ValueError("dispatch_id must be a non-blank string")
    dispatch_id = dispatch_id.strip()
    runtime_command = list(runtime_command or ["claude", "-p", "-"])
    import pauta
    if require_pauta:
        proposta = pauta.require_proposta(dispatch_id, log=log)
    else:
        # round 4 (Variant A): proposta_for itself verifies the live proposta (forged
        # voz authority, out-of-roster forma) and RAISES — the r3 per-door roster
        # re-check that lived here is deleted; this door inherits the buckle for free.
        proposta = pauta.proposta_for(dispatch_id, log=log)
    if proposta is None:
        decision = {"dispatch_id": dispatch_id, "producer": None,
                    "pauta": "pendente — rode o funil da Pauta (tools/pauta.py sortear → "
                             "propose) e re-derive o plano via tools/_beat.py dispatch-plan "
                             "antes de abrir Ato-2 (o dente, ADR-0024)"}
    else:
        decision = {"dispatch_id": dispatch_id, "producer": proposta["forma"],
                    "pauta_seq": proposta.get("seq"), "tema": proposta.get("tema"),
                    "slug_prefix": proposta.get("slug_prefix")}
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
        path = Path(os.path.expanduser(str(home or REPO))) / "agent.yaml"
        if not path.exists():
            path = REPO / "agent.yaml"
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
    """Interactive fallback: the same authoritative plan seam — the DENTE included (no live
    pauta.proposta for the dispatch id → this command fails loud; Ato-2 never opens)."""
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    plan_parser = sub.add_parser("dispatch-plan")
    plan_parser.add_argument("--home", default=str(REPO))
    plan_parser.add_argument("--group", default=None)
    plan_parser.add_argument("--subject", default="lead")
    plan_parser.add_argument("--dispatch-id", required=True)
    plan_parser.add_argument("--claude-bin", default=None)
    plan_parser.add_argument("--mcp-config", default=None)
    args = parser.parse_args(argv)
    stdout = sys.stdout if stdout is None else stdout
    home = Path(os.path.expanduser(args.home)).resolve()
    claude_bin = args.claude_bin or resolve_claude_bin()
    config_path = (Path(args.mcp_config).resolve() if args.mcp_config else
                   ensure_cortex_config(home, group=args.group))
    command = build_beat_command(claude_bin, mcp_config_path=config_path)
    result = dispatch_plan(
        args.subject, args.dispatch_id,
        runtime_command=command,
        log=home / "state" / "events" / "log.jsonl",
    )
    json.dump(result, stdout, ensure_ascii=False, sort_keys=True)
    stdout.write("\n")
    return result


if __name__ == "__main__":
    main()
