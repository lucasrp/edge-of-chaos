"""grounding_yield — the yield join + rendered table (Loop R · faceta 2, S7). Genotype tool.

The transparent posterior of the contextual bandit (R4.*): join `fold_grounding` (attempts,
faceta 1) × the reward half (`source.signal`, ADR-0009), rendered as a TABLE — advice in the
briefing/gather, a `/sources` panel, **never a router**. The scar of the ROUTING table (#248,
enforcement→monster) is binding here: this module exports the FOLD and the RENDER and NOTHING
ELSE. There is no `choose_source()`, no argmax, no route — the consumer is always an agent
reading text; the table advises, the agent decides, the manifest records what it actually did
(the deviation from the advice is itself data — natural exploration, for free).

The join, two mechanical hops:

  - **Salto 1 (slug → dispatch)** is already materialized by S2 (E1/E1b): the `artefato.published`
    payload carries the proof-bound `dispatch_id`. This fold just CONSUMES it. A legacy publish
    with no `dispatch_id` (pre-S2) is reconstructed tolerantly by seq interval (the max
    `dispatch.open` seq below the publish). An unconsumed `dispatch.open` (aborted beat) → the
    `unconsumed` stratum (visible, out of learning — crash ≠ bad source, R4.2).

  - **Salto 2 (ref → attempt)**. The cited `ref` (source.signal) is mapped to a source by its
    HOST through the SAME `agent.yaml sources[].via` seam faceta 1's recognizers derive from
    (`harvest.build_recognizers`) — after DECLARED URL normalization (scheme+host lowercased,
    default port + trailing slash + tracking params dropped), NEVER fuzzy (a normalized miss is
    an orphan, never an invented match). Within the cited artefato's dispatch, the ladder — with
    the tier recorded:

      | tier      | rule                                                       | feeds cell score? |
      |-----------|------------------------------------------------------------|-------------------|
      | exact     | host→source S resolves to EXACTLY ONE scoring cell in the dispatch | yes — that cell |
      | coarse    | host→source S but no per-cell attempt to pin (0 cells in D) | no — source marginal only |
      | ambiguous | host→source S maps to 2+ scoring cells in the dispatch      | no — source marginal only |
      | orphan    | host maps to no declared source (incl recall/self cites)   | no — counted, visible |

    NOTE (realizable form): the design's exact tier reads `ref ∈ retrieval.documents of one row`
    — the per-document hit list is the OTel/OpenInference projection (R2.1), explicitly DEFERRED
    (out of plan). Manifest rows carry a hit COUNT, not the returned document URLs. So exact is
    realized as host→source + dispatch-cell-uniqueness (unambiguous attribution within the
    dispatch) — the SPIRIT preserved (per-cell credit only when unambiguous), the tier names and
    the feeds-score column intact. When R2.1's doc-lists land, exact can sharpen to per-document
    without changing the surfaces.

Cell key = (intent, source, interface, lens, geometry). `intent` (mechanical) = the dispatch's
declared intent (dispatch.open `intent`), overridden-onto by the consuming artefato's `skill`
when no declared intent — the row's own attribution intent is the last resort. `geometry:ambient`
(wake/delta) has NO reward channel (it never publishes) → its cells render HEALTH only
(attempts/hits/dry), never a score.

Graduated reward (PURPLE — relevance ≠ utility), three tiers never flattened into a binary:
  - cited-with-score → r = similarity (revealed use × measured relevance — the strong signal);
  - cited-WITHOUT-score → `similarity == 0.0` from a no-embedder publisher (publisher.py emits
    0.0 when embed_fn is None) is an INSTRUMENT ARTIFACT, not a measure: it counts in `cited`
    but is EXCLUDED from mean_sim/score (else the no-embedder poisons the mean downward);
  - hit-without-citation → r = 0 in the score (recovered-not-used is low utility), but the `hits`
    column stays as a diagnostic.
"""
import html as _html
from statistics import fmean

