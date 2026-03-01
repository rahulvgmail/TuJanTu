"""API tests for symbol resolution endpoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.symbols import router
from src.models.symbol_resolution import CompanyMaster
from src.repositories.mongo import MongoCompanyMasterRepository


def test_symbol_resolve_endpoint_returns_matches(mongo_db) -> None:
    app = FastAPI()
    app.include_router(router)
    repo = MongoCompanyMasterRepository(mongo_db)

    async def _seed() -> None:
        await repo.upsert(
            CompanyMaster(
                nse_symbol="SBIN",
                bse_scrip_code="500112",
                company_name="State Bank of India",
                aliases=["SBI"],
                tags=["public_sector_bank"],
            )
        )

    import asyncio

    asyncio.run(_seed())

    app.state.company_master_repo = repo
    client = TestClient(app)

    response = client.get("/api/v1/symbols/resolve", params={"q": "state bank"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    assert payload["matches"][0]["nse_symbol"] == "SBIN"


def test_symbol_resolve_endpoint_uses_tag_filter(mongo_db) -> None:
    app = FastAPI()
    app.include_router(router)
    repo = MongoCompanyMasterRepository(mongo_db)

    async def _seed() -> None:
        await repo.upsert(
            CompanyMaster(
                nse_symbol="SBIN",
                company_name="State Bank of India",
                tags=["public_sector_bank"],
            )
        )
        await repo.upsert(
            CompanyMaster(
                nse_symbol="HDFCBANK",
                company_name="HDFC Bank Limited",
                tags=["private_bank"],
            )
        )

    import asyncio

    asyncio.run(_seed())

    app.state.company_master_repo = repo
    client = TestClient(app)

    response = client.get("/api/v1/symbols/resolve", params={"q": "bank", "tag": "public_sector_bank"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["matches"][0]["nse_symbol"] == "SBIN"
