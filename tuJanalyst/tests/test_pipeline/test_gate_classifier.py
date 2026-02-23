"""Tests for Layer 2 gate classifier behavior."""

from __future__ import annotations

import logging

from src.dspy_modules.gate import GateDecision
from src.pipeline.layer2_gate.gate_classifier import GateClassifier


class _RecordingModule:
    def __init__(self, decision: GateDecision):
        self.decision = decision
        self.calls: list[dict[str, str]] = []

    def forward(self, announcement_text: str, company_name: str, sector: str) -> GateDecision:
        self.calls.append(
            {
                "announcement_text": announcement_text,
                "company_name": company_name,
                "sector": sector,
            }
        )
        return self.decision


class _FailingModule:
    def forward(self, announcement_text: str, company_name: str, sector: str) -> GateDecision:
        raise RuntimeError("upstream LLM unavailable")


class _FlakyModule:
    def __init__(self, failures_before_success: int):
        self.failures_before_success = failures_before_success
        self.calls = 0

    def forward(self, announcement_text: str, company_name: str, sector: str) -> GateDecision:
        del announcement_text, company_name, sector
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise TimeoutError("transient timeout")
        return GateDecision(is_worth_investigating=True, reason="Recovered after retries")


def test_gate_classifier_truncates_input_and_returns_structured_result(caplog) -> None:
    caplog.set_level(logging.INFO)
    long_text = "A" * 2500
    module = _RecordingModule(GateDecision(is_worth_investigating=True, reason="Quarterly results update"))
    classifier = GateClassifier(
        model="claude-haiku",
        module=module,
        configure_lm=False,
    )

    result = classifier.classify(announcement_text=long_text, company_name=" ", sector="")

    assert result == {
        "passed": True,
        "reason": "Quarterly results update",
        "method": "llm_classification",
        "model": "claude-haiku",
    }
    assert len(module.calls) == 1
    assert len(module.calls[0]["announcement_text"]) == 2000
    assert module.calls[0]["company_name"] == "Unknown"
    assert module.calls[0]["sector"] == "Unknown"
    assert "Gate PASSED: Quarterly results update" in caplog.text


def test_gate_classifier_logs_rejection_result(caplog) -> None:
    caplog.set_level(logging.INFO)
    module = _RecordingModule(GateDecision(is_worth_investigating=False, reason="Routine compliance notice"))
    classifier = GateClassifier(
        model="claude-haiku",
        module=module,
        configure_lm=False,
    )

    result = classifier.classify(announcement_text="Routine filing", company_name="Inox Wind", sector="Capital Goods")

    assert result["passed"] is False
    assert result["method"] == "llm_classification"
    assert "Gate REJECTED: Routine compliance notice" in caplog.text


def test_gate_classifier_fail_open_on_module_error(caplog) -> None:
    caplog.set_level(logging.WARNING)
    classifier = GateClassifier(
        model="claude-haiku",
        module=_FailingModule(),
        configure_lm=False,
    )

    result = classifier.classify(announcement_text="Important corporate update", company_name="Inox Wind", sector="")

    assert result["passed"] is True
    assert result["method"] == "error_fallthrough"
    assert result["model"] == "claude-haiku"
    assert "fail-open policy" in result["reason"]
    assert "Gate classification failed; applying fail-open policy" in caplog.text


def test_gate_classifier_retries_transient_failures_before_success() -> None:
    module = _FlakyModule(failures_before_success=2)
    classifier = GateClassifier(
        model="claude-haiku",
        module=module,  # type: ignore[arg-type]
        configure_lm=False,
    )

    result = classifier.classify(announcement_text="Material update", company_name="ABB", sector="Industrial")

    assert result["passed"] is True
    assert result["method"] == "llm_classification"
    assert module.calls == 3
