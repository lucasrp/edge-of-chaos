"""The rito runtime — the experiment's rite as the genotype's production path.

Promoted from the canonical harness (drafts/old-edge-double-grounding-repro/run.py): the
SAME stage sequence, sealing pattern (begin/finish/fail receipts with sha256 + manifest),
deterministic gates (treatment scan, fail-closed acceptance header, draft immutability) and
pinned render — now terminating in PUBLICATION instead of the blind package (the blind read
is experiment/acceptance apparatus, not a production stage; the first authorial draft stays
sealed and addressable in the run dir so a later blind read is always possible).

The operator's contract (docs/rito-runtime.md): the rite is the WHOLE causal execution,
grounding-1 through publication of the rendered page. We prove EXECUTION — never score the
artifact's appearance. The approved renderer and its output hash are pinned AS A STAGE.

Seams:
- Cognition is prose-owned: the producer hands `grounding1_fn()` and per-stage
  `prompts[stage](outputs) -> str`. This module contains no prompt content.
- Transport is injected: `complete_fn(route, prompt, max_tokens) -> str`.
- Publication is inside the rite: `publish_fn(markdown, manifest) -> receipt`, defaulting
  to `publisher.publish_rito`. A run that didn't publish didn't finish the rite.

The DETECTOR `verify_rito(run_dir, log=…, blog_dir=…)` answers, from disk + log alone:
"did this traverse the experiment's rite, with the experiment's form?" — all stages
completed in causal order with sealed receipts, page bytes == pinned render of the sealed
markdown, publication event bound to the manifest. CLI:

    tools/edge-python tools/rito.py verify <run_dir> [--log PATH] [--blog-dir PATH]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eventlog  # noqa: E402
import render  # noqa: E402
import yaml_rite  # noqa: E402

SCHEMA = "edge.rito-manifest/v1"
RITO_VERSION = "artefato-double-grounding/experiment-b"
MANIFEST_NAME = "00_MANIFEST.json"

# (ordinal, name, output filename, route, max_tokens) — the experiment's causal order
# (run.py STAGES 1–10) with `publication` promoted to the terminal stage in place of the
# blind package. Routes are FIXED: chat = the author, review = an independent reviewer.
STAGES = [
    (1, "grounding1_dossier", "01_GROUNDING1_DOSSIER.md", None, None),
    (2, "first_authorial_draft", "02_FIRST_AUTHORIAL_DRAFT.md", "chat", 11_000),
    (3, "gap_critique", "03_GAP_CRITIQUE.md", "review", 9_000),
    (4, "grounding2_targeted", "04_GROUNDING2_MEMO.md", "review", 10_000),
    (5, "provisional_rewrite", "05_PROVISIONAL_REWRITE.md", "chat", 14_000),
    (6, "fact_audit", "06_FACT_AUDIT.md", "review", 9_000),
    (7, "author_correction", "07_AUDITED_FINAL.md", "chat", 14_000),
    (8, "feynman_gate_1", "08a_FEYNMAN_GATE_1.json", "review", 4_000),
    (9, "feynman_grounding_a", "08b_FEYNMAN_GROUNDING_A.md", "review", 10_000),
    (10, "feynman_rewrite_1", "08c_FEYNMAN_REWRITE_1.md", "chat", 14_000),
    (11, "feynman_gate_2", "08d_FEYNMAN_GATE_2.json", "review", 4_000),
    (12, "feynman_grounding_b", "08e_FEYNMAN_GROUNDING_B.md", "review", 10_000),
    (13, "feynman_rewrite_2", "08f_FEYNMAN_REWRITE_2.md", "chat", 14_000),
    (14, "treatment_cleanup", "08_BLIND_SAFE_FINAL.md", "chat", 14_000),
    (15, "final_html", "09_FINAL.html", None, None),
    (16, "final_review", "10_FINAL_REVIEW.md", "review", 9_000),
    (17, "publication", "11_PUBLICATION.json", None, None),
]

LLM_STAGES = tuple(name for _, name, _, route, _ in STAGES if route)
COGNITIVE_STAGES = tuple(name for _, name, _, _, _ in STAGES if name != "publication")

# The deterministic treatment scan (run.py FIRST_ARTIFACT_FORBIDDEN, verbatim): the reader-
# facing text must never disclose the production process. A gate, not cognition.
FORBIDDEN = {
    "draft": re.compile(r"\b(?:neste|este|primeiro)\s+draft\b|\bdraft\b", re.IGNORECASE),
    "rascunho": re.compile(r"\brascunh[oa]\b", re.IGNORECASE),
    "grounding": re.compile(r"\bgrounding\b", re.IGNORECASE),
    "post_gate": re.compile(r"\b(?:post|p[oó]s)[ -]?gate\b", re.IGNORECASE),
    "next_phase": re.compile(
        r"\bpr[oó]xima fase\b.{0,80}\b(?:texto|escrita|rito|grounding|coleta externa)\b"
        r"|\bfase posterior\b.{0,80}\b(?:texto|escrita|rito|grounding|coleta externa)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    "treatment": re.compile(
        r"\btratamento\s+(?:experimental|de escrita|do texto|deste texto|deste artefato)\b"
        r"|\b(?:experimental|writing) treatment\b",
        re.IGNORECASE,
    ),
    "harness": re.compile(r"\bharness\b", re.IGNORECASE),
    "prompt": re.compile(
        r"\b(?:este|neste|o|no|do|pelo|um)\s+prompt\b|"
        r"\bprompt\s+(?:acima|abaixo|fornecido|de escrita|deste texto)\b",
        re.IGNORECASE,
    ),
    "hidden": re.compile(
        r"\bhidden\s+(?:arm|stage|treatment)\b"
        r"|\b(?:etapa|fase|arm)\s+escondid[oa]\b",
        re.IGNORECASE,
    ),
}

DEFAULT_PUBLISH = object()  # sentinel: use publisher.publish_rito (imported lazily)


class StageFailure(RuntimeError):
    pass


# --- sealing primitives (run.py pattern) ---------------------------------------------------

def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha_bytes(payload.encode("utf-8"))


def file_receipt(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "exists": False}
    data = path.read_bytes()
    return {"path": str(path), "exists": True, "bytes": len(data), "sha256": sha_bytes(data)}


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def read_text(path: Path) -> str:
    if not path.is_file():
        raise StageFailure(f"required stage/input missing: {path}")
    value = path.read_text(encoding="utf-8", errors="replace")
    if not value.strip():
        raise StageFailure(f"required stage/input empty: {path}")
    return value


def treatment_leaks(text: str) -> list[dict[str, Any]]:
    leaks: list[dict[str, Any]] = []
    for label, pattern in FORBIDDEN.items():
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            leaks.append({"label": label, "line": line, "match": match.group(0)})
    return leaks


def parse_acceptance(text: str) -> dict[str, Any]:
    """The fail-closed final-review header (run.py parse_final_review_acceptance, verbatim)."""
    header = [line.strip() for line in text.splitlines() if line.strip()][:3]
    if len(header) != 3:
        raise StageFailure(
            "final review lacks deterministic ACCEPTANCE/UNSUPPORTED_CLAIMS/TREATMENT_LEAK header")
    acceptance = re.fullmatch(r"ACCEPTANCE:\s*(PASS|FAIL)", header[0], re.IGNORECASE)
    unsupported = re.fullmatch(r"UNSUPPORTED_CLAIMS:\s*(\d+)", header[1], re.IGNORECASE)
    treatment = re.fullmatch(r"TREATMENT_LEAK:\s*(YES|NO)", header[2], re.IGNORECASE)
    if not (acceptance and unsupported and treatment):
        raise StageFailure(
            "final review's first three non-empty lines are not the required acceptance header")
    parsed = {
        "acceptance": acceptance.group(1).upper(),
        "unsupported_claims": int(unsupported.group(1)),
        "treatment_leak": treatment.group(1).upper(),
    }
    parsed["package_allowed"] = (
        parsed["acceptance"] == "PASS"
        and parsed["unsupported_claims"] == 0
        and parsed["treatment_leak"] == "NO")
    return parsed


def _ambient_theme_review_contract(dispatch_id, log) -> str:
    """Bind an autonomous rite to the Pauta's live PROPOSTA (o dente no rito — ADR-0024).

    Authority is mechanical (a live `pauta.proposta` penned by the funnel, whose own floors did
    the judging: substrato, delta_voz-against-the-Voz-baseline, gate da abordagem); whether the
    artefact actually DEVELOPS that proposal is semantic, so the final reviewer judges it. The
    Voz-anchor gate this replaces (dispatch.theme / vf:*) died with the old road: the autonomous
    Pauta road needs no prior Voice anchor by construction (fog nunca-abordada, curiosidade,
    coringa) — the Voz enters as the delta_voz baseline, never as a precondition of existence."""
    if not eventlog._is_canonical_log(log):
        return ""
    if eventlog.dispatch_origin(dispatch_id, log=log) != "beat":
        return ""  # the explicit user request itself opens a user_requested dispatch
    import pauta as _pauta
    proposta = _pauta.proposta_for(dispatch_id, log=log)
    if not isinstance(proposta, dict):
        raise StageFailure(
            "ambient beat sem pauta.proposta viva — o dente (ADR-0024): rode o funil da Pauta "
            "(tools/pauta.py sortear -> shortlist -> propose) antes do rito do produtor")
    cell = f"{proposta.get('abordagem')} x {proposta.get('objeto')}"
    return f"""

