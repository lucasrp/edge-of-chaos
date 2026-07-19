"""onboarding — first-run lifecycle without agent.yaml (yaml is phenotype output).

Install knobs live in state/bootstrap.json until mentor emit writes agent.yaml.
Secrets are read from <home>/secrets/ (or EDGE_SECRETS_DIR); values never logged.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

_VAR_LINE = re.compile(
    r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$"
)

BOOTSTRAP_NAME = "bootstrap.json"
INSUMO_NAME = "onboarding-insumo.md"
SECRETS_CURSOR = "secrets-inventory-cursor.json"


def secrets_dir(home: Path | str, env: Optional[dict] = None) -> Path:
    """Canonical secrets path for this install (CONTRACT C4)."""
    env = env if env is not None else os.environ
    raw = env.get("EDGE_SECRETS_DIR")
    if raw:
        return Path(os.path.expanduser(str(raw)))
    return Path(home).expanduser() / "secrets"


def _parse_env_file(path: Path) -> list[str]:
    """Return variable *names* from an env file (never values)."""
    names: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return names
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _VAR_LINE.match(line)
        if m:
            names.append(m.group(1))
    return names


def inventory_secrets(secrets: Path | str) -> dict[str, Any]:
    """List secrets files and variable names only — no values (safe to log/stamp)."""
    root = Path(secrets)
    files: list[str] = []
    vars_: list[str] = []
    by_file: dict[str, list[str]] = {}
    if not root.is_dir():
        return {"files": files, "vars": vars_, "by_file": by_file, "path": str(root)}
    for p in sorted(root.iterdir()):
        if not p.is_file():
            continue
        if p.suffix != ".env" and not p.name.endswith(".env"):
            # still accept *.env; also plain .env files named *.env
            if ".env" not in p.name:
                continue
        names = _parse_env_file(p)
        files.append(p.name)
        by_file[p.name] = names
        for n in names:
            if n not in vars_:
                vars_.append(n)
    return {"files": files, "vars": vars_, "by_file": by_file, "path": str(root)}


def require_name(cli_value: Optional[str], env: Optional[dict] = None) -> str:
    env = env if env is not None else os.environ
    name = (cli_value or env.get("EDGE_AGENT_NAME") or "").strip()
    if not name:
        raise ValueError(
            "agent name required at bootstrap: pass --name or set EDGE_AGENT_NAME "
            "(identity seed before phenotype exists)"
        )
    return name


def require_backfill_days(cli_value: Optional[int | str], env: Optional[dict] = None) -> int:
    env = env if env is not None else os.environ
    raw = cli_value
    if raw is None or raw == "":
        raw = env.get("EDGE_ASSEMBLE_BACKFILL_DAYS")
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        raise ValueError(
            "assemble lookback required at bootstrap: pass --backfill-days N or set "
            "EDGE_ASSEMBLE_BACKFILL_DAYS (days of session history the initial assemble scans)"
        )
    try:
        n = int(raw)
    except (TypeError, ValueError) as e:
        raise ValueError(f"backfill_days must be an integer ≥ 0, got {raw!r}") from e
    if n < 0:
        raise ValueError(f"backfill_days must be ≥ 0, got {n}")
    return n


def resolve_adversarial_cast(
    members: Optional[list[str]],
    *,
    primary: str = "claude",
    available: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Who runs blind review. Empty/unavailable → self (primary model)."""
    primary = (primary or "claude").strip() or "claude"
    requested = [m.strip().lower() for m in (members or []) if m and str(m).strip()]
    # de-dupe preserve order
    seen = set()
    ordered = []
    for m in requested:
        if m not in seen and m != "self":
            seen.add(m)
            ordered.append(m)
    if available is not None:
        ordered = [m for m in ordered if m in available]
    if not ordered:
        return {
            "mode": "self",
            "members": ["self"],
            "primary": primary,
            "note": "no other adversarial configured or available — primary model self-adversarial",
        }
    return {
        "mode": "declared",
        "members": ordered,
        "primary": primary,
        "note": None,
    }


def embedding_from_inventory(inventory: dict) -> Optional[dict[str, str]]:
    """Optional embeddings secret. None = declared-dark (install continues)."""
    vars_ = set(inventory.get("vars") or [])
    by_file = inventory.get("by_file") or {}
    if "OPENAI_API_KEY" not in vars_:
        return None
    # prefer openai.env if present
    file_name = "openai.env"
    for fname, names in by_file.items():
        if "OPENAI_API_KEY" in names:
            file_name = fname
            break
    return {
        "secret_ref": f"{file_name}:OPENAI_API_KEY",
        "provider": "openai",
        "model": "text-embedding-3-small",
        "status": "on",
    }