import eventlog
import sources as sources_mod


# --- policy as DATA (design §3) — a posterior-as-table, NOT Thompson sampling -------------------
YIELD_POLICY = {
    "min_attempts": 5,      # below: the cell renders "EXPLORE (n<5)", never a score. The
                            # exploration bonus is a DECLARED LABEL, not a hidden UCB term —
                            # transparency > optimal regret (trade-off assumed). With the 3h
                            # heartbeat a hot cell crosses in ~1 day; a cold one stays EXPLORE
                            # (which IS the advice).
    "shrink_pseudo_n": 3,   # empirical-Bayes: score = (n·mean_sim + k·global_mean)/(n+k) — a
                            # young cell regresses to the global mean, never cravs 0.9 with n=2.
    "cite_prior": (1, 2),   # Beta(1,2) on the citation rate: mildly pessimistic — a citation is
                            # rare by construction; a uniform prior would inflate a fresh arm.
}

# the reward channel joins over these four event families; canary.result rides along for the
# instrument-health (dry taxonomy) the panel renders (same as fold_grounding).
YIELD_FOLD_TYPES = ["grounding.manifest", "canary.result", "dispatch.open",
                    "artefato.published", "source.signal"]

# DECLARED URL normalization (Salto 2) — never fuzzy. Tracking params are dropped so
# `?utm_source=x` and the bare URL are the SAME ref; scheme+host are lowercased; a default port
# and a single trailing slash are stripped. Anything else stays byte-exact.
_TRACKING_PARAMS = frozenset((
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "ref", "ref_src", "s", "t",
))
_DEFAULT_PORTS = {"http": "80", "https": "443"}


def _split_url(ref):
    """(scheme, host, rest) of a ref string, or None when it is not a URL — a recall/self cite
    (`artefato:slug`, a bare commit sha) has no host and folds to orphan. Pure, tolerant."""
    if not isinstance(ref, str) or "://" not in ref:
        return None
    scheme, _, tail = ref.partition("://")
    host, sep, rest = tail.partition("/")
    return scheme.lower(), host.lower(), (sep + rest if sep else "")


def normalize_ref(ref):
    """The DECLARED normalization of a cited ref (Salto 2): lowercase scheme+host, drop a default
    port and a single trailing slash, drop tracking query params. Order-preserving on the
    surviving params. A non-URL ref returns itself (it will orphan). NEVER fuzzy."""
    parts = _split_url(ref)
    if parts is None:
        return ref
    scheme, host, rest = parts
    if ":" in host:
        h, _, port = host.partition(":")
        if _DEFAULT_PORTS.get(scheme) == port:
            host = h
    path, q, query = rest.partition("?")
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    if q:
        kept = [kv for kv in query.split("&")
                if kv and kv.split("=", 1)[0] not in _TRACKING_PARAMS]
        rest = path + ("?" + "&".join(kept) if kept else "")
    else:
        rest = path
    return f"{scheme}://{host}{rest}"


def _host_of(ref):
    """The lowercased host of a ref, or None (recall/self cite → orphan)."""
    parts = _split_url(ref)
    return parts[1].split(":", 1)[0] if parts else None


def host_source_map(sources=None):
    """host → source, DERIVED from `agent.yaml sources[].via` (the SAME seam faceta 1's
    recognizers use — `harvest.build_recognizers`). E8-safe: no source is named here; a
    never-seen declared source (Overleaf) maps automatically. Imported lazily so the pure fold
    stays offline-testable (a test injects the map)."""
    import harvest  # lazy — keeps fold_grounding_yield import-clean for offline tests
    recs = harvest.build_recognizers(sources)
    return {r["host"]: r["source"] for r in recs.get("url", []) if r.get("host") and r.get("source")}


# --- the fold ----------------------------------------------------------------------------------

