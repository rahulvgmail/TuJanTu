# ADR-005: Gate Failure Policy (Fail-Open vs Fail-Closed)

| Field | Value |
|-------|-------|
| **Status** | Decided |
| **Owner** | Team |
| **Decision date** | 2026-02-23 |
| **Affects tasks** | T-209, T-210 |

## Context

When the LLM gate (Layer 2) fails — timeout, API error, malformed response — should the trigger pass through (fail-open) or be dropped (fail-closed)?

## Decision

**Fail-open.** If the gate LLM call fails, the trigger passes to Layer 3.

## Rationale

- Missing an important announcement is worse than spending extra LLM tokens on noise.
- The gate is a cost optimization, not a safety gate. False positives (extra analysis) cost money. False negatives (missed news) cost opportunity.
- At MVP scale (one sector, ~50-100 triggers/day), the cost of processing a few extra triggers is negligible.
- Gate errors are logged and monitored so systematic failures get caught quickly.

## Implementation

```python
try:
    result = gate_module(announcement_text=text, company_name=name, sector=sector)
    return result.is_worth_investigating
except Exception as e:
    logger.warning(f"Gate LLM failed for trigger {trigger_id}, failing open: {e}")
    return True  # Fail open
```

## Revision Trigger

Revisit if: (a) gate failure rate exceeds 10%, or (b) fail-open triggers are causing noticeable cost increases.
