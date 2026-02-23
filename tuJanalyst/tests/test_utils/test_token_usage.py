"""Tests for DSPy token-usage helpers."""

from __future__ import annotations

from src.utils.token_usage import extract_token_counts


def test_extract_token_counts_sums_input_and_output_keys() -> None:
    usage_by_model = {
        "anthropic/claude-3-haiku": {
            "prompt_tokens": 120,
            "completion_tokens": 40,
            "prompt_tokens_details": {"cache_creation_input_tokens": 5},
        },
        "openai/gpt-4o-mini": {
            "input_tokens": 60,
            "output_tokens": 20,
            "reasoning_tokens": 3,
            "cache_read_input_tokens": 7,
        },
    }

    input_tokens, output_tokens = extract_token_counts(usage_by_model)

    assert input_tokens == 192
    assert output_tokens == 63


def test_extract_token_counts_falls_back_to_total_tokens() -> None:
    usage_by_model = {"provider/model": {"total_tokens": 91}}

    input_tokens, output_tokens = extract_token_counts(usage_by_model)

    assert input_tokens == 0
    assert output_tokens == 91
