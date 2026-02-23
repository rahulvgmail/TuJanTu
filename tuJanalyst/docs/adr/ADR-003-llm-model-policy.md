# ADR-003: LLM Model Selection Policy

| Field | Value |
|-------|-------|
| **Status** | Decided |
| **Owner** | Team |
| **Decision date** | 2026-02-23 |
| **Affects tasks** | T-209 (Gate Classifier), T-302-T-305 (Analysis), T-401-T-404 (Decision/Reports) |

## Context

Different pipeline layers have different quality/cost/speed requirements. We need a clear policy for which model serves which layer.

## Decision

| Layer | Model | Rationale |
|-------|-------|-----------|
| **Layer 2: Gate** | Claude Haiku | Cheapest and fastest. Gate is a binary classification — doesn't need depth. |
| **Layer 3: Analysis** | Claude Sonnet | Best quality/cost balance for analytical work. Synthesis and metric extraction need reasoning. |
| **Layer 4: Decision** | Claude Sonnet | Same as analysis. Upgrade to Opus selectively if decision quality is insufficient after live testing. |
| **Layer 5: Reports** | Claude Sonnet | Report generation needs good writing quality but Sonnet handles this well. |

## Fallback Policy

- If Anthropic has downtime, the pipeline pauses (no silent fallback to a different provider in MVP).
- Multi-provider support (OpenAI fallback) is deferred to Iteration 2.
- DSPy's provider abstraction makes the future swap straightforward.

## Cost Guard Rails

- Log token usage per investigation (implemented in Layer 3 output model).
- Set alert if any single investigation exceeds 50K tokens.
- Review weekly cost during live operation.

## Revision Trigger

Revisit this ADR if: (a) gate accuracy is below 80%, (b) report quality ratings are below 70% "useful", or (c) monthly LLM cost exceeds $200.
