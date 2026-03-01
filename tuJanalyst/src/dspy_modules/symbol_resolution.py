"""DSPy module for fallback ticker resolution."""

from __future__ import annotations

import dspy

from src.dspy_modules.signatures import TickerResolution


class TickerResolutionModule(dspy.Module):
    """Wrapper around DSPy signature for ticker fallback resolution."""

    def __init__(self):
        super().__init__()
        self.predictor = dspy.Predict(TickerResolution)

    def forward(self, raw_symbol: str, company_name: str, title: str, content: str):
        return self.predictor(
            raw_symbol=raw_symbol,
            company_name=company_name,
            title=title,
            content=content,
        )

