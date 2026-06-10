"""Session reader + delta — the raw layer of the measure-first spike (ADR-0004 decision A).

A Claude transcript is the non-lossy raw: one `.jsonl` = one session. This module discovers
sessions and (later slices) parses them into ordered turns and deltas them since a watermark.
It is locator/offset-based, carrying no semantics (ADR-0001).
"""
import json
from dataclasses import dataclass
from pathlib import Path

ROLES = {"user": "human", "assistant": "edge"}


@dataclass(frozen=True)
class Session:
    """One Claude transcript: a session id (the filename uuid) and its path."""
    id: str
    path: Path


@dataclass(frozen=True)
class Turn:
    """One dialogue turn: who spoke (`human`/`edge`) and what they said (text only)."""
    role: str
    text: str


def list_sessions(project_dir) -> list:
    """Discover sessions: every `.jsonl` in the project dir is one session."""
    return [Session(id=p.stem, path=p) for p in Path(project_dir).glob("*.jsonl")]


def _text_of(content) -> str:
    """The human-readable text of a message: the joined text blocks (or a bare string)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content
                       if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _turns_from_lines(lines) -> list:
    """Parse raw transcript lines into ordered human/edge dialogue turns, dropping noise.
    A corrupt/truncated line (a session written mid-sweep, a crashed writer) is dropped as
    noise — one bad line must never kill the whole sweep."""
    turns = []
    for line in lines:
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        role = ROLES.get(obj.get("type"))
        if not role:
            continue
        text = _text_of(obj.get("message", {}).get("content")).strip()
        if not text:
            continue
        turns.append(Turn(role=role, text=text))
    return turns


def read_turns(path) -> list:
    """Parse a transcript into ordered human/edge dialogue turns."""
    return _turns_from_lines(Path(path).read_text().splitlines())


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


def delta(path, since_line: int):
    """The turns after a raw-line watermark, with the new watermark (total line count).

    Transcripts are append-only, so the watermark is the count of raw lines already seen.
    """
    lines = Path(path).read_text().splitlines()
    return _turns_from_lines(lines[since_line:]), len(lines)
