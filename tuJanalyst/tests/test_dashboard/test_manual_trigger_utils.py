"""Unit tests for manual trigger payload helpers."""

from __future__ import annotations

import pytest

from src.dashboard.manual_trigger_utils import build_manual_trigger_payload


def test_build_manual_trigger_payload_requires_symbol_and_summary() -> None:
    with pytest.raises(ValueError, match="Company symbol is required"):
        build_manual_trigger_payload(company_symbol="  ", event_summary="Some event")

    with pytest.raises(ValueError, match="Event summary is required"):
        build_manual_trigger_payload(company_symbol="SUZLON", event_summary="   ")


def test_build_manual_trigger_payload_normalizes_and_keeps_optional_fields() -> None:
    payload = build_manual_trigger_payload(
        company_symbol=" suzlon ",
        event_summary="  Quarterly results announced  ",
        company_name=" Suzlon Energy ",
        source_url=" https://example.com/announcement ",
        triggered_by=" analyst-1 ",
        notes=" Priority review ",
    )

    assert payload == {
        "company_symbol": "SUZLON",
        "content": "Quarterly results announced",
        "company_name": "Suzlon Energy",
        "source_url": "https://example.com/announcement",
        "triggered_by": "analyst-1",
        "notes": "Priority review",
    }

