"""Layer 5 report delivery (Slack + optional email stub)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from src.models.report import AnalysisReport, ReportDeliveryStatus

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Return timezone-aware current UTC timestamp."""
    return datetime.now(timezone.utc)


class ReportDeliverer:
    """Deliver reports via configured outbound channels."""

    def __init__(
        self,
        *,
        slack_webhook_url: str | None = None,
        smtp_config: dict[str, Any] | None = None,
        report_repo: Any | None = None,
        timeout_seconds: float = 10.0,
    ):
        self.slack_webhook_url = (slack_webhook_url or "").strip()
        self.smtp_config = smtp_config or {}
        self.report_repo = report_repo
        self.timeout_seconds = timeout_seconds

    async def deliver(self, report: AnalysisReport) -> list[str]:
        """Deliver report and return successfully used channels."""
        channels: list[str] = []
        channel_attempted = False

        if self.slack_webhook_url:
            channel_attempted = True
            if await self._deliver_slack(report):
                channels.append("slack")

        # Optional email delivery placeholder.
        if self.smtp_config:
            channel_attempted = True
            if await self._deliver_email(report):
                channels.append("email")

        if channels:
            report.delivery_status = ReportDeliveryStatus.DELIVERED
            report.delivered_via = channels
            report.delivered_at = utc_now()
        elif channel_attempted:
            report.delivery_status = ReportDeliveryStatus.DELIVERY_FAILED

        if self.report_repo is not None:
            try:
                await self.report_repo.save(report)
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to persist report delivery status: report_id=%s error=%s", report.report_id, exc)

        return channels

    async def _deliver_slack(self, report: AnalysisReport) -> bool:
        payload = self._build_slack_message(report)
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self.slack_webhook_url, json=payload)
                response.raise_for_status()
            logger.info("Slack delivery succeeded: report_id=%s", report.report_id)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Slack delivery failed: report_id=%s error=%s", report.report_id, exc)
            return False

    async def _deliver_email(self, report: AnalysisReport) -> bool:
        logger.info("Email delivery stub skipped: report_id=%s", report.report_id)
        return False

    def _build_slack_message(self, report: AnalysisReport) -> dict[str, Any]:
        recommendation = (report.recommendation_summary.split() or [""])[0].lower()
        emoji = {"buy": "🟢", "sell": "🔴", "hold": "🟡"}.get(recommendation, "⚪")
        disclaimer = "Decision support only - not an automated trade instruction."

        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{emoji} {report.title}",
                    },
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*{report.recommendation_summary}*"},
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": report.executive_summary},
                },
                {"type": "divider"},
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": f"Report ID: `{report.report_id}`"}],
                },
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": disclaimer}],
                },
            ]
        }
