"""API endpoints for admin watchlist and agent policy views."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.models.company import Company, Sector, WatchlistConfig

router = APIRouter(prefix="/api/v1/watchlist", tags=["watchlist"])

_DEFAULT_AGENT_POLICY_PATH = "config/agent_access_policy.yaml"

_DEFAULT_DOMAINS = ["triggers", "documents", "reports", "notes", "users", "licenses"]
_DEFAULT_ACTIONS = ["read", "create", "update", "delete"]


class WatchlistCompanyRow(BaseModel):
    """Admin watchlist company row."""

    symbol: str
    name: str
    sector: str
    priority: str
    aliases: list[str] = Field(default_factory=list)
    status: str
    last_trigger: datetime | None = None
    total_investigations: int = 0
    current_recommendation: str = "none"


class WatchlistSectorRow(BaseModel):
    """Admin watchlist sector row."""

    sector_name: str
    keywords: list[str] = Field(default_factory=list)
    companies_count: int = 0


class WatchlistOverviewResponse(BaseModel):
    """Admin watchlist overview payload."""

    watchlist_path: str
    watchlist_loaded_at: datetime | None = None
    companies: list[WatchlistCompanyRow]
    sectors: list[WatchlistSectorRow]


class AgentPermissionRow(BaseModel):
    """Flattened agent permission row."""

    agent: str
    domain: str
    actions: list[str] = Field(default_factory=list)


class AgentPolicyResponse(BaseModel):
    """Agent policy placeholder payload."""

    source: str
    policy_path: str
    exists: bool
    last_loaded_at: datetime | None = None
    editable_in_ui: bool = False
    domains: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    permissions: list[AgentPermissionRow] = Field(default_factory=list)


def _coerce_datetime(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _db(request: Request) -> Any:
    db = getattr(request.app.state, "mongo_db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Database is not configured")
    return db


def _watchlist_from_state(request: Request) -> WatchlistConfig:
    watchlist = getattr(request.app.state, "watchlist", None)
    if not isinstance(watchlist, WatchlistConfig):
        raise HTTPException(status_code=503, detail="Watchlist is not configured")
    return watchlist


def _resolve_sector(company: Company, sectors: list[Sector]) -> str:
    if company.sector:
        return company.sector
    if len(sectors) == 1:
        return sectors[0].name
    return "Unassigned"


def _flatten_permissions(payload: Any) -> list[AgentPermissionRow]:
    rows: list[AgentPermissionRow] = []
    if not isinstance(payload, list):
        return rows

    for entry in payload:
        if not isinstance(entry, dict):
            continue
        agent = str(entry.get("agent") or entry.get("name") or "").strip()
        if not agent:
            continue
        permissions = entry.get("permissions")
        if not isinstance(permissions, list):
            continue
        for permission in permissions:
            if not isinstance(permission, dict):
                continue
            domain = str(permission.get("domain") or "").strip().lower()
            if not domain:
                continue
            actions = permission.get("actions")
            if not isinstance(actions, list):
                actions = []
            normalized_actions = [str(action).strip().lower() for action in actions if str(action).strip()]
            rows.append(AgentPermissionRow(agent=agent, domain=domain, actions=normalized_actions))
    return rows


async def _triggers_by_symbol(db: Any, symbols: list[str]) -> dict[str, datetime | None]:
    if not symbols:
        return {}
    pipeline = [
        {"$match": {"company_symbol": {"$in": symbols}}},
        {"$group": {"_id": "$company_symbol", "last_trigger": {"$max": "$created_at"}}},
    ]
    result: dict[str, datetime | None] = {}
    async for row in db["triggers"].aggregate(pipeline):
        symbol = str(row.get("_id") or "").upper()
        if not symbol:
            continue
        result[symbol] = _coerce_datetime(row.get("last_trigger"))
    return result


async def _investigation_counts_by_symbol(db: Any, symbols: list[str]) -> dict[str, int]:
    if not symbols:
        return {}
    pipeline = [
        {"$match": {"company_symbol": {"$in": symbols}}},
        {"$group": {"_id": "$company_symbol", "count": {"$sum": 1}}},
    ]
    result: dict[str, int] = {}
    async for row in db["investigations"].aggregate(pipeline):
        symbol = str(row.get("_id") or "").upper()
        if not symbol:
            continue
        result[symbol] = int(row.get("count") or 0)
    return result


async def _recommendations_by_symbol(db: Any, symbols: list[str]) -> dict[str, str]:
    if not symbols:
        return {}
    cursor = db["positions"].find(
        {"company_symbol": {"$in": symbols}},
        projection={"company_symbol": 1, "current_recommendation": 1, "_id": 0},
    )
    result: dict[str, str] = {}
    async for row in cursor:
        symbol = str(row.get("company_symbol") or "").upper()
        if not symbol:
            continue
        result[symbol] = str(row.get("current_recommendation") or "none").lower()
    return result


@router.get("/overview", response_model=WatchlistOverviewResponse)
async def watchlist_overview(request: Request) -> WatchlistOverviewResponse:
    """Return watchlist, runtime coverage, and recommendation summary for admin UI."""
    watchlist = _watchlist_from_state(request)
    db = _db(request)

    symbols = [company.symbol.upper() for company in watchlist.companies]
    trigger_map = await _triggers_by_symbol(db, symbols)
    investigation_map = await _investigation_counts_by_symbol(db, symbols)
    recommendation_map = await _recommendations_by_symbol(db, symbols)

    sector_counts: dict[str, int] = {}
    company_rows: list[WatchlistCompanyRow] = []
    for company in watchlist.companies:
        symbol = company.symbol.upper()
        sector = _resolve_sector(company, watchlist.sectors)
        sector_counts[sector] = sector_counts.get(sector, 0) + 1

        company_rows.append(
            WatchlistCompanyRow(
                symbol=symbol,
                name=company.name,
                sector=sector,
                priority=company.priority,
                aliases=company.aliases,
                status="active" if company.monitoring_active else "paused",
                last_trigger=trigger_map.get(symbol),
                total_investigations=investigation_map.get(symbol, 0),
                current_recommendation=recommendation_map.get(symbol, "none"),
            )
        )

    sector_rows = [
        WatchlistSectorRow(
            sector_name=sector.name,
            keywords=sector.keywords,
            companies_count=sector_counts.get(sector.name, 0),
        )
        for sector in watchlist.sectors
    ]

    watchlist_path = str(getattr(request.app.state, "watchlist_path", "config/watchlist.yaml"))
    loaded_at = _coerce_datetime(getattr(request.app.state, "watchlist_loaded_at", None))

    return WatchlistOverviewResponse(
        watchlist_path=watchlist_path,
        watchlist_loaded_at=loaded_at,
        companies=company_rows,
        sectors=sector_rows,
    )


@router.get("/agent-policy", response_model=AgentPolicyResponse)
async def agent_policy_placeholder(request: Request) -> AgentPolicyResponse:
    """Return agent access policy source/path for admin placeholder view."""
    policy_path = str(getattr(request.app.state, "agent_policy_path", _DEFAULT_AGENT_POLICY_PATH))
    path = Path(policy_path)
    if not path.is_absolute():
        path = Path.cwd() / path

    if not path.exists():
        return AgentPolicyResponse(
            source="config_file",
            policy_path=str(path),
            exists=False,
            last_loaded_at=None,
            editable_in_ui=False,
            domains=list(_DEFAULT_DOMAINS),
            actions=list(_DEFAULT_ACTIONS),
            permissions=[],
        )

    try:
        with path.open(encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Unable to read agent policy file: {exc}") from exc

    if not isinstance(payload, dict):
        payload = {}

    domains = payload.get("domains")
    if not isinstance(domains, list):
        domains = list(_DEFAULT_DOMAINS)
    normalized_domains = [str(domain).strip().lower() for domain in domains if str(domain).strip()]

    actions = payload.get("actions")
    if not isinstance(actions, list):
        actions = list(_DEFAULT_ACTIONS)
    normalized_actions = [str(action).strip().lower() for action in actions if str(action).strip()]

    permissions = _flatten_permissions(payload.get("agents"))
    last_loaded_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return AgentPolicyResponse(
        source="config_file",
        policy_path=str(path),
        exists=True,
        last_loaded_at=last_loaded_at,
        editable_in_ui=False,
        domains=normalized_domains,
        actions=normalized_actions,
        permissions=permissions,
    )
