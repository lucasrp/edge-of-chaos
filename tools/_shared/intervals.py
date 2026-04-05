"""Interval parsing shared between edge-render and edge-apply.

systemd.time(7) accepts formats like "30min", "6h", "1h30min", "2d". We
mirror that grammar so the yaml is the source of truth for heartbeat cadence
instead of a hardcoded allowlist that silently rebaixa unknown values.
"""

import re

_UNIT_SECONDS = {"s": 1, "min": 60, "h": 3600, "d": 86400}
# Full-match: one or more (number + unit) tokens, whitespace tolerated between.
_FULL_RE = re.compile(r"^\s*(?:\d+\s*(?:min|h|s|d)\s*)+$")
_TOKEN_RE = re.compile(r"(\d+)\s*(min|h|s|d)")


def parse_interval(spec: str) -> int:
    """Parse an interval spec into total seconds.

    Accepts tokens like '30min', '6h', '1h30min', '2d'. Whitespace between
    tokens is tolerated. Raises ValueError for anything unparseable — silent
    fallback is exactly the bug this module exists to prevent.

    >>> parse_interval("6h")
    21600
    >>> parse_interval("30min")
    1800
    >>> parse_interval("1h30min")
    5400
    >>> parse_interval("2d")
    172800
    """
    if not isinstance(spec, str) or not spec.strip():
        raise ValueError(f"heartbeat_interval vazio ou não-string: {spec!r}")

    if not _FULL_RE.match(spec):
        raise ValueError(
            f"heartbeat_interval inválido: {spec!r}. "
            f"Formatos aceitos: '30min', '6h', '1h30min', '2d', etc. "
            f"(grammar de systemd.time(7))"
        )

    total = 0
    for num, unit in _TOKEN_RE.findall(spec):
        total += int(num) * _UNIT_SECONDS[unit]
    return total