_SUSPECT = eventlog._GROUNDING_SUSPECT_LABELS
_EXCLUDED_ATTR = eventlog._GROUNDING_EXCLUDED_ATTRIBUTION


def _dim(payload, key):
    v = payload.get(key)
    return v if isinstance(v, str) else None


def _sim(payload):
    """The cited similarity as a float, or None (unscorable → treated like the no-embedder 0.0)."""
    s = payload.get("similarity")
    if isinstance(s, bool) or not isinstance(s, (int, float)):
        return None
    return float(s)


def _scorable(sim):
    """Does a cited similarity COUNT in mean_sim? §2 excludes EXACTLY the no-embedder 0.0 (an
    instrument artifact, not a measure) and None. A GENUINE negative similarity is a real
    dis-similarity signal and MUST count. A NaN is not a measure either (`sim != sim`) — it is
    routed to the excluded pool so it never reaches fmean and never crashes."""
    return sim is not None and sim == sim and sim != 0.0


def _winners_and_canaries(events):
    """The WINNING (event, payload) manifest rows + interpreted canary attestations — delegates to
    `eventlog.winning_manifest_rows` (the ONE reader), so faceta 1's interpretation cannot drift."""
    rows, canaries, _ = eventlog.winning_manifest_rows(events)
    return rows, canaries


def _dispatch_context(events):
    """The two hops' dispatch scaffolding from the log: declared intents, publish→dispatch
    resolution (S2 dispatch_id, legacy interval fallback), the consuming skill, and the
    unconsumed (aborted-beat) stratum."""
    opens = []            # (seq, dispatch_id) in seq order
    open_ids = set()
    declared_intent = {}  # dispatch_id -> declared intent
    for e in events:
        if e.get("type") != "dispatch.open":
            continue
        p = e.get("payload")
        if not isinstance(p, dict):
            continue
        did = p.get("dispatch_id")
        if isinstance(did, str) and did.strip():
            open_ids.add(did)
            opens.append((eventlog._event_seq(e), did))
            it = p.get("intent")
            if isinstance(it, str) and it.strip():
                declared_intent[did] = it.strip()
    opens.sort()
    pub_dispatch = {}     # slug -> resolved dispatch_id
    consumed_ids = set()
    skill_of = {}         # dispatch_id -> the consuming artefato's skill
    for e in events:
        if e.get("type") != "artefato.published":
            continue
        p = e.get("payload")
        if not isinstance(p, dict):
            continue
        slug = p.get("slug")
        if not isinstance(slug, str):
            continue
        did = p.get("dispatch_id")
        if not (isinstance(did, str) and did.strip()):
            # legacy tolerance (§1): reconstruct by seq interval — the newest open below the publish
            pub_seq = eventlog._event_seq(e)
            below = [d for s, d in opens if s < pub_seq]
            did = below[-1] if below else None
        if did:
            consumed_ids.add(did)
            pub_dispatch[slug] = did
            sk = p.get("skill")
            if isinstance(sk, str) and sk.strip():
                skill_of[did] = sk.strip()
    unconsumed = len(open_ids - consumed_ids)

    def intent_of(did):
        return declared_intent.get(did) or skill_of.get(did)
    return pub_dispatch, intent_of, unconsumed


def _empty_cell(key):
    intent, source, interface, lens, geometry = key
    return {"intent": intent, "source": source, "interface": interface, "lens": lens,
            "geometry": geometry, "attempts": 0, "hits": None, "hits_unknown": 0, "dry": {},
            "excluded": 0, "cited": 0, "rewards": [], "mean_sim": None, "score": None,
            "cite_rate": None, "_scoring_attempts": 0, "_scored": [], "_noembed": 0,
            "canary": None}


