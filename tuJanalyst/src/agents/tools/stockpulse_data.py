"""Higher-level tool that wraps StockPulseClient to produce TechnicalContext for agent consumption."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.agents.tools.stockpulse_client import StockPulseClient
from src.models.stockpulse import StockPulseIndicators
from src.models.technical_context import TechnicalContext

logger = logging.getLogger(__name__)

# DMA / WMA period keys used by StockPulse indicators
_DMA_PERIODS = ("10", "20", "50", "100", "200")
_WMA_PERIODS = ("5", "10", "20", "30")


class StockPulseDataTool:
    """Fetches and assembles technical context from StockPulse for agent consumption."""

    def __init__(self, client: StockPulseClient):
        self.client = client

    async def get_technical_context(self, symbol: str) -> TechnicalContext | None:
        """Fetch indicators, events, and stock info from StockPulse.

        Runs 3 API calls concurrently using asyncio.gather.
        Returns None if StockPulse is unreachable or stock not found.
        """
        indicators_raw, events_raw, stock_raw = await asyncio.gather(
            self.client.get_indicators(symbol, period="1d"),
            self.client.get_events(symbol, limit=10),
            self.client.get_stock(symbol),
            return_exceptions=True,
        )

        # If indicators call raised or returned None, we can't build meaningful context.
        if isinstance(indicators_raw, BaseException):
            logger.warning(
                "StockPulse indicators call failed for %s: %s", symbol, indicators_raw,
            )
            indicators_raw = None
        if indicators_raw is None:
            logger.info("No indicator data from StockPulse for %s; returning None", symbol)
            return None

        # Treat exceptions in non-critical calls as empty results.
        if isinstance(events_raw, BaseException):
            logger.warning("StockPulse events call failed for %s: %s", symbol, events_raw)
            events_raw = []
        if isinstance(stock_raw, BaseException):
            logger.warning("StockPulse stock call failed for %s: %s", symbol, stock_raw)
            stock_raw = None

        # Parse indicators through the Pydantic model for validation / defaults.
        indicators = StockPulseIndicators.model_validate(indicators_raw)

        # Build moving-average signal dicts.
        dma_signals = self._extract_ma_signals(indicators_raw, indicators, "dma", _DMA_PERIODS)
        wma_signals = self._extract_ma_signals(indicators_raw, indicators, "wma", _WMA_PERIODS)

        # Derive color from stock response.
        color: str | None = None
        if isinstance(stock_raw, dict):
            color = stock_raw.get("color")

        # Build recent_events list.
        recent_events: list[dict[str, Any]] = []
        if isinstance(events_raw, list):
            for evt in events_raw:
                if isinstance(evt, dict):
                    recent_events.append({
                        "event_type": evt.get("event_type", "UNKNOWN"),
                        "payload": evt.get("payload") or {},
                        "created_at": evt.get("created_at", ""),
                    })

        context = TechnicalContext(
            symbol=symbol,
            current_price=indicators.current_price,
            pct_change=indicators.pct_change,
            dma_signals=dma_signals,
            wma_signals=wma_signals,
            is_52w_high_intraday=indicators.is_52w_high_intraday,
            is_52w_closing_high=indicators.is_52w_closing_high,
            high_52w=indicators.high_52w,
            is_volume_breakout=indicators.is_volume_breakout,
            today_volume=indicators.today_volume,
            max_vol_21d=indicators.max_vol_21d,
            avg_vol_140d=indicators.avg_vol_140d,
            gap_pct=indicators.gap_pct,
            is_gap_up=indicators.is_gap_up,
            is_gap_down=indicators.is_gap_down,
            is_90d_high=indicators.is_90d_high,
            is_90d_low_touch=indicators.is_90d_low_touch,
            is_biweek_bo=indicators.is_biweek_bo,
            is_week_bo=indicators.is_week_bo,
            days_to_result=indicators.days_to_result,
            result_within_7d=indicators.result_within_7d,
            result_within_10d=indicators.result_within_10d,
            result_within_15d=indicators.result_within_15d,
            result_declared_10d=indicators.result_declared_10d,
            color=color,
            recent_events=recent_events,
            screener_names=[],
        )

        logger.debug("Built TechnicalContext for %s: price=%s", symbol, context.current_price)
        return context

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_ma_signals(
        raw: dict[str, Any],
        parsed: StockPulseIndicators,
        prefix: str,
        periods: tuple[str, ...],
    ) -> dict[str, str | None]:
        """Extract moving-average signals, handling both flat and nested response shapes.

        Flat shape:   {"dma_10_signal": "Hold", ...}
        Nested shape: {"dma_10": {"signal": "Hold", ...}, ...}
        """
        signals: dict[str, str | None] = {}
        for period in periods:
            key = f"{prefix}_{period}"
            signal: str | None = None

            # Try flat key first (e.g. dma_10_signal).
            flat_key = f"{key}_signal"
            if flat_key in raw:
                signal = raw[flat_key]
            else:
                # Fall back to nested object via the parsed Pydantic model.
                entry = getattr(parsed, key, None)
                if entry is not None:
                    signal = getattr(entry, "signal", None)

            signals[period] = signal
        return signals
