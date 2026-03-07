"""Tests for company master repository operations."""

from __future__ import annotations

import pytest

from src.models.symbol_resolution import CompanyMaster
from src.repositories.mongo import MongoCompanyMasterRepository


@pytest.fixture
def company_master_repo(mongo_db):
    return MongoCompanyMasterRepository(mongo_db)


@pytest.mark.asyncio
async def test_company_master_repo_upsert_and_lookup(company_master_repo: MongoCompanyMasterRepository) -> None:
    company = CompanyMaster(
        nse_symbol="SBIN",
        bse_scrip_code="500112",
        isin="INE062A01020",
        company_name="State Bank of India",
        aliases=["SBI"],
        tags=["public_sector_bank"],
    )

    await company_master_repo.upsert(company)

    by_nse = await company_master_repo.get_by_nse_symbol("sbin")
    by_bse = await company_master_repo.get_by_bse_scrip_code("500112")
    by_isin = await company_master_repo.get_by_isin("ine062a01020")

    assert by_nse is not None
    assert by_nse.company_name == "State Bank of India"
    assert by_bse is not None
    assert by_bse.nse_symbol == "SBIN"
    assert by_isin is not None
    assert by_isin.bse_scrip_code == "500112"


@pytest.mark.asyncio
async def test_company_master_repo_search_by_name_and_tag(company_master_repo: MongoCompanyMasterRepository) -> None:
    await company_master_repo.upsert(
        CompanyMaster(
            nse_symbol="SBIN",
            bse_scrip_code="500112",
            company_name="State Bank of India",
            aliases=["SBI"],
            tags=["public_sector_bank"],
        )
    )
    await company_master_repo.upsert(
        CompanyMaster(
            nse_symbol="PNB",
            bse_scrip_code="532461",
            company_name="Punjab National Bank",
            aliases=["PNB"],
            tags=["public_sector_bank"],
        )
    )

    search_rows = await company_master_repo.search_by_name("state bank", limit=5)
    tag_rows = await company_master_repo.list_by_tag("public_sector_bank", limit=5)

    assert len(search_rows) == 1
    assert search_rows[0].nse_symbol == "SBIN"
    assert len(tag_rows) == 2
