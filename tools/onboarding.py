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


# O que o lookback do primeiro assemble/wake vai comer, por harness instalado.
# ponytail: taxa fixa; calibrar quando houver medição real de assemble/min.
_EST_MB_PER_MIN = 5.0

_SESSION_STORES = {
    "claude": ".claude/projects",
    "codex": ".codex/sessions",
    "grok": ".grok/sessions",
}


def backfill_estimate(days: int, home: Path | str | None = None,
                      env: Optional[dict] = None) -> dict[str, Any]:
    """Quanto histórico o lookback de `days` pega (o cheque do 'não vai demorar demais').

    Varre `*.jsonl` mais novos que `days` nos session stores dos harnesses PRESENTES
    (mesma detecção do bootstrap: diretório-home do harness existe). Devolve números
    mecânicos — {surfaces: {nome: {files, mb}}, files, mb, est_minutes}; o juízo de
    "absurdo" é semântico e fica com o agente que guia o onboarding, nunca aqui."""
    import time as _time
    home = Path(home).expanduser() if home else Path.home()
    cutoff = _time.time() - int(days) * 86400
    surfaces: dict[str, dict] = {}
    total_files, total_bytes = 0, 0
    for name, rel in _SESSION_STORES.items():
        harness_home = home / rel.split("/")[0]
        if not harness_home.is_dir():
            continue
        store = home / rel
        files, size = 0, 0
        if store.is_dir():
            for p in store.rglob("*.jsonl"):
                try:
                    st = p.stat()
                except OSError:
                    continue
                if st.st_mtime >= cutoff:
                    files += 1
                    size += st.st_size
        surfaces[name] = {"files": files, "mb": round(size / 1e6, 2)}
        total_files += files
        total_bytes += size
    mb = round(total_bytes / 1e6, 2)
    return {"surfaces": surfaces, "files": total_files, "mb": mb,
            "days": int(days), "est_minutes": round(mb / _EST_MB_PER_MIN, 1)}


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


# Auto-detecção por var conhecida, em ordem de preferência. Azure NÃO auto-detecta
# sozinho um base_url — entra por escolha explícita (a entrevista pergunta o endpoint).
_EMBED_PROVIDER_VARS = (
    ("openai", "OPENAI_API_KEY"),
    ("openrouter", "OPENROUTER_API_KEY"),
    ("azure", "AZURE_OPENAI_API_KEY"),
)
_DEFAULT_EMBED_MODEL = "text-embedding-3-small"


def embedding_from_inventory(inventory: dict, provider: Optional[str] = None,
                             var: Optional[str] = None, model: Optional[str] = None,
                             base_url: Optional[str] = None) -> Optional[dict[str, str]]:
    """Optional embeddings secret → o adapter declarado no fenótipo.

    Escolha explícita (provider/var/model/base_url — a entrevista do onboarding) vence;
    var explícita ausente do inventário é fail-loud. Sem escolha: auto-detecção pela
    primeira var conhecida. Sem chave nenhuma: None = declared-dark (install continues).
    base_url explícito cobre azure e qualquer endpoint OpenAI-compatível fora do registry
    (_llm.resolve_base_url: explícito vence, senão deriva do provider)."""
    vars_ = set(inventory.get("vars") or [])
    by_file = inventory.get("by_file") or {}
    if provider or var:
        var = var or dict((p, v) for p, v in _EMBED_PROVIDER_VARS).get(provider)
        if not var or var not in vars_:
            raise ValueError(
                f"embedding: var {var!r} não está nos secrets (inventário: {sorted(vars_)})")
    else:
        for p, v in _EMBED_PROVIDER_VARS:
            if v in vars_:
                provider, var = p, v
                break
        else:
            return None
    file_name = next((f for f, names in by_file.items() if var in names), None)
    out = {
        "secret_ref": f"{file_name}:{var}",
        "provider": provider or "openai",
        "model": model or _DEFAULT_EMBED_MODEL,
        "status": "on",
    }
    if base_url:
        out["base_url"] = base_url
    return out


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
            "model": embedding.get("model", _DEFAULT_EMBED_MODEL),
        }
        if embedding.get("base_url"):
            routers["embedding"]["base_url"] = embedding["base_url"]
    return routers


# Known secret files → optional phenotype wiring (names only; values never leave secrets/).
_KNOWN_SECRET_SOURCES = (
    # (file, var, source_name, kind, description)
    ("exa.env", "EXA_API_KEY", "exa", "api",
     "Neural/semantic web + paper search (Mundo/Atividade)."),
    ("xai.env", "XAI_API_KEY", "x", "api",
     "X/Twitter practitioner chatter (Mundo) — API fallback; prefer grok CLI when present."),
    ("github.env", "GITHUB_TOKEN", "github", "cli",
     "GitHub via gh CLI (Atividade + Mundo)."),
)


