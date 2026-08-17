"""briefing — the deterministic composer of Memento's tattoo (ADR-0009). Genotype tool.

The agent has anterograde amnesia: it must orient **entirely** from the briefing and trust
nothing that isn't inscribed there (CONTEXT.md, the `**Briefing**` entry). So the load-bearing
lines — the curated Direction, what is open / the next bet, the source yield, what the agent
already did — are **deterministically inscribed from the log** (folds of `tools/eventlog.py`),
never left to an LLM to remember. Only the **Recap** (the corpus↔live-Atividade relation) is
synthesized fresh; `assemble` fills its slot. The **Facts leg** (Knowledge clusters) navigates the
graph (ADR-0011: graph mandatory, Cortex guaranteed); a real outage degrades only that leg to the
Tier-0 note — the log-fold legs still compose, the beat never crashes.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eventlog import LOG, docs_at  # noqa: E402  (Plataforma constant; queries go through the door)
import cortex  # noqa: E402  (porta Módulo-2 — §5 lê as communities consolidadas)
from cortex import (direction_at, corpus_at, artefatos_without_kernel,  # noqa: E402
                    source_feedback_at, objective_at, report_at)
import _identity  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
import _identity as _id_state
AGENT_YAML = _id_state.identity_path("agent.yaml")
MEMORY = _id_state.identity_path("memory")
STATE = _id_state.runtime_root() / "state"

KIND_ORDER = ["phase", "priority", "constraint", "thread"]

# The identity fields the genotype CANNOT compose without — a thin agent.yaml that omits any of
# these is a lobotomy (ADR-0009), not a valid install. The personality `.tpl` substitutes them.
REQUIRED_IDENTITY = ["name", "mission", "voice"]


class BriefingIdentityError(Exception):
    """Fail-closed signal: a genotype-identity input the briefing REQUIRES is missing/thin (thin
    agent.yaml identity, absent doctrine, blank idiom, or no declared source roster). Raised instead
    of silently blanking a load-bearing identity section, so `_validate`/`edge-apply` can catch it
    and a lobotomized edge never reaches HEALTHY (briefing-lifecycle gate, issue #26)."""

# The native source the edge always reads — the mentee's Claude sessions (the transcript store the
# sweep digests). Not declared in agent.yaml because it is intrinsic to the runtime; a constant floor
# entry so the roster is never blank even on a stock agent.yaml (ADR-0011, Source roadmap floor).
NATIVE_SOURCE = {"name": "claude-sessions", "kind": "native",
                 "label": "the mentee's Claude sessions (native transcript store)"}


def _onboarding_roster_from_bootstrap(agent_yaml=AGENT_YAML):
    """Soft roster while phenotype is absent: native sessions + secrets inventory names.

    Used only when agent.yaml is missing but state/bootstrap.json exists (first-run path).
    Never invents sources; secrets appear as availability markers, not as API sources.
    """
    try:
        import onboarding
        import _identity
    except ImportError:
        return None
    p = Path(agent_yaml)
    # home: EDGE_HOME → parent of agent_yaml if under an install → edge_home from bootstrap
    home = os.environ.get("EDGE_HOME")
    if home:
        home = Path(os.path.expanduser(home))
    elif p.exists():
        home = p.parent
    else:
        # bootstrap may live under cwd install
        cand = Path.cwd() / "state" / "bootstrap.json"
        home = Path.cwd() if cand.is_file() else None
    if home is None or not (Path(home) / "state" / "bootstrap.json").is_file():
        return None
    inv = onboarding.inventory_secrets(onboarding.secrets_dir(home))
    boot = onboarding.load_bootstrap(home)
    roster = [dict(NATIVE_SOURCE)]
    roster.append({
        "name": "secrets-inventory",
        "kind": "local",
        "label": (
            f"operator secrets at {inv.get('path')} — files: "
            f"{', '.join(inv.get('files') or []) or '(none)'}; "
            f"vars: {', '.join(inv.get('vars') or []) or '(none)'} "
            f"(onboarding mode; no phenotype yet; lookback_days={boot.get('backfill_days')})"
        ),
    })
    return roster


def source_roster(agent_yaml=AGENT_YAML):
    """The declared source roster (← Source roadmap, ADR-0011) — the source orientation's floor.
    FAIL-CLOSED (gate root-cause #2): requires agent.yaml to exist and carry a non-empty `sources:`
    list whose every entry has name + kind + description, each a non-empty STRING (a blank/
    whitespace/non-string field is a thin roster, not a real one); the native Claude-sessions source
    is prepended as an ADDITIVE floor, never a SUBSTITUTE for the declared roster (so a missing/
    malformed source list cannot masquerade as a non-empty section). Per-entry `label` is the
    (stripped) description. Pure-ish: only reads agent.yaml, so compose_briefing
    stays a pure composer when handed a roster explicitly.

    Onboarding exception: if agent.yaml is absent but state/bootstrap.json exists, return a soft
    roster (native + secrets inventory) instead of raising — first-run assemble/wake must run.
    """
    import yaml
    p = Path(agent_yaml)
    if not p.exists():
        soft = _onboarding_roster_from_bootstrap(agent_yaml=agent_yaml)
        if soft is not None:
            return soft
        raise BriefingIdentityError(f"agent.yaml absent ({p}) — no declared source roster to inject")
    data = yaml.safe_load(p.read_text()) or {}
    sources = data.get("sources")
    if not sources:
        # empty sources on a bootstrap phenotype mid-flight: soft if bootstrap present
        soft = _onboarding_roster_from_bootstrap(agent_yaml=agent_yaml)
        if soft is not None and not sources:
            return soft
        raise BriefingIdentityError("agent.yaml declares no sources — the source roster is empty "
                                    "(the native floor is additive, never the whole roster)")
    if not isinstance(sources, list):
        raise BriefingIdentityError(
            f"agent.yaml `sources` is not a list ({type(sources).__name__}) — the source roster must "
            "be a list of mappings (name + kind + description), not a string/mapping")
    roster = [dict(NATIVE_SOURCE)]
    for s in sources:
        if not isinstance(s, dict):
            raise BriefingIdentityError(
                f"malformed source entry {s!r} — each declared source must be a mapping with "
                "name + kind + description")
        name, kind, desc = s.get("name"), s.get("kind"), s.get("description")
        for field, val in (("name", name), ("kind", kind), ("description", desc)):
            if not isinstance(val, str) or not val.strip():
                raise BriefingIdentityError(
                    f"malformed source entry {s!r} — `{field}` must be a non-empty string "
                    "(name + kind + description); a blank/whitespace/non-string field is a thin roster")
        roster.append({"name": name.strip(), "kind": kind.strip(), "label": desc.strip()})
    return roster



def _render_direction_items(items):
    by_kind = {}
    for it in items:
        by_kind.setdefault(it.get("kind", "thread"), []).append(it)
    lines = []
    for kind in KIND_ORDER + [k for k in by_kind if k not in KIND_ORDER]:
        for it in by_kind.get(kind, []):
            lines.append(f"- **[{kind}]** {it.get('body', '')}")
    return "\n".join(lines) if lines else "_none_"


def _section_objective(log, seq, ts):
    """The spine (ADR-0006/0007): the mentee's **confirmed objective** — the anchor everything below
    is measured against, so it sits ABOVE Direction. Inscribed from the log fold (objective_at), a
    saved-as-confirmed-hypothesis prior the next grill re-tests. No objective set yet → an honest
    marker (the briefing still composes on a fresh log)."""
    obj = objective_at(seq=seq, ts=ts, log=log)
    if obj is None:
        return "## Objective — the anchor\n\n_no confirmed objective yet._"
    body = obj.get("body", "")
    rationale = obj.get("rationale")
    why = f"\n\n_why:_ {rationale}" if rationale else ""
    return f"## Objective — the anchor\n\n{body}{why}"


def _section_direction(log, seq, ts):
    d = direction_at(seq=seq, ts=ts, log=log)
    if d is None:
        return "## 1. Direction\n\n_no direction set yet._"
    return ("## 1. Direction\n\n"
            "**Set — curated (Voz, highest authority):**\n\n"
            f"{_render_direction_items(d.get('set', []))}\n\n"
            "**Proposed — non-curated (grill achados):**\n\n"
            f"{_render_direction_items(d.get('proposed', []))}")


def _section_report(log, seq, ts):
    """The direcionamento — the rolling steer injected every wake (ADR-0006/0007). Direction's
    proposed/set bullets are the skeleton; this report is the flesh actually read: objective + the
    steer + the live insight, re-derived from the data each grill. Only the LATEST shows (the present
    steer; the lineage is the grill's to read). Inscribed from the log fold (report_at). No report
    yet → an honest marker (additive — Direction still renders above)."""
    r = report_at(seq=seq, ts=ts, log=log)
    latest = r.get("latest")
    if latest is None:
        return "## Direcionamento — the rolling steer\n\n_no direcionamento report yet._"
    return f"## Direcionamento — the rolling steer\n\n{latest.get('body', '')}"


def _section_continuity(corpus):
    """The literal tattoo: what the cold agent was mid-doing — the *why* of the most-recent
    kernels, most-recent-first. Empty corpus (or no recorded why yet) → an honest empty marker."""
    whys = [c["intent"] for c in reversed(corpus) if c.get("intent")]
    body = "\n".join(f"- {w}" for w in whys[:2]) if whys else "_nothing open recorded yet._"
    return f"## 2. What is open / the next bet\n\n{body}"


def _section_corpus(corpus, debt):
    """What I already did: recent slugs + their why, most-recent-first, so the agent builds rather
    than repeats. Kernel-less Artefatos are surfaced as C3 debt (show the gap, don't hide it)."""
    if not corpus:
        body = "_no corpus yet._"
    else:
        lines = []
        for it in reversed(corpus):
            why = it.get("intent") or "_no intent recorded (C3 debt)_"
            lines.append(f"- **{it['slug']}** — {why}")
        body = "\n".join(lines)
    if debt:
        body += "\n\n**C3 debt** (Artefatos with no recorded intent): " + ", ".join(debt)
    return f"## 3. Corpus — what I already did\n\n{body}"


def _section_sources(log, seq, ts, roster):
    """Source orientation (ADR-0011): the declared **roster** (← Source roadmap) as the never-blank
    **floor**, then the two-tier source feedback — the **curated** stratum (← source.curated, the
    grill-distilled mentee opinion) ABOVE the non-curated **yield** (ref · kind · count · mean sim,
    highest first), mirroring _section_direction (set over proposed). The grill consults the yield;
    the roster + curated keep the section honest before/after signal accrues. Degrade, never crash."""
    floor = "\n".join(f"- **{r['name']}** ({r.get('kind')}) — {r.get('label', r['name'])}"
                      for r in (roster or []))
    parts = ["## 4. Source orientation", "**Declared roster** (the floor — what each source is for):",
             floor or "_no roster declared._"]
    fb = source_feedback_at(seq=seq, ts=ts, log=log)
    if fb["curated"]:
        cur = "\n".join(f"- **{c['source']}** — {c['opinion']}" for c in fb["curated"])
        parts += ["**Curated — mentee opinion (Voz-grounded, highest authority):**", cur]
    yld = fb["non_curated"]
    if yld:
        rows = sorted(yld.values(), key=lambda r: r["mean_similarity"], reverse=True)
        lines = [f"- **{r['ref']}** ({r['kind']}) · {r['count']}× · mean sim {r['mean_similarity']:.2f}"
                 for r in rows]
        parts += ["**Source feedback — non-curated (how each source actually yielded):**", "\n".join(lines)]
    # S7 — the yield advisory block (grounding_yield §4): ≤6 lines, never-blank via the roadmap
    # seed rows. Degrade-dark (like the graph leg): a yield-fold failure must never crash the
    # briefing — the log-fold legs above still compose.
    try:
        import grounding_yield
        parts.append(grounding_yield.briefing_yield_block(log=log, seq=seq, ts=ts))
    except Exception:  # noqa: BLE001 — advisory only; the briefing never crashes on it
        pass
    return "\n\n".join(parts)


def _section_clusters(clusters, hot_cutoff=None):
    """Knowledge clusters (← graph): as communities AUTO-consolidadas (Módulo 2), o tier emergente
    do frio. Estados: None → nota de degrade (graph DARK ≠ vazio); [] → alcançável, nada
    consolidado ainda; [{name, summary, size, last_touched}] → o índice recency-first.
    `hot_cutoff` (ISO ts) = TEMPO-DIVIDE-DONOS: cluster tocado dentro da janela do quente NÃO
    expande aqui (vira ponteiro '→ coberto no quente') — o wake nunca conta a mesma história 2×.
    [str, ...] → labels crus (pure-composer callers). Never crash on the graph."""
    if clusters is None:
        return ("## 5. Knowledge clusters\n\n"
                "_Tier-0: clusters unavailable — the graph leg is DARK, which is NOT the same as "
                "'no clusters yet'. Before narrating 'graph offline', CHECK: (1) did this process load "
                "the install secrets (`_secrets.load_env(secrets/)`)? a `claude -p` dispatch must, or "
                "EDGE_NEO4J_PASSWORD is absent and the leg darkens though neo4j is up; (2) is EDGE_GROUP "
                "/ agent.yaml graph_group set? `edge-apply --validate` is the ground truth for "
                "reachability. If both hold, the graph is reachable and this is a load gap, not an "
                "outage — do not report 'offline'. Knowledge this beat = the swept log + Direction._")
    if not clusters:
        return "## 5. Knowledge clusters\n\n_graph reachable — no clusters yet (consolidação ainda não rodou)._"
    if isinstance(clusters[0], dict):
        parts = ["## 5. Knowledge clusters",
                 "_Communities consolidadas automaticamente (tier-HIPÓTESE — sumário de extração, "
                 "nunca assertado). Navegue: cortex.community(nome) → membros, sessões-fonte, artefatos._"]
        for c in clusters:
            name, lt, size = c.get("name"), c.get("last_touched") or "?", c.get("size", "?")
            if hot_cutoff and c.get("last_touched") and c["last_touched"] >= hot_cutoff:
                parts.append(f"- **{name}** ({size} · tocado {lt}) → coberto no quente")
            else:
                parts.append(f"- **{name}** ({size} · tocado {lt})\n  {c.get('summary', '')}")
        return "\n".join(parts)
    return "## 5. Knowledge clusters\n\n" + "\n".join(f"- {c}" for c in clusters)


def _section_recap(recap):
    """Recap (← corpus): the one synthesized-fresh part — the corpus↔live-Atividade relation.
    None → a slot marker the assemble LLM fills; otherwise inscribe the synthesized text."""
    body = recap or "_(Recap synthesized at compose-time — corpus × live Atividade)_"
    return f"## 6. Recap\n\n{body}"


def _live_context(log, seq, ts):
    """O contexto vivo contra o qual a relevância dos docs é medida (I8): Direction (set ∪ proposed)
    + threads ativas — a string que a busca por embedding consulta."""
    d = direction_at(seq=seq, ts=ts, log=log) or {"set": [], "proposed": []}
    return "\n".join(i.get("body", "") for i in (d.get("set", []) + d.get("proposed", [])))


def _section_docs(log=LOG, seq=None, ts=None, embed_fn=None, k=5):
    """Seção **Documentos canônicos** (issue #130): (i) os índices das threads VIVAS na Direction
    sobem SEMPRE; (ii) o resto do canon + docs vivos entra por relevância top-K ao contexto vivo,
    via embedding (fiação da infra dos artefatos). Provider dark → degradação DECLARADA (fallback
    thread+recência), NUNCA silenciosa (spec). `embed_fn` injetável (mock nos testes)."""
    import md_to_mem
    indices = md_to_mem.live_thread_indices(seq=seq, ts=ts, log=log)
    lines = ["## Documentos canônicos"]
    if indices:
        lines.append("**Índices das threads vivas** (sobem sempre enquanto a thread vive):")
        lines += [f"- {d['slug']}" + (f" ({', '.join(d['threads'])})" if d.get("threads") else "")
                  for d in indices]
    index_slugs = {d["slug"] for d in indices}
    try:
        relevant = md_to_mem.relevant_docs(_live_context(log, seq, ts), log=log,
                                           embed_fn=embed_fn, k=k, seq=seq, ts=ts)
        extra = [d for d in relevant if d["slug"] not in index_slugs]
        if extra:
            lines.append(f"**Por relevância** (top-{k} ao contexto vivo):")
            lines += [f"- {d['slug']}" for d in extra]
    except md_to_mem.RelevanceDegraded as e:
        # degradação DECLARADA: o provider de embedding está dark; caímos pra thread+recência.
        state = docs_at(seq=seq, ts=ts, log=log)
        canon_md = {c["ref"] for c in state["canon"] if c["kind"] == "md"}
        fallback = [d for d in sorted(state["live"], key=lambda x: x.get("ts") or "", reverse=True)
                    if d["slug"] in canon_md and d["slug"] not in index_slugs][:k]
        lines.append(f"_provider de embedding dark ({e}) — relevância DEGRADA para thread+recência:_")
        lines += [f"- {d['slug']}" for d in fallback]
    if len(lines) == 1:
        lines.append("_nenhum documento canônico ainda._")
    return "\n\n".join([lines[0], "\n".join(lines[1:])])


BANNER = ("<!-- generated by tools/briefing.py — Memento's tattoo (ADR-0009); "
          "load-bearing lines inscribed from the log, only the Recap synthesized fresh -->")


def _render_tpl(text, agent_yaml=AGENT_YAML):
    """Substitute {{var}} from agent.yaml identity fields (same convention as templates/).
    FAIL-CLOSED (gate root-cause #1): a referenced identity field (name/mission/voice) that is
    absent or blank in agent.yaml raises BriefingIdentityError rather than silently substituting
    empty — a thin identity must fail loud, never blank the personality tattoo.

    First-run soft path: when agent.yaml is absent but state/bootstrap.json exists, fill name
    from bootstrap and temporary mission/voice placeholders so wake/assemble can orient.
    """
    import re
    import yaml
    cfg = {}
    p = Path(agent_yaml)
    if p.exists():
        cfg = yaml.safe_load(p.read_text()) or {}
    else:
        # onboarding: soft identity from bootstrap
        try:
            import onboarding as _onb
            home = os.environ.get("EDGE_HOME")
            if home and (Path(os.path.expanduser(home)) / "state" / "bootstrap.json").is_file():
                boot = _onb.load_bootstrap(home)
                cfg = {
                    "name": boot.get("name") or "edge",
                    "codename": boot.get("name") or "edge",
                    "mission": "(first-run — mission born in mentor)",
                    "voice": "(first-run — voice born in mentor)",
                }
        except Exception:
            cfg = {}
    cfg.setdefault("codename", cfg.get("name", ""))
    refs = set(re.findall(r"\{\{\s*(\w+)\s*\}\}", text))
    missing = [k for k in REQUIRED_IDENTITY if k in refs and not str(cfg.get(k, "")).strip()]
    if missing:
        raise BriefingIdentityError(
            f"agent.yaml identity is thin — {', '.join(missing)} blank/absent; the personality "
            "tattoo would silently blank. Fill the identity (ADR-0009).")
    return re.sub(r"\{\{\s*(\w+)\s*\}\}",
                  lambda m: str(cfg.get(m.group(1), m.group(0))), text)


def _read_doc(name, memory=MEMORY, agent_yaml=AGENT_YAML):
    """Read a memory doctrine doc — rendered `.md` preferred, else render the `.md.tpl`. '' if absent.
    The `.tpl` render is fail-closed on thin identity (via _render_tpl)."""
    md, tpl = Path(memory) / f"{name}.md", Path(memory) / f"{name}.md.tpl"
    if md.exists():
        return md.read_text().strip()
    if tpl.exists():
        return _render_tpl(tpl.read_text(), agent_yaml=agent_yaml).strip()
    return ""


def _section_tattoos(memory=MEMORY, agent_yaml=AGENT_YAML):
    """The **immutable** head of the briefing — the *initial tattoos*: who the edge is (**personality**),
    how it thinks (**method**, the Feynman doctrine) and what it holds as taste (**cânone**, ticket 05:
    as boas lembranças que não morrem no reset — o exemplar a apontar, o academicismo a evitar). Loaded
    ONLY here, at the edge's wake (via the briefing) — never the global `CLAUDE.md` system prompt (that
    would change Claude, not the edge). Read from `memory/` as the **current** doctrine (not
    cursor-versioned — the tattoos are foundational, not historical). FAIL-CLOSED (gate root-cause #1):
    personality, method AND canone must ALL render non-empty, or it raises BriefingIdentityError — an
    absent/blank tattoo is a lobotomy, never a silent marker."""
    personality = _read_doc("personality", memory=memory, agent_yaml=agent_yaml)
    method = _read_doc("method", memory=memory, agent_yaml=agent_yaml)
    canone = _read_doc("canone", memory=memory, agent_yaml=agent_yaml)
    missing = [n for n, v in (("personality", personality), ("method", method),
                              ("canone", canone)) if not v]
    if missing:
        raise BriefingIdentityError(
            f"doctrine absent/blank — {', '.join(missing)} not inscribed in {memory}; "
            "the initial tattoos are REQUIRED at every stage (ADR-0009).")
    return "\n\n".join([
        "## Initial tattoos (immutable) — who I am, how I think",
        "_The permanent tattoos: loaded every wake, unchanged by the log. Operate from these "
        "before reading the state below._",
        "### Personality\n\n" + personality,
        "### Method\n\n" + method,
        "### Cânone\n\n" + canone,
    ])


def _section_idiom(agent_yaml=AGENT_YAML, state_dir=STATE):
    """The Idiom / glossary (← the mentee's terms, ADR-0005). The glossaries are NOT genotype — they
    are a per-install CONSEQUENCE of `agent.yaml` `ground_truth.documents` (the mentee's projects'
    CONTEXT.md, the authored canon / Voz ground-truth). This reads that declared list (paths, `~`
    expanded), reads each EXISTING non-empty file, and INJECTS its content as the glossary FLOOR — so
    the amnesiac beat speaks the mentee's language. The edge's own curated `state/idiom.md` (grilling-
    accreted, expected-empty on a fresh install) is LAYERED on top when present, never the floor.

    Fail-closed distinguishes a config-gap from a genotype lobotomy:
      • ground_truth declared but ALL documents absent/empty → BriefingIdentityError (a declared-but-
        missing canon is a real config failure);
      • some present, some missing → inject the present ones + note the missing (never silently drop);
      • ground_truth NOT declared at all → an honest "no ground_truth declared" marker (an agent.yaml
        CONFIG gap, NOT a lobotomy — does NOT raise, distinct from the fail-closed tattoos)."""
    import yaml
    p = Path(agent_yaml)
    data = yaml.safe_load(p.read_text()) if p.exists() else None
    gt = (data or {}).get("ground_truth") if isinstance(data, dict) else None
    documents = (gt or {}).get("documents") if isinstance(gt, dict) else None

    if not documents:
        # An agent.yaml CONFIG gap — honest marker, not a raise (distinct from the lobotomy tattoos).
        return ("## Idiom — the mentee's terms\n\n"
                "_no ground_truth declared in agent.yaml — the glossary floor "
                "(`ground_truth.documents`) is unconfigured; this is an agent.yaml CONFIG gap, not a "
                "genotype lobotomy. No mentee glossary is injected this wake._")

    blocks, missing = [], []
    for raw in documents:
        path = Path(os.path.expanduser(str(raw)))
        content = path.read_text().strip() if path.exists() else ""
        if content:
            blocks.append(f"### {raw}\n\n{content}")
        else:
            missing.append(str(raw))

    if not blocks:
        raise BriefingIdentityError(
            f"ground_truth declared but ALL documents absent/empty ({', '.join(missing)}) — a "
            "declared-but-missing canon is a real config failure; the glossary floor is REQUIRED "
            "when ground_truth is declared (ADR-0005).")

    parts = ["## Idiom — the mentee's terms",
             "_Glossary floor — the ground_truth.documents (the mentee's projects' authored canon)._"]
    parts += blocks
    if missing:
        parts.append("_Missing ground_truth document(s) (declared but absent/empty): "
                     + ", ".join(missing) + "._")

    idiom = Path(state_dir) / "idiom.md"
    layer = idiom.read_text().strip() if idiom.exists() else ""
    if layer:
        parts.append("### Curated Idiom (edge-accreted)\n\n" + layer)
    return "\n\n".join(parts)


_AUTO = object()  # sentinel: "fetch clusters for me" vs an explicit None ("I have none — Tier-0")


def compose_briefing(log=LOG, recap=None, clusters=_AUTO, roster=None, seq=None, ts=None, group=None,
                     agent_yaml=AGENT_YAML, memory=MEMORY, hot_cutoff=None):
    """Render the briefing (Memento's tattoo) as one markdown string, from the log. Deterministic:
    sections in tattoo priority (load-bearing first). Cursor-aware (seq/ts) like the folds it reads.
    The genotype-identity head (Personality, Method, Idiom, the declared Source roster) is
    FAIL-CLOSED: a thin agent.yaml, absent doctrine, blank idiom, or no declared sources raises
    BriefingIdentityError (briefing-lifecycle gate) — never a silent blank. `roster` defaults to
    source_roster() (reads agent.yaml); pass it explicitly (e.g. []) to keep compose_briefing a
    pure composer (tests, Tier-0). `clusters` is the Facts leg: left unset, it navigates the Cortex
    for `group` (defaults to EDGE_GROUP) via cortex.communities() — as communities consolidadas
    automaticamente (o rail curated_cluster foi APOSENTADO: nunca carregou um cluster; trilho
    órfão) — degradando a None em outage.
    The memory-salient view is NOT a section here: recall is a third independent brief, peer to
    this one (ADR-0014, `tools/recall.py:compose_recall_brief`) — the briefing's four parts only.
    `hot_cutoff` (ISO ts, tempo-divide-donos) = o window_start do quente: clusters tocados dentro
    da janela deferem no §5 ('→ coberto no quente') em vez de expandir — o 4º brief é o dono da
    história recente (predispatch o computa via quente.select_window; None = tudo expande)."""
    if roster is None:
        roster = source_roster(agent_yaml=agent_yaml)
    # resolve the group LAZILY — only when an auto-fetch actually needs it (Codex P3): a caller that
    # pinned clusters (Tier-0 / custom-agent tests) must stay hermetic and not trigger a default
    # identity lookup that could read the wrong install or fail.
    def _group():
        return group if group is not None else _identity.group()
    if clusters is _AUTO:
        clusters = cortex.communities(_group())
    corpus = corpus_at(seq=seq, ts=ts, log=log)
    parts = [
        BANNER + "\n# Briefing — orient entirely from here",
        _section_tattoos(memory=memory, agent_yaml=agent_yaml),
        _section_idiom(agent_yaml=agent_yaml, state_dir=Path(memory).parent / "state"),
        _section_objective(log, seq, ts),
        _section_direction(log, seq, ts),
        _section_report(log, seq, ts),
        _section_docs(log, seq, ts),
        _section_continuity(corpus),
        _section_corpus(corpus, artefatos_without_kernel(log=log)),
        _section_sources(log, seq, ts, roster),
        _section_clusters(clusters, hot_cutoff=hot_cutoff),
        _section_recap(recap),
    ]
    return "\n\n".join(parts) + "\n"