def fold_grounding_yield(events, hsmap=None, policy=None):
    """Pure, tolerant fold of `[grounding.manifest, canary.result, dispatch.open,
    artefato.published, source.signal]` → the yield posterior. Same house idiom as fold_direction:
    a non-dict payload is skipped, never crashed. `hsmap` is host→source (agent.yaml via-seam);
    None defers to `host_source_map()` (the cursor supplies it — kept out of the pure core so a
    test injects it offline).

    Returns `{cells, marginals, excluded, orphans, unconsumed}` (design §2). Cell key =
    (intent, source, interface, lens, geometry); marginal keyed by source (the roster floor +
    backoff granularity + the footer's ambiguous/coarse tallies)."""
    policy = policy or YIELD_POLICY
    if hsmap is None:
        hsmap = host_source_map()
    min_attempts = policy["min_attempts"]
    k = policy["shrink_pseudo_n"]
    a_prior, b_prior = policy["cite_prior"]

    winners, canaries = _winners_and_canaries(events)
    pub_dispatch, intent_of, unconsumed = _dispatch_context(events)

    cells = {}
    excluded = {"seca-suspeita": 0}
    excluded.update({f"attribution:{a}": 0 for a in _EXCLUDED_ATTR})
    # per dispatch: source -> the set of SCORING cell keys that have an attempt in that dispatch
    in_dispatch = {}   # dispatch_id -> {source -> set(cell_key)}

    for e, p in winners:
        did = p.get("dispatch_id")
        did = did if isinstance(did, str) and did.strip() else None
        source, interface, lens, geometry = (_dim(p, "source"), _dim(p, "interface"),
                                             _dim(p, "lens"), _dim(p, "geometry"))
        intent = intent_of(did) or _dim(p, "intent")
        key = (intent, source, interface, lens, geometry)
        cell = cells.setdefault(key, _empty_cell(key))
        cell["attempts"] += 1
        hits = p.get("hits")
        if isinstance(hits, bool) or not isinstance(hits, (int, float)):
            cell["hits_unknown"] += 1
            hits = None
        else:
            cell["hits"] = (cell["hits"] or 0) + hits
        label = eventlog._dry_label(e, p, hits, source, interface, canaries)
        is_suspect = False
        if label is not None:
            cell["dry"][label] = cell["dry"].get(label, 0) + 1
            if label in _SUSPECT:
                excluded["seca-suspeita"] += 1
                is_suspect = True
        attr = p.get("attribution")
        excluded_attr = attr in _EXCLUDED_ATTR
        if excluded_attr:
            excluded[f"attribution:{attr}"] += 1
        # a row is scoring-eligible iff not seca-suspeita, not inferred/unknown attribution,
        # and not ambient geometry (ambient has no reward channel — health only).
        if is_suspect or excluded_attr or geometry == "ambient":
            cell["excluded"] += (1 if (is_suspect or excluded_attr) else 0)
        else:
            cell["_scoring_attempts"] += 1
            if did is not None and source is not None:
                in_dispatch.setdefault(did, {}).setdefault(source, set()).add(key)
        if cell["canary"] is None:
            cell["canary"] = _canary_state(source, interface, canaries)

    # per-source marginal accumulators for coarse/ambiguous cites (cell cites feed the marginal too)
    marginal_extra = {}   # source -> {"scored": [...], "noembed": n, "coarse": n, "ambiguous": n}
    orphans = 0

    for e in events:
        if e.get("type") != "source.signal":
            continue
        p = e.get("payload")
        if not isinstance(p, dict):
            continue
        slug = p.get("slug")
        did = pub_dispatch.get(slug) if isinstance(slug, str) else None
        if did is None:
            orphans += 1     # a cite from an artefato that maps into no dispatch — visible, unscored
            continue
        host = _host_of(p.get("ref"))
        source = hsmap.get(host) if host else None
        if source is None:
            orphans += 1     # host maps to no declared source (recall/self cite, or unknown host)
            continue
        keys = in_dispatch.get(did, {}).get(source, set())
        sim = _sim(p)
        me = marginal_extra.setdefault(source, {"scored": [], "noembed": 0,
                                                "coarse": 0, "ambiguous": 0})
        if len(keys) == 1:
            cell = cells[next(iter(keys))]
            if _scorable(sim):
                cell["_scored"].append(sim)
            else:
                cell["_noembed"] += 1     # cited-without-score (no-embedder 0.0 / NaN) — off mean
        elif len(keys) >= 2:
            me["ambiguous"] += 1          # 2+ cells — per-cell credit would be fabricated
            (me["scored"].append(sim) if _scorable(sim) else _incr(me, "noembed"))
        else:
            me["coarse"] += 1             # host maps to S but no per-cell attempt to pin
            (me["scored"].append(sim) if _scorable(sim) else _incr(me, "noembed"))

    # finalize cells: rewards = scored sims + a 0 per uncited scoring attempt (revealed utility);
    # the no-embedder cites are counted in `cited` but left OUT of both numerator and the zero pool.
    all_rewards = []
    for cell in cells.values():
        scored = cell["_scored"]
        noembed = cell["_noembed"]
        cell["cited"] = len(scored) + noembed
        if cell["geometry"] == "ambient":
            continue   # ambient: health only, no reward channel
        zeros = max(0, cell["_scoring_attempts"] - cell["cited"])
        cell["rewards"] = list(scored) + [0.0] * zeros
        cell["mean_sim"] = fmean(cell["rewards"]) if cell["rewards"] else None
        all_rewards.extend(cell["rewards"])
    global_mean = fmean(all_rewards) if all_rewards else 0.0

    for cell in cells.values():
        if cell["geometry"] == "ambient":
            continue
        # citation-rate posterior — Beta(a,b) prior (mildly pessimistic)
        denom = cell["_scoring_attempts"] + a_prior + b_prior
        cell["cite_rate"] = (cell["cited"] + a_prior) / denom if denom else None
        if cell["attempts"] < min_attempts:
            cell["score"] = None          # EXPLORE — a declared label, never a fabricated score
            continue
        n = len(cell["rewards"])
        m = cell["mean_sim"] if cell["mean_sim"] is not None else 0.0
        cell["score"] = (n * m + k * global_mean) / (n + k) if (n + k) else None

    marginals = _build_marginals(cells, marginal_extra, global_mean, policy)
    # strip the private accumulators before returning (keep the surface clean)
    for cell in cells.values():
        for pk in ("_scoring_attempts", "_scored", "_noembed"):
            cell.pop(pk, None)
    return {"cells": cells, "marginals": marginals, "excluded": excluded,
            "orphans": orphans, "unconsumed": unconsumed}


