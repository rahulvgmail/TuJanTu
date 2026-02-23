"""Layer 2 watchlist filter for fast signal/noise reduction."""

from __future__ import annotations

from dataclasses import dataclass

from src.config import load_watchlist_config
from src.models.trigger import TriggerEvent


@dataclass(frozen=True)
class FilterResult:
    passed: bool
    reason: str
    method: str


class WatchlistFilter:
    """Apply low-cost watchlist and keyword gates before LLM classification."""

    def __init__(self, watchlist_path: str = "config/watchlist.yaml"):
        watchlist = load_watchlist_config(watchlist_path)
        self._symbols = {company.symbol.upper() for company in watchlist.companies}
        self._names = {
            candidate.lower(): company.symbol.upper()
            for company in watchlist.companies
            for candidate in [company.name, *company.aliases]
            if candidate.strip()
        }
        self._sectors = {sector.name.lower() for sector in watchlist.sectors}
        self._keywords = {
            keyword.lower()
            for sector in watchlist.sectors
            for keyword in sector.keywords
            if keyword.strip()
        }
        self._global_keywords = {keyword.lower() for keyword in watchlist.global_keywords if keyword.strip()}

    def check(self, trigger: TriggerEvent) -> FilterResult:
        """Return structured pass/reject result for a trigger."""
        symbol = (trigger.company_symbol or "").strip().upper()
        company_name = (trigger.company_name or "").strip().lower()
        sector = (trigger.sector or "").strip().lower()
        content = " ".join(
            [
                (trigger.raw_content or "").lower(),
                (trigger.source_feed_title or "").lower(),
            ]
        ).strip()

        # 1) Explicit symbol match.
        if symbol and symbol in self._symbols:
            return FilterResult(True, f"Watched symbol matched: {symbol}", "symbol_match")

        # 2) Company name / alias substring match.
        if company_name:
            for name_or_alias, matched_symbol in self._names.items():
                if name_or_alias in company_name:
                    return FilterResult(
                        True,
                        f"Watched company/alias matched: {name_or_alias} ({matched_symbol})",
                        "name_match",
                    )

        # 3) Sector-gated keyword check.
        if sector and sector in self._sectors:
            matched_keyword = self._find_keyword(content)
            if matched_keyword:
                return FilterResult(
                    True,
                    f"Watched sector + keyword matched: {matched_keyword}",
                    "keyword_match",
                )
            return FilterResult(False, "Watched sector matched but no relevant keywords found", "sector_no_keyword")

        # 4) Content scan for known company names/aliases/symbols.
        for name_or_alias, matched_symbol in self._names.items():
            if name_or_alias in content:
                return FilterResult(
                    True,
                    f"Company mention in content: {name_or_alias} ({matched_symbol})",
                    "content_scan",
                )
        for watched_symbol in self._symbols:
            if watched_symbol.lower() in content:
                return FilterResult(
                    True,
                    f"Company symbol mention in content: {watched_symbol}",
                    "content_scan",
                )

        return FilterResult(False, "No watchlist symbol/name/sector-keyword match", "no_match")

    def _find_keyword(self, content: str) -> str | None:
        for keyword in sorted(self._keywords | self._global_keywords):
            if keyword in content:
                return keyword
        return None
