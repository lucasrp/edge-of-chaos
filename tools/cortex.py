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

Interface (contracts live on the substrate functions these name): cosine · direction_at ·
objective_at · report_at · corpus_at · grounding_at · source_yield_at · source_feedback_at ·
artefatos_without_kernel · supersede_rank (PUBLIC here — harvest used to reach into the private
eventlog._supersede_rank; a private reach-in is not an interface).
"""
import eventlog
import communities as _communities


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


# --- community navigation (Módulo 2 read door over tools/communities.py; same late-binding
# rule; graph leg degrades DARK (None) — never raises into a bare-python caller) ---

def communities(*args, **kwargs):
    return _communities.communities(*args, **kwargs)


def community(*args, **kwargs):
    return _communities.community(*args, **kwargs)


def locate(*args, **kwargs):
    return _communities.locate(*args, **kwargs)