def _incr(d, key):
    d[key] += 1


def _canary_state(source, interface, canaries):
    """The latest canary attestation for a source×interface → 'pass'|'fail'|None (no probe yet)."""
    if not (isinstance(source, str) and isinstance(interface, str)):
        return None
    joins = [c for c in canaries if c["source"] == source and c["interface"] == interface]
    if not joins:
        return None
    latest = max(joins, key=lambda c: c["seq"])
    return "pass" if latest["passed"] else "fail"


def _build_marginals(cells, marginal_extra, global_mean, policy):
    """Per-source marginal (the roster floor + backoff granularity, design §2/§4). Aggregates each
    source's cell rewards + its coarse/ambiguous cite sims; the score uses the same empirical-Bayes
    shrink so a source with no cell above min_attempts still shows a floor."""
    k = policy["shrink_pseudo_n"]
    a_prior, b_prior = policy["cite_prior"]
    by_source = {}
    for cell in cells.values():
        src = cell["source"]
        if cell["geometry"] == "ambient":
            continue
        m = by_source.setdefault(src, {"source": src, "attempts": 0, "cited": 0,
                                       "rewards": [], "coarse": 0, "ambiguous": 0,
                                       "mean_sim": None, "score": None, "cite_rate": None})
        m["attempts"] += cell["attempts"]
        m["cited"] += cell["cited"]
        m["rewards"].extend(cell["rewards"])
    for src, extra in marginal_extra.items():
        m = by_source.setdefault(src, {"source": src, "attempts": 0, "cited": 0,
                                       "rewards": [], "coarse": 0, "ambiguous": 0,
                                       "mean_sim": None, "score": None, "cite_rate": None})
        m["rewards"].extend(extra["scored"])
        m["cited"] += extra["coarse"] + extra["ambiguous"]
        m["coarse"] += extra["coarse"]
        m["ambiguous"] += extra["ambiguous"]
    for m in by_source.values():
        m["mean_sim"] = fmean(m["rewards"]) if m["rewards"] else None
        n = len(m["rewards"])
        mean = m["mean_sim"] if m["mean_sim"] is not None else 0.0
        m["score"] = (n * mean + k * global_mean) / (n + k) if (n + k) else None
        denom = m["attempts"] + a_prior + b_prior
        m["cite_rate"] = (m["cited"] + a_prior) / denom if denom else None
    return by_source


