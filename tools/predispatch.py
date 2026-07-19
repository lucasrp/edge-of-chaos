"""predispatch — the mechanical entry-driver of every dispatch (ADR-0016). Genotype tool.

The wake stops being a prose-only contract: this driver performs the mechanical pre-dispatch
floor. IDENTITY PRECEDES GROUNDING (#62): digestion sweep to currency (fail-loud store,
ADR-0015) → compose the briefing → stamp `dispatch.open` (IDENTITY-ONLY) in the Tier-0 log and
emit `DISPATCH_ID=` — and ONLY THEN the O(store) grounding legs (harvest the transcript store
into grounding.manifest rows, render the recall brief, run the canary battery), all degrade-dark,
whose read-side metrics land on a separate `dispatch.grounding` event. So a slow/blocking/dark
harvest can never delay or swallow the id. The publisher refuses to publish without a
`dispatch.open` that MINTED the artefato's `dispatch_id` and is not yet consumed (identity-held
gate, E1): **no wake, no publish**. The skill prose *describes* the wake; this driver *performs* it.

Delta is NOT here (ADR-0001/0011): the world-read is agentic judgment, fanned by the skill when
it judges it needs the world — it never gates and is never stamped.

Degrade contract: a RAISING sweep aborts before the stamp (a dispatch that could not wake must
not look woken — e.g. the transcript store is missing, ADR-0015). A degraded *brief* still
stamps — the gate proves the wake ran, not that the world cooperated (a graph outage darkens the
recall brief honestly; `compose_recall_brief` itself never raises, the wrap here is defense in
depth). The S5 grounding legs (harvest, canary) NEVER abort the wake either — a dead source is an
annotated dark leg, the stamp still lands (R3.2: grounding annotates, it never gates). A raising
briefing compose aborts too: `BriefingIdentityError` is a lobotomized install
(ADR-0009 fail-closed), not an outage. A crash anywhere in the sweep→stamp gap is safe by the
same shape: the sweep's effects are durable and idempotent, no stamp means the publisher refuses,
and re-running this driver recovers. After identity and grounding are durable, the driver enqueues
the log-checkpointed rationalizer's systemd worker; enqueue failure is visible but never gates wake.
"""
import argparse
import contextlib
import io
import os
import re
import secrets
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog          # noqa: E402
import sessions as sessions_mod  # noqa: E402
import sources as sources_mod   # noqa: E402  — the agent.yaml interfaces[] seam (S3): the canary
#   battery iterates the DECLARED interfaces, NEVER a source named in code (E8, the Overleaf test)


def _hot_cutoff(window_fn=None):
    """A perna quente do briefing (tempo-divide-donos): o window_start das K sessões substanciais
    (quente.select_window — a MESMA seleção que alimenta o 4º brief, host-agnóstica via
    _identity.project_dir) vira o hot_cutoff do compose_briefing, pra o §5 deferir os clusters
    que o quente cobre. DEGRADE-DARK: qualquer falha ou janela vazia → None (tudo expande) —
    a perna quente nunca derruba nem atrasa o wake (mesma forma das grounding legs)."""
    try:
        import quente as _quente
        _sel, window_start = (window_fn or _quente.select_window)()
        return window_start or None
    except Exception as e:  # noqa: BLE001 — advisory; o briefing sem hot_cutoff é o briefing de ontem
        print(f"predispatch: hot-cutoff leg DARK ({type(e).__name__}: {e}) — clusters expandem "
              "normalmente este wake.")
        return None


def mint_dispatch_id():
    """Mint the dispatch's IDENTITY (S2, E1): a lexicographically-sortable unique id — a
    zero-padded ms timestamp prefix + 64 random bits. The repo has no ULID helper and the house
    rules forbid a new dep, so this is the ULID-equivalent: the timestamp prefix keeps ids
    monotonic across dispatches (sortable like a seq), the random suffix makes concurrent mints
    collision-free. Minted ONCE per dispatch at entry and CARRIED explicitly through
    close/publish — never reconstructed from "the last dispatch.open before the publish" (E1)."""
    return f"{int(time.time() * 1000):013d}-{secrets.token_hex(8)}"


