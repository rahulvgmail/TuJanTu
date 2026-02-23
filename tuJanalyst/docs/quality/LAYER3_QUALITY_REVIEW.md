# Layer 3 Quality Review (T-308)

## Scope
- Date: 2026-02-23
- Sample set: 5 live triggers captured from `tujanalyst_week2_e2e.triggers`
- Artifact: `docs/quality/layer3_examples.json`

## What was reviewed
- Trigger context quality feeding Layer 3
- Prompt requirements for:
  - `MetricsExtraction`
  - `InvestigationSynthesis`
- Readiness of stored examples for future DSPy optimization/training

## Findings
1. Trigger text often contains only a company name/title and lacks financial detail.
2. Exchange feed normalization currently leaves many `company_symbol` values empty for real RSS items.
3. For Layer 3 prompts, stronger instructions are needed to force value+period specificity when numeric evidence is present.

## Prompt tuning applied
- `MetricsExtraction` docstring updated to require explicit value+period extraction patterns.
- `InvestigationSynthesis` docstring updated to require number-backed evidence in narrative output.

## Saved examples
- `docs/quality/layer3_examples.json` now contains 5 labeled examples with review notes.

## Residual gaps
- Team-scored quality review (1-5 ratings) not completed yet.
- Live LLM extraction accuracy benchmark (target >80%) not yet measured.
