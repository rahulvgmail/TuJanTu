"""Unit tests for dashboard recommendation ranking helpers."""

from __future__ import annotations

from src.dashboard.recommendation_utils import (
    average_confidence_pct,
    expected_impact_score,
    extract_confidence_pct,
    infer_recommendation_signal,
    sort_reports_by_expected_impact,
)


def test_extract_confidence_pct_parses_and_bounds() -> None:
    assert extract_confidence_pct("BUY (Confidence: 82%, Timeframe: medium_term)") == 82
    assert extract_confidence_pct("HOLD confidence: 999%") == 100
    assert extract_confidence_pct("No confidence text") == 50


def test_infer_recommendation_signal_falls_back_to_none() -> None:
    assert infer_recommendation_signal("Upgrade to BUY") == "BUY"
    assert infer_recommendation_signal("Downgrade to SELL") == "SELL"
    assert infer_recommendation_signal("Maintain HOLD") == "HOLD"
    assert infer_recommendation_signal("No action") == "NONE"


def test_expected_impact_score_prioritizes_signal_then_confidence_then_recency() -> None:
    high_signal = {
        "recommendation_summary": "BUY (Confidence: 60%)",
        "created_at": "2026-02-25T10:00:00+00:00",
    }
    low_signal = {
        "recommendation_summary": "HOLD (Confidence: 95%)",
        "created_at": "2026-02-25T10:05:00+00:00",
    }
    assert expected_impact_score(high_signal) > expected_impact_score(low_signal)


def test_sort_reports_by_expected_impact_descending() -> None:
    reports = [
        {
            "report_id": "r3",
            "recommendation_summary": "HOLD (Confidence: 90%)",
            "created_at": "2026-02-25T11:00:00+00:00",
        },
        {
            "report_id": "r1",
            "recommendation_summary": "BUY (Confidence: 70%)",
            "created_at": "2026-02-25T09:00:00+00:00",
        },
        {
            "report_id": "r2",
            "recommendation_summary": "SELL (Confidence: 65%)",
            "created_at": "2026-02-25T10:00:00+00:00",
        },
    ]
    sorted_reports = sort_reports_by_expected_impact(reports)
    assert [item["report_id"] for item in sorted_reports] == ["r1", "r2", "r3"]


def test_average_confidence_pct_handles_empty_and_non_empty_rows() -> None:
    assert average_confidence_pct([]) == 0.0
    rows = [{"confidence_pct": 70}, {"confidence_pct": 80}, {"confidence_pct": 65}]
    assert average_confidence_pct(rows) == 71.7
