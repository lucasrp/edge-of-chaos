"""Dogfood shadow — production stays natural; harvest grounding/rito; enqueue gate-policy
arms + one-at-a-time blind model slots.

Agreed design 2026-07-13 (operator):
  * Heartbeat/publish UNCHANGED.
  * Baseline B = natural production (genus full as shipped).
  * Open-compare arms = gate policies (visual-coverage, rich-rite, R0, grounding) + three.js
    operational gate — not cosmetic "v1 prose".
  * Blind models = ONE slot at a time (never multi-letter sitting).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import eventlog
import _identity

# Open-compare arms (re-runs). Production HTML is baseline B — not listed as a re-run arm.
GATE_ARMS = (
    {
        "id": "g-vis",
        "label": "visual-coverage",
        "gate_family": "visual-coverage",
        "summary": (
            "Satisfy close `_check_visual_coverage`: if the seed has quantitative/multi-value "
            "material, emit SUBSTANTIVE palette visuals (no hollow chrome)."
        ),
        "writer_focus": (
            "Prioritize substantive metrics-grid / comparison-table / chart when the content "
            "earns them. Do not invent numbers. Hollow headers do not count."
        ),
    },
    {
        "id": "g-rite",
        "label": "rich-rite",
        "gate_family": "rich-rite",
        "summary": (
            "Satisfy `_check_rich_rite` (#30): developed prose owes derivation, knowledge "
            "boundary, external frame (cites), and lineage — via blocks or content markers."
        ),
        "writer_focus": (
            "Make reasoning, unknowns, sourcing, and builds-on explicit. Charts optional."
        ),
    },
    {
        "id": "g-r0",
        "label": "R0 storytelling",
        "gate_family": "r0",
        "summary": (
            "Satisfy R0 + R0-for-values: every visual/structure has explaining prose; every "
            "numeric magnitude in a data cell also appears in reader-visible prose."
        ),
        "writer_focus": (
            "Never ship figurinha oca. Explain every visual. Numbers live in prose, not only cells."
        ),
    },
    {
        "id": "g-ground",
        "label": "visual-grounding",
        "gate_family": "visual-grounding",
        "summary": (
            "Satisfy `_check_visual_grounding` + recipes: chart/diagram only with claim-bearing "
            "grounded data from the seed; no fabricate-to-count."
        ),
        "writer_focus": (
            "Use closed visual recipes when a real series/topology exists in the seed; else skip."
        ),
    },
    {
        "id": "g-3d",
        "label": "three.js operational",
        "gate_family": "operational-3d",
        "summary": (
            "OTHER gate type (not S6 visual family): interactive three.js scene ONLY if the seed "
            "has real spatial/relational topology. Else degrade to static diagram and declare "
            "no spatial structure. Eval: can the operator use the scene in a short sitting?"
        ),
        "writer_focus": (
            "If topology is real: one navigable scene that serves the same decision as the prose. "
            "If not: static diagram + explicit note. Never empty WebGL chrome. Content floor (R0) still holds."
        ),
    },
)

DEFAULT_SKILLS = ("report", "research", "map", "plan")
# Explicit override / first roster slot. Without an override, assignments cycle across arms.
DEFAULT_ARM_ID = "g-vis"
# Same model writes original path (when known) AND the single variation.
DEFAULT_MODEL = "grok"
_SLUG_SAFE = re.compile(r"[^a-z0-9-]+")

MODEL_CLI = {
    "grok": ["grok", "--always-approve", "--prompt-file", "{prompt_file}"],
    "codex": ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "-"],
    "opus": ["claude", "-p", "-", "--dangerously-skip-permissions", "--model", "opus"],
    "fable": ["claude", "-p", "-", "--dangerously-skip-permissions", "--model", "fable"],
}

# Back-compat
RICHNESS_VARIETIES = GATE_ARMS
DEFAULT_MODEL_ARMS = (DEFAULT_MODEL,)


def resolve_arm(arm_id: str | None = None) -> dict:
    aid = (arm_id or DEFAULT_ARM_ID).strip().lower()
    for arm in GATE_ARMS:
        if arm["id"] == aid:
            return arm
    raise ValueError(f"unknown arm {arm_id!r}; choose one of {[a['id'] for a in GATE_ARMS]}")


def resolve_model(model: str | None = None) -> str:
    m = (model or DEFAULT_MODEL).strip().lower()
    if m not in MODEL_CLI:
        raise ValueError(f"unknown model {model!r}; choose one of {list(MODEL_CLI)}")
    return m


def default_downloads_dir() -> Path:
    env = os.environ.get("EDGE_DOGFOOD_DOWNLOADS")
    if env:
        return Path(os.path.expanduser(env)).resolve()
    return (Path.home() / "Downloads" / "exp003-gate-dogfood-shadow").resolve()


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_cfg(home: Path, agent_yaml=None) -> dict:
    try:
        import yaml
        path = Path(agent_yaml) if agent_yaml else Path(home) / "agent.yaml"
        if not path.is_file():
            return {}
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        exp = cfg.get("experiments") if isinstance(cfg.get("experiments"), dict) else {}
        block = exp.get("dogfood_shadow") if isinstance(exp, dict) else None
        out = block if isinstance(block, dict) else {}
        # default: one variation per artefato, cycling gates; same model for the pair
        out.setdefault("model", DEFAULT_MODEL)
        out.setdefault("one_variation_per_artefato", True)
        return out
    except Exception:
        return {"model": DEFAULT_MODEL}


def is_enabled(cfg: dict) -> bool:
    return bool(cfg) and bool(cfg.get("enabled", True)) and bool(cfg.get("experiment_id"))


def index_path(exp_dir: Path) -> Path:
    return exp_dir / "runs" / "index.json"


def load_index(exp_dir: Path) -> dict:
    raw = _read_json(index_path(exp_dir), default={})
    if not isinstance(raw, dict):
        return {"by_slug": {}}
    if not isinstance(raw.get("by_slug"), dict):
        raw["by_slug"] = {}
    return raw


def save_index(exp_dir: Path, index: dict) -> None:
    _write_json(index_path(exp_dir), index)


def run_id_for(slug: str, ts: str | None = None) -> str:
    stamp = (ts or _utc_stamp())[:15].replace(":", "").replace("-", "")
    safe = _SLUG_SAFE.sub("-", (slug or "item").lower()).strip("-")[:40] or "item"
    digest = hashlib.sha256(f"{slug}|{ts}".encode()).hexdigest()[:8]
    return f"{stamp}-{safe}-{digest}"


def _rito_dir(home: Path, slug: str) -> Path | None:
    output = _identity.runtime_root(Path(home) / "agent.yaml", fallback_root=home)
    p = output / "state" / "rito" / slug
    return p if p.is_dir() else None


def _entry_html(home: Path, slug: str) -> Path | None:
    output = _identity.runtime_root(Path(home) / "agent.yaml", fallback_root=home)
    p = output / "blog" / "entries" / f"{slug}.html"
    return p if p.is_file() else None


def harvest_production(home, item: dict, exp_dir: Path, *, experiment_id: str) -> Path:
    """Snapshot one corpus item under ``exp_dir/runs/<run_id>/production/``. Idempotent per slug."""
    home = Path(home)
    exp_dir = Path(exp_dir)
    slug = item.get("slug")
    if not isinstance(slug, str) or not slug.strip():
        raise ValueError("corpus item missing slug")
    slug = slug.strip()

    index = load_index(exp_dir)
    existing = index["by_slug"].get(slug)
    if isinstance(existing, str):
        prior = exp_dir / "runs" / existing
        if prior.is_dir() and (prior / "meta.json").is_file():
            return prior

    rid = run_id_for(slug, item.get("ts") or item.get("latest_ts"))
    run = exp_dir / "runs" / rid
    prod = run / "production"
    prod.mkdir(parents=True, exist_ok=True)

    corpus_dump = {
        "slug": slug,
        "intent": item.get("intent"),
        "skill": item.get("skill"),
        "origin": item.get("origin"),
        "ts": item.get("ts"),
        "latest_ts": item.get("latest_ts"),
        "cites": item.get("cites") or [],
        "proposes": item.get("proposes") or [],
        "distills": item.get("distills") or [],
        "lineage": item.get("lineage") or [],
        "reports_on": item.get("reports_on") or [],
        "spec": item.get("spec"),
        "gate": item.get("gate"),
    }
    _write_json(prod / "corpus_item.json", corpus_dump)

    recovered = {"html": False, "rito_files": [], "rito_dir": None, "markdown_fallback": False}
    html_src = _entry_html(home, slug)
    if html_src is not None:
        shutil.copy2(html_src, prod / "entry.html")
        recovered["html"] = True
    else:
        spec = item.get("spec") if isinstance(item.get("spec"), dict) else {}
        md = spec.get("markdown") if isinstance(spec, dict) else None
        if isinstance(md, str) and md.strip():
            (prod / "entry.md").write_text(md, encoding="utf-8")
            recovered["markdown_fallback"] = True

    rito = _rito_dir(home, slug)
    rito_files = []
    if rito is not None:
        dest = prod / "rito"
        dest.mkdir(exist_ok=True)
        for child in sorted(rito.iterdir()):
            if child.is_file():
                shutil.copy2(child, dest / child.name)
                rito_files.append(child.name)
            elif child.is_dir() and child.name == "prompts":
                shutil.copytree(child, dest / "prompts", dirs_exist_ok=True)
                rito_files.append("prompts/")
        recovered["rito_files"] = rito_files
        recovered["rito_dir"] = str(rito)

    seed_bits = [f"# Seed — {slug}\n", f"experiment: `{experiment_id}`\n",
                 f"baseline: production (genus full as shipped)\n"]
    g1 = prod / "rito" / "01_GROUNDING1_DOSSIER.md"
    if g1.is_file():
        seed_bits.append("\n## Grounding1 dossier (frozen)\n\n")
        seed_bits.append(g1.read_text(encoding="utf-8"))
    g2 = prod / "rito" / "04_GROUNDING2_MEMO.md"
    if g2.is_file():
        seed_bits.append("\n## Grounding2 memo (frozen)\n\n")
        seed_bits.append(g2.read_text(encoding="utf-8"))
    if not g1.is_file():
        seed_bits.append("\n## Intent\n\n")
        seed_bits.append(str(item.get("intent") or "(none)") + "\n")
        cites = item.get("cites") or []
        if cites:
            seed_bits.append("\n## Cites\n\n")
            seed_bits.append(json.dumps(cites, ensure_ascii=False, indent=2) + "\n")
    (prod / "SEED.md").write_text("".join(seed_bits), encoding="utf-8")

    meta = {
        "run_id": rid,
        "slug": slug,
        "experiment_id": experiment_id,
        "skill": item.get("skill"),
        "origin": item.get("origin"),
        "ts": item.get("ts") or item.get("latest_ts"),
        "harvested_at": _utc_iso(),
        "baseline": "production",
        "recovered": recovered,
    }
    _write_json(run / "meta.json", meta)

    index["by_slug"][slug] = rid
    index["updated_at"] = meta["harvested_at"]
    save_index(exp_dir, index)
    return run


def _arm_brief(meta: dict, arm: dict) -> str:
    return (
        f"# Gate arm — `{arm['id']}`\n\n"
        f"- **label:** {arm['label']}\n"
        f"- **gate_family:** `{arm['gate_family']}`\n"
        f"- **slug (production baseline B):** `{meta.get('slug', '')}`\n"
        f"- **run_id:** `{meta.get('run_id', '')}`\n"
        f"- **skill form:** `{meta.get('skill', 'report')}`\n\n"
        f"## Seed (frozen — do not re-gather world)\n\n"
        f"Read `../../production/SEED.md` and recovered rito under `../../production/rito/`.\n"
        f"Open compare against `../../production/entry.html` (baseline B).\n\n"
        f"## Gate contract\n\n"
        f"{arm['summary']}\n\n"
        f"## Writer focus\n\n"
        f"{arm['writer_focus']}\n\n"
        f"Same decision/intent as production; do not change the bet. "
        f"Do not name the arm id or that this is an experiment in the body.\n\n"
        f"## Done when\n\n"
        f"Write `output.html` here and set `status.json` → `status: done`.\n"
    )


def assign_one_variation(
    run_dir: Path,
    exp_dir: Path,
    *,
    arm_id: str | None = None,
    model: str | None = None,
    cfg: dict | None = None,
    variation: dict | None = None,
    force: bool = False,
) -> dict:
    """Exactly ONE variation per artefato, cycling gates across artefatos."""
    run_dir = Path(run_dir)
    exp_dir = Path(exp_dir)
    meta = _read_json(run_dir / "meta.json", default={}) or {}
    cfg = cfg or {}

    existing = meta.get("variation")
    if not force and isinstance(existing, dict) and existing.get("id") and existing.get("model"):
        return existing

    explicit_model = bool(variation and variation.get("kind") == "model")
    if arm_id or cfg.get("arm"):
        arm_def = resolve_arm(arm_id or cfg.get("arm"))
    else:
        assigned = 0
        runs = exp_dir / "runs"
        if runs.is_dir():
            for meta_path in runs.glob("*/meta.json"):
                if meta_path.parent == run_dir:
                    continue
                prior = _read_json(meta_path, default={}) or {}
                if isinstance(prior.get("variation"), dict):
                    assigned += 1
        arm_def = GATE_ARMS[assigned % len(GATE_ARMS)]

    model = resolve_model(
        (variation or {}).get("model") or model or cfg.get("model")
        or meta.get("production_model") or DEFAULT_MODEL
    )
    kind = "model" if explicit_model else "gate"
    vid = model if explicit_model else arm_def["id"]
    cli = MODEL_CLI[model]
    dest = run_dir / "variation"
    dest.mkdir(parents=True, exist_ok=True)
    # wipe sibling multi-arm leftovers so only one variation exists
    for junk in ("arms", "model-arms", "richness"):
        p = run_dir / junk
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)

    arm_path = run_dir / ("model-arms" if explicit_model else "arms") / vid
    arm_path.mkdir(parents=True, exist_ok=True)
    status = {
        "status": "pending",
        "kind": kind,
        "arm_id": arm_def["id"],
        "gate_family": arm_def["gate_family"],
        "label": arm_def["label"],
        "model": model,
        "same_model_as_pair": True,
        "cli": cli,
        "enqueued_at": _utc_iso(),
        "seed": "production/SEED.md",
        "one_per_artefato": True,
    }
    brief = (
        _arm_brief(meta, arm_def)
        + f"\n## Model (same for original pair + this variation)\n\n"
        f"- **model:** `{model}`\n"
        f"- **CLI:** `{' '.join(cli)}`\n"
        f"- Produce this variation **with that CLI only**. Do not switch models.\n"
        f"- Write `output.html` here when done.\n"
    )
    _write_json(dest / "status.json", status)
    _write_json(arm_path / "status.json", status)
    (dest / "BRIEF.md").write_text(brief, encoding="utf-8")
    (arm_path / "BRIEF.md").write_text(brief, encoding="utf-8")
    # prompt for the runner
    seed = run_dir / "production" / "SEED.md"
    seed_txt = seed.read_text(encoding="utf-8") if seed.is_file() else "(no seed)"
    (dest / "PROMPT.md").write_text(
        f"# Rewrite task — one arm, same model\n\n"
        f"You are running as **{model}**. Produce ONE artefato (skill "
        f"`{meta.get('skill', 'report')}`) under arm **{vid}** ({arm_def['label']}).\n\n"
        f"## Gate / arm contract\n\n{arm_def['summary']}\n\n"
        f"## Writer focus\n\n{arm_def['writer_focus']}\n\n"
        f"## Frozen seed (do not re-gather world)\n\n{seed_txt}\n\n"
        f"## Output\n\nWrite a full HTML report to the path the launcher expects "
        f"(variation/output.html). Same decision/intent as production; do not name the arm.\n",
        encoding="utf-8",
    )

    assignment = {
        "kind": kind,
        "id": vid,
        "label": (variation or {}).get("label") or arm_def["label"],
        "gate_family": arm_def["gate_family"],
        "model": model,
        "same_model_for_pair": True,
        "cli": cli,
        "output_rel": f"{'model-arms' if explicit_model else 'arms'}/{vid}/output.html",
        "variation_output_rel": "variation/output.html",
        "model_is_producer": explicit_model,
        "assigned_at": _utc_iso(),
    }
    meta["variation"] = assignment
    meta["production_model"] = model  # pair uses this model
    meta["one_variation_per_artefato"] = True
    _write_json(run_dir / "meta.json", meta)
    _write_json(dest / "assignment.json", assignment)
    return assignment


def enqueue_gate_arms(run_dir: Path, *, arms=None, exp_dir=None, cfg=None) -> list:
    exp = Path(exp_dir) if exp_dir else Path(run_dir).parent.parent
    var = assign_one_variation(run_dir, exp, cfg=cfg or {})
    return [Path(run_dir) / "arms" / var["id"]]


def enqueue_richness_arms(run_dir: Path, *, varieties=None, exp_dir=None, cfg=None) -> list:
    return enqueue_gate_arms(run_dir, exp_dir=exp_dir, cfg=cfg)


def enqueue_prototype(run_dir: Path, *, treatment: str = "one-arm", exp_dir=None, cfg=None) -> Path:
    exp = Path(exp_dir) if exp_dir else Path(run_dir).parent.parent
    var = assign_one_variation(run_dir, exp, cfg=cfg or {})
    proto = Path(run_dir) / "prototype"
    proto.mkdir(exist_ok=True)
    _write_json(proto / "status.json", {
        "status": "pending",
        "treatment": treatment,
        "baseline": "production",
        "variation": var,
        "one_per_artefato": True,
        "same_model": var.get("model"),
        "enqueued_at": _utc_iso(),
    })
    (proto / "BRIEF.md").write_text(
        f"# One variation — one arm — same model\n\n"
        f"- **B original:** `../production/entry.html`\n"
        f"- **arm:** `{var.get('id')}`\n"
        f"- **model (both):** `{var.get('model')}`\n"
        f"- **output:** `../variation/output.html`\n",
        encoding="utf-8",
    )
    return proto


def enqueue_model_arms(run_dir: Path, *, models=None, exp_dir=None, cfg=None) -> list:
    """No model bake-off: model is fixed for the pair; only one arm variation."""
    exp = Path(exp_dir) if exp_dir else Path(run_dir).parent.parent
    var = assign_one_variation(run_dir, exp, cfg=cfg or {})
    return [Path(run_dir) / "variation"]


def next_blind_slot(exp_dir: Path, *, run_id: str | None = None) -> dict | None:
    """Issue exactly one pending model arm for blind eval. Marks it ``issued``."""
    exp_dir = Path(exp_dir)
    if run_id:
        runs = [exp_dir / "runs" / run_id]
    else:
        runs_dir = exp_dir / "runs"
        runs = sorted(
            (p for p in runs_dir.iterdir()
             if p.is_dir() and (p / "meta.json").is_file()),
            key=lambda p: p.name,
            reverse=True,
        ) if runs_dir.is_dir() else []

    for run in runs:
        arms = run / "model-arms"
        if not arms.is_dir():
            continue
        for arm in sorted(arms.iterdir()):
            if not arm.is_dir():
                continue
            st = _read_json(arm / "status.json", default={}) or {}
            if st.get("status") == "issued":
                return {
                    "run_id": run.name,
                    "model": st.get("model") or arm.name,
                    "path": str(arm),
                    "status": "issued",
                    "output": str(arm / "output.html") if (arm / "output.html").is_file() else None,
                    "blind_letter": "X",
                    "reading": str(exp_dir / "reading" / "one-at-a-time" / run.name / "X.html"),
                }
        for arm in sorted(arms.iterdir()):
            if not arm.is_dir():
                continue
            st = _read_json(arm / "status.json", default={}) or {}
            if st.get("status") != "pending":
                continue
            st["status"] = "issued"
            st["issued_at"] = _utc_iso()
            _write_json(arm / "status.json", st)
            reading = exp_dir / "reading" / "one-at-a-time" / run.name
            reading.mkdir(parents=True, exist_ok=True)
            letter = reading / "X.html"
            if (arm / "output.html").is_file():
                shutil.copy2(arm / "output.html", letter)
            else:
                letter.write_text(
                    "<!-- pending production of this blind arm -->\n",
                    encoding="utf-8",
                )
            (reading / "README.md").write_text(
                f"# Leitura cega — UM de cada vez\n\n"
                f"- **run_id:** `{run.name}`\n"
                f"- Arquivo: `X.html` (única peça desta sentada)\n"
                f"- Não abra `model-arms/` nem `.blind-keys/`.\n",
                encoding="utf-8",
            )
            key_dir = exp_dir / ".blind-keys"
            key_dir.mkdir(exist_ok=True)
            key_path = key_dir / f"{run.name}-one.json"
            key = _read_json(key_path, default={"run_id": run.name, "sittings": []}) or {}
            sittings = key.get("sittings") if isinstance(key.get("sittings"), list) else []
            sittings.append({
                "letter": "X",
                "model": st.get("model") or arm.name,
                "issued_at": st["issued_at"],
            })
            key["sittings"] = sittings
            _write_json(key_path, key)
            try:
                os.chmod(key_path, 0o600)
            except OSError:
                pass
            return {
                "run_id": run.name,
                "model": st.get("model") or arm.name,
                "path": str(arm),
                "status": "issued",
                "reading": str(letter),
                "blind_letter": "X",
            }
    return None


def mark_blind_done(exp_dir: Path, *, run_id: str, model: str) -> dict:
    arm = Path(exp_dir) / "runs" / run_id / "model-arms" / model
    st = _read_json(arm / "status.json", default={}) or {}
    st["status"] = "evaluated" if (arm / "output.html").is_file() else "done"
    st["evaluated_at"] = _utc_iso()
    _write_json(arm / "status.json", st)
    run = Path(exp_dir) / "runs" / run_id
    if run.is_dir():
        mirror_run_to_downloads(run)
    return st


def mirror_run_to_downloads(run_dir: Path, downloads_root: Path | None = None) -> Path:
    """Copy original + versions side-by-side into Downloads for operator reading.

    Layout per slug::
        Downloads/exp003-gate-dogfood-shadow/<slug>/
          00-original.html
          00-original.meta.json
          arm-g-vis.html          # when done
          model-opus.html         # when done (model under test = producer)
          SIDE_BY_SIDE.md
    """
    run_dir = Path(run_dir)
    root = Path(downloads_root) if downloads_root else default_downloads_dir()
    root.mkdir(parents=True, exist_ok=True)
    meta = _read_json(run_dir / "meta.json", default={}) or {}
    slug = meta.get("slug") or run_dir.name
    dest = root / _SLUG_SAFE.sub("-", str(slug).lower()).strip("-")
    dest.mkdir(parents=True, exist_ok=True)

    # Original (baseline B)
    prod_html = run_dir / "production" / "entry.html"
    prod_md = run_dir / "production" / "entry.md"
    if prod_html.is_file():
        shutil.copy2(prod_html, dest / "00-original.html")
    elif prod_md.is_file():
        shutil.copy2(prod_md, dest / "00-original.md")
    _write_json(dest / "00-original.meta.json", {
        "role": "original",
        "slug": slug,
        "skill": meta.get("skill"),
        "origin": meta.get("origin"),
        "ts": meta.get("ts"),
        "run_id": meta.get("run_id") or run_dir.name,
        "experiment_id": meta.get("experiment_id"),
        "host_note": meta.get("host"),
        "mirrored_at": _utc_iso(),
    })

    # Exactly one variation (gate or model)
    var = meta.get("variation") if isinstance(meta.get("variation"), dict) else None
    if var and var.get("output_rel"):
        out = run_dir / var["output_rel"]
        # also check variation/output.html
        if not out.is_file():
            alt = run_dir / "variation" / "output.html"
            if alt.is_file():
                out = alt
        kind = var.get("kind") or "gate"
        vid = var.get("id") or "variation"
        if out.is_file():
            if kind == "model":
                name = f"01-variation-model-{vid}.html"
            else:
                name = f"01-variation-{vid}.html"
            shutil.copy2(out, dest / name)
        _write_json(dest / "01-variation.meta.json", {
            "role": "one_variation",
            "kind": kind,
            "id": vid,
            "model_is_producer": bool(var.get("model_is_producer")),
            "cli": var.get("cli"),
            "has_output": out.is_file() if out else False,
            "assignment": var,
        })
    else:
        # legacy: any single arm/model output
        for sub, prefix in (("arms", "arm"), ("model-arms", "model")):
            root = run_dir / sub
            if not root.is_dir():
                continue
            for arm in sorted(root.iterdir()):
                if arm.is_dir() and (arm / "output.html").is_file():
                    shutil.copy2(arm / "output.html", dest / f"01-variation-{prefix}-{arm.name}.html")

    files = sorted(
        p.name for p in dest.iterdir()
        if p.suffix in (".html", ".md") and p.name != "SIDE_BY_SIDE.md"
    )
    var_line = ""
    if var:
        var_line = f"- **variação (1):** `{var.get('kind')}:{var.get('id')}`\n"
    lines = [
        f"# {slug} — lado a lado\n",
        f"- **original:** `00-original.html`\n",
        var_line,
        f"- **regra:** uma variação por artefato; se model, a CLI do modelo **escreve** o HTML\n\n",
        f"## Arquivos\n\n",
    ]
    for name in files:
        lines.append(f"- `{name}`\n")
    (dest / "SIDE_BY_SIDE.md").write_text("".join(lines), encoding="utf-8")
    return dest


def export_all_to_downloads(exp_dir: Path, downloads_root: Path | None = None) -> dict:
    """Mirror every run under exp_dir/runs into Downloads; refresh root INDEX."""
    exp_dir = Path(exp_dir)
    root = Path(downloads_root) if downloads_root else default_downloads_dir()
    root.mkdir(parents=True, exist_ok=True)
    runs_dir = exp_dir / "runs"
    mirrored = []
    if runs_dir.is_dir():
        for run in sorted(runs_dir.iterdir()):
            if run.is_dir() and (run / "meta.json").is_file():
                dest = mirror_run_to_downloads(run, root)
                mirrored.append(str(dest))
    # root INDEX
    rows = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        orig = child / "00-original.html"
        versions = sorted(
            p.name for p in child.iterdir()
            if p.suffix == ".html" and p.name != "00-original.html"
        )
        rows.append(
            f"| `{child.name}` | {'yes' if orig.is_file() else 'no'} | "
            f"{', '.join(versions) or '_(só original)_'} |"
        )
    (root / "INDEX.md").write_text(
        f"# exp003 — Downloads (originais + versões lado a lado)\n\n"
        f"Pasta: `{root}`\n\n"
        f"**Regra:** em `model-*`, o modelo sob teste **é** quem produziu o HTML (CLI).\n\n"
        f"| slug | original | versões |\n"
        f"|------|----------|----------|\n"
        + ("\n".join(rows) if rows else "| _(vazio)_ | | |\n")
        + f"\n\n_Updated {_utc_iso()}_\n",
        encoding="utf-8",
    )
    return {"downloads_root": str(root), "mirrored": mirrored, "n": len(mirrored)}


def sweep(home, exp_dir: Path, cfg: dict, *, log=None) -> dict:
    home = Path(home)
    exp_dir = Path(exp_dir)
    exp_dir.mkdir(parents=True, exist_ok=True)
    (exp_dir / "runs").mkdir(exist_ok=True)

    experiment_id = str(cfg.get("experiment_id") or "exp000")
    skills = {str(s).strip() for s in (cfg.get("skills") or list(DEFAULT_SKILLS)) if str(s).strip()}
    origins = cfg.get("origins")
    if origins is not None:
        origins = {str(o).strip() for o in origins}
    output = _identity.runtime_root(home / "agent.yaml", fallback_root=home)
    log_path = Path(log) if log else output / "state" / "events" / "log.jsonl"
    corpus = eventlog.corpus_at(log=log_path)
    index = load_index(exp_dir)

    harvested = 0
    skipped = 0
    enqueued = []
    for item in corpus:
        slug = item.get("slug")
        if not slug:
            continue
        if skills and item.get("skill") not in skills:
            continue
        if origins is not None and item.get("origin") not in origins:
            continue
        if slug in index["by_slug"]:
            rid = index["by_slug"][slug]
            if (exp_dir / "runs" / rid).is_dir():
                skipped += 1
                continue
        run = harvest_production(home, item, exp_dir, experiment_id=experiment_id)
        var = assign_one_variation(run, exp_dir, cfg=cfg)
        enqueue_prototype(run, treatment=str(cfg.get("prototype") or "one-variation"),
                          exp_dir=exp_dir)
        mirror_run_to_downloads(run)
        harvested += 1
        enqueued.append({"run_id": run.name, "slug": item.get("slug"), "variation": var})

    refresh_live_index(exp_dir)
    export_all_to_downloads(exp_dir)
    return {
        "harvested": harvested,
        "skipped": skipped,
        "runs": enqueued,
        "experiment_id": experiment_id,
        "exp_dir": str(exp_dir),
        "rule": "one_variation_per_artefato",
        "baseline": "production",
        "model_is_producer": True,
        "downloads": str(default_downloads_dir()),
    }


def refresh_live_index(exp_dir: Path) -> Path:
    exp_dir = Path(exp_dir)
    live = exp_dir / "live"
    live.mkdir(parents=True, exist_ok=True)
    runs_dir = exp_dir / "runs"
    rows = []
    if runs_dir.is_dir():
        for run in sorted(runs_dir.iterdir(), reverse=True):
            if not run.is_dir() or not (run / "meta.json").is_file():
                continue
            meta = _read_json(run / "meta.json", default={}) or {}
            slug = meta.get("slug") or run.name
            prod = "yes" if (run / "production" / "entry.html").is_file() else (
                "md" if (run / "production" / "entry.md").is_file() else "no")
            var = meta.get("variation") if isinstance(meta.get("variation"), dict) else {}
            vlabel = f"{var.get('kind')}:{var.get('id')}" if var else "—"
            out_ok = "—"
            if var.get("output_rel"):
                out_ok = "✓" if (run / var["output_rel"]).is_file() else "pending"
            rows.append(
                f"| `{slug}` | `{run.name}` | {prod} | `{vlabel}` | {out_ok} |"
            )

    body = (
        f"# Dogfood shadow — live board\n\n"
        f"**Regra:** **1 variação por artefato** (round-robin de gates + modelos). "
        f"Baseline B = production. Se a variação for model, **a CLI do modelo escreve** o report.\n\n"
        f"| slug | run_id | B | variation | output |\n"
        f"|------|--------|---|------------|--------|\n"
        + ("\n".join(rows) if rows else "| _(no runs yet)_ | | | | |\n")
        + f"\n\n## Roster (ciclo)\n\n"
        + "\n".join(
            f"- gate `{a['id']}` — {a['label']}" for a in GATE_ARMS
        )
        + "\n"
        + "\n".join(f"- model `{m}` — producer CLI" for m in DEFAULT_MODEL_ARMS)
        + f"\n\n_Updated {_utc_iso()}_\n"
    )
    index = live / "INDEX.md"
    index.write_text(body, encoding="utf-8")
    return index


def resolve_exp_dir(home: Path, cfg: dict) -> Path:
    home = Path(home)
    if cfg.get("exp_dir"):
        return Path(os.path.expanduser(str(cfg["exp_dir"]))).resolve()
    eid = str(cfg.get("experiment_id") or "exp000")
    root = home / "experiments"
    env = os.environ.get("EDGE_EXPERIMENTS_DIR")
    if env:
        root = Path(os.path.expanduser(env)).resolve()
    if root.is_dir():
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child.name == eid or child.name.startswith(f"{eid}-")):
                return child
    slug = str(cfg.get("slug") or "gate-dogfood-shadow")
    return root / f"{eid}-{slug}"


def seed_experiment_workspace(exp_dir: Path, *, experiment_id: str, title: str,
                              hypothesis: str) -> Path:
    exp_dir = Path(exp_dir)
    exp_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("runs", "arms", "outputs", "live"):
        (exp_dir / sub).mkdir(exist_ok=True)

    projeto = exp_dir / "projeto.md"
    if not projeto.is_file():
        arms_md = "\n".join(
            f"- **`{a['id']}`** — {a['label']} (`{a['gate_family']}`): {a['summary']}"
            for a in GATE_ARMS
        )
        projeto.write_text(
            f"# {title}\n\n"
            f"- **experiment_id:** `{experiment_id}`\n"
            f"- **kind:** meta\n"
            f"- **baseline B:** natural production (genus full as shipped)\n"
            f"- **inherits:** exp001 (rito seed), exp002 (length ≠ free signal), "
            f"visual/R0/grounding gates in close.py\n\n"
            f"## Question\n\n"
            f"On the same frozen production seed, which gate-policy re-run (or three.js operational "
            f"arm) does the operator prefer for real use — and do models move that preference "
            f"when judged blind, one at a time?\n\n"
            f"## Hypothesis\n\n"
            f"{hypothesis}\n\n"
            f"## Not testing\n\n"
            f"- Seizing heartbeats.\n"
            f"- Multi-letter blind sittings.\n"
            f"- Fabricating visuals to hit a count.\n"
            f"- Cosmetic v1-prose baseline (replaced by production B).\n\n"
            f"## Arms (open compare)\n\n"
            f"{arms_md}\n\n"
            f"## Eval\n\n"
            f"**Open:** production vs each arm — publicaria? vai usar? ficou mais burro?\n\n"
            f"**Blind models:** one X.html at a time; export judgment before next slot.\n\n"
            f"## Method\n\n"
            f"1. Natural publish → `edge-dogfood-shadow sweep` or `harvest-slug`.\n"
            f"2. Re-run arms from `production/SEED.md`.\n"
            f"3. `next-blind` for models.\n",
            encoding="utf-8",
        )

    for a in GATE_ARMS:
        arm_md = exp_dir / "arms" / f"{a['id']}.md"
        if not arm_md.is_file():
            arm_md.write_text(
                f"# Arm `{a['id']}` — {a['label']}\n\n"
                f"**gate_family:** `{a['gate_family']}`\n\n{a['summary']}\n",
                encoding="utf-8",
            )

    timeline = exp_dir / "timeline.md"
    if not timeline.is_file():
        timeline.write_text(
            f"# Timeline — {experiment_id}\n\n## Log\n\n"
            f"- _seeded gate-policy dogfood workspace_\n",
            encoding="utf-8",
        )
    return exp_dir