def grounding_yield_at(seq=None, ts=None, log=eventlog.LOG, hsmap=None):
    """Fold the yield posterior up to a cursor (design §2). Pure replay reconstructs that past
    posterior — strategic versioning, as `grounding_at`/`direction_at`. Empty log → the empty
    shape. `hsmap` defaults to the live agent.yaml via-seam (E8: the roster is data)."""
    evs = eventlog.read(types=YIELD_FOLD_TYPES, until_seq=seq, until_ts=ts, log=log)
    if hsmap is None:
        hsmap = host_source_map()
    return fold_grounding_yield(evs, hsmap=hsmap)


# --- render surface 1: the briefing advisory block (≤6 lines, never blank) ---------------------

def _seed_lines(roadmap_text, limit):
    """The SEED rows from the Source roadmap (provenance `seed:…`) — prose, NEVER pseudo-events,
    NEVER folded (ADR-0006: seeding a count would fabricate the log). Rendered as the never-blank
    floor while real cells are below min_attempts, replaced cell-by-cell as measures arrive."""
    parsed = sources_mod.parse_roadmap(roadmap_text)
    lines = []
    for src, entry in parsed.items():
        for note in entry.get("yield_notes", []):
            if str(note.get("provenance", "")).startswith("seed:"):
                lines.append(f"- {src}: {note['text']} _(seed — prose, not measured)_")
                if len(lines) >= limit:
                    return lines
    return lines


