"""cortex — Modulo 2 (Cortex / Memoria). Genotype tool.

The front door over the Cortex-query surface, reclaimed from eventlog (C4, Costura B). ADR-0010
names the read architecture — navigate the Cortex, replay the log — but eventlog was double-duty:
the append-log (Plataforma) AND the query surface other modules navigated state through. ADR-0019
resolves the straddle: Cortex OWNS the queries and NAMES the interface; eventlog stays the
substrate (append · replay · folds) behind it. Callers import THIS, never eventlog's query names —
so #68 swaps the substrate behind the door without moving a caller.

The interface is the READ family callers actually navigate state through — writes stay
`eventlog.append` (Plataforma; nothing is true unless an event). One documented exception:
blog/server composes `eventlog.fold_direction` over its own tolerant iterator (fail-soft web
surface, "no parallel fold") — a substrate-level composition, not a query behind this door.

Interface:
  cosine(a, b)              the one similarity (ADR-0009) — pure math; embedding calls stay
                            with the callers (sweep/relate/publisher).
  direction_at(...)         Direction state at a cursor — {set, proposed} tiers.
  objective_at(...)         the Objective anchor at a cursor.
  report_at(...)            the direcionamento reports at a cursor.
  corpus_at(...)            the edge's own published work at a cursor.
  grounding_at(...)         the grounding/canary verdict state at a cursor.
  source_yield_at(...)      per-source signal yield at a cursor.
  source_feedback_at(...)   yield x curadoria per source at a cursor.
  artefatos_without_kernel(...)  the C3-debt detector (published without intent.kernel).
  supersede_rank(p, e)      the E2b competing-interpretation rank, PUBLIC here — harvest used to
                            reach into eventlog._supersede_rank; a private reach-in is not an
                            interface.
"""
import eventlog


# Each door delegates LATE (resolved at call time on the eventlog module), never an import-time
# alias: the test phenotype isolates by swapping eventlog attributes (e.g. test_sweep._isolate
# replaces eventlog.artefatos_without_kernel), and an alias would freeze the original past the
# swap. The full contract of each query lives on the substrate function it names.

def cosine(a, b):
    return eventlog.cosine(a, b)


def direction_at(*args, **kwargs):
    return eventlog.direction_at(*args, **kwargs)


def objective_at(*args, **kwargs):
    return eventlog.objective_at(*args, **kwargs)


def report_at(*args, **kwargs):
    return eventlog.report_at(*args, **kwargs)


def corpus_at(*args, **kwargs):
    return eventlog.corpus_at(*args, **kwargs)


def grounding_at(*args, **kwargs):
    return eventlog.grounding_at(*args, **kwargs)


def source_yield_at(*args, **kwargs):
    return eventlog.source_yield_at(*args, **kwargs)


def source_feedback_at(*args, **kwargs):
    return eventlog.source_feedback_at(*args, **kwargs)


def artefatos_without_kernel(*args, **kwargs):
    return eventlog.artefatos_without_kernel(*args, **kwargs)


def supersede_rank(payload, event):
    return eventlog._supersede_rank(payload, event)
