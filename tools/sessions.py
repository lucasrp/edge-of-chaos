"""Session reader + delta — the raw layer of the measure-first spike (ADR-0004 decision A).

A transcript is the non-lossy raw: one `.jsonl` = one session. Claude Code remains the original
store/format; Codex is an additional surface normalized into the same Turn(role, text) shape. This
module discovers sessions and parses ordered dialogue deltas since a watermark. It is
locator/offset-based, carrying no semantics (ADR-0001).
"""
import json
import os
from dataclasses import dataclass
from pathlib import Path

ROLES = {"user": "human", "assistant": "edge"}
CODEX_ROLES = {"user": "human", "assistant": "edge"}
CODEX_SCAFFOLDING_PREFIXES = ("<environment_context>", "<turn_aborted>")


@dataclass(frozen=True)
class Session:
    """One transcript: an id, its path, and the surface that wrote it."""
    id: str
    path: Path
    surface: str = "claude"


@dataclass(frozen=True)
class Turn:
    """One dialogue turn: who spoke (`human`/`edge`) and what they said (text only)."""
    role: str
    text: str


def list_sessions(project_dir) -> list:
    """Discover sessions: every `.jsonl` in the project dir is one session."""
    return [Session(id=p.stem, path=p) for p in Path(project_dir).glob("*.jsonl")]


def codex_sessions_dir():
    """The Codex transcript root. EDGE_CODEX_SESSIONS_DIR wins; else CODEX_HOME/sessions; else
    ~/.codex/sessions. Missing is a dark optional surface, not a sweep failure."""
    raw = os.environ.get("EDGE_CODEX_SESSIONS_DIR")
    if raw:
        return Path(os.path.expanduser(raw))
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(os.path.expanduser(codex_home)) / "sessions"
    return Path.home() / ".codex" / "sessions"


def _codex_session_id(path) -> str:
    """Codex filenames include timestamps; the stable session id lives in session_meta when present."""
    p = Path(path)
    try:
        for line in p.read_text(errors="replace").splitlines()[:20]:
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if obj.get("type") == "session_meta":
                payload = obj.get("payload") or {}
                if isinstance(payload.get("id"), str) and payload["id"].strip():
                    return payload["id"].strip()
    except OSError:
        pass
    return p.stem


def list_codex_sessions(root=None) -> list:
    """Discover Codex sessions recursively. [] means the optional Codex store is absent/dark."""
    root = codex_sessions_dir() if root is None else Path(root)
    if not root.is_dir():
        return []
    return [Session(id=_codex_session_id(p), path=p, surface="codex")
            for p in sorted(root.rglob("*.jsonl"))]


def _text_of(content) -> str:
    """The human-readable text of a message: the joined text blocks (or a bare string)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict)
                       and b.get("type") in ("text", "input_text", "output_text"))
    return ""


def _claude_turn_from_obj(obj):
    role = ROLES.get(obj.get("type"))
    if not role:
        return None
    text = _text_of(obj.get("message", {}).get("content")).strip()
    return Turn(role=role, text=text) if text else None


def _codex_turn_from_obj(obj):
    if obj.get("type") != "response_item":
        return None
    payload = obj.get("payload") or {}
    if payload.get("type") != "message":
        return None
    role = CODEX_ROLES.get(payload.get("role"))
    if not role:
        return None
    text = _text_of(payload.get("content")).strip()
    if not text or any(text.startswith(p) for p in CODEX_SCAFFOLDING_PREFIXES):
        return None
    return Turn(role=role, text=text)


def _turns_from_lines(lines, surface="claude") -> list:
    """Parse raw transcript lines into ordered human/edge dialogue turns, dropping noise.
    A corrupt/truncated line (a session written mid-sweep, a crashed writer) is dropped as
    noise — one bad line must never kill the whole sweep."""
    turns = []
    turn_from_obj = _codex_turn_from_obj if surface == "codex" else _claude_turn_from_obj
    for line in lines:
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        turn = turn_from_obj(obj)
        if turn is not None:
            turns.append(turn)
    return turns


def read_turns(path, surface="claude") -> list:
    """Parse a transcript into ordered human/edge dialogue turns."""
    return _turns_from_lines(Path(path).read_text(errors="replace").splitlines(), surface=surface)


@dataclass(frozen=True)
class Claim:
    """A discrete assertion about the mentee or the work, mined from a session's dialogue."""
    text: str


