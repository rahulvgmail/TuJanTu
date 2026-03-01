# NSE/BSE Ticker Resolution Design

**Date:** 2026-03-01  
**Status:** Draft for review

## 1. Problem Statement

Current trigger ingestion depends on weak symbol heuristics:
- `src/pipeline/layer1_triggers/rss_poller.py` infers `company_symbol` from mixed feed fields, URL number fragments, or inline text regex.
- `company_symbol` is then used downstream as if canonical in Layer 2+.
- For BSE items, `company_symbol` may be a numeric scrip code; for NSE it may be a trading symbol; for edge cases it may be missing or wrong.

This creates downstream regressions:
- Gate filtering misses watchlist companies when symbol formats differ.
- Market data lookups fail (`MarketDataTool` expects NSE/BSE tradable symbols for `.NS` / `.BO` lookup).
- Historical and vector context retrieval fragments by inconsistent IDs.
- Manual trigger UX requires users to know exact symbols.

## 2. Refined Requirements

From the request and current codebase constraints, the feature should provide:

1. A canonical company identifier layer for NSE/BSE processing, including:
   - NSE trading symbol
   - BSE scrip code
   - Company name and aliases
   - ISIN (when available)
2. Deterministic resolution first (no LLM cost) using local master data.
3. Web-assisted resolution fallback when deterministic matching is low confidence.
4. DSPy-based fallback only when unresolved after deterministic + web stages.
5. A growing local company universe DB, starting with public sector banks.
6. API/UI support so manual trigger flows can search/select a valid symbol.
7. Observability of resolution confidence, method, and failures.

## 3. External Data Findings (Authoritative Inputs)

### 3.1 NSE official data contracts

NSE official documents indicate symbol-based identifiers in announcement feeds and separate BOD/master files:
- **NSE Real-Time Product Specification** (NSE data products) includes "Corporate Announcement & Quick Result" payloads with a `Symbol` field (Code 1004).
- **NSE End-of-Day Corporate Announcement Technical Specification** defines corporate announcement records with `Symbol` and announcement metadata.
- **NSE Real-Time Stock Product Spec (BOD packet)** describes master/security records with fields including `Token`, `Symbol`, `Series`, and `ISIN`.

Implication: our resolver should treat symbol + ISIN master mapping as first-class, not inferred text.

### 3.2 BSE official discovery constraints

- BSE publishes company/scrip discovery pages (List Scrips / API pages), but these are frequently bot-protected and require browser-like access patterns.
- Existing BSE public surfaces still expose core identifiers such as scrip/security code, security ID/symbol, company/security name, and ISIN.

Implication: we need a resilient fetch/cache strategy and must not hard-block processing on temporary BSE endpoint access issues.

### 3.3 Regulatory scope cross-check

- SEBI official market infrastructure references both NSE and BSE as primary exchanges, validating a dual-exchange resolution strategy.

## 4. Current-State Gap Analysis

### 4.1 Layer 1 trigger normalization gap

`ExchangeRSSPoller._infer_company_symbol` currently:
- Returns raw feed symbol/scrip value if present.
- Else extracts numeric strings from URL (`_extract_nse_scrip_code_from_url`).
- Else regex extracts "symbol: XYZ" from free text.

No validation against a canonical master.

### 4.2 Layer 2 watchlist matching gap

`WatchlistFilter` maintains symbol/name maps from static YAML only. It cannot normalize exchange ID variants (e.g., BSE scrip code -> NSE symbol).

### 4.3 Layer 3 market data gap

`MarketDataTool` uses input symbol as trading symbol; unresolved or numeric BSE code results in `yfinance_unavailable`.

### 4.4 Dashboard/manual trigger gap

Manual trigger form requires exact symbol string. There is no assisted lookup endpoint/UI.

## 5. Option Analysis

### Option A: Extend watchlist YAML only

- Add more aliases and BSE codes manually.
- Keep existing heuristic resolver.

Pros:
- Minimal code changes.

Cons:
- Manual curation burden.
- No scalable path beyond initial sector.
- High miss rate for unseen companies and name variants.

### Option B (Recommended): Canonical master DB + staged resolver

- Build a symbol master store from exchange master feeds.
- Resolve with deterministic matching first.
- Add web fallback (domain-scoped extraction) then DSPy fallback.

Pros:
- High precision, low LLM cost.
- Scales from PSU banks to full universe.
- Clear auditability (method + confidence + source).

