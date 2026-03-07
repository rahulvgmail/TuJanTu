"""Tests for symbol resolution and company master models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models.symbol_resolution import CompanyMaster, ResolutionInput, ResolutionMethod, ResolutionResult


def test_company_master_normalizes_identifiers() -> None:
    company = CompanyMaster(
        nse_symbol=" sbin ",
        bse_scrip_code=500112,
        isin=" ine062a01020 ",
        company_name="State Bank of India",
        aliases=[" SBI ", "sbi"],
    )

    assert company.nse_symbol == "SBIN"
    assert company.bse_scrip_code == "500112"
    assert company.isin == "INE062A01020"
    assert company.aliases == ["SBI"]


def test_resolution_result_confidence_bounds() -> None:
    with pytest.raises(ValidationError):
        ResolutionResult(
            method=ResolutionMethod.EXACT_SYMBOL,
            confidence=1.2,
            resolved=False,
        )


def test_resolution_input_symbol_normalization() -> None:
    payload = ResolutionInput(raw_symbol=" sbin ", source_exchange="nse")

    assert payload.raw_symbol == "SBIN"
