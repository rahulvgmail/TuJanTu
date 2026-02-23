"""Health and lightweight operational stats endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/v1/health", tags=["health"])


def _get_scheduler_status(request: Request) -> tuple[str, dict[str, str | None]]:
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        return "not_initialized", {}
    try:
        status = "running" if scheduler.running else "stopped"
    except Exception:  # noqa: BLE001
        return "unknown", {}

    jobs: dict[str, str | None] = {}
    try:
        for job in scheduler.get_jobs():
            next_run = getattr(job, "next_run_time", None)
            jobs[job.id] = next_run.isoformat() if next_run else None
    except Exception:  # noqa: BLE001
        jobs = {}
    return status, jobs


@router.get("")
async def health_check(request: Request) -> dict[str, Any]:
    """Report core dependency health."""
    mongodb_status = "disconnected"
    chromadb_status = "not_initialized"
    scheduler_status, scheduler_jobs = _get_scheduler_status(request)

    db = getattr(request.app.state, "mongo_db", None)
    if db is not None:
        try:
            await db.command("ping")
            mongodb_status = "connected"
        except Exception:  # noqa: BLE001
            try:
                await db.list_collection_names()
                mongodb_status = "connected"
            except Exception:  # noqa: BLE001
                mongodb_status = "disconnected"

    if getattr(request.app.state, "vector_repo", None) is not None:
        chromadb_status = "connected"

    overall = "healthy" if mongodb_status == "connected" else "unhealthy"
    return {
        "status": overall,
        "mongodb": mongodb_status,
        "chromadb": chromadb_status,
        "scheduler": scheduler_status,
        "scheduler_jobs": scheduler_jobs,
    }


@router.get("/stats")
async def health_stats(request: Request) -> dict[str, Any]:
    """Return lightweight system stats used by internal dashboards."""
    db = getattr(request.app.state, "mongo_db", None)
    if db is None:
        return {
            "triggers_today": 0,
            "gate_pass_rate": 0.0,
            "status_counts": {},
        }

    start_of_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    triggers_collection = db["triggers"]

    triggers_today = await triggers_collection.count_documents({"created_at": {"$gte": start_of_day}})

    status_counts: dict[str, int] = {}
    async for row in triggers_collection.aggregate(
        [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
    ):
        status = row.get("_id") or "unknown"
        status_counts[str(status)] = int(row.get("count", 0))

    total = sum(status_counts.values())
    gate_passed = status_counts.get("gate_passed", 0)
    gate_pass_rate = (gate_passed / total) if total else 0.0

    return {
        "triggers_today": triggers_today,
        "gate_pass_rate": round(gate_pass_rate, 4),
        "status_counts": status_counts,
    }
