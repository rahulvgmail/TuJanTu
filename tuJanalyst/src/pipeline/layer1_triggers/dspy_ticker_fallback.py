"""DSPy-based fallback resolver for ticker mapping."""

from __future__ import annotations

import json
from typing import Any

from src.dspy_modules.gate import configure_dspy_lm
from src.dspy_modules.symbol_resolution import TickerResolutionModule
from src.models.symbol_resolution import ResolutionInput
from src.utils.retry import is_transient_error, retry_in_thread
from src.utils.token_usage import run_with_dspy_usage


class DspyTickerFallbackResolver:
    """Run DSPy ticker inference only when deterministic/web resolution fails."""

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        api_key: str | None,
        base_url: str | None = None,
        module: TickerResolutionModule | None = None,
    ):
        configure_dspy_lm(provider=provider, model=model, api_key=api_key, base_url=base_url)
        self.module = module or TickerResolutionModule()

    async def resolve(self, payload: ResolutionInput) -> dict[str, Any]:
        """Return parsed ticker identifiers from DSPy output."""

        def _call():
            return self.module(
                raw_symbol=payload.raw_symbol or "",
                company_name=payload.company_name or "",
                title=payload.title or "",
                content=(payload.content or "")[:4000],
            )

        prediction, _, _ = await retry_in_thread(
            lambda: run_with_dspy_usage(_call),
            attempts=2,
            base_delay_seconds=0.2,
            should_retry=is_transient_error,
        )
        raw_json = str(getattr(prediction, "resolution_json", "") or "").strip()
        if not raw_json:
            return {}
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, dict):
            return {}
        return {
            "nse_symbol": str(parsed.get("nse_symbol") or "").strip().upper(),
            "bse_scrip_code": str(parsed.get("bse_scrip_code") or "").strip(),
            "isin": str(parsed.get("isin") or "").strip().upper(),
            "confidence": float(parsed.get("confidence") or 0.0),
            "reason": str(parsed.get("reason") or "").strip(),
        }