PAUTA GATE (blocking, semantic — the dente at the rite)
The Pauta bound this rite to a judged PROPOSTA; the artefact must develop IT, not another theme.

Celula: {cell}   Forma: {proposta.get('forma')}
Tema: {proposta.get('tema')}
Faceta: {proposta.get('faceta')}

Set ACCEPTANCE: FAIL unless the artefact's actual actionable question is a reasonably direct
development of that tema/faceta, and the abordagem's promised elements (per its signed gate —
mecanismo/trade-off/confronto/caminho, docs/agencia/pauta-tabela-normativa.md par.5) are present
in the text, anywhere, never as named sections. Mere subject overlap is insufficient. Commits,
agent execution, Direction, Wayfind, frontier, and open bets may support state/lineage only; if they
supply the specific action, order, priority, or problem that the PROPOSTA did not carry, fail.
Also fail when the artefact makes the reader adopt the delegated agent's implementation altitude —
file/symbol/command-level decisions or executor jargon as the spine/action list — unless the human
turns themselves reasoned about the trade-off at that level. Implementation may prove what changed;
it must be translated into the human's purpose, decision horizon, and vocabulary before it becomes
reader-facing guidance. Infer this from dialog roles and meaning, never profession, vocabulary,
filenames, or a technical-word list.
""".rstrip()


def manifest_core_hash(manifest: dict[str, Any]) -> str:
    """The binding hash: identity + the sealed receipts of the 10 COGNITIVE stages (the
    publication stage is excluded — its receipt carries this hash, so including it would be
    circular). The published event carries this; the detector recomputes it."""
    stages = [s for s in (manifest.get("stages") or []) if s.get("name") != "publication"]
    core = {"schema": manifest.get("schema"), "rito_version": manifest.get("rito_version"),
            "run_id": manifest.get("run_id"), "slug": manifest.get("slug"), "stages": stages}
    return canonical_hash(core)


# --- manifest lifecycle ----------------------------------------------------------------------

class _Run:
    """Paths + manifest I/O for one rite run (bound to run_dir, no globals)."""

    def __init__(self, run_dir: Path):
        self.dir = Path(run_dir)
        self.manifest_path = self.dir / MANIFEST_NAME
        self.prompts_dir = self.dir / "prompts"

    def output_for(self, name: str) -> Path:
        return self.dir / next(f for _, n, f, _, _ in STAGES if n == name)

    def save(self, manifest: dict[str, Any]) -> None:
        manifest["updated_at"] = now()
        write_text(self.manifest_path,
                   json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))

    def load(self) -> dict[str, Any]:
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))


def _stage_record(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)


def _new_manifest(slug: str, intent: str, skill: str, dispatch_id) -> dict[str, Any]:
    started = now()
    return {
        "schema": SCHEMA,
        "rito_version": RITO_VERSION,
        "run_id": str(uuid.uuid4()),
        "slug": slug,
        "intent": intent,
        "skill": skill,
        "dispatch_id": dispatch_id,
        "status": "running",
        "started_at": started,
        "updated_at": started,
        "finished_at": None,
        "failed_stage": None,
        "renderer_id": render.RENDERER_ID,
        "stages": [
            {"ordinal": n, "name": name, "output_file": filename, "route": route,
             "max_tokens": tokens, "status": "pending"}
            for n, name, filename, route, tokens in STAGES
        ],
    }


def _begin(run: _Run, manifest: dict[str, Any], name: str, prompt: str | None = None):
    stage = _stage_record(manifest, name)
    stage.update({"status": "running", "started_at": now(), "finished_at": None, "error": None})
    if prompt is not None:
        prompt_path = run.prompts_dir / f"{stage['ordinal']:02d}_{name}.md"
        write_text(prompt_path, prompt)
        stage["prompt"] = file_receipt(prompt_path)
    run.save(manifest)
    return stage


def _finish(run: _Run, manifest: dict[str, Any], name: str) -> None:
    output = run.output_for(name)
    read_text(output)
    receipt = file_receipt(output)
    receipt["words"] = len(re.findall(r"\w+", output.read_text(encoding="utf-8"), re.UNICODE))
    stage = _stage_record(manifest, name)
    stage.update({"status": "completed", "finished_at": now(), "output": receipt})
    run.save(manifest)


def _fail(run: _Run, manifest: dict[str, Any], name: str, exc: BaseException) -> None:
    stage = _stage_record(manifest, name)
    stage.update({
        "status": "failed", "finished_at": now(),
        "error": {"type": type(exc).__name__, "message": str(exc),
                  "traceback": traceback.format_exc()},
    })
    manifest.update({"status": "failed", "failed_stage": name, "finished_at": now()})
    run.save(manifest)


def _completed_output(run: _Run, manifest: dict[str, Any], name: str) -> str | None:
    """Resume seam (run.py completed_output): a completed stage's sealed output is reused —
    after verifying it has not drifted on disk."""
    stage = _stage_record(manifest, name)
    if stage.get("status") != "completed":
        return None
    path = run.output_for(name)
    expected = stage.get("output", {}).get("sha256")
    if not path.is_file() or (expected and sha_bytes(path.read_bytes()) != expected):
        raise StageFailure(f"completed stage drifted on disk: {name} ({path})")
    return read_text(path)


def _llm_stage(run, manifest, name, prompt, complete_fn, outputs) -> str:
    prior = _completed_output(run, manifest, name)
    if prior is not None:
        outputs[name] = prior
        return prior
    _, _, _, route, max_tokens = next(s for s in STAGES if s[1] == name)
    _begin(run, manifest, name, prompt)
    try:
        result = complete_fn(route, prompt, max_tokens)
        if not (isinstance(result, str) and result.strip()):
            raise StageFailure(f"route {route!r} returned an empty response at {name}")
        write_text(run.output_for(name), result)
        _finish(run, manifest, name)
    except BaseException as exc:
        _fail(run, manifest, name, exc)
        raise
    result = read_text(run.output_for(name))
    outputs[name] = result
    return result


# --- the runtime -----------------------------------------------------------------------------


def _run_feynman_gate_stage(run, manifest, name, page, complete_fn) -> dict[str, Any]:
    """LLM reviewer notes (old-edge review-gate). Records the verdict; does not raise.

    Two rounds always run. A score does not skip a lastro. A low score does
    not extra-loop. Mid-loop never StageFailure. The close tooth after
    rewrite 2 is what may refuse publication.
    """
    prior = _completed_output(run, manifest, name)
    if prior is not None:
        return json.loads(prior)
    import feynman_gate as _fg
    prompt = _fg.reviewer_prompt(page)
    _begin(run, manifest, name, prompt)
    try:
        verdict = _fg.review(page, complete_fn)
        write_text(
            run.output_for(name),
            json.dumps(verdict, ensure_ascii=False, indent=2, sort_keys=True),
        )
        rec = _stage_record(manifest, name)
        rec["verdict"] = verdict.get("verdict")
        rec["overall"] = verdict.get("overall")
        _finish(run, manifest, name)
    except BaseException as exc:
        _fail(run, manifest, name, exc)
        raise
    return json.loads(read_text(run.output_for(name)))


def run_rito(slug, *, run_dir, grounding1_fn, prompts, complete_fn, intent, skill="report",
             dispatch_id=None, log=eventlog.LOG, blog_dir=None,
             publish_fn=DEFAULT_PUBLISH, publish_meta=None, resume=False) -> dict[str, Any]:
    """Execute the WHOLE rite for one artefato: stages 1–10 then publication. Returns the
    completed manifest; raises StageFailure (manifest sealed as failed) on any break.

    `prompts` maps each LLM stage name → callable(outputs) -> str, where `outputs` maps the
    already-completed stage names to their text (plus `treatment_leaks` for the cleanup
    stage). `grounding1_fn()` returns the factual dossier. `complete_fn(route, prompt,
    max_tokens)` is the transport. `publish_fn(markdown, manifest) -> receipt` terminates
    the rite; the default is publisher.publish_rito on (slug, run_dir, intent, skill,
    dispatch_id, log, blog_dir)."""
    theme_review_contract = _ambient_theme_review_contract(dispatch_id, log)
    run = _Run(run_dir)
    if run.manifest_path.is_file():
        if not resume:
            raise StageFailure(f"a rite run already exists at {run.dir}; pass resume=True")
        manifest = run.load()
        if manifest.get("slug") != slug:
            raise StageFailure(f"resume slug mismatch: manifest has {manifest.get('slug')!r}")
        manifest.update({"status": "running", "failed_stage": None, "finished_at": None,
                         "resumed_at": now()})
        run.save(manifest)
    else:
        manifest = _new_manifest(slug, intent, skill, dispatch_id)
        run.save(manifest)

    import feynman_gate as _feynman_gate
    prompts = dict(prompts)
    for _fname, _ffactory in _feynman_gate.LOOP_PROMPTS.items():
        prompts.setdefault(_fname, _ffactory)

    missing = [name for name in LLM_STAGES if name not in prompts]
    if missing:
        raise StageFailure(f"producer supplied no prompt for LLM stages: {missing}")

    outputs: dict[str, str] = {}
    try:
        # 1 — grounding1_dossier (producer callable; the rite's factual authority)
        grounding1 = _completed_output(run, manifest, "grounding1_dossier")
        if grounding1 is None:
            _begin(run, manifest, "grounding1_dossier")
            try:
                grounding1 = grounding1_fn()
                write_text(run.output_for("grounding1_dossier"), grounding1)
                _finish(run, manifest, "grounding1_dossier")
            except BaseException as exc:
                _fail(run, manifest, "grounding1_dossier", exc)
                raise
        outputs["grounding1_dossier"] = grounding1

        # 2 — first authorial draft, then the deterministic treatment scan (fail the run,
        # never silently clean: the FIRST draft must be treatment-blind by construction)
        draft = _llm_stage(run, manifest, "first_authorial_draft",
                           prompts["first_authorial_draft"](outputs), complete_fn, outputs)
        first_leaks = treatment_leaks(draft)
        stage = _stage_record(manifest, "first_authorial_draft")
        stage["treatment_scan"] = {"checked_at": now(), "passed": not first_leaks,
                                   "leaks": first_leaks}
        run.save(manifest)
        if first_leaks:
            exc = StageFailure(f"first authorial draft anticipates treatment: {first_leaks}")
            manifest.update({"status": "failed",
                             "failed_stage": "first_artifact_treatment_scan",
                             "finished_at": now()})
            run.save(manifest)
            raise exc
        draft_sealed_sha = _stage_record(manifest, "first_authorial_draft")["output"]["sha256"]

        # 3–7 — critique, targeted grounding, rewrite, audit, correction
        for name in ("gap_critique", "grounding2_targeted", "provisional_rewrite",
                     "fact_audit", "author_correction"):
            _llm_stage(run, manifest, name, prompts[name](outputs), complete_fn, outputs)

        # Feynman content loop (hard contract): two deterministic iterations.
        # evaluate (LLM reviewer notes) -> new lastro -> rewrite -> evaluate ->
        # new lastro -> rewrite. A score does not skip a lastro. A low score
        # does not extra-loop. Mid-loop never StageFailure.
        page = outputs["author_correction"]
        for gate_name, ground_name, rewrite_name in (
            ("feynman_gate_1", "feynman_grounding_a", "feynman_rewrite_1"),
            ("feynman_gate_2", "feynman_grounding_b", "feynman_rewrite_2"),
        ):
            facing = yaml_rite.reader_facing_text(page)
            verdict = _run_feynman_gate_stage(
                run, manifest, gate_name, facing, complete_fn)
            outputs[gate_name] = json.dumps(verdict, ensure_ascii=False, indent=2)
            outputs["feynman_page"] = facing
            outputs["feynman_gate_verdict"] = outputs[gate_name]
            outputs["feynman_briefing"] = _feynman_gate.briefing(verdict)
            _llm_stage(run, manifest, ground_name,
                       prompts[ground_name](outputs), complete_fn, outputs)
            page = _llm_stage(run, manifest, rewrite_name,
                              prompts[rewrite_name](outputs), complete_fn, outputs)
            # Leaks in a loop rewrite are cleaned by treatment_cleanup (the close),
            # same as a leaky author_correction was. Do not abort the second round.

        # 8 — treatment cleanup: deterministic byte-copy when the scan is clean, else the
        # SAME AUTHOR route rewrites (run.py's conditional stage, promoted as-is)
        audited = outputs["feynman_rewrite_2"]
        cleanup_leaks = treatment_leaks(audited)
        cleanup_stage = _stage_record(manifest, "treatment_cleanup")
        if cleanup_stage["status"] == "completed":
            blind_safe = _completed_output(run, manifest, "treatment_cleanup")
        elif cleanup_leaks:
            outputs["treatment_leaks"] = json.dumps(cleanup_leaks, ensure_ascii=False)
            blind_safe = _llm_stage(run, manifest, "treatment_cleanup",
                                    prompts["treatment_cleanup"](outputs), complete_fn, outputs)
            _stage_record(manifest, "treatment_cleanup")["execution"] = {"mode": "same_author"}
        else:
            _begin(run, manifest, "treatment_cleanup")
            write_text(run.output_for("treatment_cleanup"), audited)
            _stage_record(manifest, "treatment_cleanup")["execution"] = {
                "mode": "deterministic_copy",
                "reason": "feynman rewrite 2 already passed the treatment scan"}
            _finish(run, manifest, "treatment_cleanup")
            blind_safe = read_text(run.output_for("treatment_cleanup"))
        outputs["treatment_cleanup"] = blind_safe
        remaining = treatment_leaks(blind_safe)
        cleanup_stage = _stage_record(manifest, "treatment_cleanup")
        cleanup_stage["treatment_scan"] = {"checked_at": now(), "passed": not remaining,
                                           "leaks": remaining}
        run.save(manifest)
        if remaining:
            exc = StageFailure(f"treatment cleanup left stage disclosure: {remaining}")
            manifest.update({"status": "failed", "failed_stage": "treatment_cleanup_scan",
                             "finished_at": now()})
            run.save(manifest)
            raise exc

        # #585 / #647: probe/review consume the mentee page, not raw YAML keys.
        # Markdown drafts stay the pinned renderer; leftover YAML still renders to HTML.
        reader_facing = yaml_rite.reader_facing_text(blind_safe)
        outputs["reader_facing"] = reader_facing

        # Close tooth: review the sealed page (LLM reviewer). The two rounds
        # already ran -- this is not a loop controller. ACCEPTANCE PASS /
        # assume-known / sibling do not waive.
        final_verdict = _feynman_gate.review(reader_facing, complete_fn)
        manifest["feynman_gate"] = final_verdict
        run.save(manifest)
        if final_verdict.get("verdict") != "PASS":
            exc = StageFailure(
                f"feynman gate rejected publication: {final_verdict['verdict']} "
                f"{final_verdict.get('critical_issues') or final_verdict.get('reasons')}"
            )
            manifest.update({"status": "failed", "failed_stage": "feynman_gate",
                             "finished_at": now()})
            run.save(manifest)
            raise exc

        # 9 — final_html: YAML → spec_to_html; markdown stays the pinned renderer.
        if _completed_output(run, manifest, "final_html") is None:
            _begin(run, manifest, "final_html")
            try:
                page_bytes = yaml_rite.page_bytes(blind_safe)
                out = run.output_for("final_html")
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(page_bytes)
                _finish(run, manifest, "final_html")
                _stage_record(manifest, "final_html")["renderer_id"] = yaml_rite.renderer_id_for(blind_safe)
                run.save(manifest)
            except BaseException as exc:
                _fail(run, manifest, "final_html", exc)
                raise

        # 10 — final review, fail-closed acceptance header + local scan.
        # A lente lectures-on-physics é parte fixa da revisão (feynman_gate.LENS_BLOCK):
        # clareza pedagógica é critério de strike, com os contrapesos vinculantes
        # (fato é do fact-audit; enchimento ≠ crescimento) escritos na própria lente.
        import feynman_gate as _feynman_gate
        review_outputs = dict(outputs)
        review_outputs["treatment_cleanup"] = outputs.get("reader_facing", blind_safe)
        final_review_prompt = (prompts["final_review"](review_outputs)
                               + "\n\n" + _feynman_gate.LENS_BLOCK)
        if theme_review_contract:
            final_review_prompt = f"{final_review_prompt}\n\n{theme_review_contract}"
        final_review = _llm_stage(run, manifest, "final_review",
                                  final_review_prompt, complete_fn, outputs)
        acceptance = parse_acceptance(final_review)
        local_leaks = treatment_leaks(blind_safe)
        acceptance["local_treatment_scan_passed"] = not local_leaks
        acceptance["package_allowed"] = acceptance["package_allowed"] and not local_leaks
        _stage_record(manifest, "final_review")["acceptance"] = acceptance
        run.save(manifest)
        if not acceptance["package_allowed"]:
            exc = StageFailure(f"final review rejected publication: {acceptance}")
            manifest.update({"status": "failed", "failed_stage": "final_review_acceptance",
                             "finished_at": now()})
            run.save(manifest)
            raise exc

        # draft immutability: the sealed first draft must be byte-identical at end of run
        # (blind-read addressability — the run.py invariant, kept in production)
        current_draft_sha = sha_bytes(run.output_for("first_authorial_draft").read_bytes())
        manifest["draft_immutability"] = {
            "sealed_sha256": draft_sealed_sha, "end_of_run_sha256": current_draft_sha,
            "unchanged": draft_sealed_sha == current_draft_sha}
        run.save(manifest)
        if draft_sealed_sha != current_draft_sha:
            raise StageFailure("first authorial draft changed during the rite")

        # 11 — PUBLICATION, inside the rite. The publisher recomputes the pinned render from
        # the sealed markdown and refuses a mismatch; the receipt (event + page + binding)
        # seals as the terminal stage.
        if _stage_record(manifest, "publication")["status"] != "completed":
            _begin(run, manifest, "publication")
            try:
                if publish_fn is DEFAULT_PUBLISH:
                    import publisher  # lazy: the detector must not need publisher's deps
                    receipt = publisher.publish_rito(
                        slug, run.dir, intent=intent, skill=skill,
                        dispatch_id=dispatch_id, log=log, blog_dir=blog_dir,
                        **(publish_meta or {}))
                else:
                    receipt = publish_fn(blind_safe, manifest)
                write_text(run.output_for("publication"),
                           json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
                _finish(run, manifest, "publication")
            except BaseException as exc:
                _fail(run, manifest, "publication", exc)
                raise

        manifest.update({"status": "completed", "finished_at": now(), "failed_stage": None})
        run.save(manifest)
        return manifest
    except StageFailure:
        raise
    except BaseException as exc:
        if manifest.get("status") != "failed":
            manifest.update({"status": "failed", "finished_at": now()})
            run.save(manifest)
        raise StageFailure(str(exc)) from exc


# --- the detector ------------------------------------------------------------------------------

def verify_rito(run_dir, *, log, blog_dir) -> dict[str, Any]:
    """Did this run traverse the experiment's rite, with the experiment's form? Collects ALL
    failures (named codes), never short-circuits after the manifest loads. Proves EXECUTION:
    stages + causal order + sealed receipts + pinned render bytes + bound publication event.
    Never scores the artifact's content."""
    run = _Run(run_dir)
    failures: list[str] = []
    if not run.manifest_path.is_file():
        return {"pass": False, "failures": ["manifest-missing"], "run_dir": str(run.dir)}
    try:
        manifest = run.load()
    except (json.JSONDecodeError, OSError):
        return {"pass": False, "failures": ["manifest-unreadable"], "run_dir": str(run.dir)}

    if manifest.get("schema") != SCHEMA or manifest.get("rito_version") != RITO_VERSION:
        failures.append("schema-mismatch")
    if manifest.get("status") != "completed" or manifest.get("failed_stage") is not None:
        failures.append("manifest-not-completed")
    if manifest.get("renderer_id") != render.RENDERER_ID:
        failures.append("renderer-id-mismatch")
    slug = manifest.get("slug")
    if not (isinstance(slug, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug)):
        # same slug discipline as the publisher's _safe_target (#4): a funny slug must not
        # steer the detector's page read outside blog_dir
        failures.append("slug-invalid")
        slug = None
    stages = manifest.get("stages") or []
    expected_names = [name for _, name, _, _, _ in STAGES]
    if [s.get("name") for s in stages] != expected_names:
        failures.append("stage-order")
    by_name = {s.get("name"): s for s in stages}

    # the immutable per-stage contract (ordinal / output file / route / token budget) must BE
    # the experiment's — same names with rewired routes is not the rite (codex [med])
    for n, name, filename, route, tokens in STAGES:
        stage = by_name.get(name)
        if stage is None:
            continue
        if (stage.get("ordinal") != n or stage.get("output_file") != filename
                or stage.get("route") != route or stage.get("max_tokens") != tokens):
            failures.append(f"stage-contract-drift:{name}")

    # every stage completed, receipts match disk, LLM stages carry sealed prompts
    for _, name, _, route, _ in STAGES:
        stage = by_name.get(name)
        if stage is None:
            failures.append(f"stage-missing:{name}")
            continue
        if stage.get("status") != "completed":
            failures.append(f"stage-not-completed:{name}")
            continue
        receipt = stage.get("output") or {}
        path = run.output_for(name)
        if not (path.is_file()
                and receipt.get("sha256") == sha_bytes(path.read_bytes())):
            failures.append(f"receipt-mismatch:{name}")
        if route:
            if (name == "treatment_cleanup"
                    and (stage.get("execution") or {}).get("mode") == "deterministic_copy"):
                # the conditional stage's no-LLM branch: legal ONLY when byte-identical to
                # the author correction (the same-author continuity proof is the byte copy)
                source = run.output_for("feynman_rewrite_2")
                if not (path.is_file() and source.is_file()
                        and path.read_bytes() == source.read_bytes()):
                    failures.append("cleanup-copy-not-identical")
                continue
            prompt = stage.get("prompt") or {}
            prompt_path = Path(prompt.get("path", "")) if prompt.get("path") else None
            ordinal = next(n for n, s, _, _, _ in STAGES if s == name)
            if not (prompt_path and prompt_path.is_file()
                    and prompt_path.resolve().parent == run.prompts_dir.resolve()
                    and prompt_path.name == f"{ordinal:02d}_{name}.md"
                    and prompt.get("sha256") == sha_bytes(prompt_path.read_bytes())):
                failures.append(f"prompt-receipt-missing:{name}")

    # causal order: begin/finish receipts monotonic across ordinals; render BEFORE review
    def _ts(name, key):
        return (by_name.get(name) or {}).get(key) or ""
    completed = [name for name in expected_names
                 if (by_name.get(name) or {}).get("status") == "completed"]
    for prev, nxt in zip(completed, completed[1:]):
        if _ts(prev, "finished_at") > _ts(nxt, "started_at"):
            failures.append(f"causal-order:{prev}->{nxt}")
    if ("final_html" in completed and "final_review" in completed
            and _ts("final_html", "finished_at") > _ts("final_review", "started_at")):
        if "causal-order:final_html->final_review" in failures:
            failures.remove("causal-order:final_html->final_review")
        failures.append("review-before-render")

    # acceptance: fail-closed header must have allowed the package
    review_stage = by_name.get("final_review") or {}
    if not (review_stage.get("acceptance") or {}).get("package_allowed"):
        failures.append("acceptance-fail")

    # THE FORM PIN: recompute the pinned render of the sealed markdown; it must hash-match
    # the sealed final_html receipt AND the published page bytes. Pipeline identity, not a score.
    md_path = run.output_for("treatment_cleanup")
    page_path = Path(blog_dir) / f"{slug}.html" if slug else None
    expected_page = None
    sealed_md = None
    stage_renderer = (by_name.get("final_html") or {}).get("renderer_id")
    _verify_rid = render.RENDERER_ID
    if md_path.is_file():
        _verify_rid = yaml_rite.renderer_id_for(md_path.read_text(encoding="utf-8"))
    if stage_renderer != _verify_rid and "renderer-id-mismatch" not in failures:
        failures.append("renderer-id-mismatch")
    if md_path.is_file():
        sealed_md = md_path.read_text(encoding="utf-8")
        expected_page = yaml_rite.page_bytes(sealed_md)
        sealed = (by_name.get("final_html") or {}).get("output") or {}
        if sealed.get("sha256") != sha_bytes(expected_page):
            failures.append("form-renderer-mismatch")
        if not (page_path and page_path.is_file()
                and page_path.read_bytes() == expected_page):
            failures.append("page-bytes-mismatch")
    else:
        failures.append("sealed-markdown-missing")

    # publication binding: the artefato.published event must exist, bind manifest + page,
    # and CARRY the sealed markdown itself (codex [high]: a swapped source that still
    # page-hash-matches must not pass)
    core = manifest_core_hash(manifest)
    try:
        events = [e for e in eventlog.read(log=log)
                  if e.get("type") == "artefato.published"
                  and (e.get("payload") or {}).get("slug") == slug]
    except OSError:
        events = []
    bound = []
    for ev in events:
        spec = (ev.get("payload") or {}).get("spec") or {}
        if (isinstance(spec, dict)
                and spec.get("format") == "edge-markdown/v1"
                and spec.get("renderer_id") == yaml_rite.renderer_id_for(sealed_md or "")
                and spec.get("rito_manifest_sha256") == core
                and expected_page is not None
                and spec.get("page_sha256") == sha_bytes(expected_page)
                and spec.get("markdown") == sealed_md):
            bound.append(ev)
    if not events:
        failures.append("publication-event-missing")
    elif not bound:
        failures.append("publication-event-unbound")

    # the SEALED terminal receipt must name one of the bound events (codex [high]: 'any
    # matching event for the slug' is forgeable; the receipt is what the rite sealed)
    receipt_path = run.output_for("publication")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        receipt = None
    if not (isinstance(receipt, dict)
            and any(ev.get("seq") == receipt.get("event_seq") for ev in bound)
            and receipt.get("rito_manifest_sha256") == core
            and receipt.get("renderer_id") == yaml_rite.renderer_id_for(sealed_md or "")
            and expected_page is not None
            and receipt.get("page_sha256") == sha_bytes(expected_page)):
        failures.append("publication-receipt-unbound")

    return {"pass": not failures, "failures": failures, "run_dir": str(run.dir),
            "slug": slug, "run_id": manifest.get("run_id")}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="did this run traverse the rite, with its form?")
    verify.add_argument("run_dir")
    verify.add_argument("--log", default=str(eventlog.LOG))
    verify.add_argument("--blog-dir", default=str(Path(eventlog.REPO) / "blog" / "entries"))
    args = parser.parse_args(argv)
    verdict = verify_rito(args.run_dir, log=Path(args.log), blog_dir=Path(args.blog_dir))
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    return 0 if verdict["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
