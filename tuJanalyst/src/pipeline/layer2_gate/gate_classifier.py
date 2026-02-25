"""Service wrapper around DSPy GateModule for Layer 2 classification."""

from __future__ import annotations

import logging
import time

from src.dspy_modules.gate import GateModule, configure_dspy_lm
from src.utils.retry import is_transient_error, retry_sync

logger = logging.getLogger(__name__)


class GateClassifier:
    """Applies cheap LLM gating with operational safeguards."""

    def __init__(
        self,
        model: str,
        provider: str = "anthropic",
        api_key: str | None = None,
        base_url: str | None = None,
        max_input_chars: int = 2000,
        gate_module: GateModule | None = None,
        configure_lm: bool = True,
    ):
        self.model = model
        self.provider = provider
        self.max_input_chars = max_input_chars

        if configure_lm:
            configure_dspy_lm(provider=provider, model=model, api_key=api_key, base_url=base_url)

        self.gate_module = gate_module or GateModule()

    def classify(self, announcement_text: str, company_name: str = "", sector: str = "") -> dict[str, str | bool]:
        """Return pass/reject gate decision with method and reason."""
        text = self._truncate(announcement_text)
        company = (company_name or "").strip() or "Unknown"
        sector_value = (sector or "").strip() or "Unknown"

        try:
            started = time.time()
            prediction = retry_sync(
                lambda: self.gate_module(
                    announcement_text=text,
                    company_name=company,
                    sector=sector_value,
                ),
                attempts=3,
                base_delay_seconds=0.2,
                should_retry=is_transient_error,
            )
            result = {
                "passed": bool(prediction.is_worth_investigating),
                "reason": str(prediction.reason).strip() or "No reason provided",
                "method": "llm_classification",
                "model": self.model,
            }
            status_label = "PASSED" if result["passed"] else "REJECTED"
            logger.info("Gate %s: %s", status_label, result["reason"])
            logger.info(
                "Gate LLM call: model=%s input_tokens=%s output_tokens=%s latency_seconds=%.4f",
                self.model,
                len(text.split()),
                len(result["reason"].split()),
                time.time() - started,
            )
            return result
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gate classification failed; applying fail-open policy: %s", exc)
            return {
                "passed": True,
                "reason": f"Gate classifier failure, passed by fail-open policy: {exc}",
                "method": "error_fallthrough",
                "model": self.model,
            }

    def _truncate(self, text: str) -> str:
        if len(text) <= self.max_input_chars:
            return text
        return text[: self.max_input_chars]
