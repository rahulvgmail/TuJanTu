"""Tests for Weeks 3-4 data models."""

from __future__ import annotations

from src.models import (
    AnalysisReport,
    CompanyPosition,
    DecisionAssessment,
    ExtractedMetric,
    ForwardStatement,
    HistoricalContext,
    Investigation,
    MarketDataSnapshot,
    Recommendation,
    RecommendationTimeframe,
    ReportDeliveryStatus,
    SignificanceLevel,
    WebSearchResult,
)


def test_investigation_model_round_trip_with_nested_components() -> None:
    investigation = Investigation(
        trigger_id="trigger-123",
        company_symbol="INOXWIND",
        company_name="Inox Wind Limited",
        extracted_metrics=[
            ExtractedMetric(
                name="Revenue",
                value="₹1200 Cr",
                raw_value="Revenue: ₹1200 Cr",
                unit="Cr",
                period="Q3 FY26",
                yoy_change=18.5,
            )
        ],
        forward_statements=[ForwardStatement(statement="Order book to grow in FY27", category="order_book")],
        web_search_results=[
            WebSearchResult(
                query="Inox Wind order book",
                source="https://example.test/news",
                title="Order momentum",
                summary="Order book continues to grow",
                relevance="high",
            )
        ],
        market_data=MarketDataSnapshot(current_price=180.5, market_cap_cr=22000.0),
        historical_context=HistoricalContext(total_past_investigations=3),
        significance=SignificanceLevel.HIGH,
        is_significant=True,
    )

    payload = investigation.model_dump(mode="json")
    rebuilt = Investigation.model_validate(payload)

    assert payload["significance"] == SignificanceLevel.HIGH.value
    assert rebuilt.company_symbol == "INOXWIND"
    assert rebuilt.extracted_metrics[0].period == "Q3 FY26"
    assert rebuilt.web_search_results[0].relevance == "high"


def test_decision_assessment_defaults_and_enum_serialization() -> None:
    assessment = DecisionAssessment(
        investigation_id="inv-1",
        trigger_id="trg-1",
        company_symbol="ABB",
        company_name="ABB India Limited",
    )
    payload = assessment.model_dump(mode="json")

    assert payload["new_recommendation"] == Recommendation.NONE.value
    assert payload["timeframe"] == RecommendationTimeframe.MEDIUM_TERM.value
    assert assessment.confidence == 0.0


def test_company_position_tracks_current_recommendation() -> None:
    position = CompanyPosition(
        company_symbol="SIEMENS",
        company_name="Siemens Limited",
        current_recommendation=Recommendation.BUY,
        recommendation_basis="Strong order book and margins",
        recommendation_history=[
            {"recommendation": Recommendation.HOLD.value, "assessment_id": "a1", "confidence": 0.62},
            {"recommendation": Recommendation.BUY.value, "assessment_id": "a2", "confidence": 0.78},
        ],
        total_investigations=5,
    )

    payload = position.model_dump(mode="json")
    assert payload["current_recommendation"] == Recommendation.BUY.value
    assert len(payload["recommendation_history"]) == 2
    assert position.total_investigations == 5


def test_analysis_report_defaults_and_delivery_enum() -> None:
    report = AnalysisReport(
        assessment_id="assess-1",
        investigation_id="inv-1",
        trigger_id="trg-1",
        company_symbol="BHEL",
        company_name="Bharat Heavy Electricals Limited",
        title="BHEL Q3 Update",
        executive_summary="Order flow remains stable and margins improved.",
    )

    payload = report.model_dump(mode="json")
    assert payload["delivery_status"] == ReportDeliveryStatus.GENERATED.value
    assert payload["delivered_via"] == []
    assert report.report_id


def test_model_exports_include_layer3_types() -> None:
    assert Investigation.collection_name == "investigations"
    assert DecisionAssessment.collection_name == "assessments"
    assert AnalysisReport.collection_name == "reports"
    assert CompanyPosition.collection_name == "positions"
