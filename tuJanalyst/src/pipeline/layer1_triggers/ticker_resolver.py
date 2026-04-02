"""Canonical NSE/BSE ticker resolution service."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from src.models.symbol_resolution import CompanyMaster, ResolutionInput, ResolutionMethod, ResolutionResult
from src.repositories.base import CompanyMasterRepository

_TITLE_COMPANY_SEPARATORS = (" - ", " – ", ":")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


class TickerResolver:
    """Resolve mixed exchange identifiers into canonical company metadata."""

    def __init__(
        self,
        *,
        company_master_repo: CompanyMasterRepository,
        web_lookup: Any | None = None,
        dspy_resolver: Any | None = None,
        fuzzy_threshold: float = 0.92,
        review_threshold: float = 0.9,
        enable_web_fallback: bool = True,
        enable_dspy_fallback: bool = False,
    ):
        self.company_master_repo = company_master_repo
        self.web_lookup = web_lookup
        self.dspy_resolver = dspy_resolver
        self.fuzzy_threshold = max(0.0, min(1.0, float(fuzzy_threshold)))
        self.review_threshold = max(0.0, min(1.0, float(review_threshold)))
        self.enable_web_fallback = enable_web_fallback
        self.enable_dspy_fallback = enable_dspy_fallback

    async def resolve(self, payload: ResolutionInput) -> ResolutionResult:
        """Resolve to canonical identity using deterministic-first lookup order."""
        if payload.raw_symbol:
            by_symbol = await self._resolve_by_raw_symbol(payload.raw_symbol)
            if by_symbol is not None:
                return by_symbol

        if payload.isin:
            match = await self.company_master_repo.get_by_isin(payload.isin)
            if match is not None:
                return self._build_resolved(
                    match,
                    method=ResolutionMethod.EXACT_ISIN,
                    confidence=1.0,
                    evidence=[f"isin:{payload.isin}"],
                )

        by_name = await self._resolve_by_name(payload)
        if by_name is not None:
            return by_name

        if self.enable_web_fallback and self.web_lookup is not None:
            by_web = await self._resolve_by_web(payload)
            if by_web is not None:
                return by_web

        if self.enable_dspy_fallback and self.dspy_resolver is not None:
            by_dspy = await self._resolve_by_dspy(payload)
            if by_dspy is not None:
                return by_dspy

        return ResolutionResult(
            method=ResolutionMethod.UNRESOLVED,
            confidence=0.0,
            resolved=False,
            review_required=True,
            evidence=["unresolved"],
        )

    async def _resolve_by_raw_symbol(self, raw_symbol: str) -> ResolutionResult | None:
        if raw_symbol.isdigit():
            match = await self.company_master_repo.get_by_bse_scrip_code(raw_symbol)
            if match is not None:
                return self._build_resolved(
                    match,
                    method=ResolutionMethod.EXACT_BSE_CODE,
                    confidence=1.0,
                    evidence=[f"bse_scrip_code:{raw_symbol}"],
                )
            return None

        match = await self.company_master_repo.get_by_nse_symbol(raw_symbol)
        if match is not None:
            return self._build_resolved(
                match,
                method=ResolutionMethod.EXACT_SYMBOL,
                confidence=1.0,
                evidence=[f"nse_symbol:{raw_symbol}"],
            )
        return None

    async def _resolve_by_name(self, payload: ResolutionInput) -> ResolutionResult | None:
        names = self._candidate_names(payload)
        if not names:
            return None

        for candidate_name in names:
            rows = await self.company_master_repo.search_by_name(candidate_name, limit=15)
            if not rows:
                continue

            exact = self._exact_name_match(candidate_name, rows)
            if exact is not None:
                return self._build_resolved(
                    exact,
                    method=ResolutionMethod.EXACT_NAME,
                    confidence=0.98,
                    evidence=[f"company_name:{candidate_name}"],
                )

            fuzzy_match, fuzzy_score = self._best_fuzzy_match(candidate_name, rows)
            if fuzzy_match is not None and fuzzy_score >= self.fuzzy_threshold:
                return self._build_resolved(
                    fuzzy_match,
                    method=ResolutionMethod.FUZZY_NAME,
                    confidence=round(float(fuzzy_score), 4),
                    evidence=[f"fuzzy_name:{candidate_name}"],
                )

        return None

    async def _resolve_by_web(self, payload: ResolutionInput) -> ResolutionResult | None:
        query = self._fallback_query(payload)
        if not query:
            return None
        candidate = await self.web_lookup.lookup(query)
        if not isinstance(candidate, dict):
            return None

        nse_symbol = str(candidate.get("nse_symbol") or "").strip().upper()
        bse_code = str(candidate.get("bse_scrip_code") or "").strip()
        isin = str(candidate.get("isin") or "").strip().upper()

        match: CompanyMaster | None = None
        if nse_symbol:
            match = await self.company_master_repo.get_by_nse_symbol(nse_symbol)
        if match is None and bse_code:
            match = await self.company_master_repo.get_by_bse_scrip_code(bse_code)
        if match is None and isin:
            match = await self.company_master_repo.get_by_isin(isin)
        if match is None:
            return None

        return self._build_resolved(
            match,
            method=ResolutionMethod.WEB,
            confidence=0.85,
            evidence=[f"web_query:{query}"],
        )

    async def _resolve_by_dspy(self, payload: ResolutionInput) -> ResolutionResult | None:
        if not hasattr(self.dspy_resolver, "resolve"):
            return None
        raw_result = await self.dspy_resolver.resolve(payload)
        if not isinstance(raw_result, dict):
            return None

        nse_symbol = str(raw_result.get("nse_symbol") or "").strip().upper()
        bse_code = str(raw_result.get("bse_scrip_code") or "").strip()
        isin = str(raw_result.get("isin") or "").strip().upper()
        dspy_company_name = str(raw_result.get("company_name") or "").strip()
        dspy_confidence = min(float(raw_result.get("confidence") or 0.7), 0.85)

        if not nse_symbol and not bse_code and not isin:
            return None

        # Try to match against company_master first
        match: CompanyMaster | None = None
        if nse_symbol:
            match = await self.company_master_repo.get_by_nse_symbol(nse_symbol)
        if match is None and bse_code:
            match = await self.company_master_repo.get_by_bse_scrip_code(bse_code)
        if match is None and isin:
            match = await self.company_master_repo.get_by_isin(isin)

        if match is not None:
            return self._build_resolved(
                match,
                method=ResolutionMethod.DSPY,
                confidence=dspy_confidence,
                evidence=[f"dspy_react:{raw_result.get('reason', 'web_search')}"],
            )

        # No company_master match — build result directly from DSPy output
        # This handles companies not yet in the master (new listings, micro-caps)
        return ResolutionResult(
            method=ResolutionMethod.DSPY,
            confidence=dspy_confidence,
            resolved=True,
            review_required=True,
            nse_symbol=nse_symbol or None,
            bse_scrip_code=bse_code or None,
            isin=isin or None,
            company_name=dspy_company_name or None,
            evidence=[f"dspy_react_unverified:{raw_result.get('reason', 'web_search')}"],
        )

    def _build_resolved(
        self,
        company: CompanyMaster,
        *,
        method: ResolutionMethod,
        confidence: float,
        evidence: list[str],
    ) -> ResolutionResult:
        return ResolutionResult(
            method=method,
            confidence=confidence,
            resolved=True,
            review_required=confidence < self.review_threshold,
            canonical_id=company.canonical_id,
            nse_symbol=company.nse_symbol,
            bse_scrip_code=company.bse_scrip_code,
            isin=company.isin,
            company_name=company.company_name,
            evidence=evidence,
        )

    def _candidate_names(self, payload: ResolutionInput) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for candidate in [payload.company_name, self._title_prefix(payload.title)]:
            text = str(candidate or "").strip()
            if not text:
                continue
            lowered = text.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            names.append(text)
        return names

    def _title_prefix(self, title: str | None) -> str | None:
        text = str(title or "").strip()
        if not text:
            return None
        for separator in _TITLE_COMPANY_SEPARATORS:
            if separator in text:
                candidate = text.split(separator, 1)[0].strip()
                if candidate:
                    return candidate
        return None

    def _exact_name_match(self, query: str, rows: list[CompanyMaster]) -> CompanyMaster | None:
        normalized_query = self._normalize_name(query)
        for row in rows:
            candidates = [row.company_name, *row.aliases]
            for candidate in candidates:
                if self._normalize_name(candidate) == normalized_query:
                    return row
        return None

    def _best_fuzzy_match(self, query: str, rows: list[CompanyMaster]) -> tuple[CompanyMaster | None, float]:
        normalized_query = self._normalize_name(query)
        best_row: CompanyMaster | None = None
        best_score = 0.0
        for row in rows:
            for candidate in [row.company_name, *row.aliases]:
                score = SequenceMatcher(None, normalized_query, self._normalize_name(candidate)).ratio()
                if score > best_score:
                    best_score = score
                    best_row = row
        return best_row, best_score

    def _normalize_name(self, value: str) -> str:
        return _NON_ALNUM.sub(" ", str(value or "").strip().lower()).strip()

    def _fallback_query(self, payload: ResolutionInput) -> str:
        for candidate in [payload.company_name, self._title_prefix(payload.title), payload.raw_symbol]:
            text = str(candidate or "").strip()
            if text:
                return text
        return ""

