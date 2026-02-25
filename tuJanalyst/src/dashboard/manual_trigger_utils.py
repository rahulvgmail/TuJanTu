"""Helpers for building manual-trigger payloads from UI input."""

from __future__ import annotations


def build_manual_trigger_payload(
    *,
    company_symbol: str,
    event_summary: str,
    company_name: str = "",
    source_url: str = "",
    triggered_by: str = "",
    notes: str = "",
) -> dict[str, str]:
    """Validate and build payload for `POST /api/v1/triggers/human`."""
    normalized_symbol = company_symbol.strip().upper()
    normalized_summary = event_summary.strip()
    if not normalized_symbol:
        raise ValueError("Company symbol is required")
    if not normalized_summary:
        raise ValueError("Event summary is required")

    payload: dict[str, str] = {
        "company_symbol": normalized_symbol,
        "content": normalized_summary,
    }

    optional_fields = {
        "company_name": company_name.strip(),
        "source_url": source_url.strip(),
        "triggered_by": triggered_by.strip(),
        "notes": notes.strip(),
    }
    payload.update({key: value for key, value in optional_fields.items() if value})
    return payload

