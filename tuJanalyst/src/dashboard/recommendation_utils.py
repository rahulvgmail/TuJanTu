"""Helpers for ranking recommendation reports in the investor dashboard."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

_CONFIDENCE_PATTERN = re.compile(r"confidence\s*[:=]\s*(\d{1,3})\s*%", flags=re.IGNORECASE)


def parse_created_at(value: str | None) -> datetime:
    """Parse an API datetime field into a comparable UTC-like timestamp."""
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min


def extract_confidence_pct(text: str) -> int:
    """Extract confidence percentage from a recommendation summary string."""
    match = _CONFIDENCE_PATTERN.search(text or "")
    if not match:
        return 50
    value = int(match.group(1))
    return max(0, min(100, value))


def infer_recommendation_signal(text: str) -> str:
    """Infer BUY/HOLD/SELL/NONE from recommendation summary text."""
    lowered = (text or "").lower()
    if "sell" in lowered:
        return "SELL"
    if "buy" in lowered:
        return "BUY"
    if "hold" in lowered:
        return "HOLD"
    return "NONE"


def signal_weight(signal: str) -> int:
    """Map a recommendation signal to a coarse impact weight."""
    normalized = signal.upper().strip()
    if normalized in {"BUY", "SELL"}:
        return 3
    if normalized == "HOLD":
        return 2
    return 1


def expected_impact_score(report: dict[str, Any]) -> float:
    """Compute a sortable score for recommendations.

    Higher score means higher expected impact. Weight recommendation signal first,
    then confidence, then report recency.
    """
    summary = str(report.get("recommendation_summary") or "")
    signal = infer_recommendation_signal(summary)
    confidence = extract_confidence_pct(summary)
    created_at = parse_created_at(str(report.get("created_at") or ""))
    # Keep recency as a tie-breaker only; signal and confidence should dominate.
    recency = (created_at.timestamp() / 1_000_000.0) if created_at != datetime.min else 0.0
    return (signal_weight(signal) * 10_000.0) + (confidence * 10.0) + recency


def sort_reports_by_expected_impact(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return reports sorted by expected impact score descending."""
    return sorted(reports, key=expected_impact_score, reverse=True)