def persist_bootstrap(home: Path | str, **payload: Any) -> Path:
    home = Path(home).expanduser()
    state = home / "state"
    state.mkdir(parents=True, exist_ok=True)
    path = state / BOOTSTRAP_NAME
    data = dict(payload)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_bootstrap(home: Path | str) -> dict:
    path = Path(home).expanduser() / "state" / BOOTSTRAP_NAME
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _adversarials_for_cfg(cast: dict, primary: str) -> dict:
    """Map cast → agent.yaml-shaped adversarials block."""
    if cast.get("mode") == "self" or cast.get("members") == ["self"]:
        return {
            "self": {
                "route": "review",
                "auth": "subscription",
                "model": primary,
                "directive": (
                    "Self-adversarial fallback (same primary model). Refute-first; "
                    "strike what does not survive. Same-model review is weaker than a "
                    "second model — prefer configuring codex/grok when available."
                ),
            }
        }
    out = {}
    for m in cast.get("members") or []:
        if m == "codex":
            out["codex"] = {
                "route": "review",
                "auth": "subscription",
                "model": "gpt-5.5",
                "directive": (
                    "Refute-first. Strike what does not survive; the 0-5 score is advisory."
                ),
            }
        elif m == "grok":
            out["grok"] = {
                "route": "review_grok",
                "auth": "subscription",
                "model": "grok-4.5",
                "directive": (
                    "Refute-first, AND ground the verdict in a LIVE X search when possible."
                ),
            }
        else:
            out[m] = {
                "route": "review",
                "auth": "subscription",
                "model": m,
                "directive": "Refute-first. Strike what does not survive.",
            }
    return out or _adversarials_for_cfg(
        {"mode": "self", "members": ["self"], "primary": primary}, primary
    )


def _routers_for_cfg(cast: dict, primary: str, embedding: Optional[dict]) -> dict:
    routers: dict[str, Any] = {
        "chat": {"provider": primary if primary in ("claude", "codex", "grok") else "claude",
                 "model": primary if primary not in ("claude",) else "opus"},
    }
    # normalize chat provider
    if primary in ("claude", "opus", "fable"):
        routers["chat"] = {"provider": "claude", "model": "opus" if primary == "claude" else primary}
    elif primary == "codex":
        routers["chat"] = {"provider": "codex", "model": "gpt-5.5"}
    elif primary == "grok":
        routers["chat"] = {"provider": "grok", "model": "grok-4.5"}

    if cast.get("mode") == "self" or "self" in (cast.get("members") or []):
        routers["review"] = dict(routers["chat"])
    else:
        for m in cast.get("members") or []:
            if m == "codex":
                routers["review"] = {"provider": "codex", "model": "gpt-5.5"}
            elif m == "grok":
                routers["review_grok"] = {"provider": "grok", "model": "grok-4.5"}
    if embedding:
        routers["embedding"] = {
            "provider": embedding.get("provider", "openai"),
            "secret_ref": embedding["secret_ref"],
            "model": embedding.get("model", "text-embedding-3-small"),
        }
    return routers


def bootstrap_cfg(
    *,
    home: Path | str,
    name: str,
    backfill_days: int,
    adversarials: dict,
    embedding: Optional[dict],
    inventory: Optional[dict] = None,
    primary: str = "claude",
) -> dict:
    """Minimal phenotype-shaped cfg for bootstrap (pre–agent.yaml)."""
    home_s = str(Path(home).expanduser())
    if home_s.startswith(str(Path.home())):
        # keep ~ form when under home for readability
        try:
            home_s = "~/" + str(Path(home).expanduser().relative_to(Path.home()))
        except ValueError:
            pass
    cast = adversarials or resolve_adversarial_cast([], primary=primary)
    cfg: dict[str, Any] = {
        "name": name,
        "codename": name,
        "graph_group": os.environ.get("EDGE_GROUP") or name,
        "edge_home": home_s if home_s.endswith("/") else home_s + "/",
        "skill_prefix": name if name != "edge" else "ed",
        "tool_prefix": "edge",
        "language": "en",
        "mission": "",  # mentor authors
        "voice": "",
        "lentes": {"backfill_days": int(backfill_days)},
        "adversarials": _adversarials_for_cfg(cast, cast.get("primary") or primary),
        "routers": _routers_for_cfg(cast, cast.get("primary") or primary, embedding),
        "sources": [],  # filled later / dark until phenotype
        "heartbeat_interval": "8h",
    }
    if inventory is not None:
        cfg["_secrets_inventory"] = {
            "files": inventory.get("files") or [],
            "vars": inventory.get("vars") or [],
        }
    return cfg


