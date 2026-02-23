"""Exchange announcement pollers for NSE/BSE trigger ingestion."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import feedparser
import httpx

from src.models.trigger import TriggerEvent, TriggerPriority, TriggerSource
from src.repositories.base import TriggerRepository

logger = logging.getLogger(__name__)


@dataclass
class NormalizedAnnouncement:
    """Normalized exchange announcement record for downstream trigger creation."""

    source: TriggerSource
    source_url: str
    title: str
    raw_content: str
    company_symbol: str | None = None
    company_name: str | None = None
    sector: str | None = None
    published_at: datetime | None = None
    document_urls: list[str] = field(default_factory=list)


class ExchangeRSSPoller:
    """Polls NSE and BSE announcement feeds and creates deduplicated triggers."""

    def __init__(
        self,
        trigger_repo: TriggerRepository,
        nse_url: str,
        bse_url: str | None = None,
        session: httpx.AsyncClient | None = None,
    ):
        self.trigger_repo = trigger_repo
        self.nse_url = nse_url
        self.bse_url = bse_url
        self.session = session or httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json, application/xml, text/xml;q=0.9, */*;q=0.8",
            },
            timeout=30.0,
            follow_redirects=True,
        )

    async def poll(self) -> list[TriggerEvent]:
        """Fetch latest exchange announcements and create triggers for unseen items."""
        created_triggers: list[TriggerEvent] = []
        sources: list[tuple[TriggerSource, str]] = [(TriggerSource.NSE_RSS, self.nse_url)]
        if self.bse_url:
            sources.append((TriggerSource.BSE_RSS, self.bse_url))

        for source, url in sources:
            try:
                announcements = await self._fetch_announcements(source=source, url=url)
                created = await self._create_new_triggers(announcements)
                created_triggers.extend(created)
                logger.info(
                    "Poll source complete: source=%s total=%s created=%s",
                    source.value,
                    len(announcements),
                    len(created),
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed polling %s (%s): %s", source.value, url, exc)

        logger.info("Poll cycle complete: created=%s", len(created_triggers))
        return created_triggers

    async def _fetch_announcements(self, source: TriggerSource, url: str) -> list[NormalizedAnnouncement]:
        response = await self.session.get(url)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "").lower()
        payload = self._decode_payload(response.text, content_type)
        rows = self._extract_rows(source, payload)
        return [self._normalize_row(source=source, row=row, base_url=url) for row in rows]

    def _decode_payload(self, body: str, content_type: str) -> Any:
        if "json" in content_type:
            return json.loads(body)

        parsed = feedparser.parse(body)
        if parsed.entries:
            return {"entries": parsed.entries}

        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {}

    def _extract_rows(self, source: TriggerSource, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]

        if not isinstance(payload, dict):
            return []

        if "entries" in payload and isinstance(payload["entries"], list):
            entries: list[dict[str, Any]] = []
            for entry in payload["entries"]:
                entries.append(
                    {
                        "desc": entry.get("title", ""),
                        "attchmntFile": entry.get("link", ""),
                        "an_dt": entry.get("published", ""),
                        "symbol": entry.get("symbol"),
                        "sm_name": entry.get("company"),
                    }
                )
            return entries

        if source == TriggerSource.NSE_RSS:
            for key in ("data", "rows", "announcements"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [row for row in value if isinstance(row, dict)]

        if source == TriggerSource.BSE_RSS:
            for key in ("Table", "Data", "data", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [row for row in value if isinstance(row, dict)]

        return []

    def _normalize_row(self, source: TriggerSource, row: dict[str, Any], base_url: str) -> NormalizedAnnouncement:
        title = self._pick_str(row, ["desc", "headline", "News_Sub", "title", "subject"], default="")
        raw_content = self._pick_str(
            row,
            ["desc", "details", "description", "News_Sub", "title", "subject"],
            default=title,
        )
        company_symbol = self._pick_str(
            row,
            ["symbol", "sm_symbol", "SCRIP_CD", "scrip_cd", "scripcode"],
            default=None,
        )
        company_name = self._pick_str(
            row,
            ["sm_name", "companyName", "company_name", "CompanyName", "scripname"],
            default=None,
        )
        sector = self._pick_str(row, ["industry", "sector"], default=None)
        source_url = self._pick_str(
            row,
            ["attchmntFile", "link", "url", "attachment", "Attachment"],
            default="",
        )
        source_url = urljoin(base_url, source_url) if source_url else self._synthetic_source_url(source, row)
        published_at = self._parse_date(
            self._pick_str(
                row,
                ["an_dt", "an_date", "news_date", "News_submission_dt", "date", "published"],
                default=None,
            )
        )
        document_urls = self._extract_document_urls(row=row, base_url=base_url)

        return NormalizedAnnouncement(
            source=source,
            source_url=source_url,
            title=title or raw_content[:120],
            raw_content=raw_content,
            company_symbol=company_symbol,
            company_name=company_name,
            sector=sector,
            published_at=published_at,
            document_urls=document_urls,
        )

    async def _create_new_triggers(self, announcements: list[NormalizedAnnouncement]) -> list[TriggerEvent]:
        created: list[TriggerEvent] = []
        for announcement in announcements:
            if await self.trigger_repo.exists_by_url(announcement.source_url):
                continue

            trigger = TriggerEvent(
                source=announcement.source,
                source_url=announcement.source_url,
                source_feed_title=announcement.title,
                source_feed_published=announcement.published_at,
                company_symbol=announcement.company_symbol,
                company_name=announcement.company_name,
                sector=announcement.sector,
                raw_content=announcement.raw_content,
                priority=TriggerPriority.NORMAL,
            )
            await self.trigger_repo.save(trigger)
            created.append(trigger)
        return created

    def _extract_document_urls(self, row: dict[str, Any], base_url: str) -> list[str]:
        urls: list[str] = []
        for key in ("attchmntFile", "link", "url", "attachment", "Attachment", "attachments"):
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                urls.append(urljoin(base_url, value.strip()))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item.strip():
                        urls.append(urljoin(base_url, item.strip()))
                    elif isinstance(item, dict):
                        nested = self._pick_str(item, ["url", "link", "href"], default=None)
                        if nested:
                            urls.append(urljoin(base_url, nested))

        # Remove duplicates while preserving order.
        seen: set[str] = set()
        deduped: list[str] = []
        for candidate in urls:
            if candidate not in seen:
                seen.add(candidate)
                deduped.append(candidate)
        return deduped

    def _synthetic_source_url(self, source: TriggerSource, row: dict[str, Any]) -> str:
        raw = "|".join(
            [
                source.value,
                self._pick_str(row, ["desc", "headline", "title"], default=""),
                self._pick_str(row, ["an_dt", "date", "published"], default=""),
                self._pick_str(row, ["symbol", "sm_symbol", "SCRIP_CD"], default=""),
            ]
        )
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        return f"urn:tuj:{source.value}:{digest}"

    def _pick_str(self, row: dict[str, Any], keys: list[str], default: str | None = "") -> str | None:
        for key in keys:
            value = row.get(key)
            if value is None:
                continue
            if isinstance(value, str):
                stripped = value.strip()
                if stripped:
                    return stripped
            elif isinstance(value, (int, float)):
                return str(value)
        return default

    def _parse_date(self, value: str | None) -> datetime | None:
        if not value:
            return None

        for fmt in (
            "%d-%b-%Y",
            "%d-%b-%Y %H:%M:%S",
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
            "%d/%m/%Y",
            "%d/%m/%Y %H:%M:%S",
        ):
            try:
                parsed = datetime.strptime(value, fmt)
                return parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None


class NSERSSPoller(ExchangeRSSPoller):
    """Backward-compatible alias for exchange poller used in current task docs."""