def briefing_yield_block(log=eventlog.LOG, seq=None, ts=None, roadmap=sources_mod.ROADMAP,
                         hsmap=None, policy=None):
    """The ≤6-line advisory block for `_section_sources` (design §4). Tone of advice:
    `- research → exa/search-deep: util 0.62 (n=9, cited 5×)` · `- discovery → x: EXPLORE (n=2<5)`.
    NEVER-BLANK floor (§5): with no cell crossing min_attempts yet, the SEED rows from the roadmap
    fill in (marked prose, never events); real advisory lines replace them cell-by-cell as cells
    cross min_attempts. Returns the markdown body (a heading + up to 6 lines)."""
    policy = policy or YIELD_POLICY
    y = grounding_yield_at(seq=seq, ts=ts, log=log, hsmap=hsmap)
    min_attempts = policy["min_attempts"]
    crossed, seen_sources = [], set()
    scoring = sorted(
        (c for c in y["cells"].values() if c["geometry"] != "ambient" and c["score"] is not None),
        key=lambda c: c["score"], reverse=True)
    for c in scoring:
        crossed.append(
            f"- {c['intent'] or '—'} → {c['source']}/{c['interface']}: "
            f"util {c['score']:.2f} (n={c['attempts']}, cited {c['cited']}×)")
        seen_sources.add(c["source"])
        if len(crossed) >= 6:
            break
    lines = list(crossed)
    if len(lines) < 6:
        # EXPLORE cells (below min_attempts): the cell's own EXPLORE label stays honest (the
        # specific cell is still sparse), but the advice BACKS OFF to the source MARGINAL as a
        # floor rather than going silent (design §2 chain: cell-score → source-marginal → seed →
        # never-blank). A source with no populated marginal (mean_sim is None — nothing measured)
        # emits no bare line; it falls through to the seed roster below. A source-less cell is
        # skipped (no `→ None`, no source-level advice to give).
        marginals = y["marginals"]
        for c in sorted((c for c in y["cells"].values()
                         if c["geometry"] != "ambient" and c["score"] is None
                         and c["source"] is not None and c["source"] not in seen_sources),
                        key=lambda c: -c["attempts"]):
            m = marginals.get(c["source"])
            if not (m and m["mean_sim"] is not None):
                continue   # no source-level floor either → the seed roster covers it (§5)
            lines.append(
                f"- {c['intent'] or '—'} → {c['source']}/{c['interface']}: "
                f"EXPLORE (n={c['attempts']}<{min_attempts}) — "
                f"fonte: util {m['score']:.2f} (n={m['attempts']})")
            seen_sources.add(c["source"])
            if len(lines) >= 6:
                break
    if not lines:
        try:
            lines = _seed_lines(_read_text(roadmap), 6)
        except OSError:
            lines = []
    body = "\n".join(lines) if lines else "_no yield yet (no manifest, no seed rows)._"
    return "**Yield — advisory (revealed utility per source×interface):**\n" + body


def _read_text(path):
    from pathlib import Path
    return Path(path).read_text()


# --- render surface 2: the /sources panel (observe rung — a table, never a router) -------------

def _fmt(x, nd=2):
    return f"{x:.{nd}f}" if isinstance(x, (int, float)) else "—"


def _panel_rows(cells, declared):
    """Aggregate the (intent,source,interface,lens,geometry) cells to one row per
    source×interface (the panel's grain, design §4), then UNION with the DECLARED roster so a
    source×interface with no manifest renders as a visible DEAD LEG (E8: the roster is data —
    a never-seen declared source appears with zero code change)."""
    agg = {}
    for c in cells.values():
        sk = (c["source"], c["interface"])
        r = agg.setdefault(sk, {"source": c["source"], "interface": c["interface"],
                                "attempts": 0, "hits": None, "hits_unknown": 0, "cited": 0,
                                "dry": {}, "rewards": [], "score": None, "canary": None,
                                "dead_leg": False})
        r["attempts"] += c["attempts"]
        if c["hits"] is not None:
            r["hits"] = (r["hits"] or 0) + c["hits"]
        r["hits_unknown"] += c["hits_unknown"]
        r["cited"] += c["cited"]
        for lbl, n in c["dry"].items():
            r["dry"][lbl] = r["dry"].get(lbl, 0) + n
        r["rewards"].extend(c["rewards"])
        if c["canary"] and r["canary"] is None:
            r["canary"] = c["canary"]
        if c["score"] is not None:
            r["score"] = c["score"] if r["score"] is None else max(r["score"], c["score"])
    for src, iface, installed in declared:
        sk = (src, iface)
        if sk not in agg:
            agg[sk] = {"source": src, "interface": iface, "attempts": 0, "hits": None,
                       "hits_unknown": 0, "cited": 0, "dry": {}, "rewards": [], "score": None,
                       "canary": None, "dead_leg": True, "installed": installed}
        else:
            agg[sk]["installed"] = installed
    for r in agg.values():
        r.setdefault("dead_leg", r["attempts"] == 0)
        r.setdefault("installed", True)
        r["mean_sim"] = fmean(r["rewards"]) if r["rewards"] else None
    return sorted(agg.values(), key=lambda r: (r["source"] or "", r["interface"] or ""))


