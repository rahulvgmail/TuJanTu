"""Exchange announcement pollers for NSE/BSE trigger ingestion."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import feedparser
import httpx

from src.models.trigger import TriggerEvent, TriggerPriority, TriggerSource
from src.repositories.base import TriggerRepository

logger = logging.getLogger(__name__)

_TRACKING_QUERY_PREFIXES = ("utm_",)
_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "source",
}
_NSE_SCRIP_CODE_FROM_URL = re.compile(r"(?:^|_)(\d{5,10})(?:_|\.|$)")
_TITLE_COMPANY_SEPARATORS = (" - ", " – ", ":")


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
        dedup_cache_ttl_seconds: int = 1800,
        dedup_lookback_days: int = 14,
        dedup_recent_limit: int = 5000,
    ):
        self.trigger_repo = trigger_repo
        self.nse_url = nse_url
        self.bse_url = bse_url
        self.dedup_cache_ttl_seconds = max(1, int(dedup_cache_ttl_seconds))
        self.dedup_lookback_days = max(1, int(dedup_lookback_days))
        self.dedup_recent_limit = max(1, int(dedup_recent_limit))
        self._known_dedup_keys: set[str] = set()
        self._dedup_cache_seeded_at: datetime | None = None
        self._supports_recent_listing = callable(getattr(trigger_repo, "list_recent", None))
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
        await self._refresh_dedup_cache_if_needed()
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
                        "symbol": (
                            entry.get("symbol")
                            or entry.get("sm_symbol")
                            or entry.get("nse_symbol")
                            or entry.get("nseSymbol")
                            or entry.get("scrip_cd")
                            or entry.get("scripCode")
                        ),
                        "sm_name": (
                            entry.get("company")
                            or entry.get("sm_name")
                            or entry.get("company_name")
                            or entry.get("author")
                        ),
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
            [
                "symbol",
                "sm_symbol",
                "smSymbol",
                "nse_symbol",
                "nseSymbol",
                "SCRIP_CD",
                "scrip_cd",
                "scripcode",
                "scripCode",
                "script_code",
                "scriptCode",
            ],
            default=None,
        )
        company_name = self._pick_str(
            row,
            ["sm_name", "company", "companyName", "company_name", "CompanyName", "scripname", "name"],
            default=None,
        )
        sector = self._pick_str(row, ["industry", "sector"], default=None)
        source_url = self._pick_str(
            row,
            ["attchmntFile", "link", "url", "attachment", "Attachment"],
            default="",
        )
        source_url = urljoin(base_url, source_url) if source_url else self._synthetic_source_url(source, row)
        source_url = self._canonicalize_url(source_url)
        company_symbol = self._infer_company_symbol(
            source=source,
            row=row,
            source_url=source_url,
            title=title,
            raw_content=raw_content,
            existing_symbol=company_symbol,
        )
        company_name = self._infer_company_name(title=title, existing_name=company_name)
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
            dedup_keys = self._announcement_dedup_keys(announcement)
            if await self._is_duplicate(dedup_keys):
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
            self._remember_dedup_keys(dedup_keys)
            created.append(trigger)
        return created

    def _extract_document_urls(self, row: dict[str, Any], base_url: str) -> list[str]:
        urls: list[str] = []
        for key in ("attchmntFile", "link", "url", "attachment", "Attachment", "attachments"):
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                urls.append(self._canonicalize_url(urljoin(base_url, value.strip())))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item.strip():
                        urls.append(self._canonicalize_url(urljoin(base_url, item.strip())))
                    elif isinstance(item, dict):
                        nested = self._pick_str(item, ["url", "link", "href"], default=None)
                        if nested:
                            urls.append(self._canonicalize_url(urljoin(base_url, nested)))

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

    def _infer_company_symbol(
        self,
        *,
        source: TriggerSource,
        row: dict[str, Any],
        source_url: str,
        title: str,
        raw_content: str,
        existing_symbol: str | None,
    ) -> str | None:
        if existing_symbol:
            return existing_symbol.strip().upper()

        row_symbol = self._pick_str(
            row,
            [
                "symbol",
                "sm_symbol",
                "smSymbol",
                "nse_symbol",
                "nseSymbol",
                "SCRIP_CD",
                "scrip_cd",
                "scripcode",
                "scripCode",
                "script_code",
                "scriptCode",
            ],
            default=None,
        )
        if row_symbol:
            return row_symbol.strip().upper()

        if source == TriggerSource.NSE_RSS:
            inferred_scrip = self._extract_nse_scrip_code_from_url(source_url)
            if inferred_scrip:
                return inferred_scrip

        inline_symbol = self._extract_inline_symbol(text=f"{title} {raw_content}")
        if inline_symbol:
            return inline_symbol
        return None

    def _infer_company_name(self, *, title: str, existing_name: str | None) -> str | None:
        if existing_name:
            return existing_name.strip()

        for separator in _TITLE_COMPANY_SEPARATORS:
            if separator not in title:
                continue
            candidate = title.split(separator, 1)[0].strip()
            if candidate:
                return candidate
        return None

    def _extract_nse_scrip_code_from_url(self, source_url: str) -> str | None:
        parsed = urlparse(source_url)
        file_name = parsed.path.rsplit("/", 1)[-1]
        for value in (file_name, parsed.path):
            if not value:
                continue
            match = _NSE_SCRIP_CODE_FROM_URL.search(value)
            if match:
                return match.group(1)
        return None

    def _extract_inline_symbol(self, text: str) -> str | None:
        match = re.search(r"\b(?:nse\s*symbol|symbol)\s*[:\-]\s*([A-Z0-9]{2,15})\b", text, flags=re.IGNORECASE)
        if not match:
            return None
        return match.group(1).upper()

    async def _refresh_dedup_cache_if_needed(self) -> None:
        if not self._supports_recent_listing:
            return

        now = datetime.now(timezone.utc)
        if self._dedup_cache_seeded_at is not None:
            elapsed = (now - self._dedup_cache_seeded_at).total_seconds()
            if elapsed < self.dedup_cache_ttl_seconds:
                return

        try:
            list_recent = getattr(self.trigger_repo, "list_recent")
            recent = await list_recent(
                limit=self.dedup_recent_limit,
                since=now - timedelta(days=self.dedup_lookback_days),
            )
            keys: set[str] = set()
            for trigger in recent:
                keys.update(self._trigger_dedup_keys(trigger))
            self._known_dedup_keys = keys
            self._dedup_cache_seeded_at = now
            logger.info("RSS dedup cache refreshed: keys=%s", len(keys))
        except Exception as exc:  # noqa: BLE001
            logger.warning("RSS dedup cache refresh failed; falling back to per-item checks: %s", exc)
            self._supports_recent_listing = False

    async def _is_duplicate(self, dedup_keys: set[str]) -> bool:
        if dedup_keys & self._known_dedup_keys:
            return True

        if not self._supports_recent_listing:
            for key in dedup_keys:
                if not key:
                    continue
                if await self.trigger_repo.exists_by_url(key):
                    self._remember_dedup_keys(dedup_keys)
                    return True

        return False

    def _remember_dedup_keys(self, dedup_keys: set[str]) -> None:
        self._known_dedup_keys.update(dedup_keys)

    def _announcement_dedup_keys(self, announcement: NormalizedAnnouncement) -> set[str]:
        keys: set[str] = set()
        if announcement.source_url:
            keys.add(announcement.source_url)
            base_url = self._base_url_without_query(announcement.source_url)
            if base_url:
                keys.add(base_url)

        for url in announcement.document_urls:
            if not url:
                continue
            keys.add(url)
            base_url = self._base_url_without_query(url)
            if base_url:
                keys.add(base_url)

        keys.add(
            self._content_dedup_key(
                source=str(announcement.source.value),
                title=announcement.title,
                raw_content=announcement.raw_content,
                company_symbol=announcement.company_symbol,
                published_at=announcement.published_at,
            )
        )
        return {key for key in keys if key}

    def _trigger_dedup_keys(self, trigger: TriggerEvent) -> set[str]:
        keys: set[str] = set()
        source_url = self._canonicalize_url(trigger.source_url or "")
        if source_url:
            keys.add(source_url)
            base_url = self._base_url_without_query(source_url)
            if base_url:
                keys.add(base_url)

        keys.add(
            self._content_dedup_key(
                source=str(trigger.source),
                title=trigger.source_feed_title or "",
                raw_content=trigger.raw_content or "",
                company_symbol=trigger.company_symbol,
                published_at=trigger.source_feed_published,
            )
        )
        return {key for key in keys if key}

    def _content_dedup_key(
        self,
        *,
        source: str,
        title: str,
        raw_content: str,
        company_symbol: str | None,
        published_at: datetime | None,
    ) -> str:
        canonical = "|".join(
            [
                source.strip().lower(),
                (company_symbol or "").strip().upper(),
                (published_at.isoformat() if published_at else ""),
                " ".join((title or "").split()).lower(),
                " ".join((raw_content or "").split()).lower()[:512],
            ]
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]
        return f"urn:tuj:dedup:{digest}"

    def _canonicalize_url(self, value: str) -> str:
        url = (value or "").strip()
        if not url:
            return ""

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return url

        clean_query_pairs: list[tuple[str, str]] = []
        for key, item in parse_qsl(parsed.query, keep_blank_values=False):
            lowered = key.lower()
            if lowered.startswith(_TRACKING_QUERY_PREFIXES) or lowered in _TRACKING_QUERY_KEYS:
                continue
            clean_query_pairs.append((key, item))
        clean_query_pairs.sort()

        path = parsed.path or "/"
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")

        return urlunparse(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                path,
                "",
                urlencode(clean_query_pairs, doseq=True),
                "",
            )
        )

    def _base_url_without_query(self, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"}:
            return value
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

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