def run(sweep_fn=None, briefing_fn=None, recall_fn=None, harvest_fn=None, probe_fn=None,
        log=eventlog.LOG, dispatch_id=None, theme=None, intent=None, geometry=None,
        id_sink=None, origin=None, enqueue_fn=None, employment=False, ready_fn=None,
        drain_fn=None):
    """The mechanical floor, in order: budgeted Assemble drain → ready gate → sweep →
    briefing → STAMP dispatch.open (+ emit the id to `id_sink`) → grounding legs →
    dispatch.grounding. Returns (briefing_text, recall_text). Injectable for tests.

    ASSEMBLE (tkt-002/003/004, R1=C) — open path tries budgeted ``drain_fn`` then
    ``ready_fn`` (default assert_ready). Worker recovers remainder offline. Quality > latency:
    open pending after drain still blocks stamp. Inject ``ready_fn=lambda: None`` and
    ``drain_fn=lambda: None`` in hermetic tests that do not exercise Assemble.

    IDENTITY PRECEDES GROUNDING (#62) — the identity is minted, stamped and emitted BEFORE any
    O(store) grounding leg, so a slow/blocking/dark harvest can never delay or swallow the id.
    `id_sink` (main() passes the real stdout captured before its floor-noise redirect) receives
    `DISPATCH_ID=<id>\\n` the instant the stamp is durable. The stamp is IDENTITY-ONLY.

    S5 (grounding iteration) — AFTER the stamp, the floor runs two degrade-dark legs that the
    wake must NEVER raise from (R3.2: grounding annotates, it never gates). `harvest_fn` mines the
    transcript store to currency into `grounding.manifest` rows (real default: harvest.harvest —
    bounded/non-blocking/incremental, #62); the canary step probes the DECLARED interfaces that
    carry a PENDING dry read (`probe_fn`, real default: _default_probe) and appends `canary.result`
    attestations the two-factor fold (B1, eventlog._dry_label) joins. A dead source is an annotated
    dark leg, not a crash. The read-side metrics `harvested` (rows this wake emitted) and
    `ambient_rows` (the ambient read volume in the log) land on a SEPARATE `dispatch.grounding`
    event — never on the identity stamp (they had zero downstream readers there and gated nothing).
    Only after those durable effects, ``enqueue_fn`` schedules sleep-time rationalization and returns;
    its worker is process-owned elsewhere and never executes cognition in this wake process.
    Only a raising SWEEP or BRIEFING aborts before the stamp: a dispatch that could not wake must
    not look woken.

    S2 (E1) — the stamp now carries the dispatch's IDENTITY + SESSION ANCHOR: `dispatch_id`
    (minted here when not handed in; main() mints and prints it machine-readable, because the
    live path is CLI → skill-snippet across processes and an in-process return does not cross),
    `session_id` (Claude session id, `codex:<id>`, or `grok:<GROK_SESSION_ID>` when present, else null —
    never fabricated), and the
    optional DECLARED fields theme/intent/geometry (attribution tier `declared`). The MONOTONIC
    anchor is the dispatch.open event's own `seq` (stamped by append) — S4's harvest maps rows
    by (session anchor, dispatch interval), so no extra cursor is persisted here. Geometry:
    predispatch cannot see its caller (separate process), so it is declared — default `ambient`
    (the heartbeat entry), flipped to `themed` when a theme is declared; an explicit geometry
    always wins.

    UX.W-floor-employment — default `recall_fn` is portfolio-aware when this is an employment
    wake: ``origin == "user_requested"``, geometry ``themed``, or ``employment=True``
    (``--employment``). Ambient heartbeat (beat + ambient, no flag) stays map-blind
    ``compose_recall_brief`` so lazer/delta paths never get the portfolio tail by accident.
    ``compose_portfolio_recall_brief`` already concatenates space-0 + portfolio lanes."""
    if geometry is None:
        geometry = "themed" if theme else "ambient"
    if drain_fn is None:
        import assemble_drain as _assemble_drain
        # R1=C: budgeted open attempt; remainder is worker territory
        drain_fn = lambda: _assemble_drain.drain(log=log, budget=20)  # noqa: E731
    if ready_fn is None:
        import assemble_ready as _assemble_ready
        ready_fn = lambda: _assemble_ready.assert_ready(log=log)  # noqa: E731
    if sweep_fn is None:
        import sweep as _sweep
        sweep_fn = _sweep.run
    if briefing_fn is None:
        import briefing as _briefing
        # o default carrega a perna quente (hot_cutoff = window_start do quente, degrade-dark);
        # um briefing_fn injetado fica intacto — o seam dos testes não muda de shape
        briefing_fn = lambda: _briefing.compose_briefing(hot_cutoff=_hot_cutoff())  # noqa: E731
    if recall_fn is None:
        import recall as _recall
        # employment stamp (UX.W-floor-employment): portfolio on user-facing wakes only
        if (employment or origin == "user_requested" or geometry == "themed"):
            recall_fn = _recall.compose_portfolio_recall_brief
        else:
            recall_fn = _recall.compose_recall_brief
    if harvest_fn is None:
        import harvest as _harvest
        harvest_fn = lambda: _harvest.harvest(log=log)   # noqa: E731 — real default (S5)
    if probe_fn is None:
        probe_fn = _default_probe
    # ASSEMBLE (R1=C): budgeted drain then ready gate — before sweep/stamp.
    drain_fn()
    ready_fn()
    # IDENTITY PRECEDES GROUNDING (#62): only a raising SWEEP or BRIEFING aborts before the stamp
    # (a dispatch that could not wake must not look woken). Everything the identity needs runs
    # FIRST; the O(store) grounding legs run AFTER the id is minted, stamped and emitted, so a
    # slow/blocking/dark harvest can never delay or swallow the id.
    swept = sweep_fn()                      # raises on a missing store (ADR-0015) — no stamp
    briefing_text = briefing_fn()           # raises on a lobotomized identity — no stamp
    if dispatch_id is None:
        dispatch_id = mint_dispatch_id()
    # the stamp is IDENTITY-ONLY now (#62): harvested/ambient_rows move to the dispatch.grounding
    # event below — they had zero downstream readers on the stamp and gated nothing.
    # ticket 05 (hierarquia de ORIGEM): the dispatch DECLARES where it came from —
    # user_requested (first-order signal, o gradiente) or beat (exploração). Default beat:
    # an undeclared origin is never promoted. The artefato reads it back at publish
    # (eventlog.dispatch_origin) and carries it on artefato.published.
    eventlog.dispatch_open({"swept_sessions": swept, "dispatch_id": dispatch_id,
                            "session_id": sessions_mod.current_session_anchor(),
                            "theme": theme, "intent": intent, "geometry": geometry,
                            "origin": origin if origin in eventlog.ORIGINS else "beat"}, log=log)
    # the machine-readable id, the moment the identity is durable — written DIRECTLY to the real
    # stream (bypassing any floor-noise capture), BEFORE the grounding legs print anything.
    if id_sink is not None:
        id_sink.write(f"DISPATCH_ID={dispatch_id}\n")
        id_sink.flush()
    # --- grounding legs (S5), side-effects only, ALL degrade-dark — never gate, never delay id ---
    # voz is a read-model ANNOTATION of the briefing, NOT an identity gate (#62 codex): it runs
    # AFTER the id is stamped+emitted, so neither a raise NOR a HANG in voz can delay or suppress
    # the id. It still augments the RETURNED briefing_text (the stamp is identity-only, untouched).
    try:
        import voz as _voz
        voz_section = _voz.brief(log=log)   # bounded (contagens + top-N); '' sem pendência
        if voz_section:
            briefing_text = f"{briefing_text}\n\n{voz_section}"
    except Exception as e:  # noqa: BLE001 — voz annotates the briefing; it never gates the wake
        print(f"predispatch: voz leg DARK ({type(e).__name__}: {e}) — briefing without voz; "
              "stamp already landed.")
    # harvest leg: mine the transcript store into grounding.manifest rows. A dead harvest is an
    # annotated dark leg, never a crash (the cursor is idempotent, the next wake retries).
    try:
        harvested = harvest_fn()
        if not (isinstance(harvested, int) and not isinstance(harvested, bool)):
            print(f"predispatch: harvest returned non-int {harvested!r} — counted as 0 "
                  "(contract regression, surfaced not swallowed).")
            harvested = 0
    except Exception as e:  # noqa: BLE001 — a dark harvest is honest; the wake still runs
        harvested = 0
        print(f"predispatch: harvest leg DARK ({type(e).__name__}: {e}) — grounding manifest not "
              f"advanced this wake; the next wake retries (cursor idempotent).")
    try:
        recall_text = recall_fn()
    except Exception as e:  # noqa: BLE001 — a dark brief is honest; the wake still ran
        recall_text = (f"# Recall — the memory-salient brief\n\n_Recall leg DARK "
                       f"({type(e).__name__}: {e}) — orient from the briefing; recall on demand "
                       f"(`skills/_shared/memory.md`) when the graph is reachable._\n")
    # canary leg: probe the DECLARED interfaces carrying a pending dry, append the canary.result
    # attestations the two-factor fold joins, and read back the ambient read volume. Wrapped as
    # defense in depth so nothing here reaches a raise (the inner step already catches per-probe).
    try:
        ambient_rows, _canary_note = _run_canary(log, probe_fn)
    except Exception as e:  # noqa: BLE001 — the canary leg NEVER raises into the wake (R3.2)
        ambient_rows = 0
        print(f"predispatch: canary leg DARK ({type(e).__name__}: {e}) — stamp still lands.")
    # the grounding annotation (#62): read-side metrics, AFTER the stamp, never on the identity.
    # Degrade-dark like every grounding leg (#62 codex): a failed annotation must NOT gate a wake
    # whose id already landed — the counts are best-effort telemetry, not part of the identity.
    try:
        eventlog.append("dispatch.grounding", "grounding",
                        {"dispatch_id": dispatch_id, "harvested": harvested,
                         "ambient_rows": ambient_rows}, log=log)
    except Exception as e:  # noqa: BLE001 — the grounding summary never gates a stamped wake
        print(f"predispatch: dispatch.grounding annotation DARK ({type(e).__name__}: {e}) — "
              "id already stamped; counts not recorded this wake.")
    if enqueue_fn is not None or Path(log).resolve() == Path(eventlog.LOG).resolve():
        try:
            if enqueue_fn is None:
                import sweep as _sweep
                enqueue_fn = _sweep.enqueue_rationalization
            if enqueue_fn() is False:
                raise RuntimeError("systemd start returned failure")
        except Exception as e:  # noqa: BLE001 — the log-checkpointed backlog survives enqueue dark
            print(f"predispatch: rationalization enqueue DARK ({type(e).__name__}: {e}) — "
                  "wake already stamped; backlog retained for the next trigger.")
    return briefing_text, recall_text


