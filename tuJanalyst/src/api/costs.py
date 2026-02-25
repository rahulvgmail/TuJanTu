"""API endpoints for estimated API cost summaries."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/costs", tags=["costs"])

_DEFAULT_WEB_SEARCH_COST_PER_CALL_USD: dict[str, float] = {
    "brave": 0.005,
    "tavily": 0.005,
}


class CostSummaryResponse(BaseModel):
    """Estimated cost summary for a selected time window."""

    window_start: datetime
    window_end: datetime
    llm_input_tokens: int
    llm_output_tokens: int
    llm_estimated_cost_usd: float
    web_search_calls: int
    web_search_estimated_cost_usd: float
    total_estimated_cost_usd: float
    completed_reports: int
    cost_per_completed_report_usd: float


def _start_of_today_utc() -> datetime:
    now = datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _pricing_for_model(model_name: str) -> tuple[float, float]:
    """Return `(input_per_million, output_per_million)` USD estimates for an LLM model."""
    normalized = model_name.lower()
    if "haiku" in normalized:
        return 0.8, 4.0
    if "sonnet" in normalized:
        return 3.0, 15.0
    if "opus" in normalized:
        return 15.0, 75.0
    return 3.0, 15.0


def _estimate_llm_cost_usd(model_name: str, input_tokens: int, output_tokens: int) -> float:
    input_per_million, output_per_million = _pricing_for_model(model_name)
    return (input_tokens * input_per_million / 1_000_000) + (output_tokens * output_per_million / 1_000_000)


def _estimate_web_search_cost_per_call(request: Request) -> float:
    settings = getattr(request.app.state, "settings", None)
    provider = str(getattr(settings, "web_search_provider", "none") or "none")
    return _DEFAULT_WEB_SEARCH_COST_PER_CALL_USD.get(provider, 0.0)


async def _aggregate_llm_usage(
    collection: Any,
    *,
    window_start: datetime,
    window_end: datetime,
) -> list[dict[str, int | str]]:
    pipeline = [
        {"$match": {"created_at": {"$gte": window_start, "$lte": window_end}}},
        {
            "$group": {
                "_id": {"$ifNull": ["$llm_model_used", "unknown"]},
                "input_tokens": {"$sum": {"$ifNull": ["$total_input_tokens", 0]}},
                "output_tokens": {"$sum": {"$ifNull": ["$total_output_tokens", 0]}},
            }
        },
    ]

    rows: list[dict[str, int | str]] = []
    async for row in collection.aggregate(pipeline):
        rows.append(
            {
                "model": str(row.get("_id") or "unknown"),
                "input_tokens": int(row.get("input_tokens", 0)),
                "output_tokens": int(row.get("output_tokens", 0)),
            }
        )
    return rows


@router.get("/summary", response_model=CostSummaryResponse)
async def cost_summary(
    request: Request,
    since: datetime | None = None,
    until: datetime | None = None,
) -> CostSummaryResponse:
    """Return estimated LLM + web-search cost metrics for a time window."""
    db = getattr(request.app.state, "mongo_db", None)
    if db is None:
        now = datetime.now(UTC)
        return CostSummaryResponse(
            window_start=since or _start_of_today_utc(),
            window_end=until or now,
            llm_input_tokens=0,
            llm_output_tokens=0,
            llm_estimated_cost_usd=0.0,
            web_search_calls=0,
            web_search_estimated_cost_usd=0.0,
            total_estimated_cost_usd=0.0,
            completed_reports=0,
            cost_per_completed_report_usd=0.0,
        )

    window_start = since or _start_of_today_utc()
    window_end = until or datetime.now(UTC)
    if window_end < window_start:
        raise HTTPException(status_code=400, detail="'until' must be greater than or equal to 'since'")

    llm_rows: list[dict[str, int | str]] = []
    for collection_name in ("investigations", "assessments", "reports"):
        llm_rows.extend(
            await _aggregate_llm_usage(
                db[collection_name],
                window_start=window_start,
                window_end=window_end,
            )
        )

    llm_input_tokens = sum(int(row["input_tokens"]) for row in llm_rows)
    llm_output_tokens = sum(int(row["output_tokens"]) for row in llm_rows)
    llm_estimated_cost_usd = sum(
        _estimate_llm_cost_usd(
            model_name=str(row["model"]),
            input_tokens=int(row["input_tokens"]),
            output_tokens=int(row["output_tokens"]),
        )
        for row in llm_rows
    )

    web_search_calls = 0
    async for row in db["investigations"].aggregate(
        [
            {"$match": {"created_at": {"$gte": window_start, "$lte": window_end}}},
            {"$group": {"_id": None, "calls": {"$sum": {"$ifNull": ["$web_search_calls", 0]}}}},
        ]
    ):
        web_search_calls = int(row.get("calls", 0))

    web_search_cost_per_call_usd = _estimate_web_search_cost_per_call(request)
    web_search_estimated_cost_usd = web_search_calls * web_search_cost_per_call_usd

    completed_reports = int(
        await db["reports"].count_documents(
            {
                "created_at": {"$gte": window_start, "$lte": window_end},
                "delivery_status": {"$in": ["generated", "delivered"]},
            }
        )
    )

    total_estimated_cost_usd = llm_estimated_cost_usd + web_search_estimated_cost_usd
    cost_per_completed_report_usd = total_estimated_cost_usd / completed_reports if completed_reports else 0.0

    return CostSummaryResponse(
        window_start=window_start,
        window_end=window_end,
        llm_input_tokens=llm_input_tokens,
        llm_output_tokens=llm_output_tokens,
        llm_estimated_cost_usd=round(llm_estimated_cost_usd, 6),
        web_search_calls=web_search_calls,
        web_search_estimated_cost_usd=round(web_search_estimated_cost_usd, 6),
        total_estimated_cost_usd=round(total_estimated_cost_usd, 6),
        completed_reports=completed_reports,
        cost_per_completed_report_usd=round(cost_per_completed_report_usd, 6),
    )
