"""Tests for deterministic ticker resolution."""

from __future__ import annotations

import pytest

from src.models.symbol_resolution import CompanyMaster, ResolutionInput, ResolutionMethod
from src.pipeline.layer1_triggers.ticker_resolver import TickerResolver
from src.repositories.mongo import MongoCompanyMasterRepository


@pytest.fixture
async def seeded_repo(mongo_db):
    repo = MongoCompanyMasterRepository(mongo_db)
    await repo.upsert(
        CompanyMaster(
            nse_symbol="SBIN",
            bse_scrip_code="500112",
            isin="INE062A01020",
            company_name="State Bank of India",
            aliases=["SBI"],
            tags=["public_sector_bank"],
        )
    )
    await repo.upsert(
        CompanyMaster(
            nse_symbol="PNB",
            bse_scrip_code="532461",
            company_name="Punjab National Bank",
            aliases=["PNB"],
            tags=["public_sector_bank"],
        )
    )
    return repo


@pytest.mark.asyncio
async def test_resolver_prefers_exact_symbol_match(seeded_repo: MongoCompanyMasterRepository) -> None:
    resolver = TickerResolver(company_master_repo=seeded_repo)

    result = await resolver.resolve(ResolutionInput(raw_symbol="sbin", source_exchange="nse"))

    assert result.resolved is True
    assert result.nse_symbol == "SBIN"
    assert result.method == ResolutionMethod.EXACT_SYMBOL
    assert result.confidence == 1.0


@pytest.mark.asyncio
async def test_resolver_maps_bse_scrip_to_nse_symbol(seeded_repo: MongoCompanyMasterRepository) -> None:
    resolver = TickerResolver(company_master_repo=seeded_repo)

    result = await resolver.resolve(ResolutionInput(raw_symbol="500112", source_exchange="bse"))

    assert result.resolved is True
    assert result.nse_symbol == "SBIN"
    assert result.bse_scrip_code == "500112"
    assert result.method == ResolutionMethod.EXACT_BSE_CODE


@pytest.mark.asyncio
async def test_resolver_resolves_by_company_name(seeded_repo: MongoCompanyMasterRepository) -> None:
    resolver = TickerResolver(company_master_repo=seeded_repo)

    result = await resolver.resolve(ResolutionInput(company_name="State Bank of India"))

    assert result.resolved is True
    assert result.nse_symbol == "SBIN"
    assert result.method in {ResolutionMethod.EXACT_NAME, ResolutionMethod.FUZZY_NAME}


@pytest.mark.asyncio
async def test_resolver_returns_unresolved_for_unknown_company(seeded_repo: MongoCompanyMasterRepository) -> None:
    resolver = TickerResolver(company_master_repo=seeded_repo)

    result = await resolver.resolve(ResolutionInput(company_name="Unknown Bank Limited"))

    assert result.resolved is False
    assert result.method == ResolutionMethod.UNRESOLVED
    assert result.review_required is True


@pytest.mark.asyncio
async def test_resolver_uses_dspy_fallback_when_enabled(seeded_repo: MongoCompanyMasterRepository) -> None:
    class _FakeDspyResolver:
        async def resolve(self, payload):  # noqa: ANN001
            del payload
            return {
                "nse_symbol": "SBIN",
                "bse_scrip_code": "500112",
                "isin": "INE062A01020",
                "confidence": 0.72,
                "reason": "Fallback inference",
            }

    resolver = TickerResolver(
        company_master_repo=seeded_repo,
        dspy_resolver=_FakeDspyResolver(),
        enable_dspy_fallback=True,
        enable_web_fallback=False,
    )

    result = await resolver.resolve(ResolutionInput(company_name="Unknown Input"))

    assert result.resolved is True
    assert result.nse_symbol == "SBIN"
    assert result.method == ResolutionMethod.DSPY
