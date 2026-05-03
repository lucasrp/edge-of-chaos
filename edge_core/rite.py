from __future__ import annotations

from dataclasses import dataclass
from typing import Any


REQUIRED_ORDER = [
    "CycleOpened",
    "DeltaPrepared",
    "ContextReadinessReviewed",
    "BroadSearchCompleted",
    "ReportDrafted",
    "ReportReviewed",
    "ReportWritten",
    "ThreadUpdated",
    "DigestRebuilt",
    "BlogBuilt",
]

REQUIRED_REVIEW_MARKERS = [
    "adversarial",
    "general-review",
    "feynman-review",
    "method-review",
]


@dataclass
class RiteCheck:
    passed: bool
    missing: list[str]
    order: list[str]
    review_markers: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": "pass" if self.passed else "fail",
            "missing": self.missing,
            "order": self.order,
            "review_markers": self.review_markers,
        }


def verify_rite(events: list[dict[str, Any]]) -> RiteCheck:
    event_types = [str(event.get("type") or "") for event in events]
    missing: list[str] = []
    cursor = -1
    for event_type in REQUIRED_ORDER:
        try:
            cursor = event_types.index(event_type, cursor + 1)
        except ValueError:
            missing.append(event_type)

    reviewers = [str(event.get("reviewer") or "") for event in events if event.get("type") == "ReportReviewed"]
    for marker in REQUIRED_REVIEW_MARKERS:
        if not any(marker in reviewer for reviewer in reviewers):
            missing.append(f"review:{marker}")

    broad_search = [event for event in events if event.get("type") == "BroadSearchCompleted"]
    if not broad_search or int(broad_search[-1].get("results") or 0) <= 0:
        missing.append("broad-search:results")

    return RiteCheck(
        passed=not missing,
        missing=missing,
        order=event_types,
        review_markers=reviewers,
    )
