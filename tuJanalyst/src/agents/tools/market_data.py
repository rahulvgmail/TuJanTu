"""Market data tool for Indian equities via yfinance."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable

from src.models.investigation import MarketDataSnapshot
from src.utils.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Return timezone-aware current UTC timestamp."""
    return datetime.now(timezone.utc)


class MarketDataTool:
    """Fetch market snapshot for NSE/BSE listed symbols."""

    def __init__(
        self,
        *,
        ticker_factory: Callable[[str], Any] | None = None,
        now_fn: Callable[[], datetime] = utc_now,
        circuit_breaker_failure_threshold: int = 3,
        circuit_breaker_recovery_seconds: int = 120,
        circuit_time_fn: Callable[[], float] | None = None,
    ):
        self._ticker_factory = ticker_factory
        self._now_fn = now_fn
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=circuit_breaker_failure_threshold,
            recovery_seconds=float(circuit_breaker_recovery_seconds),
            time_fn=circuit_time_fn or time.monotonic,
        )

    async def get_snapshot(self, symbol: str) -> MarketDataSnapshot:
        """Return market snapshot for `<symbol>`, trying `.NS` then `.BO`."""
        if self._circuit_breaker.is_open():
            logger.warning(
                "Market data circuit breaker open; skipping request: retry_in=%.1fs",
                self._circuit_breaker.seconds_until_close(),
            )
            return MarketDataSnapshot(data_source="market_data_circuit_open")

        normalized = symbol.strip().upper()
        if not normalized:
            return MarketDataSnapshot(data_source="yfinance_unavailable")

        try:
            ticker, info = self._get_first_available_ticker(normalized)
            if ticker is None or info is None:
                logger.warning("No market data found for %s", normalized)
                return MarketDataSnapshot(data_source="yfinance_unavailable")

            snapshot = MarketDataSnapshot(
                current_price=self._to_float(info.get("regularMarketPrice") or info.get("currentPrice")),
                market_cap_cr=self._to_crores(self._to_float(info.get("marketCap"))),
                pe_ratio=self._to_float(info.get("trailingPE")),
                pb_ratio=self._to_float(info.get("priceToBook")),
                week_52_high=self._to_float(info.get("fiftyTwoWeekHigh")),
                week_52_low=self._to_float(info.get("fiftyTwoWeekLow")),
                avg_volume_30d=self._to_int(info.get("averageVolume")),
                price_change_1d=self._to_float(info.get("regularMarketChangePercent")),
                price_change_1w=None,
                price_change_1m=None,
                sector_pe_avg=None,
                fii_holding_pct=None,
                dii_holding_pct=None,
                promoter_holding_pct=None,
                promoter_pledge_pct=None,
                data_source="yfinance",
                data_timestamp=self._now_fn(),
            )
            self._apply_price_changes_from_history(snapshot, ticker)
            self._circuit_breaker.record_success()
            return snapshot

        except Exception as exc:  # noqa: BLE001
            self._circuit_breaker.record_failure()
            logger.warning("Market data fetch failed for %s: %s", normalized, exc)
            return MarketDataSnapshot(data_source=f"error: {exc}")

    def _get_first_available_ticker(self, symbol: str) -> tuple[Any | None, dict[str, Any] | None]:
        nse_ticker = self._build_ticker(f"{symbol}.NS")
        nse_info = self._safe_info(nse_ticker)
        if self._has_price(nse_info):
            return nse_ticker, nse_info

        bse_ticker = self._build_ticker(f"{symbol}.BO")
        bse_info = self._safe_info(bse_ticker)
        if self._has_price(bse_info):
            return bse_ticker, bse_info

        return None, None

    def _build_ticker(self, symbol_code: str) -> Any:
        if self._ticker_factory is not None:
            return self._ticker_factory(symbol_code)

        import yfinance as yf

        return yf.Ticker(symbol_code)

    def _safe_info(self, ticker: Any) -> dict[str, Any]:
        info = getattr(ticker, "info", None)
        return info if isinstance(info, dict) else {}

    def _has_price(self, info: dict[str, Any]) -> bool:
        return info.get("regularMarketPrice") is not None or info.get("currentPrice") is not None

    def _apply_price_changes_from_history(self, snapshot: MarketDataSnapshot, ticker: Any) -> None:
        try:
            history = ticker.history(period="1mo")
            closes = self._extract_closing_values(history)
            if not closes:
                return

            latest = closes[-1]
            if len(closes) >= 5:
                snapshot.price_change_1w = self._pct_change(latest, closes[-5])
            if len(closes) >= 20:
                snapshot.price_change_1m = self._pct_change(latest, closes[0])
        except Exception:  # noqa: BLE001
            return

    def _extract_closing_values(self, history: Any) -> list[float]:
        try:
            close_series = history["Close"]
        except Exception:  # noqa: BLE001
            return []

        if hasattr(close_series, "tolist"):
            raw_values = close_series.tolist()
        else:
            try:
                raw_values = list(close_series)
            except Exception:  # noqa: BLE001
                return []

        values: list[float] = []
        for value in raw_values:
            as_float = self._to_float(value)
            if as_float is not None:
                values.append(as_float)
        return values

    def _pct_change(self, latest: float, base: float) -> float | None:
        if base == 0:
            return None
        return ((latest / base) - 1) * 100

    def _to_crores(self, value: float | None) -> float | None:
        if value is None:
            return None
        return round(value / 10_000_000, 2)

    def _to_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _to_int(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
