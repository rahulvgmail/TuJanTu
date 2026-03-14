"""Tests for StockPulseNotifier — pushes analysis results back to StockPulse."""

from __future__ import annotations

from unittest.mock import AsyncMock

from src.integrations.stockpulse_notifier import StockPulseNotifier
from src.models.decision import DecisionAssessment
from src.models.investigation import Investigation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_investigation(**overrides) -> Investigation:
    """Create a minimal Investigation with sensible defaults."""
    defaults = {
        "trigger_id": "trigger-001",
        "company_symbol": "INFY",
        "company_name": "Infosys Ltd",
        "key_findings": ["Revenue grew 15% YoY"],
        "red_flags": [],
        "positive_signals": [],
        "significance": "medium",
    }
    defaults.update(overrides)
    return Investigation(**defaults)


def _make_assessment(**overrides) -> DecisionAssessment:
    """Create a minimal DecisionAssessment with sensible defaults."""
    defaults = {
        "investigation_id": "inv-001",
        "trigger_id": "trigger-001",
        "company_symbol": "INFY",
        "company_name": "Infosys Ltd",
        "new_recommendation": "hold",
        "confidence": 0.5,
        "timeframe": "medium_term",
    }
    defaults.update(overrides)
    return DecisionAssessment(**defaults)


def _make_notifier() -> tuple[StockPulseNotifier, AsyncMock]:
    """Return a notifier wired to a fully-mocked StockPulseClient."""
    mock_client = AsyncMock()
    notifier = StockPulseNotifier(client=mock_client)
    return notifier, mock_client


# ---------------------------------------------------------------------------
# 1. test_post_investigation_note_success
# ---------------------------------------------------------------------------


async def test_post_investigation_note_success():
    notifier, mock_client = _make_notifier()
    mock_client.post_note.return_value = {"id": 1, "content": "ok"}

    investigation = _make_investigation(
        key_findings=["Revenue grew 15% YoY", "Margins expanded"],
        red_flags=["Debt increased 20%"],
    )

    result = await notifier.post_investigation_note(investigation)

    assert result is True
    mock_client.post_note.assert_awaited_once()

    call_args = mock_client.post_note.call_args
    assert call_args[0][0] == "INFY"  # symbol
    content = call_args[0][1]
    assert "Revenue grew 15% YoY" in content
    assert "Margins expanded" in content
    assert "Debt increased 20%" in content


# ---------------------------------------------------------------------------
# 2. test_post_investigation_note_failure
# ---------------------------------------------------------------------------


async def test_post_investigation_note_failure():
    notifier, mock_client = _make_notifier()
    mock_client.post_note.return_value = None

    investigation = _make_investigation()

    result = await notifier.post_investigation_note(investigation)

    assert result is False


# ---------------------------------------------------------------------------
# 3. test_post_recommendation_event_success
# ---------------------------------------------------------------------------


async def test_post_recommendation_event_success():
    notifier, mock_client = _make_notifier()
    mock_client.post_note.return_value = {"id": 2}

    assessment = _make_assessment(
        new_recommendation="buy",
        confidence=0.82,
    )

    result = await notifier.post_recommendation_event(assessment)

    assert result is True
    mock_client.post_note.assert_awaited_once()

    content = mock_client.post_note.call_args[0][1]
    assert "BUY" in content
    assert "82%" in content


# ---------------------------------------------------------------------------
# 4. test_update_color_blue_for_good_results
# ---------------------------------------------------------------------------


async def test_update_color_blue_for_good_results():
    notifier, mock_client = _make_notifier()
    mock_client.update_color.return_value = {"color": "Blue"}

    investigation = _make_investigation(
        significance="high",
        positive_signals=["Strong earnings", "Market leader"],
        red_flags=["Minor regulatory risk"],
    )
    assessment = _make_assessment()

    result = await notifier.update_color_from_assessment(assessment, investigation)

    assert result is True
    mock_client.update_color.assert_awaited_once()

    call_args = mock_client.update_color.call_args
    assert call_args[0][0] == "INFY"   # symbol
    assert call_args[0][1] == "Blue"   # color


# ---------------------------------------------------------------------------
# 5. test_update_color_red_for_bad_results
# ---------------------------------------------------------------------------


async def test_update_color_red_for_bad_results():
    notifier, mock_client = _make_notifier()
    mock_client.update_color.return_value = {"color": "Red"}

    investigation = _make_investigation(
        significance="high",
        positive_signals=["Decent revenue"],
        red_flags=["Debt spike", "Management exodus", "Margin collapse"],
    )
    assessment = _make_assessment()

    result = await notifier.update_color_from_assessment(assessment, investigation)

    assert result is True
    mock_client.update_color.assert_awaited_once()

    call_args = mock_client.update_color.call_args
    assert call_args[0][1] == "Red"


# ---------------------------------------------------------------------------
# 6. test_update_color_skipped_for_inconclusive
# ---------------------------------------------------------------------------


async def test_update_color_skipped_for_inconclusive():
    notifier, mock_client = _make_notifier()

    investigation = _make_investigation(
        significance="low",
        positive_signals=["Some upside"],
        red_flags=["Some risk"],
    )
    assessment = _make_assessment()

    result = await notifier.update_color_from_assessment(assessment, investigation)

    assert result is False
    mock_client.update_color.assert_not_awaited()


# ---------------------------------------------------------------------------
# 7. test_notifier_never_crashes_pipeline
# ---------------------------------------------------------------------------


async def test_notifier_never_crashes_pipeline():
    notifier, mock_client = _make_notifier()
    mock_client.post_note.side_effect = RuntimeError("connection exploded")

    investigation = _make_investigation()

    result = await notifier.post_investigation_note(investigation)

    assert result is False