_CLAIM_PROMPT = """\
Below is the text dialogue of one work session between a person (human) and their mentor (edge).
Extract the discrete claims it asserts about the person or their work — decisions, preferences,
facts, and stated hypotheses. One claim per item. Reply ONLY a JSON array of strings.

DIALOGUE:
{dialogue}"""


def extract_claims(turns, complete_fn) -> list:
    """Mine a session's discrete claims, agentically, via an injected LLM `complete_fn`."""
    dialogue = "\n".join(f"{t.role}: {t.text}" for t in turns)
    raw = complete_fn(_CLAIM_PROMPT.format(dialogue=dialogue))
    return [Claim(text=c) for c in json.loads(raw)]


KINDS = ("replacement", "duplicate", "divergence", "novel")


@dataclass(frozen=True)
class Classification:
    """A claim labelled against prior state — the G5 distinction (time vs meaning)."""
    text: str
    kind: str


_CLASSIFY_PROMPT = """\
A mentor holds this STATE of claims about a person and their work:
{state}

A new work session asserts these NEW claims:
{new}

Label each NEW claim against the STATE, exactly one of:
- "replacement": a clean factual update of a state claim (the old fact is now wrong)
- "duplicate": restates a state claim, no new information
- "divergence": shifts meaning/interpretation (hypothesis, irony, self-image) without cleanly
  replacing a fact — the two coexist in tension
- "novel": unrelated to anything in the state

Reply ONLY a JSON array of {{"text": <claim>, "kind": <label>}}, one per NEW claim, in order."""


def classify_session(state, new_claims, complete_fn) -> list:
    """Label each new claim against the accumulated state in one batched LLM call."""
    raw = complete_fn(_CLASSIFY_PROMPT.format(
        state="\n".join(f"- {s}" for s in state) or "(empty)",
        new="\n".join(f"- {c.text}" for c in new_claims)))
    return [Classification(text=o["text"], kind=o["kind"]) for o in json.loads(raw)]


def run_spike(sessions_turns, extract_fn, classify_fn) -> dict:
    """Walk sessions oldest->newest: classify each against the state grown so far, then fold
    its claims into the state. Returns the G5 measurement over all classifications."""
    state = []
    labelled = []
    for turns in sessions_turns:
        claims = extract_fn(turns)
        labelled.extend(classify_fn(state, claims))
        state.extend(c.text for c in claims)
    return measure(labelled)


def measure(classifications) -> dict:
    """Aggregate labels into the G5 verdict: `time` (replacement+duplicate, Zep solves) vs
    `meaning` (divergence, Zep does not solve — grill-me's domain). Novel is excluded."""
    counts = {k: 0 for k in KINDS}
    for c in classifications:
        counts[c.kind] = counts.get(c.kind, 0) + 1
    time = counts["replacement"] + counts["duplicate"]
    meaning = counts["divergence"]
    return {"counts": counts, "verdict": "time" if time > meaning else "meaning"}


def delta(path, since_line: int, surface="claude"):
    """The turns after a raw-line watermark, with the new watermark (total line count).

    Transcripts are append-only, so the watermark is the count of raw lines already seen.
    A truncated FINAL line (a writer flushing mid-sweep) is NOT consumed by the watermark —
    when the writer completes it, the next sweep re-reads it (non-lossy raw). A corrupt
    interior line is a crashed writer: dropped and consumed (`_turns_from_lines`)."""
    lines = Path(path).read_text(errors="replace").splitlines()
    watermark = len(lines)
    new = lines[since_line:]
    if new:
        try:
            json.loads(new[-1])
        except ValueError:
            watermark -= 1          # leave the half-flushed tail for the next sweep
            new = new[:-1]
    return _turns_from_lines(new, surface=surface), watermark