def declared_interfaces(sources=None):
    """The declared source×interface roster from agent.yaml (E8: the panel iterates THIS, never a
    fixed list) → list of (source, interface_id, installed). A dead-leg (installed:false) key is
    kept — it is a VISIBLE dead leg, not a silent drop."""
    if sources is None:
        sources, _ = sources_mod.load_sources()
    out = []
    for s in sources or []:
        for iface in s.get("interfaces", []) or []:
            out.append((s.get("name"), iface.get("interface_id"), iface.get("installed", True)))
    return out


def render_sources_panel(yield_result, declared):
    """The `/sources` panel HTML fragment (design §4): one row per source×interface with
    tentativas · hits · citadas · mean sim · score · secas(by tier) · excluídas(by reason) ·
    canário · dead-leg; the footer carries orphans/ambiguous/coarse + unconsumed. A thin adapter
    (blog/server.py) wraps this in the page shell — the observe rung. No argmax, no router."""
    rows = _panel_rows(yield_result["cells"], declared)
    body = []
    for r in rows:
        dry = ", ".join(f"{_html.escape(k)}:{v}" for k, v in sorted(r["dry"].items())) or "—"
        hits = "—" if r["hits"] is None else str(r["hits"])
        if r["hits_unknown"]:
            hits += f" (+{r['hits_unknown']}?)"
        score = "EXPLORE" if (r["score"] is None and not r["dead_leg"]) else _fmt(r["score"])
        canary = r["canary"] or "—"
        leg = ' class="dead-leg"' if r["dead_leg"] else ""
        note = " — DEAD LEG (declared, no manifest yet)" if r["dead_leg"] else ""
        if r["dead_leg"] and not r.get("installed", True):
            note = " — DEAD LEG (declared WITHOUT key)"
        body.append(
            f'<tr{leg}><td>{_html.escape(str(r["source"]))}</td>'
            f'<td>{_html.escape(str(r["interface"]))}{note}</td>'
            f'<td>{r["attempts"]}</td><td>{hits}</td><td>{r["cited"]}</td>'
            f'<td>{_fmt(r["mean_sim"])}</td><td>{score}</td>'
            f'<td>{_html.escape(dry)}</td><td>{_html.escape(canary)}</td></tr>')
    excl = ", ".join(f"{_html.escape(k)}:{v}" for k, v in sorted(yield_result["excluded"].items()))
    amb = sum(m.get("ambiguous", 0) for m in yield_result["marginals"].values())
    coarse = sum(m.get("coarse", 0) for m in yield_result["marginals"].values())
    footer = (f'<p class="meta">excluídas (fora do aprendizado, por motivo): {_html.escape(excl)} · '
              f'orphans: {yield_result["orphans"]} · ambiguous: {amb} · coarse: {coarse} · '
              f'unconsumed (beats abortados): {yield_result["unconsumed"]}</p>')
    table = (
        '<table class="sources-yield"><thead><tr>'
        '<th>source</th><th>interface</th><th>tentativas</th><th>hits</th><th>citadas</th>'
        '<th>mean sim</th><th>score</th><th>secas (por tier)</th><th>canário</th>'
        '</tr></thead><tbody>' + "".join(body) + '</tbody></table>')
    return table + footer


def sources_panel_html(log=eventlog.LOG, seq=None, ts=None, sources=None, hsmap=None):
    """Convenience seam for the `/sources` route: fold + roster + render in one call so the
    server route stays a THIN adapter (the /llm sibling pattern)."""
    if sources is None:
        sources, _ = sources_mod.load_sources()
    if hsmap is None:
        hsmap = host_source_map(sources)   # E8: the same declared roster drives the host→source join
    y = grounding_yield_at(seq=seq, ts=ts, log=log, hsmap=hsmap)
    return render_sources_panel(y, declared_interfaces(sources))
