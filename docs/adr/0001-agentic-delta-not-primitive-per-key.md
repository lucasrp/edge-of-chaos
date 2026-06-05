# The beat is agentic-first; deltas are not primitives per key

The whole beat **starts fully agentic** — the edge runs the cycle as an agent rather than as a
deterministic 6-phase pipeline. The driving case is the **Delta** (what's new in the inputs
since the last consolidation): we compute it agentically — hand the edge a source's key (a
locator) and it figures out what's new itself — rather than with a deterministic per-source
primitive. The rebuild **starts free and sees later**; it would only harden back toward a
deterministic pipeline/primitives if it decays again. Both modes work, and we have run both.

## Status

accepted

## Considered options

- **Deterministic delta, a primitive per key.** A git primitive, a Drive primitive, a folder
  primitive, one per source kind. Reliable and reproducible, but it needs a new primitive for
  every key. **Rejected:** that per-key proliferation is exactly what bloated the prior system
  (~95k LOC) and caused it to decay — the primitives arose *because of this very problem*.
- **Agentic delta, just give the key.** One mechanism for any source; no per-source code.
  **Chosen:** keeps the genotype source-blind ("read what's at this key") and matches the
  product thesis that the edge adapts to any kind of work — many users never touch git.

## Consequences

- **The whole beat is an agent loop**, not the deterministic 6-phase pipeline. Given the source
  keys, the edge reads the world agentically — figures out what's new (delta) and reads the
  actual documents, including old ones — against the **wiki read in full** (size permitting;
  only the inputs are deltized). Depth lives in the read, not in the delta.
- The thin `tools/_pipeline.py` rite and `tools/_delta.py` (a git-coupled per-key primitive,
  the exact anti-pattern) are **retired**.
- We trade reproducibility/testability for freedom and reach, **on purpose, and only to start**
  ("vemos depois"). If decay returns, the known fallback is to reintroduce deterministic
  primitives / pipeline guardrails for the highest-value keys — selectively, not by default.
