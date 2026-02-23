"""Tests for Layer 5 ReportDeliverer."""

from __future__ import annotations

import pytest

from src.models.report import AnalysisReport, ReportDeliveryStatus
from src.pipeline.layer5_report.deliverer import ReportDeliverer


class _ReportRepo:
    def __init__(self):
        self.saved = []

    async def save(self, report):
        self.saved.append(report)
        return report.report_id


def _make_report() -> AnalysisReport:
    return AnalysisReport(
        assessment_id="a1",
        investigation_id="i1",
        trigger_id="t1",
        company_symbol="ABB",
        company_name="ABB India",
        title="ABB India Assessment",
        executive_summary="Recommendation has improved after stronger execution updates.",
        recommendation_summary="BUY (Confidence: 72%, Timeframe: medium_term)",
    )


@pytest.mark.asyncio
async def test_report_deliverer_updates_status_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _ReportRepo()
    deliverer = ReportDeliverer(
        slack_webhook_url="https://example.test/webhook",
        report_repo=repo,
    )
    report = _make_report()

    async def _success(_: AnalysisReport) -> bool:
        return True

    monkeypatch.setattr(deliverer, "_deliver_slack", _success)

    channels = await deliverer.deliver(report)

    assert channels == ["slack"]
    assert report.delivery_status == ReportDeliveryStatus.DELIVERED.value
    assert report.delivered_via == ["slack"]
    assert report.delivered_at is not None
    assert repo.saved


@pytest.mark.asyncio
async def test_report_deliverer_marks_failure_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _ReportRepo()
    deliverer = ReportDeliverer(
        slack_webhook_url="https://example.test/webhook",
        report_repo=repo,
    )
    report = _make_report()

    async def _failure(_: AnalysisReport) -> bool:
        return False

    monkeypatch.setattr(deliverer, "_deliver_slack", _failure)

    channels = await deliverer.deliver(report)

    assert channels == []
    assert report.delivery_status == ReportDeliveryStatus.DELIVERY_FAILED.value
    assert repo.saved


def test_report_deliverer_builds_slack_block_payload_with_disclaimer() -> None:
    deliverer = ReportDeliverer(slack_webhook_url="https://example.test/webhook")
    report = _make_report()

    payload = deliverer._build_slack_message(report)

    assert "blocks" in payload
    blocks = payload["blocks"]
    assert blocks[0]["text"]["text"].startswith("🟢 ")
    assert report.report_id in blocks[4]["elements"][0]["text"]
    assert "Decision support only - not an automated trade instruction." in blocks[5]["elements"][0]["text"]