def _pending_and_ambient(log):
    """Fold the grounding log ONCE for the canary leg → (pending_dry_interfaces, ambient_rows).
    `pending` = the set of (source, interface) whose fold cell still carries a BARE `suspect`
    dry (born 0-hit with NO resolving canary within TTL — the exact rows a fresh canary can
    verify or condemn); a cell already projected verificada/instrumento/overspecified/nao-aplicavel
    is resolved and not re-probed. `ambient_rows` = the total ambient-geometry read volume (R3.1:
    wake health, never a gate). Pure over the log; the caller wraps it degrade-dark."""
    g = eventlog.grounding_at(log=log)
    pending, ambient_rows = set(), 0
    for cell in g.get("cells", {}).values():
        if cell.get("geometry") == "ambient":
            ambient_rows += cell.get("attempts", 0)
        if cell.get("dry", {}).get("suspect"):   # bare suspect = pending (unresolved by a canary)
            src, iface = cell.get("source"), cell.get("interface")
            if isinstance(src, str) and isinstance(iface, str):
                pending.add((src, iface))
    return pending, ambient_rows


def _run_canary(log, probe_fn):
    """The canary battery (S5, design-emissao §2): for the PENDING dries, probe each DECLARED
    interface once and append a `canary.result` the two-factor fold (B1) joins. Returns
    (ambient_rows, note). Never raises — a probe that fails/times out is caught as
    `suspect:instrumento` (the instrument is broken; the world may be non-empty), a probe that
    cannot determine pass/fail is UNKNOWN (None — `hits None ≠ 0` is sacred, S4) and attests
    NOTHING.

    E8 (the Overleaf test): the battery iterates `sources_mod.load_sources()` interfaces, keyed
    by (source, interface) — NO source is ever named here. An interface with `dry_semantics:
    never-dry` is skipped (its risk is confident filler, not drought — the fold labels its 0-hit
    reads `nao-aplicavel`, never `suspect`, so it is not in `pending` anyway; the guard is
    defense in depth). An interface with no declared `canary` mapping cannot be probed."""
    pending, ambient_rows = _pending_and_ambient(log)
    if not pending:
        return ambient_rows, "no pending dries"
    sources, _findings = sources_mod.load_sources()
    probed = fails = unknown = 0
    dark = []
    for s in sources:
        name = s.get("name")
        for iface in s.get("interfaces", []) or []:
            iid = iface.get("interface_id")
            if (name, iid) not in pending:
                continue
            if iface.get("dry_semantics") == "never-dry":
                continue   # never-dry → no canary (fold labels it nao-aplicavel, B1)
            spec = iface.get("canary")
            if not isinstance(spec, dict):
                continue   # no declared canary battery for this interface — cannot probe
            try:
                passed = probe_fn({"source": name, "interface": iid, "via": iface.get("via"),
                                   "canary": spec, "secret_ref": iface.get("secret_ref")})
            except Exception as e:  # noqa: BLE001 — a broken instrument is suspect:instrumento
                passed = False
                dark.append(f"{name}/{iid}({type(e).__name__})")
            if passed is None:
                unknown += 1   # UNKNOWN: hits None ≠ 0 sacred — never fabricate a pass/fail
                continue
            eventlog.append("canary.result", "grounding",
                            {"source": name, "interface": iid, "pass": bool(passed)}, log=log)
            probed += 1
            if not passed:
                fails += 1
    note = f"{probed} probed, {fails} instrument-fail, {unknown} unknown"
    if dark:
        print(f"predispatch: canary leg — {len(dark)} dead source(s) probed → suspect:instrumento "
              f"({', '.join(dark)}); stamp still lands.")
        note += f"; DARK: {', '.join(dark)}"
    return ambient_rows, note


