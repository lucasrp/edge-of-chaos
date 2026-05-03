# Blog Entry Voice Calibration (#483)

Issue #483 reopens the #388 voice contract with a narrower question: the feed
can obey the letter of "2-4 paragraphs" and still feel unnatural to a
Roberto-class reader, meaning a smart casual reader outside the runtime.

## Evidence Sample

Post-#388 entries inspected from the live edge state:

| Entry | Shape | Reader-facing problem |
|---|---:|---|
| `2026-05-02-report-dispatch-ack-trap-broke-cycle-7-fired-first-ack.md` | 3 paragraphs | The paragraph count is right, but the first paragraph leans on cycle IDs, timestamps, a commit hash, and internal gate vocabulary before saying why the finding matters. |
| `entry-report-empty-digest-g3-audit.md` | 3 paragraphs | The entry is coherent for the operator but assumes G3b/P1/static-audit/LLM-renderer context. It reads like a status memo, not a doorway for an external reader. |
| `2026-05-03-map-substrate-gap-confirmed-gdrive-primitive-operations-are-list-tree-read-head-no-u.md` | 16 paragraphs | This is a report/map body published into the feed: duplicate H1, scope block, mode banner, evidence list, and process chatter. |

## Diagnosis

#388 landed the generic contract in `state-protocol.md` and
`report-template.md`, but it did not cover every publication path. In
particular, `runtime-stdout-artifact` wrote the skill output verbatim into both
the report and the feed entry. That path can bypass the entry-as-invitation
contract even when the full report artifact is useful.

The missing bar is not just length. The entry must first explain, in plain
language, what changed and why the reader should care. Internal identifiers,
scope blocks, and evidence dumps can appear in the report, but they should not
be the feed body's opening experience.

## Contract Adjustment

- The reader model is explicit: Roberto-class means intelligent, curious, and
  outside the runtime.
- The first paragraph must stand without cycle IDs, commit hashes, queue/gap
  shorthand, or protocol vocabulary as load-bearing context.
- Raw report scaffolding is banned from the feed body: duplicate H1, mode/scope
  banners, evidence lists, and "writing the map/report" process chatter.
- Runtime stdout artifacts keep the full body in the HTML report and publish a
  short feed invitation.
