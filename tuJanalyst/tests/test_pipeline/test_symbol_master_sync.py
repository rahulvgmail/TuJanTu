"""Tests for company master seed sync."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from src.pipeline.layer1_triggers.symbol_master_sync import SymbolMasterSync
from src.repositories.mongo import MongoCompanyMasterRepository


@pytest.mark.asyncio
async def test_symbol_master_sync_loads_seed_file(mongo_db) -> None:
    repo = MongoCompanyMasterRepository(mongo_db)
    syncer = SymbolMasterSync(company_master_repo=repo)

    seed_path = Path("config/public_sector_banks_seed.yaml")
    upserted = await syncer.sync_from_seed(seed_path)

    assert upserted >= 10
    sbin = await repo.get_by_nse_symbol("SBIN")
    assert sbin is not None
    assert sbin.bse_scrip_code == "500112"


@pytest.mark.asyncio
async def test_symbol_master_sync_raises_for_missing_file(mongo_db) -> None:
    repo = MongoCompanyMasterRepository(mongo_db)
    syncer = SymbolMasterSync(company_master_repo=repo)

    with pytest.raises(FileNotFoundError):
        await syncer.sync_from_seed("config/does-not-exist.yaml")


@pytest.mark.asyncio
async def test_symbol_master_sync_loads_nse_bse_sources_and_merges(mongo_db) -> None:
    repo = MongoCompanyMasterRepository(mongo_db)
    nse_url = "https://example.test/nse_master.csv"
    bse_url = "https://example.test/bse_master.csv"
    nse_csv = "SYMBOL,NAME OF COMPANY,ISIN NUMBER,SERIES\nSBIN,State Bank of India,INE062A01020,EQ\n"
    bse_csv = "Security Code,Security Id,Security Name,ISIN No\n500112,SBIN,State Bank of India,INE062A01020\n"

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == nse_url:
            return httpx.Response(200, text=nse_csv, headers={"content-type": "text/csv"})
        if str(request.url) == bse_url:
            return httpx.Response(200, text=bse_csv, headers={"content-type": "text/csv"})
        return httpx.Response(404, text="not found")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        syncer = SymbolMasterSync(company_master_repo=repo, session=session)
        upserted = await syncer.sync_from_exchange_sources(nse_url=nse_url, bse_url=bse_url)

    assert upserted == 2
    sbin = await repo.get_by_nse_symbol("SBIN")
    assert sbin is not None
    assert sbin.bse_scrip_code == "500112"
    assert sbin.nse_listed is True
    assert sbin.bse_listed is True
