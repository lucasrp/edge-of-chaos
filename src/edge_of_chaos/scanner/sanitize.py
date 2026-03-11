"""Sanitize extracted heuristics data before writing to bootstrap memory.

Three modes:
- strict:   Remove all named entities, paths, specific values
- balanced: Keep tech terms and patterns, remove personal data
- raw:      Keep everything (user opts in to full data)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from edge_of_chaos.scanner.heuristics import Correction, HeuristicsResult, Preference


# ---------------------------------------------------------------------------
# Secret detection patterns
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = [
    re.compile(r"\b(?:sk|pk|api|key|token|secret|password|auth)[-_]?[A-Za-z0-9]{16,}\b", re.I),
    re.compile(r"\bghp_[A-Za-z0-9]{36,}\b"),  # GitHub PAT
    re.compile(r"\bghs_[A-Za-z0-9]{36,}\b"),  # GitHub App token
    re.compile(r"\bglpat-[A-Za-z0-9\-]{20,}\b"),  # GitLab PAT
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),  # AWS access key
    re.compile(r"\bxox[bpras]-[A-Za-z0-9\-]+\b"),  # Slack tokens
    re.compile(r"\beyJ[A-Za-z0-9\-_]{20,}\.[A-Za-z0-9\-_]+\b"),  # JWT
    re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"),  # Long base64 (potential keys)
    re.compile(r"(?:password|passwd|pwd)\s*[=:]\s*\S+", re.I),
    re.compile(r"Bearer\s+[A-Za-z0-9\-_.]+", re.I),
]

# Personal data patterns (for strict/balanced modes)
_PERSONAL_PATTERNS = [
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),  # Email
    re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),  # Phone (US)
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),  # IP address
]

# Path patterns for strict mode (removes all absolute paths)
_PATH_PATTERN = re.compile(r"/(?:home|Users|root)/\S+")


# ---------------------------------------------------------------------------
# Sanitization functions
# ---------------------------------------------------------------------------

def _remove_secrets(text: str) -> str:
    """Remove apparent secrets from text."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def _remove_personal(text: str) -> str:
    """Remove personal data (emails, phones, IPs)."""
    for pattern in _PERSONAL_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def _remove_paths(text: str) -> str:
    """Remove absolute paths containing home directories."""
    return _PATH_PATTERN.sub("[PATH]", text)


def _sanitize_text(text: str, mode: str) -> str:
    """Sanitize a text string according to mode."""
    if mode == "raw":
        return text

    # Both strict and balanced remove secrets
    text = _remove_secrets(text)

    if mode == "strict":
        text = _remove_personal(text)
        text = _remove_paths(text)
    elif mode == "balanced":
        text = _remove_personal(text)

    return text


def sanitize(result: HeuristicsResult, mode: str = "balanced") -> HeuristicsResult:
    """Sanitize extracted heuristics data.

    Args:
        result: The raw HeuristicsResult from run_heuristics().
        mode: One of "strict", "balanced", "raw".

    Returns:
        A new HeuristicsResult with sanitized data.
    """
    if mode not in ("strict", "balanced", "raw"):
        raise ValueError(f"Unknown sanitization mode: {mode!r}")

    if mode == "raw":
        return result

    # Sanitize preferences (values are generally safe, but sanitize anyway)
    sanitized_prefs = [
        Preference(
            category=p.category,
            value=_sanitize_text(p.value, mode),
            occurrences=p.occurrences,
            confidence=p.confidence,
        )
        for p in result.preferences
    ]

    # Sanitize corrections (these contain user text that may have personal info)
    sanitized_corrections = [
        Correction(
            user_text=_sanitize_text(c.user_text, mode),
            preceding_assistant_text=_sanitize_text(c.preceding_assistant_text, mode),
            pattern_matched=c.pattern_matched,
        )
        for c in result.corrections
    ]

    # Tech stack: names are safe, keep as-is
    sanitized_tech = dict(result.tech_stack)

    # Structure patterns: directory names are safe, keep as-is
    sanitized_structure = dict(result.structure_patterns)

    # Topics: individual words, generally safe
    sanitized_topics = dict(result.topics)

    if mode == "strict":
        # In strict mode, limit corrections to just the pattern matched
        sanitized_corrections = [
            Correction(
                user_text="[REDACTED]",
                preceding_assistant_text="[REDACTED]",
                pattern_matched=c.pattern_matched,
            )
            for c in result.corrections
        ]

    return HeuristicsResult(
        preferences=sanitized_prefs,
        corrections=sanitized_corrections,
        tech_stack=sanitized_tech,
        structure_patterns=sanitized_structure,
        topics=sanitized_topics,
    )
