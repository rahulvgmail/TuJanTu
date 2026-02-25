"""API endpoints for recommendation performance tracking."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/performance", tags=["performance"])

_TIMEFRAME_DAYS: dict[str, int] = {
    "short_term": 30,
    "medium_term": 90,
    "long_term": 180,
}

_ACTIONABLE_RECOMMENDATIONS = {"buy", "sell"}


class PerformanceRecommendationRow(BaseModel):
    """A single recommendation outcome row."""

    assessment_id: str
    investigation_id: str
    company_symbol: str
    company_name: str
    recommendation: str
    timeframe: str
    confidence: float
    recommendation_date: datetime
    price_at_recommendation: float | None = None
    price_now: float | None = None
    return_pct: float | None = None
    status: Literal["within_timeframe", "expired"] = "within_timeframe"
    outcome: Literal["win", "loss", "neutral", "unknown"] = "unknown"


class PerformanceRecommendationsResponse(BaseModel):
    """Paged response for recommendation outcomes."""

    items: list[PerformanceRecommendationRow]
    total: int
    limit: int
    offset: int


class PerformanceCall(BaseModel):
    """Best/worst call payload."""

    assessment_id: str
    company_symbol: str
    recommendation: str
    return_pct: float


class PerformanceSummaryResponse(BaseModel):
    """Aggregated recommendation performance metrics."""

    total_recommendations: int
    buy_recommendations: int
    sell_recommendations: int
    hold_recommendations: int
    evaluated_recommendations: int
    wins: int
    win_rate: float
    avg_return_buy: float | None = None
    avg_return_sell: float | None = None
    best_call: PerformanceCall | None = None
    worst_call: PerformanceCall | None = None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct_change(base_price: float | None, latest_price: float | None) -> float | None:
    if base_price is None or latest_price is None:
        return None
    if base_price <= 0:
        return None
    return ((latest_price / base_price) - 1.0) * 100.0


def _status_for_timeframe(
    created_at: datetime,
    timeframe: str,
    now: datetime,
) -> Literal["within_timeframe", "expired"]:
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    else:
        created_at = created_at.astimezone(UTC)
    days = _TIMEFRAME_DAYS.get(timeframe, _TIMEFRAME_DAYS["medium_term"])
    deadline = created_at + timedelta(days=days)
    return "within_timeframe" if now <= deadline else "expired"


def _outcome_for_recommendation(
    recommendation: str,
    return_pct: float | None,
) -> Literal["win", "loss", "neutral", "unknown"]:
    normalized = recommendation.lower().strip()
    if return_pct is None:
        return "unknown"
    if normalized == "buy":
        return "win" if return_pct > 0 else "loss"
    if normalized == "sell":
        return "win" if return_pct < 0 else "loss"
    if normalized == "hold":
        return "neutral"
    return "unknown"


async def _latest_prices_from_history(db: Any, symbols: set[str]) -> dict[str, float | None]:
    prices: dict[str, float | None] = {}
    for symbol in symbols:
        row = await db["investigations"].find_one(
            {
                "company_symbol": symbol,
                "market_data.current_price": {"$ne": None},
            },
            sort=[("created_at", -1)],
            projection={"market_data.current_price": 1, "_id": 0},
        )
        current_price = _as_float(((row or {}).get("market_data") or {}).get("current_price"))
        prices[symbol] = current_price
    return prices


async def _live_prices(
    request: Request,
    symbols: set[str],
    fallback_prices: dict[str, float | None],
) -> dict[str, float | None]:
    tool = getattr(request.app.state, "market_data_tool", None)
    if tool is None:
        return fallback_prices

    async def _fetch(symbol: str) -> tuple[str, float | None]:
        try:
            snapshot = await tool.get_snapshot(symbol)
            price = _as_float(getattr(snapshot, "current_price", None))
            return symbol, price if price is not None else fallback_prices.get(symbol)
        except Exception:  # noqa: BLE001
            return symbol, fallback_prices.get(symbol)

    rows = await asyncio.gather(*(_fetch(symbol) for symbol in symbols))
    return dict(rows)


async def _fetch_assessment_rows(
    db: Any,
    *,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    query = {"recommendation_changed": True}
    total = int(await db["assessments"].count_documents(query))
    cursor = db["assessments"].find(query).sort("created_at", -1).skip(offset).limit(limit)
    items = [row async for row in cursor]
    return items, total


async def _build_rows(
    request: Request,
    *,
    limit: int,
    offset: int,
    include_live_price: bool,
) -> tuple[list[PerformanceRecommendationRow], int]:
    db = getattr(request.app.state, "mongo_db", None)
    if db is None:
        return [], 0

    assessment_rows, total = await _fetch_assessment_rows(db, limit=limit, offset=offset)
    if not assessment_rows:
        return [], total

    investigation_ids = [
        str(row.get("investigation_id") or "")
        for row in assessment_rows
        if row.get("investigation_id")
    ]
    investigations: dict[str, dict[str, Any]] = {}
    if investigation_ids:
        cursor = db["investigations"].find(
            {"investigation_id": {"$in": investigation_ids}},
            projection={
                "investigation_id": 1,
                "market_data.current_price": 1,
                "_id": 0,
            },
        )
        async for row in cursor:
            key = str(row.get("investigation_id") or "")
            if key:
                investigations[key] = row

    symbols = {str(row.get("company_symbol") or "").upper() for row in assessment_rows if row.get("company_symbol")}
    historical_prices = await _latest_prices_from_history(db, symbols)
    latest_prices = (
        await _live_prices(request, symbols, historical_prices)
        if include_live_price
        else historical_prices
    )

    now = datetime.now(UTC)
    items: list[PerformanceRecommendationRow] = []
    for assessment in assessment_rows:
        assessment_id = str(assessment.get("assessment_id") or "")
        investigation_id = str(assessment.get("investigation_id") or "")
        company_symbol = str(assessment.get("company_symbol") or "").upper()
        company_name = str(assessment.get("company_name") or company_symbol)
        recommendation = str(assessment.get("new_recommendation") or "none").lower()
        timeframe = str(assessment.get("timeframe") or "medium_term").lower()
        confidence = _as_float(assessment.get("confidence")) or 0.0
        created_at = assessment.get("created_at")
        if not isinstance(created_at, datetime):
            created_at = now

        investigation = investigations.get(investigation_id, {})
        rec_price = _as_float((investigation.get("market_data") or {}).get("current_price"))
        price_now = latest_prices.get(company_symbol)
        return_pct = _pct_change(rec_price, price_now)
        status = _status_for_timeframe(created_at, timeframe, now)
        outcome = _outcome_for_recommendation(recommendation, return_pct)

        items.append(
            PerformanceRecommendationRow(
                assessment_id=assessment_id,
                investigation_id=investigation_id,
                company_symbol=company_symbol,
                company_name=company_name,
                recommendation=recommendation,
                timeframe=timeframe,
                confidence=confidence,
                recommendation_date=created_at,
                price_at_recommendation=rec_price,
                price_now=price_now,
                return_pct=round(return_pct, 4) if return_pct is not None else None,
                status=status,
                outcome=outcome,
            )
        )

    return items, total


@router.get("/recommendations", response_model=PerformanceRecommendationsResponse)
async def list_recommendation_performance(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    include_live_price: bool = Query(default=False),
) -> PerformanceRecommendationsResponse:
    """Return recommendation-level performance rows."""
    items, total = await _build_rows(
        request,
        limit=limit,
        offset=offset,
        include_live_price=include_live_price,
    )
    return PerformanceRecommendationsResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/summary", response_model=PerformanceSummaryResponse)
async def summarize_recommendation_performance(
    request: Request,
    limit: int = Query(default=200, ge=1, le=1000),
    include_live_price: bool = Query(default=False),
) -> PerformanceSummaryResponse:
    """Return aggregate recommendation performance metrics."""
    items, _ = await _build_rows(
        request,
        limit=limit,
        offset=0,
        include_live_price=include_live_price,
    )

    buy_rows = [item for item in items if item.recommendation == "buy"]
    sell_rows = [item for item in items if item.recommendation == "sell"]
    hold_rows = [item for item in items if item.recommendation == "hold"]

    actionable = [
        item
        for item in items
        if item.recommendation in _ACTIONABLE_RECOMMENDATIONS and item.return_pct is not None
    ]
    wins = sum(1 for item in actionable if item.outcome == "win")
    win_rate = (wins / len(actionable)) if actionable else 0.0

    buy_returns = [item.return_pct for item in buy_rows if item.return_pct is not None]
    sell_returns = [item.return_pct for item in sell_rows if item.return_pct is not None]

    best_call = None
    worst_call = None
    rows_with_return = [item for item in items if item.return_pct is not None]
    if rows_with_return:
        best_row = max(rows_with_return, key=lambda item: float(item.return_pct or 0.0))
        worst_row = min(rows_with_return, key=lambda item: float(item.return_pct or 0.0))
        best_call = PerformanceCall(
            assessment_id=best_row.assessment_id,
            company_symbol=best_row.company_symbol,
            recommendation=best_row.recommendation,
            return_pct=float(best_row.return_pct or 0.0),
        )
        worst_call = PerformanceCall(
            assessment_id=worst_row.assessment_id,
            company_symbol=worst_row.company_symbol,
            recommendation=worst_row.recommendation,
            return_pct=float(worst_row.return_pct or 0.0),
        )

    return PerformanceSummaryResponse(
        total_recommendations=len(items),
        buy_recommendations=len(buy_rows),
        sell_recommendations=len(sell_rows),
        hold_recommendations=len(hold_rows),
        evaluated_recommendations=len(actionable),
        wins=wins,
        win_rate=round(win_rate, 4),
        avg_return_buy=round(sum(buy_returns) / len(buy_returns), 4) if buy_returns else None,
        avg_return_sell=round(sum(sell_returns) / len(sell_returns), 4) if sell_returns else None,
        best_call=best_call,
        worst_call=worst_call,
    )
