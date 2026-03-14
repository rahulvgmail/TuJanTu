"""Higher-level tool that wraps StockPulseClient to produce TechnicalContext for agent consumption."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.agents.tools.stockpulse_client import StockPulseClient
from src.models.technical_context import TechnicalContext

logger = logging.getLogger(__name__)

# DMA / WMA period keys used by StockPulse indicators
_DMA_PERIODS = ("10", "20", "50", "100", "200")
_WMA_PERIODS = ("5", "10", "20", "30")


class StockPulseDataTool:
    """Fetches and assembles technical context from StockPulse for agent consumption."""

    # High-signal screener IDs to check for membership.
    # Set to None to check all screeners (expensive).
    # Populate with specific IDs after initial StockPulse setup.
    HIGH_SIGNAL_SCREENER_IDS: list[int] | None = None

    def __init__(self, client: StockPulseClient, *, fetch_screeners: bool = False):
        self.client = client
        self.fetch_screeners = fetch_screeners

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

        # Work with the raw dict directly — StockPulse may return flat fields
        # (dma_10, dma_10_signal, dma_10_touch) or nested DMAEntry objects.
        # Using the raw dict avoids Pydantic validation issues with either format.
        ind = indicators_raw

        # Build moving-average signal dicts.
        dma_signals = self._extract_ma_signals(ind, "dma", _DMA_PERIODS)
        wma_signals = self._extract_ma_signals(ind, "wma", _WMA_PERIODS)

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
            current_price=ind.get("current_price"),
            pct_change=ind.get("pct_change"),
            dma_signals=dma_signals,
            wma_signals=wma_signals,
            is_52w_high_intraday=bool(ind.get("is_52w_high_intraday", False)),
            is_52w_closing_high=bool(ind.get("is_52w_closing_high", False)),
            high_52w=ind.get("high_52w"),
            is_volume_breakout=bool(ind.get("is_volume_breakout", False)),
            today_volume=ind.get("today_volume"),
            max_vol_21d=ind.get("max_vol_21d"),
            avg_vol_140d=ind.get("avg_vol_140d"),
            gap_pct=ind.get("gap_pct"),
            is_gap_up=bool(ind.get("is_gap_up", False)),
            is_gap_down=bool(ind.get("is_gap_down", False)),
            is_90d_high=bool(ind.get("is_90d_high", False)),
            is_90d_low_touch=bool(ind.get("is_90d_low_touch", False)),
            is_biweek_bo=bool(ind.get("is_biweek_bo", False)),
            is_week_bo=bool(ind.get("is_week_bo", False)),
            days_to_result=ind.get("days_to_result"),
            result_within_7d=bool(ind.get("result_within_7d", False)),
            result_within_10d=bool(ind.get("result_within_10d", False)),
            result_within_15d=bool(ind.get("result_within_15d", False)),
            result_declared_10d=bool(ind.get("result_declared_10d", False)),
            color=color,
            recent_events=recent_events,
            screener_names=[],
        )

        # Optionally fetch screener membership (separate step — can be slow).
        if self.fetch_screeners:
            try:
                context.screener_names = await self.client.get_screener_membership(
                    symbol, screener_ids=self.HIGH_SIGNAL_SCREENER_IDS,
                )
            except Exception:  # noqa: BLE001
                logger.warning("Failed to fetch screener membership for %s", symbol)

        logger.debug("Built TechnicalContext for %s: price=%s", symbol, context.current_price)
        return context

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_ma_signals(
        raw: dict[str, Any],
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
                # Fall back to nested object.
                entry = raw.get(key)
                if isinstance(entry, dict):
                    signal = entry.get("signal")

            signals[period] = signal
        return signals
