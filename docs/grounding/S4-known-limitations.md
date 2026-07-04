# S4 grounding harvest — Known limitations (accepted)

Provenance: S4 gate r12.

The instrument holds two invariants:

- **INVARIANT A (no phantom):** a URL that was never fetched must produce NO manifest row and NO
  blind tally.
- **INVARIANT B (no silent vanish):** a URL that WAS fetched must appear in at least ONE of
  {manifest row, blind tally} — never in neither.

The cases below are places where B cannot be satisfied without breaking A. They are **accepted**:
each is an irreducible A-vs-B tradeoff, and each is a fetch shape an agent does not typically
produce. Fixing them would resurrect the very phantoms A closes.

## 1. Pipe-fed client — `echo https://real | xargs curl`

The URL reaches curl through a pipe: it is an argument on `echo`'s side, then handed to `xargs
curl` over stdin. The extractor sees a URL word only inside the `echo` invocation, whose command
word is `echo` (a non-client) — so it is correctly excluded from the `echo` side. curl on the
`xargs` side has no URL word of its own in the command text. The fetch therefore vanishes from
BOTH the row and the tally.

**Why irreducible:** the only way to tally it would be to tally URLs that appear as operands of
`echo` (and other non-clients). But `echo "https://…"` printing a URL it never fetches is exactly
the phantom INVARIANT A exists to close. Tallying echo'd-then-piped URLs would resurrect every
`echo`/`git commit -m`/prose-URL phantom. A closes that door; B cannot re-open it selectively,
because the transcript cannot distinguish "printed then piped to a client" from "merely printed".

**Assessment:** `echo URL | xargs curl` is not an agent-typical fetch shape. An agent that intends
a fetch writes `curl URL` (or a wrapped/full-path form, all of which ARE covered by r12 B-1/B-2).
Accepted.

## 2. `exec -a NAME curl` — residual tail (NOT hit in practice)

`exec -a NAME curl …` renames the process via `exec`'s `-a` flag. In the current implementation the
generic non-glued-flag rule in `_command_word` skips `-a` **and its bare value `NAME`**, then lands
on `curl` — so the common case DOES resolve to a row (see
`test_exec_dash_a_name_reaches_curl`). The residual only bites if `NAME` were itself shaped like a
new wrapper/flag/env-assignment, in which case the value-skip declines and the walk could stop
early. That shape is exotic and, if it ever occurs, fails **closed** (a DROP, never a phantom).

**Assessment:** the common `exec -a NAME curl` is covered; the exotic residual is a fail-closed
DROP, consistent with the instrument's fail-closed posture. Documented, not fixed.
