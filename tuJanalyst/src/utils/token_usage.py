"""Helpers for extracting token usage from DSPy-tracked LM calls."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, TypeVar

import dspy

T = TypeVar("T")

_INPUT_TOKEN_KEYS = {
    "prompt_tokens",
    "input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
}
_OUTPUT_TOKEN_KEYS = {
    "completion_tokens",
    "output_tokens",
    "reasoning_tokens",
}


def run_with_dspy_usage(operation: Callable[[], T]) -> tuple[T, int, int]:
    """Run an operation and return `(result, input_tokens, output_tokens)`."""
    with dspy.track_usage() as tracker:
        result = operation()

    usage_by_model = tracker.get_total_tokens()
    input_tokens, output_tokens = extract_token_counts(usage_by_model)
    return result, input_tokens, output_tokens


def extract_token_counts(usage_by_model: Mapping[str, Any] | None) -> tuple[int, int]:
    """Sum provider usage payloads into input/output token totals."""
    if not usage_by_model:
        return 0, 0

    input_tokens = _sum_tokens(usage_by_model, _INPUT_TOKEN_KEYS)
    output_tokens = _sum_tokens(usage_by_model, _OUTPUT_TOKEN_KEYS)

    # Fallback for providers that only expose a combined total.
    if input_tokens == 0 and output_tokens == 0:
        output_tokens = _sum_tokens(usage_by_model, {"total_tokens"})

    return input_tokens, output_tokens


def _sum_tokens(payload: Any, keys: set[str]) -> int:
    if isinstance(payload, Mapping):
        total = 0
        for key, value in payload.items():
            if key in keys and _is_number(value):
                total += int(value)
            total += _sum_tokens(value, keys)
        return total

    if isinstance(payload, list | tuple | set):
        return sum(_sum_tokens(item, keys) for item in payload)

    return 0


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)
