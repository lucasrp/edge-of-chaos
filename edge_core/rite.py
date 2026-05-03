from __future__ import annotations

from dataclasses import dataclass
from typing import Any


REQUIRED_ORDER = [
    "CycleOpened",
    "StateLoaded",
    "DeliveryCompleted",
    "ContinuitySearchReviewed",
    "BroadSearchCompleted",
    "DeliveryCompleted",
    "ContinuitySearchReviewed",
    "BroadSearchCompleted",
    "DeliveryCompleted",
    "ReportDrafted",
    "DeliveryCompleted",
    "AdversarialSearchReviewed",
    "BroadSearchCompleted",
    "ReportRevised",
    "DeliveryCompleted",
    "AdversarialReviewed",
    "ReportRevised",
    "DeliveryCompleted",
    "FeynmanReviewed",
    "FinalReportPrepared",
    "ReportWritten",
    "ReportUtilityClassified",
    "ThreadUpdated",
    "DigestRebuilt",
    "BlogBuilt",
]

REQUIRED_REVIEW_MARKERS = [
    "context-search",
    "adversarial",
    "feynman-review",
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

    reviewers = [
        str(event.get("reviewer") or "")
        for event in events
        if event.get("type") in {"ContinuitySearchReviewed", "AdversarialSearchReviewed", "AdversarialReviewed", "FeynmanReviewed"}
    ]
    for marker in REQUIRED_REVIEW_MARKERS:
        if not any(marker in reviewer for reviewer in reviewers):
            missing.append(f"review:{marker}")

    broad_search = [event for event in events if event.get("type") == "BroadSearchCompleted"]
    if len(broad_search) < 3:
        missing.append("broad-search:rounds")
    if any(int(event.get("results") or 0) <= 0 for event in broad_search):
        missing.append("broad-search:results")
    if sum(1 for event in events if event.get("type") == "ContinuitySearchReviewed") < 2:
        missing.append("continuity-search:rounds")
    if sum(1 for event in events if event.get("type") in {"AdversarialSearchReviewed", "AdversarialReviewed"}) < 2:
        missing.append("adversarial:rounds")

    return RiteCheck(
        passed=not missing,
        missing=missing,
        order=event_types,
        review_markers=reviewers,
    )
