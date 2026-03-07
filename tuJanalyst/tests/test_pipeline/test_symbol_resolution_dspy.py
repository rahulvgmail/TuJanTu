"""Tests for DSPy ticker fallback resolver adapter."""

from __future__ import annotations

import json

import pytest

from src.models.symbol_resolution import ResolutionInput
from src.pipeline.layer1_triggers.dspy_ticker_fallback import DspyTickerFallbackResolver


class _FakePrediction:
    def __init__(self, payload: dict[str, object]) -> None:
        self.resolution_json = json.dumps(payload)


class _FakeModule:
    def __call__(self, raw_symbol: str, company_name: str, title: str, content: str):  # noqa: ARG002
        return _FakePrediction(
            {
                "nse_symbol": "SBIN",
                "bse_scrip_code": "500112",
                "isin": "INE062A01020",
                "confidence": 0.77,
                "reason": "mocked",
            }
        )


@pytest.mark.asyncio
async def test_dspy_ticker_fallback_parses_resolution_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.pipeline.layer1_triggers.dspy_ticker_fallback.configure_dspy_lm",
        lambda **kwargs: None,  # noqa: ARG005
    )

    resolver = DspyTickerFallbackResolver(
        provider="openai",
        model="gpt-4o-mini",
        api_key="key",
        module=_FakeModule(),
    )

    result = await resolver.resolve(ResolutionInput(company_name="State Bank of India"))

    assert result["nse_symbol"] == "SBIN"
    assert result["bse_scrip_code"] == "500112"
    assert result["isin"] == "INE062A01020"
    assert float(result["confidence"]) == 0.77