def _secret_value(secret_ref):
    """Resolve a `file.env:KEY` secret_ref → value (an explicit env var wins, then secrets/<file>);
    None when absent/empty. Mirrors llm_routes._secret_value — kept local so the canary probe
    stays self-contained (no cross-tool import for a 10-line stable convention)."""
    if not (isinstance(secret_ref, str) and ":" in secret_ref):
        return None
    fname, key = secret_ref.split(":", 1)
    if os.environ.get(key):
        return os.environ[key]
    f = REPO / "secrets" / fname
    if not f.is_file():
        return None
    for line in f.read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):]
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def _default_probe(spec):
    """The real canary probe (S5): perform the interface's DECLARED canary call and answer
    pass / fail / UNKNOWN. `spec` = {source, interface, via, canary, secret_ref}. Fires the HTTP
    request the `via` declares with the canary's params/query, resolving `secret_ref` for auth
    (Bearer when the via says so, else the x-api-key convention). Returns True on a 2xx (the
    instrument is alive — auth/latency/billing, per each canary's measured pass_when), False on
    any other status. Returns None (UNKNOWN — never a fabricated pass/fail) when it cannot even
    form a request (no URL in the via). RAISES on a network error/timeout — the caller catches it
    as suspect:instrumento (the instrument is unreachable). E8-safe: everything comes from the
    declared interface spec, no source is named here."""
    import json as _json
    import urllib.parse
    import urllib.request
    via = spec.get("via") or ""
    m = re.search(r"https?://\S+", via)
    if not m:
        return None                                   # no endpoint declared → cannot probe
    url = m.group(0).rstrip(").,")
    canary = spec.get("canary") or {}
    params = dict(canary.get("params") or {})
    if canary.get("query"):
        params.setdefault("query", canary["query"])
    before = via[:m.start()].split()
    method = before[-1].upper() if before and re.fullmatch(r"[A-Za-z]+", before[-1]) else "GET"
    key = _secret_value(spec.get("secret_ref"))
    headers = {}
    if key:
        if "Bearer" in via:
            headers["Authorization"] = f"Bearer {key}"
        else:
            headers["x-api-key"] = key
    if method == "POST":
        req = urllib.request.Request(
            url, data=_json.dumps(params).encode(),
            headers={**headers, "Content-Type": "application/json"}, method="POST")
    else:
        if params:
            url = url.split("?", 1)[0] + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:   # raises on network error → caught
        return 200 <= resp.status < 300


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="predispatch — the mechanical entry-driver (ADR-0016); mints the "
                    "dispatch_id and prints it machine-readable (S2, E1)")
    parser.add_argument("--theme", default=None,
                        help="declared theme of this dispatch (tier declared; flips the "
                             "default geometry to themed)")
    parser.add_argument("--intent", default=None,
                        help="declared intent of this dispatch (tier declared)")
    parser.add_argument("--geometry", default=None, choices=("ambient", "themed"),
                        help="explicit geometry (default: ambient, themed when --theme is "
                             "declared — predispatch cannot see its caller, so it is declared)")
    parser.add_argument("--origin", default="beat", choices=eventlog.ORIGINS,
                        help="who asked for this dispatch (ticket 05): user_requested = the "
                             "mentee's live cognition (first-order signal, weighs above beat); "
                             "beat = autonomous exploration (default)")
    parser.add_argument("--employment", action="store_true",
                        help="force portfolio-aware recall (UX.W-floor-employment) even on an "
                             "ambient beat origin — open maps/atividades stamp into the recall brief")
    args = parser.parse_args(argv)
    dispatch_id = mint_dispatch_id()
    # machine-readable FIRST (S2, E1 + gate D2): the skill-snippet reads this exact line off
    # the wake's stdout — but the real floor (sweep/recall degrades) PRINTS warnings of its
    # own, so run()'s stdout is CAPTURED and flushed AFTER the DISPATCH_ID line. The noise is
    # preserved (never swallowed), just ordered. A floor that RAISES before the stamp prints
    # NO DISPATCH_ID (a dispatch that could not wake must not look woken) — the captured
    # output still surfaces for diagnosis before the raise propagates.
    real_out = sys.stdout            # capture BEFORE the redirect — run() writes the id here
    floor_out = io.StringIO()
    try:
        with contextlib.redirect_stdout(floor_out):
            briefing_text, recall_text = run(dispatch_id=dispatch_id, id_sink=real_out,
                                             theme=args.theme, intent=args.intent,
                                             geometry=args.geometry, origin=args.origin,
                                             employment=args.employment)
    except BaseException:
        sys.stdout.write(floor_out.getvalue())
        raise
    sys.stdout.write(floor_out.getvalue())
    # Dual graph entry on employment wakes (operator 2026-07-13): space-0/portfolio recall
    # already landed; append semantic jump seeded by standing objective so wake *uses* cortex
    # embeddings (assemble/project work), not only recency push. Ambient beat stays map-blind
    # and skips this — degrade-dark inside enrich.
    employment_wake = bool(
        args.employment or args.origin == "user_requested" or args.geometry == "themed"
        or (args.geometry is None and args.theme)
    )
    if employment_wake:
        try:
            import recall as _recall
            import eventlog as _eventlog
            recall_text = _recall.enrich_recall_with_objective_semantic(
                recall_text, log=_eventlog.LOG)
        except Exception as e:  # noqa: BLE001 — never gate the wake print
            print(f"predispatch: semantic enrich DARK ({type(e).__name__}: {e})",
                  file=sys.stderr)
    print(briefing_text)
    print("\n\n---\n")
    print(recall_text)


if __name__ == "__main__":
    main()