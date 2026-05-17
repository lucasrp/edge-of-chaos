from __future__ import annotations

import re
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def date_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def slugify(value: str, fallback: str = "untitled") -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or fallback


def truncate(value: str, limit: int = 600) -> str:
    value = " ".join((value or "").split())
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "..."
