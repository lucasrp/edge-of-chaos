"""cortex_usage — the Usage signal (ratified glossary term): the IMPLICIT, NON-AUTHORITATIVE record of
which Cortex nodes the edge READ while working, behind the EDGE_CORTEX_USAGE A/B toggle (REQUISITES
F7/N3/N4, R5). Genotype tool.

THE GOVERNANCE INVARIANT (N4): this store is NOT self-state.
  - It is appended to `state/cortex/usage.jsonl` — a SEPARATE store, NOT the Tier-0 `state/events/
    log.jsonl`. The eventlog never reads it; no fold reads it; no Tier-0 event is emitted.
  - It drives an EPHEMERAL READ-TIME re-rank ONLY (recency+frequency) — never a graph write, never a
    recall-rank fold. ADR-0006 ("the log is truth") holds; the read door can never reinforce the
    authoritative self. It is reconcilable-to-zero against the immutable log (the SSGM dual-track).

Distinct from VALUE feedback (cites/distills at close) and CORRECTION (node-targeted Voz / Earmarked) —
both curated and authoritative. This is neither: it is implicit usage telemetry.

THE A/B TREATMENT (F7/N3):
  - OFF (default): no write, no re-rank — a clean side-effect-free baseline.
  - ON: append the telemetry line AND re-order the SAME result set by a usage score over telemetry
    written BEFORE the call (the current write never affects its own ordering — no self-referential
    read). Cold store → ON == OFF.
"""
import json
import math
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

# R5 — recency is FIRST-CLASS (Designing Agentic Memory 2026): the usage score is recency+frequency,
# not a raw count. Each prior use contributes exp(-age / HALF_LIFE * ln2), so a stale-hot ref decays
# below a fresh-warm one (off-truth-path decay is allowed — §5 REJECT-decay's carve-out). The half-life
# is a tuning knob (open question, R5): a 7-day default makes recency dominate (a month-old hot ref
# decays ~16x and falls below a few fresh uses), measured under A/B. EDGE_CORTEX_USAGE_HALFLIFE_S tunes it.
USAGE_HALFLIFE_DEFAULT_S = 7 * 24 * 3600

# C1 / off-truth-path bound (codex Slice-3 [medium]): the re-rank reads only the most-recent
# USAGE_READ_CAP lines (the recency-weighted tail), so a large append-only store NEVER becomes the
# read door's blocking dependency — telemetry must never block the beat. A stale tail is fine: the
# half-life decays old refs to near zero anyway, so the tail carries the live signal.
USAGE_READ_CAP = 5000

# Byte budget for the backward tail scan (codex Slice-3 [high]): the scan stops at this many bytes
# even if it has not yet seen USAGE_READ_CAP newlines — so a corrupt/huge single line can NEVER be
# read into memory wholesale and make the read door a blocking/OOM dependency (C1).
USAGE_READ_BYTES = 8 * 1024 * 1024

# Cap refs written per telemetry record (codex Slice-3 [high]): a legitimate write can never create a
# pathological multi-megabyte line. A surf/search result set is small; this is a generous ceiling.
USAGE_MAX_REFS = 256

# A per-ref length cap (codex Slice-3 [medium]): a legitimate ref is a slug/uuid — bounded. A single
# pathologically long string ref is dropped at write time, so a write can never create a huge line.
USAGE_MAX_REF_LEN = 512

# Clock-skew tolerance (codex Slice-3 [medium]): a usage `ts` beyond now+skew is corrupt/clock-skewed
# and scored as fresh under a naive max(0, now-ts) clamp — so it is SKIPPED, never lifted as live signal.
USAGE_FUTURE_SKEW_S = 300


def _halflife_s():
    """The recency half-life (seconds), parsed LAZILY and HARDENED (codex Slice-3 [medium]): a
    non-numeric / zero / negative / non-finite value can neither crash the import nor invert recency —
    it falls back to the safe positive default. A negative half-life would make OLDER telemetry score
    HIGHER (R5 inverted), so it is rejected, not honored."""
    raw = os.environ.get("EDGE_CORTEX_USAGE_HALFLIFE_S")
    if raw is None:
        return float(USAGE_HALFLIFE_DEFAULT_S)
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return float(USAGE_HALFLIFE_DEFAULT_S)
    if not math.isfinite(v) or v <= 0:
        return float(USAGE_HALFLIFE_DEFAULT_S)
    return v


