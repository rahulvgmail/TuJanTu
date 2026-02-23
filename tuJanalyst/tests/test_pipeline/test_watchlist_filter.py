"""Tests for Layer 2 watchlist filter matching cascade."""

from __future__ import annotations

from src.models.trigger import TriggerEvent, TriggerSource
from src.pipeline.layer2_gate.watchlist_filter import WatchlistFilter


def _make_trigger(**overrides):
    payload = {
        "source": TriggerSource.NSE_RSS,
        "raw_content": "General announcement",
        "company_symbol": None,
        "company_name": None,
        "sector": None,
        "source_feed_title": None,
    }
    payload.update(overrides)
    return TriggerEvent(**payload)


def test_watchlist_filter_symbol_match() -> None:
    gate = WatchlistFilter("config/watchlist.yaml")
    trigger = _make_trigger(company_symbol="INOXWIND")

    result = gate.check(trigger)

    assert result["passed"] is True
    assert result["method"] == "symbol_match"


def test_watchlist_filter_name_alias_match() -> None:
    gate = WatchlistFilter("config/watchlist.yaml")
    trigger = _make_trigger(company_name="Inox Wind")

    result = gate.check(trigger)

    assert result["passed"] is True
    assert result["method"] == "name_match"


def test_watchlist_filter_sector_keyword_match() -> None:
    gate = WatchlistFilter("config/watchlist.yaml")
    trigger = _make_trigger(
        sector="Capital Goods - Electrical Equipment",
        raw_content="Board approves quarterly results and order book update",
    )

    result = gate.check(trigger)

    assert result["passed"] is True
    assert result["method"] == "keyword_match"


def test_watchlist_filter_sector_without_keyword_rejects() -> None:
    gate = WatchlistFilter("config/watchlist.yaml")
    trigger = _make_trigger(
        sector="Capital Goods - Electrical Equipment",
        raw_content="Routine procedural notice with no material updates",
    )

    result = gate.check(trigger)

    assert result["passed"] is False
    assert result["method"] == "sector_no_keyword"


def test_watchlist_filter_unwatched_company_rejects() -> None:
    gate = WatchlistFilter("config/watchlist.yaml")
    trigger = _make_trigger(
        company_symbol="UNKNOWNCO",
        company_name="Unknown Company Limited",
        raw_content="Random disclosure",
    )

    result = gate.check(trigger)

    assert result["passed"] is False
    assert result["method"] == "no_match"


def test_watchlist_filter_content_scan_match() -> None:
    gate = WatchlistFilter("config/watchlist.yaml")
    trigger = _make_trigger(
        raw_content="Inox Wind signed a large order win for new turbines.",
    )

    result = gate.check(trigger)

    assert result["passed"] is True
    assert result["method"] == "content_scan"