def _sources_from_inventory(inventory: Optional[dict]) -> list[dict]:
    """Declare sources only when the matching secret file/var is present in secrets/."""
    if not inventory:
        return []
    files = set(inventory.get("files") or [])
    vars_ = set(inventory.get("vars") or [])
    by_file = inventory.get("by_file") or {}
    out: list[dict] = []
    for fname, var, sname, kind, desc in _KNOWN_SECRET_SOURCES:
        if fname not in files and var not in vars_:
            continue
        # prefer exact file that holds the var
        secret_file = fname
        for f, names in by_file.items():
            if var in (names or []):
                secret_file = f
                break
        entry = {
            "name": sname,
            "kind": kind,
            "description": desc,
        }
        if kind == "api":
            entry["secret_ref"] = f"{secret_file}:{var}"
        out.append(entry)
    return out


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
    """Minimal phenotype-shaped cfg for bootstrap (pre–agent.yaml).

    Always declares ``env_dir`` as the install secrets folder (CONTRACT C4): the operator
    delivers keys there; apply/onboarding only read. Values never enter this cfg.
    """
    home_p = Path(home).expanduser()
    home_s = str(home_p)
    if home_s.startswith(str(Path.home())):
        # keep ~ form when under home for readability
        try:
            home_s = "~/" + str(home_p.relative_to(Path.home()))
        except ValueError:
            pass
    if not home_s.endswith("/"):
        home_s = home_s + "/"
    # env_dir: absolute secrets path preferred (apply expanduser); relative "secrets" also works
    sdir = secrets_dir(home_p)
    try:
        env_dir_s = str(sdir.relative_to(home_p))  # typically "secrets"
    except ValueError:
        env_dir_s = str(sdir)
    cast = adversarials or resolve_adversarial_cast([], primary=primary)
    routers = _routers_for_cfg(cast, cast.get("primary") or primary, embedding)
    # neo4j is not a router — graph password lives in secrets/neo4j.env (EDGE_NEO4J_PASSWORD)
    sources = _sources_from_inventory(inventory)
    # Multi-CLI: declare every surface installed on this host (claude + codex + grok)
    try:
        import surfaces_cfg as _surfaces
        surfaces_block = _surfaces.surfaces_block_for_installed()
    except Exception:
        surfaces_block = {
            "claude": {"enabled": True},
            "codex": {"enabled": True, "home": "~/.codex"},
            "grok": {"enabled": True, "home": "~/.grok"},
        }
    cfg: dict[str, Any] = {
        "name": name,
        "codename": name,
        "graph_group": os.environ.get("EDGE_GROUP") or name,
        "edge_home": home_s,
        # CONTRACT C4 — secrets live here; installer verifies, never invents keys
        "env_dir": env_dir_s,
        "skill_prefix": name if name != "edge" else "ed",
        "tool_prefix": "edge",
        "language": "en",
        "mission": "",  # mentor authors
        "voice": "",
        "lentes": {"backfill_days": int(backfill_days)},
        "adversarials": _adversarials_for_cfg(cast, cast.get("primary") or primary),
        "routers": routers,
        "sources": sources,
        "surfaces": surfaces_block,
        "heartbeat_interval": "8h",
    }
    if inventory is not None:
        # durable inventory of *names* present at emit (not values)
        cfg["secrets"] = {
            "dir": env_dir_s,
            "files": list(inventory.get("files") or []),
            "vars": list(inventory.get("vars") or []),
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
    # strip any non-yaml internal markers
    cfg.pop("_secrets_inventory", None)
    # re-assert secrets block from live inventory at emit time
    if inv:
        env_dir_s = cfg.get("env_dir") or "secrets"
        cfg["secrets"] = {
            "dir": env_dir_s,
            "files": list(inv.get("files") or []),
            "vars": list(inv.get("vars") or []),
        }
        cfg["sources"] = _sources_from_inventory(inv)
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
    embedding_choice: Optional[dict] = None,
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
    emb = embedding_from_inventory(inv, **(embedding_choice or {}))
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
    # Place canonical skills under install home so Claude/Codex/Grok wrappers resolve
    try:
        import shutil
        repo = Path(__file__).resolve().parent.parent
        src_skills = repo / "skills"
        if src_skills.is_dir():
            dst_skills = home / "skills"
            if not dst_skills.exists():
                shutil.copytree(
                    src_skills, dst_skills,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )
            else:
                # merge: copy any missing skill dirs
                for child in src_skills.iterdir():
                    if child.is_dir() and not (dst_skills / child.name).exists():
                        shutil.copytree(
                            child, dst_skills / child.name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                        )
    except Exception as e:  # noqa: BLE001
        payload["skills_copy_warning"] = f"{type(e).__name__}: {e}"

    if provision_skills:
        try:
            import surfaces_cfg
            import _claude_provision
            import _grok_provision
            import _codex_provision

            repo = Path(__file__).resolve().parent.parent
            installed = surfaces_cfg.detect_installed_surfaces()
            provisioned = []
            # Always try all installed harnesses (operator: install on claude + codex + grok)
            if installed.get("claude", True):
                claude_home = Path.home() / ".claude"
                for row in _claude_provision.provision_claude(cfg, repo, claude_home):
                    provisioned.append(f"claude: {row}")
            if installed.get("codex", False) or surfaces_cfg.provision_surface("codex", cfg=cfg):
                codex_home = Path.home() / ".codex"
                for row in _codex_provision.provision_codex(cfg, repo, home, codex_home):
                    provisioned.append(f"codex: {row}")
            if installed.get("grok", False) or surfaces_cfg.provision_surface("grok", cfg=cfg):
                grok_home = Path.home() / ".grok"
                for row in _grok_provision.provision_grok(cfg, repo, home, grok_home):
                    provisioned.append(f"grok: {row}")
            payload["provisioned_surfaces"] = provisioned
            payload["installed_surfaces"] = installed
        except Exception as e:  # noqa: BLE001 — bootstrap still succeeds; report
            payload["provision_warning"] = f"{type(e).__name__}: {e}"
    # never call install_heartbeat here
    payload["secrets_inventory"] = {"files": inv["files"], "vars": inv["vars"]}
    payload["heartbeat"] = "off"
    return payload
