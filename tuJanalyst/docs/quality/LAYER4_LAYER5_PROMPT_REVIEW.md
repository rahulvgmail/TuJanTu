# Layer 4-5 Prompt Review (T-409)

Date: 2026-02-23

## Scope
- Reviewed Decision (Layer 4) and Report (Layer 5) prompt/signature guidance.
- Focused on structure, scannability, and actionability from Week 4 end-to-end runs.

## Key Refinements Applied
- `DecisionEvaluation`:
  - Added decision-first reasoning order (verdict -> positives -> risks -> net balance).
  - Added explicit guidance that unchanged decisions should remain aligned with current stance.
  - Tightened `key_factors_json` requirement to 3-6 specific factors tied to evidence.
- `ReportGeneration`:
  - Added scannability guidance (short sections, bullet-oriented findings/risks).
  - Added requirement to keep recommendation highly visible.
  - Added preferred markdown section order:
    - Trigger
    - Findings
    - Context
    - Recommendation
    - Risks
    - Sources

## Expected Quality Impact
- Fewer ambiguous recommendations and clearer risk balancing in Layer 4 reasoning.
- More consistent, operator-friendly report layout in Layer 5 outputs.

## Validation Notes
- Validation in this pass is structural (signature-guidance refinement + regression tests).
- Live-model quality scoring and side-by-side human scoring are deferred to operational runs.
