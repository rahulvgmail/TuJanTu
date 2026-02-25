"""Tests for DSPy gate signature/module setup."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.dspy_modules.gate import GateModule, build_dspy_model_identifier, configure_dspy_lm


def test_build_dspy_model_identifier() -> None:
    assert build_dspy_model_identifier("anthropic", "claude-haiku") == "anthropic/claude-haiku"
    assert build_dspy_model_identifier("openai", "openai/gpt-4o-mini") == "openai/gpt-4o-mini"


def test_configure_dspy_lm_requires_api_key_for_remote_provider() -> None:
    with pytest.raises(ValueError):
        configure_dspy_lm(provider="anthropic", model="claude-haiku", api_key=None)


def test_configure_dspy_lm_invokes_dspy(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeLM:
        def __init__(self, identifier: str, **kwargs):
            captured["identifier"] = identifier
            captured["kwargs"] = kwargs

    def fake_configure(*, lm):
        captured["configured_lm"] = lm

    monkeypatch.setattr("src.dspy_modules.gate.dspy.LM", FakeLM)
    monkeypatch.setattr("src.dspy_modules.gate.dspy.configure", fake_configure)

    lm = configure_dspy_lm(
        provider="openai",
        model="gpt-4o-mini",
        api_key="test-key",
        base_url="https://example.test",
    )

    assert captured["identifier"] == "openai/gpt-4o-mini"
    assert captured["kwargs"] == {"api_key": "test-key", "api_base": "https://example.test"}
    assert captured["configured_lm"] is lm


def test_gate_module_returns_prediction(monkeypatch: pytest.MonkeyPatch) -> None:
    module = GateModule()
    monkeypatch.setattr(
        module,
        "classifier",
        lambda **_: SimpleNamespace(is_worth_investigating=True, reason="Quarterly results with metrics"),
    )

    result = module(
        announcement_text="Q3 financial results released",
        company_name="Inox Wind Limited",
        sector="Capital Goods",
    )

    assert result.is_worth_investigating is True
    assert "Quarterly results" in result.reason