def enabled():
    """The A/B toggle (F7): EDGE_CORTEX_USAGE in {on,1,true,yes} → ON; anything else (incl. unset) → OFF
    (the default is a clean, side-effect-free baseline)."""
    return (os.environ.get("EDGE_CORTEX_USAGE") or "").strip().lower() in {"on", "1", "true", "yes"}


def usage_path():
    """The usage store path — EDGE_CORTEX_USAGE_PATH (injectable for tests) → state/cortex/usage.jsonl.
    A SEPARATE, NON-AUTHORITATIVE store, NEVER the Tier-0 eventlog (N4).

    HARDENED (codex Slice-3 [high]/[medium]): the override is VALIDATED, not trusted verbatim — a path
    resolving with a `state/events` segment pair (the Tier-0 log dir, of THIS or ANY install) OR
    pointing at the configured authoritative log is REFUSED with a raise, so a mis-set env can never
    append non-event records into an authoritative log and corrupt replay. The VALIDATED resolved path
    is returned (validate-then-write the same path), fail closed, never silent."""
    raw = os.environ.get("EDGE_CORTEX_USAGE_PATH")
    import _identity as _id_state
    p = Path(raw) if raw else (_id_state.runtime_root() / "state" / "cortex" / "usage.jsonl")
    resolved = p.resolve()
    # reject ANY state/events target (this repo OR a foreign install), by segment pair — not a single
    # hardcoded directory. Also reject the configured Tier-0 log itself if it is resolvable.
    parts = resolved.parts
    if any(parts[i] == "state" and parts[i + 1] == "events" for i in range(len(parts) - 1)):
        raise ValueError(
            f"refusing a usage store under a state/events dir ({resolved}) — the Usage signal is "
            "off-truth-path (N4); it must NEVER write into the Tier-0 event log")
    try:
        import eventlog
        log = Path(eventlog.LOG).resolve()
        # pathname compare AND inode compare (codex Slice-3 [high]): a hard link OUTSIDE state/events
        # pointing at the same inode as the Tier-0 log resolves to a DIFFERENT pathname but the SAME
        # file — os.path.samefile catches it. Both checks, so neither spelling nor inode aliasing slips.
        if resolved == log or (resolved.exists() and log.exists()
                               and os.path.samefile(str(resolved), str(log))):
            raise ValueError(f"refusing the authoritative event log as a usage store ({resolved})")
    except ValueError:
        raise
    except Exception:  # noqa: BLE001 — eventlog unavailable: the segment guard above still holds
        pass
    return resolved


def _read_tail_lines(path, n):
    """Read the LAST `n` newline-delimited lines of `path` WITHOUT loading the whole file (codex
    Slice-3 [high]): seek to the end and read fixed-size chunks BACKWARDS until n records (or BOF) are
    collected — so a large append-only store never forces an unbounded read/allocation on the read
    door. Returns the tail lines (oldest-first), stripped of the trailing newline. [] on any error."""
    chunk = 64 * 1024
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            data = b""
            pos = f.tell()
            # read backwards until we have > n newlines, hit BOF, OR exhaust the byte budget — the
            # byte budget is the hard stop, so a pathological newline-free line never loads whole.
            while pos > 0 and data.count(b"\n") <= n and len(data) < USAGE_READ_BYTES:
                step = min(chunk, pos)
                pos -= step
                f.seek(pos)
                data = f.read(step) + data
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        return lines[-n:] if n >= 0 else lines
    except Exception:  # noqa: BLE001 — cold/unreadable store: no tail
        return []


def record(tool, refs, run_id=None):
    """Append ONE usage line {ts, tool, refs, run_id} — ONLY when the toggle is ON and there are refs
    to reinforce (a read that surfaced nothing reinforces nothing). A best-effort append: a failed
    write is swallowed (telemetry is never on the critical path, never fatal — C1 spirit). This is the
    ONLY write this module performs, and it is NON-AUTHORITATIVE (N4)."""
    if not enabled():
        return
    # Normalize at WRITE the SAME way the read scores (codex Slice-3 [medium]): only non-empty string
    # refs within the per-ref length cap, count-capped — so a legitimate write can NEVER serialize
    # schema-drifted (list/dict) or pathologically long refs into the store. Symmetric with _scores.
    refs = [r for r in (refs or [])
            if isinstance(r, str) and r and len(r) <= USAGE_MAX_REF_LEN][:USAGE_MAX_REFS]
    if not refs:
        return
    rec = {"ts": time.time(), "tool": tool, "refs": refs, "run_id": run_id}
    try:
        p = usage_path()        # raises (fails closed) if the path resolves into the Tier-0 event dir
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:  # noqa: BLE001 — telemetry never blocks/fails the read; an invalid path is a no-op
        pass