def phenotype_path(home: Path | str) -> Path:
    return Path(home).expanduser() / "agent.yaml"


def is_phenotype_present(home: Path | str) -> bool:
    return phenotype_path(home).is_file()


def secrets_delta(home: Path | str, inventory: dict) -> dict[str, Any]:
    """Delta of secrets inventory vs last cursor (file names + key names only)."""
    home = Path(home).expanduser()
    state = home / "state"
    cursor_path = state / SECRETS_CURSOR
    current_files = set(inventory.get("files") or [])
    current_vars = set(inventory.get("vars") or [])
    prev_files: set[str] = set()
    prev_vars: set[str] = set()
    if cursor_path.is_file():
        try:
            prev = json.loads(cursor_path.read_text(encoding="utf-8"))
            prev_files = set(prev.get("files") or [])
            prev_vars = set(prev.get("vars") or [])
        except (json.JSONDecodeError, OSError):
            pass
    delta = {
        "files_added": sorted(current_files - prev_files),
        "files_removed": sorted(prev_files - current_files),
        "vars_added": sorted(current_vars - prev_vars),
        "vars_removed": sorted(prev_vars - current_vars),
        "unchanged": not (
            (current_files ^ prev_files) or (current_vars ^ prev_vars)
        ) and bool(current_files or prev_files or current_vars or prev_vars),
    }
    return delta


