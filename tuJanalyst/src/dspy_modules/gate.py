"""DSPy gate module and provider-agnostic model configuration."""

from __future__ import annotations

from typing import Any

import dspy

from src.dspy_modules.signatures import GateClassification


def build_dspy_model_identifier(provider: str, model: str) -> str:
    """Build DSPy model identifier in `<provider>/<model>` format."""
    provider_clean = provider.strip().lower()
    model_clean = model.strip()
    if "/" in model_clean:
        return model_clean
    return f"{provider_clean}/{model_clean}"


def configure_dspy_lm(
    *,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None = None,
) -> Any:
    """Configure DSPy language model with provider-agnostic settings."""
    provider_clean = provider.strip().lower()
    if provider_clean in {"anthropic", "openai", "azure"} and not api_key:
        raise ValueError(f"API key is required for provider '{provider_clean}'")

    identifier = build_dspy_model_identifier(provider=provider_clean, model=model)
    kwargs: dict[str, Any] = {}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["api_base"] = base_url

    lm = dspy.LM(identifier, **kwargs)
    dspy.configure(lm=lm)
    return lm


class GateModule(dspy.Module):
    """DSPy module wrapper around the gate classification signature."""

    def __init__(self):
        super().__init__()
        self.classifier = dspy.Predict(GateClassification)

    def forward(self, announcement_text: str, company_name: str, sector: str):
        return self.classifier(
            announcement_text=announcement_text,
            company_name=company_name,
            sector=sector,
        )