Cons:
- Moderate implementation scope.
- Requires refresh jobs and endpoint resilience.

### Option C: Vector-first fuzzy matching

- Embed company names/aliases and always resolve semantically first.

Pros:
- Good for fuzzy user input.

Cons:
- Harder deterministic guarantees.
- More false positives without strict guardrails.
- Not ideal as primary exchange ID resolver.

## 6. Recommended Design

### 6.1 New component: `CompanyMaster` store

Create a canonical company identity model (Mongo-backed, optionally vector-indexed):

- `canonical_id` (internal, e.g., `IN::SBIN`)
- `nse_symbol` (nullable)
- `bse_scrip_code` (nullable)
- `isin` (nullable)
- `company_name`
- `aliases[]`
- `listing_flags` (`nse_listed`, `bse_listed`)
- `sector`, `industry`, `tags[]` (start with `public_sector_bank`)
- `description` (for vector/fuzzy support)
- `metadata` (source URLs, last refresh timestamp)

### 6.2 New component: `TickerResolver`

Deterministic-first multi-stage resolver API:

`resolve(input: ResolutionInput) -> ResolutionResult`

Input includes any available fields from trigger:
- raw symbol/scrip
- company name
- title/content snippets
- source exchange

Resolution stages:
1. Exact symbol/scrip/ISIN map match.
2. Exact normalized company-name/alias match.
3. Deterministic fuzzy (token-normalized string similarity with threshold).
4. Web fallback (`TickerWebLookup`) with restricted domains + parser.
5. DSPy fallback (`TickerResolutionModule`) only if unresolved/low confidence.

Output includes:
- normalized identifiers (`nse_symbol`, `bse_scrip_code`, `isin`, `company_name`)
- `confidence` (0-1)
- `method` (exact_symbol, exact_name, fuzzy_name, web, dspy, unresolved)
- `evidence` (matched fields/sources)

### 6.3 Integration points

- **Layer 1 (`rss_poller`)**: replace heuristic-only symbol inference with `TickerResolver` call; retain heuristics only as input features to resolver.
- **Layer 2 (`watchlist_filter`)**: use resolved canonical IDs/symbols for matching and store normalized symbol on trigger.
- **Layer 3 (`MarketDataTool` caller path)**: pass resolved `nse_symbol` preferentially; fallback to resolved BSE symbol mapping if needed.
- **API + Dashboard**:
  - Add `/api/v1/symbols/resolve` for assisted lookup.
  - Add manual-trigger symbol search UI before submit.

### 6.4 Vector usage model

Use vector DB as assistive retrieval, not source of truth:
- Collection: `company_master` embeddings over `company_name + aliases + description`.
- Use only when deterministic match confidence is below threshold.
- Require deterministic post-check before final accept (avoid vector-only false matches).

### 6.5 PSU banks rollout strategy (Phase 1)

- Seed `CompanyMaster` with public sector banks first.
- Add tag-based filtering so resolver can run in restricted-universe mode initially.
- Keep architecture ready for full NSE/BSE universe expansion.

## 7. Failure Handling and Safety

- If unresolved after all stages:
  - persist `resolution_status=unresolved` + evidence,
  - skip market-data lookup gracefully,
  - continue pipeline with `UNKNOWN` symbol only when policy allows.
- Add hard guardrails:
  - reject weak fuzzy/web matches below configurable threshold,
  - never silently overwrite high-confidence exchange-provided identifiers.

## 8. Observability

Add structured logging + metrics:
- `resolver_attempts_total{stage, outcome}`
- `resolver_confidence_bucket`
- `resolver_unresolved_total`
- `resolver_latency_ms`
- trace fields on trigger/investigation: `resolved_by`, `resolved_confidence`, `resolved_at`

## 9. Decisions Locked

1. **Canonical symbol policy**: `company_symbol` in core models will be canonical NSE symbol when available. BSE code remains in dedicated resolved fields.
2. **Unresolved trigger policy**: continue processing with low-confidence/manual-review tagging (do not hard block pipeline).
3. **Web fallback strictness**: prefer NSE/BSE official sources first; allow controlled external fallback sources when official lookup is insufficient.
4. **Phase-1 universe mode**: start with PSU banks seed data and allow unresolved passthrough with review tagging.

## 10. Recommendation

Proceed with Option B (canonical master + staged resolver), with Phase-1 restricted to PSU banks and strict confidence thresholds. This minimizes LLM spend, reduces false symbols, and provides a safe path to full-universe expansion.