def _scores(now=None):
    """The per-ref usage score from the PRIOR telemetry (recency+frequency). Reads the store written
    BEFORE this call; the current call's own append is not part of this read (N3 — no self-referential
    read, because the caller ranks BEFORE it records). A missing/corrupt store → {} (cold → no re-rank)."""
    now = now if now is not None else time.time()
    halflife = _halflife_s()
    scores = {}
    try:
        p = usage_path()
    except Exception:  # noqa: BLE001 — a refused/invalid path: no signal (fail closed)
        return scores
    # BOUNDED read (codex Slice-3 [high]): a true chunked backward tail — only the most-recent
    # USAGE_READ_CAP lines are read off disk, so a large append-only store never forces an unbounded
    # read/allocation on the read door. Old refs decay to ~0 anyway, so the tail carries the live signal.
    for line in _read_tail_lines(p, USAGE_READ_CAP):
        line = line.strip()
        if not line:
            continue
        try:
            # FULLY best-effort per line (codex Slice-3 [medium]): catch ANY exception — not only
            # JSONDecodeError but a RecursionError from a deeply-nested JSON-valid line, etc. A corrupt
            # telemetry line must be SKIPPED, never raise — a corrupt store == cold == base order, never
            # the read door's failure mode (C1/N4). Telemetry is reconcilable-to-zero, never a blocker.
            rec = json.loads(line)
            # PER-RECORD schema guard: a JSON-valid but schema-CORRUPT line ([], "x", non-numeric ts,
            # refs-not-a-list, a dict ref) is skipped too.
            if not isinstance(rec, dict):
                continue
            ts = rec.get("ts")
            if not isinstance(ts, (int, float)) or isinstance(ts, bool) or not math.isfinite(ts):
                continue
            if ts > now + USAGE_FUTURE_SKEW_S:   # a future-dated ts is corrupt — skip, never fresh
                continue
            refs = rec.get("refs")
            if not isinstance(refs, list):
                continue
            age = max(0.0, now - ts)
            decay = math.exp(-age / halflife * math.log(2))  # 1.0 now → 0.5 at the half-life
            for ref in refs[:USAGE_MAX_REFS]:            # cap read-side too; only hashable str refs
                if isinstance(ref, str) and ref:
                    scores[ref] = scores.get(ref, 0.0) + decay
        except Exception:  # noqa: BLE001 — any per-line corruption is skipped, never fatal
            continue
    return scores


def rerank(results, key="slug", now=None):
    """The ephemeral read-time re-rank (F7/N3): when the toggle is ON, sort `results` by descending
    prior-usage score (recency+frequency), STABLE — a ref with no prior usage keeps its base relative
    order, so cold == base order and an unused ref is never reordered. When OFF, return `results`
    unchanged (the side-effect-free baseline). NEVER mutates `results`; returns a new list.

    `key` names the field carrying the ref (slug for surf/search rows). The rank reads PRIOR telemetry
    only — the caller must record AFTER ranking, so the current read never reinforces its own order."""
    if not enabled():
        return list(results)
    try:
        scores = _scores(now=now)
        if not scores:
            return list(results)

        def _score(row):
            # TOTAL sort key (codex Slice-3 [medium]): a result row whose ref is unhashable (slug:[],
            # ref:{}) or non-string scores 0 — schema drift in the RESULT set must degrade to base
            # order, never raise out of the read door (C1/F7). Only a non-empty string ref is scored.
            if not isinstance(row, dict):
                return 0.0
            ref = row.get(key)
            return scores.get(ref, 0.0) if isinstance(ref, str) and ref else 0.0

        # a stable sort by descending score: Python's sort is stable, so equal-score rows (incl. all
        # the zero-usage refs) keep their incoming order — only refs with prior usage are lifted.
        return sorted(results, key=_score, reverse=True)
    except Exception:  # noqa: BLE001 — usage corruption/drift degrades to base order, never fatal
        return list(results)
