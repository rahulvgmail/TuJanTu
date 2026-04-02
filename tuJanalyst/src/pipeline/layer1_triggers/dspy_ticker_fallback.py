"""DSPy-based fallback resolver for ticker mapping.

Uses a ReAct agent with web search to identify company tickers when all
deterministic resolution methods fail.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.dspy_modules.gate import configure_dspy_lm
from src.dspy_modules.react_ticker_resolver import (
    TickerReActResolver,
    make_web_search_tool,
)
from src.dspy_modules.symbol_resolution import TickerResolutionModule
from src.models.symbol_resolution import ResolutionInput
from src.utils.retry import is_transient_error, retry_in_thread
from src.utils.token_usage import run_with_dspy_usage

logger = logging.getLogger(__name__)


class DspyTickerFallbackResolver:
    """Run DSPy ReAct ticker resolution with web search when deterministic methods fail."""

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        api_key: str | None,
        base_url: str | None = None,
        search_tool: Any = None,
        module: TickerResolutionModule | None = None,
    ):
        configure_dspy_lm(provider=provider, model=model, api_key=api_key, base_url=base_url)
        # ReAct agent with web search (preferred)
        search_fn = make_web_search_tool(search_tool) if search_tool is not None else None
        self.react_module = TickerReActResolver(search_fn=search_fn)
        # Plain Predict fallback (if ReAct fails)
        self.predict_module = module or TickerResolutionModule()

    async def resolve(self, payload: ResolutionInput) -> dict[str, Any]:
        """Return parsed ticker identifiers, trying ReAct first then plain Predict."""
        # Try ReAct agent with web search
        result = await self._try_react(payload)
        if result and result.get("nse_symbol"):
            logger.info(
                "ReAct ticker resolution succeeded: %s -> %s (confidence=%.2f)",
                payload.company_name or payload.raw_symbol or "?",
                result.get("nse_symbol"),
                result.get("confidence", 0),
            )
            return result

        # Fall back to plain Predict (no web search)
        result = await self._try_predict(payload)
        if result and result.get("nse_symbol"):
            logger.info(
                "Predict ticker resolution succeeded: %s -> %s",
                payload.company_name or payload.raw_symbol or "?",
                result.get("nse_symbol"),
            )
        return result

    async def _try_react(self, payload: ResolutionInput) -> dict[str, Any]:
        """Run ReAct agent with web search."""
        try:
            def _call():
                return self.react_module(
                    company_name=payload.company_name or payload.title or "",
                    raw_content=(payload.content or "")[:500],
                    source_url=payload.source_url or "",
                )

            prediction, _, _ = await retry_in_thread(
                lambda: run_with_dspy_usage(_call),
                attempts=2,
                base_delay_seconds=0.5,
                should_retry=is_transient_error,
            )
            return self._parse_resolution_json(prediction)
        except Exception as exc:
            logger.warning("ReAct ticker resolution failed, falling back to Predict: %s", exc)
            return {}

    async def _try_predict(self, payload: ResolutionInput) -> dict[str, Any]:
        """Run plain DSPy Predict (no tools)."""
        try:
            def _call():
                return self.predict_module(
                    raw_symbol=payload.raw_symbol or "",
                    company_name=payload.company_name or "",
                    title=payload.title or "",
                    content=(payload.content or "")[:4000],
                )

            prediction, _, _ = await retry_in_thread(
                lambda: run_with_dspy_usage(_call),
                attempts=2,
                base_delay_seconds=0.2,
                should_retry=is_transient_error,
            )
            return self._parse_resolution_json(prediction)
        except Exception as exc:
            logger.warning("Predict ticker resolution failed: %s", exc)
            return {}

    def _parse_resolution_json(self, prediction: Any) -> dict[str, Any]:
        """Extract structured resolution from DSPy prediction."""
        raw_json = str(getattr(prediction, "resolution_json", "") or "").strip()
        if not raw_json:
            return {}
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, dict):
            return {}
        return {
            "nse_symbol": str(parsed.get("nse_symbol") or "").strip().upper(),
            "bse_scrip_code": str(parsed.get("bse_scrip_code") or "").strip(),
            "isin": str(parsed.get("isin") or "").strip().upper(),
            "company_name": str(parsed.get("company_name") or "").strip(),
            "confidence": float(parsed.get("confidence") or 0.0),
            "reason": str(parsed.get("reason") or "").strip(),
        }
