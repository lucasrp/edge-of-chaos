"""aquisicao — Modulo 1 (Aquisicao / Lastro). Genotype tool.

The front door over the acquisition plumbing. Resp: read any source (self / mundo / mentee) and
bring back TRACEABLE lastro. This module NAMES the interface (ADR-0019: one owner + a narrow
interface); the deeply-built machinery stays behind it — `harvest` is the spine (the quote-aware
transcript recognizer), `sources` the roster seam, `grounding_yield` the yield fold.

Interface:
  grounding_floor(...)      the auditor gate (ADR-0021). Knob-driven (EDGE_GROUNDING_FLOOR:
                            0 off / 1 observe=auditor / 2 gate). Julgamento (close) CALLS this,
                            never re-implements it — else the format/acquisition leak returns.
  declare_dark(key, reason) the honest seca: "consultei X, zero relevantes". The declaration IS
                            lastro (fragmentos-prosa-fiduciaria: it sustains the negative claim),
                            so it is recorded, never swallowed.
  gather(subject, key)      [deferred] the subject-lens facade over sources/sweep/harvest — the
                            ~30% new build; the pieces exist, the dispatcher does not yet.
"""
import eventlog
import harvest


# --- the auditor gate (ADR-0021): Aquisicao owns it; close calls THIS, never re-implements it ---
grounding_floor = harvest.close_floor


# --- declare_dark: the honest seca is lastro, not a hole in it ---
def declare_dark(key, reason, *, log=None):
    """Declare a source dark — an honest seca ("consultei exa com as queries X e Y, zero
    relevantes"). The declaration sustains a negative claim ("nao ha benchmark publico de X"),
    so it IS lastro and is RECORDED, never swallowed. One `grounding.dark` event, keyed by source.
    Both the source and the reason are required — an unnamed or unexplained dark is not lastro."""
    if not (isinstance(key, str) and key.strip()):
        raise ValueError("declare_dark: key (source locator) must be a non-empty string")
    if not (isinstance(reason, str) and reason.strip()):
        raise ValueError("declare_dark: reason must be a non-empty string — the seca must be explained")
    return eventlog.append("grounding.dark", "grounding",
                           {"source": key, "reason": reason},
                           log=log if log is not None else eventlog.LOG)