def stamp_secrets_cursor(home: Path | str, inventory: dict) -> Path:
    home = Path(home).expanduser()
    state = home / "state"
    state.mkdir(parents=True, exist_ok=True)
    path = state / SECRETS_CURSOR
    path.write_text(
        json.dumps(
            {"files": inventory.get("files") or [], "vars": inventory.get("vars") or []},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def compose_insumo(
    *,
    home: Path | str,
    bootstrap: dict,
    inventory: dict,
    secrets_delta_: dict,
    assemble_text: str = "",
    quente_text: str = "",
    delta_text: str = "",
    recall_text: str = "",
) -> str:
    """Wake-shaped mentor insumo. Direction must stay empty."""
    name = bootstrap.get("name") or "?"
    n = bootstrap.get("backfill_days")
    cast = bootstrap.get("adversarials") or {}
    emb = bootstrap.get("embedding")
    emb_status = "on" if emb else "dark"
    lines = [
        "# Onboarding insumo (wake package — no Direction)",
        "",
        f"- **name:** {name}",
        f"- **lookback_days:** {n}",
        f"- **adversarials:** {cast.get('mode', '?')} · members={cast.get('members', [])}",
        f"- **embedding:** {emb_status}",
        "",
        "## Assemble",
        "",
        (assemble_text.strip() or "_(assemble dark / empty — no sessions in window)_"),
        "",
        "## Secrets",
        "",
        f"- path: `{inventory.get('path', secrets_dir(home))}`",
        f"- files: {', '.join(inventory.get('files') or []) or '(none)'}",
        f"- vars: {', '.join(inventory.get('vars') or []) or '(none)'}",
        "",
        "## Delta de secrets",
        "",
        f"- files added: {', '.join(secrets_delta_.get('files_added') or []) or '(none)'}",
        f"- files removed: {', '.join(secrets_delta_.get('files_removed') or []) or '(none)'}",
        f"- vars added: {', '.join(secrets_delta_.get('vars_added') or []) or '(none)'}",
        f"- vars removed: {', '.join(secrets_delta_.get('vars_removed') or []) or '(none)'}",
        "",
        "## Quente",
        "",
        (quente_text.strip() or "_(quente dark — no substantial sessions yet)_"),
        "",
        "## Delta",
        "",
        (delta_text.strip() or "_(delta empty / nothing new)_"),
        "",
        "## Recall",
        "",
        (recall_text.strip() or "_(recall dark / map-blind empty)_"),
        "",
        "## Direction",
        "",
        "_(ainda não existe — nasce no mentor)_",
        "",
        "---",
        "",
        "**Next:** `/ed-mentor` with this package. Do not start production beat until phenotype is emitted.",
        "",
    ]
    return "\n".join(lines)


def write_insumo(home: Path | str, text: str) -> Path:
    home = Path(home).expanduser()
    state = home / "state"
    state.mkdir(parents=True, exist_ok=True)
    path = state / INSUMO_NAME
    path.write_text(text, encoding="utf-8")
    return path


def insumo_path(home: Path | str) -> Path:
    return Path(home).expanduser() / "state" / INSUMO_NAME


def assert_mentor_has_insumo(home: Path | str) -> Path:
    path = insumo_path(home)
    if not path.is_file() or not path.read_text(encoding="utf-8").strip():
        raise ValueError(
            f"mentor insumo missing at {path} — run wake (assemble+wake) first so the mentor "
            "has structured material (observe FIRST)"
        )
    text = path.read_text(encoding="utf-8")
    # Direction chapter must not carry set/proposed content
    if re.search(r"(?im)^##\s*Direction\s*$", text):
        # after ## Direction until next ## or end — only placeholder allowed
        m = re.search(r"(?ims)^##\s*Direction\s*\n(.*?)(?=^##\s|\Z)", text)
        if m:
            body = m.group(1).strip()
            if body and "ainda não existe" not in body and "nasce no mentor" not in body:
                if len(body) > 80 and not body.startswith("_("):
                    raise ValueError(
                        "onboarding insumo must not carry Direction content "
                        "(Direction is born in mentor)"
                    )
    return path


def is_onboarding_complete(home: Path | str, log=None) -> bool:
    """grill_gate complete + phenotype present with name + backfill_days.

    When `log` is None, uses the install default eventlog. Pass an explicit log path
    (e.g. tmp fixture) for hermetic tests.
    """
    home = Path(home).expanduser()
    if not is_phenotype_present(home):
        return False
    try:
        import yaml

        cfg = yaml.safe_load(phenotype_path(home).read_text(encoding="utf-8")) or {}
    except Exception:
        return False
    if not str(cfg.get("name") or "").strip():
        return False
    lentes = cfg.get("lentes") or {}
    if "backfill_days" not in lentes:
        return False
    try:
        import grill_gate

        if log is not None:
            missing = grill_gate.grill_complete(log=log)
        else:
            missing = grill_gate.grill_complete()
    except Exception:
        return False
    return not missing


def assert_production_allowed(home: Path | str, log=None) -> None:
    if is_onboarding_complete(home, log=log):
        return
    raise RuntimeError(
        f"production (beat/heartbeat) refused: onboarding incomplete for {home}. "
        "Need mentor close (grill_gate) + emitted agent.yaml. "
        "See README.md first-run and docs/specs/onboarding-first-run.md"
    )


def emit_phenotype(
    home: Path | str,
    *,
    bootstrap: Optional[dict] = None,
    inventory: Optional[dict] = None,
    mission: str = "",
    voice: str = "",
    mentee: Optional[str] = None,
) -> Path:
    """Write agent.yaml as onboarding output (atomic)."""
    import yaml

    home = Path(home).expanduser()
    boot = bootstrap if bootstrap is not None else load_bootstrap(home)
    if not boot.get("name"):
        raise ValueError("cannot emit phenotype: bootstrap missing name")
    if "backfill_days" not in boot:
        raise ValueError("cannot emit phenotype: bootstrap missing backfill_days")
    inv = inventory if inventory is not None else inventory_secrets(secrets_dir(home))
    emb = boot.get("embedding")
    if emb is None:
        emb = embedding_from_inventory(inv)
    cast = boot.get("adversarials") or resolve_adversarial_cast([], primary="claude")
    cfg = bootstrap_cfg(
        home=home,
        name=boot["name"],
        backfill_days=int(boot["backfill_days"]),
        adversarials=cast,
        embedding=emb,
        inventory=inv,
        primary=cast.get("primary") or "claude",
    )
    if mission:
        cfg["mission"] = mission
    if voice:
        cfg["voice"] = voice
    if mentee:
        cfg["mentee"] = mentee
    # strip internal keys
    cfg.pop("_secrets_inventory", None)
    path = phenotype_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(
        yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def resolve_install_home(home: Optional[Path | str] = None, env: Optional[dict] = None) -> Optional[Path]:
    """Resolve install root: arg → EDGE_HOME → path with state/bootstrap.json near cwd/repo."""
    env = env if env is not None else os.environ
    if home is not None:
        return Path(home).expanduser()
    raw = env.get("EDGE_HOME")
    if raw:
        return Path(os.path.expanduser(str(raw)))
    for cand in (Path.cwd(), Path(__file__).resolve().parent.parent):
        if (cand / "state" / BOOTSTRAP_NAME).is_file():
            return cand
    return None


def is_first_run(home: Path | str) -> bool:
    """True when bootstrap exists and phenotype is not yet present (mentor not finished)."""
    home = Path(home).expanduser()
    if not (home / "state" / BOOTSTRAP_NAME).is_file():
        return False
    return not is_phenotype_present(home)


def maybe_stamp_insumo(
    home: Optional[Path | str] = None,
    *,
    briefing_text: str = "",
    recall_text: str = "",
    quente_text: str = "",
    delta_text: str = "",
) -> Optional[Path]:
    """Stamp mentor insumo when first-run; no-op if settled phenotype or no bootstrap.

    Called after predispatch/wake so mentor has structured material (observe FIRST).
    """
    home_p = resolve_install_home(home)
    if home_p is None or not is_first_run(home_p):
        return None
    boot = load_bootstrap(home_p)
    if not boot:
        return None
    inv = inventory_secrets(secrets_dir(home_p))
    delta = secrets_delta(home_p, inv)
    # Prefer full briefing as assemble body; recall as recall leg
    text = compose_insumo(
        home=home_p,
        bootstrap=boot,
        inventory=inv,
        secrets_delta_=delta,
        assemble_text=briefing_text or "",
        quente_text=quente_text or "",
        delta_text=delta_text or "",
        recall_text=recall_text or "",
    )
    path = write_insumo(home_p, text)
    stamp_secrets_cursor(home_p, inv)
    return path


def finish_onboarding(
    home: Path | str,
    *,
    log=None,
    mission: str = "",
    voice: str = "",
    mentee: Optional[str] = None,
    enable_heartbeat: bool = False,
    run=None,
) -> Path:
    """Mentor close seam: grill_gate must pass, then emit phenotype; optional heartbeat enable."""
    home = Path(home).expanduser()
    import grill_gate
    import eventlog as _eventlog

    log_path = log if log is not None else _eventlog.LOG
    grill_gate.assert_grill_complete(log=log_path)
    path = emit_phenotype(
        home, mission=mission, voice=voice, mentee=mentee
    )
    if enable_heartbeat:
        import _provision
        kwargs = {}
        if run is not None:
            kwargs["run"] = run
        _provision.enable_heartbeat(**kwargs)
    return path


def run_bootstrap(
    *,
    home: Path | str,
    name: str,
    backfill_days: int,
    adversarials: Optional[list[str]] = None,
    primary: str = "claude",
    provision_skills: bool = True,
) -> dict:
    """Layout + secrets inventory + bootstrap.json. Never enables heartbeat."""
    home = Path(home).expanduser()
    name = require_name(name)
    n = require_backfill_days(backfill_days)
    for d in ("blog/entries", "state", "memory", "threads", "secrets", "skills"):
        (home / d).mkdir(parents=True, exist_ok=True)
    sdir = secrets_dir(home)
    if not sdir.is_dir():
        sdir.mkdir(parents=True, exist_ok=True)
    inv = inventory_secrets(sdir)
    cast = resolve_adversarial_cast(adversarials or [], primary=primary)
    emb = embedding_from_inventory(inv)
    payload = {
        "name": name,
        "backfill_days": n,
        "adversarials": cast,
        "embedding": emb,
        "edge_home": str(home),
    }
    persist_bootstrap(home, **payload)
    stamp_secrets_cursor(home, inv)
    cfg = bootstrap_cfg(
        home=home,
        name=name,
        backfill_days=n,
        adversarials=cast,
        embedding=emb,
        inventory=inv,
        primary=primary,
    )
    if provision_skills:
        try:
            import _claude_provision
            import _grok_provision
            import _codex_provision

            repo = Path(__file__).resolve().parent.parent
            claude_home = Path.home() / ".claude"
            _claude_provision.provision_claude(cfg, repo, claude_home)
            _grok_provision.provision_grok(cfg, repo, home, Path.home() / ".grok")
            _codex_provision.provision_codex(cfg, repo, home, Path.home() / ".codex")
        except Exception as e:  # noqa: BLE001 — bootstrap still succeeds; report
            payload["provision_warning"] = f"{type(e).__name__}: {e}"
    # never call install_heartbeat here
    payload["secrets_inventory"] = {"files": inv["files"], "vars": inv["vars"]}
    payload["heartbeat"] = "off"
    return payload
