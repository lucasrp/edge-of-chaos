"""Shared skill classification and lifecycle policy."""

from __future__ import annotations

KNOWN_SKILLS = {
    "autonomy",
    "delta",
    "discovery",
    "heartbeat",
    "loader",
    "planner",
    "report",
    "research",
    "sources",
}

ARTIFACT_EXEMPT_SKILLS = {
    "delta",
    "heartbeat",
    "loader",
    "prompt",
}


def normalize_skill_id(value: object) -> str:
    return str(value or "").strip().lstrip("/").lower()


def canonical_skill_id(value: object, *, instance: object = "") -> str:
    normalized = normalize_skill_id(value)
    if normalized in KNOWN_SKILLS or normalized == "prompt":
        return normalized

    prefix = normalize_skill_id(instance)
    if prefix and normalized.startswith(f"{prefix}-"):
        candidate = normalized[len(prefix) + 1 :]
        if candidate in KNOWN_SKILLS or candidate == "prompt":
            return candidate

    for skill in KNOWN_SKILLS:
        if normalized.endswith(f"-{skill}"):
            return skill
    return normalized


def skill_requires_artifact_publication(skill: object, *, instance: object = "") -> bool:
    normalized = canonical_skill_id(skill, instance=instance)
    return bool(normalized and normalized not in ARTIFACT_EXEMPT_SKILLS)


def skill_accepts_stdout_artifact(skill: object, *, instance: object = "") -> bool:
    return skill_requires_artifact_publication(skill, instance=instance)
