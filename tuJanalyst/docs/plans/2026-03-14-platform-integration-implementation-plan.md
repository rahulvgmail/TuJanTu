# Implementation Plan: tuJanalyst x StockPulse Platform Integration

**Created:** 2026-03-14
**Source:** [Platform Integration Analysis](../Platform%20Integration%20Analysis%20-%20tuJanalyst%20x%20StockPulse.md)
**Scope:** All integration work between tuJanalyst and StockPulse (tuJanChart)

---

## How This Plan Is Organized

The work is divided into **4 phases**, each containing **workstreams** that can run in parallel. Within each workstream, tasks are sequenced by dependency. Each task has an estimate, the files it touches, and whether it can be parallelized with other tasks using sub-agents.

### Execution Model

Claude Code can run multiple sub-agents in parallel on independent tasks. This plan marks tasks as:
- **`[parallel]`** — Can run as a sub-agent alongside other parallel tasks in the same workstream or phase
- **`[sequential]`** — Depends on a prior task completing first
- **`[cross-dep]`** — Depends on a task in a different workstream

Within a phase, independent workstreams can always run in parallel. The plan calls out the maximum parallelism at each stage.

---

## Phase 1: Foundation — StockPulse as a Data Source for Agents

**Goal:** tuJanalyst agents can query StockPulse for rich technical data. Agent analysis results flow back as notes and events.
**Prerequisite:** Both services running and network-reachable (same Tailscale network, confirmed).

---

### Workstream 1A: StockPulse Client Library

Build an async HTTP client for tuJanalyst to call StockPulse's REST API.

| # | Task | Files | Est | Parallel? | Status |
|---|------|-------|-----|-----------|--------|
| 1A.1 | **Create `StockPulseClient` class** — async httpx client wrapping StockPulse REST API. Service-to-service auth via shared secret token in `Authorization: Bearer` header. Circuit breaker for resilience. Methods: `get_stock(symbol)`, `get_indicators(symbol)`, `get_events(symbol, limit)`, `get_screener_results(screener_id)`, `get_screeners_for_stock(symbol)`, `post_note(symbol, content, author_type)`, `update_color(symbol, color, comment)`, `create_event(stock_id, event_type, payload)`, `add_to_universe(symbol, company_name, sector)`. | `src/agents/tools/stockpulse_client.py` (new) | M | parallel | `[ ]` |
| 1A.2 | **Create Pydantic response models** — `StockPulseIndicators`, `StockPulseEvent`, `StockPulseScreenerMembership` matching StockPulse API schemas. Extend `MarketDataSnapshot` or create companion model `TechnicalDataSnapshot`. | `src/models/stockpulse.py` (new) | S | parallel | `[ ]` |
| 1A.3 | **Add configuration** — `TUJ_STOCKPULSE_BASE_URL`, `TUJ_STOCKPULSE_API_KEY`, `TUJ_STOCKPULSE_TIMEOUT_SECONDS`, `TUJ_STOCKPULSE_CIRCUIT_BREAKER_*` to Settings class. | `src/config.py` | S | parallel | `[ ]` |
| 1A.4 | **Write tests for StockPulseClient** — Unit tests with httpx mock transport. Cover: auth header sent, circuit breaker behavior, response parsing, error handling (404, 500, timeout). | `tests/tools/test_stockpulse_client.py` (new) | M | sequential (after 1A.1, 1A.2) | `[ ]` |
| 1A.5 | **Wire into main.py startup** — Instantiate `StockPulseClient` in lifespan, pass to components that need it. Skip if `TUJ_STOCKPULSE_BASE_URL` not configured (graceful degradation). | `src/main.py` | S | sequential (after 1A.1, 1A.3) | `[ ]` |

**Notes:**
- Tasks 1A.1, 1A.2, 1A.3 can all run as parallel sub-agents.
- Pattern follows `WebSearchTool` — async httpx client, circuit breaker, Pydantic models, config-driven.
- `StockPulseClient` replaces nothing — it's additive. `MarketDataTool` (yfinance) remains as fallback.

---

### Workstream 1B: StockPulse Data Tool for Agents

Create the tool that agent layers use to get enriched technical data.

| # | Task | Files | Est | Parallel? | Status |
|---|------|-------|-----|-----------|--------|
| 1B.1 | **Create `StockPulseDataTool`** — wraps `StockPulseClient` with agent-friendly interface. Method `get_technical_context(symbol) -> TechnicalContext` that fetches indicators + recent events + screener membership in parallel (3 concurrent API calls). Returns structured context object ready for DSPy prompt injection. | `src/agents/tools/stockpulse_data.py` (new) | M | cross-dep (after 1A.1, 1A.2) | `[ ]` |
| 1B.2 | **Create `TechnicalContext` model** — combines indicator snapshot, recent events, screener names, color classification, result date proximity into a single object with a `.to_prompt_text()` method that produces a concise summary string suitable for LLM context. | `src/models/technical_context.py` (new) | S | parallel with 1B.1 | `[ ]` |
| 1B.3 | **Write tests** — Unit tests for `StockPulseDataTool` and `TechnicalContext.to_prompt_text()` formatting. | `tests/tools/test_stockpulse_data.py` (new) | S | sequential (after 1B.1, 1B.2) | `[ ]` |

**Notes:**
- `TechnicalContext.to_prompt_text()` is critical — it determines how much signal the LLM receives. Example output:

```
Technical State (INOXWIND, 2026-03-14):
  Price: ₹550.25 (+3.2%) | 52W High: YES (closing) | DMA-10: Hold | DMA-20: Hold
  Volume: Breakout (today: 2.1M vs 21d-max: 1.8M) | Gap: +4.5% gap-up
  Color: Orange (post-result breakout) | Result: declared 3 days ago
  Screeners (6): 52W High + Volume, 10 DMA Hold, Orange + 10 DMA Hold, ...
  Recent Events: 52W_CLOSING_HIGH (today), VOLUME_BREAKOUT (today), DMA_CROSSOVER 10 Hold (yesterday)
```

---

### Workstream 1C: Inject Technical Data into Layer 3 (Deep Analysis)

Wire StockPulse data into the analysis pipeline so agents have full technical context.

| # | Task | Files | Est | Parallel? | Status |
|---|------|-------|-----|-----------|--------|
| 1C.1 | **Add `technical_context` field to `Investigation` model** — optional `TechnicalContext` field, serialized to MongoDB. | `src/models/investigation.py` | S | cross-dep (after 1B.2) | `[ ]` |
| 1C.2 | **Update `DeepAnalyzer` to fetch technical data** — add `stockpulse_data: StockPulseDataTool | None` param to constructor. In `analyze()`, call `get_technical_context(symbol)` alongside existing `market_data.get_snapshot()` (parallel async). Store on Investigation. | `src/pipeline/layer3_analysis/analyzer.py` | M | cross-dep (after 1B.1, 1C.1) | `[ ]` |
| 1C.3 | **Update DSPy signatures to accept technical context** — add `technical_context` input field to `InvestigationSynthesis` signature. Update prompt instruction to reference technical indicators in synthesis. | `src/dspy_modules/signatures.py` | S | parallel with 1C.2 | `[ ]` |
| 1C.4 | **Update `DeepAnalysisPipeline.forward()`** — pass `technical_context_text` to synthesis module alongside existing inputs. | `src/dspy_modules/analysis_pipeline.py` | S | sequential (after 1C.3) | `[ ]` |
| 1C.5 | **Update tests** — modify existing Layer 3 tests to handle optional technical context. Add test case with technical context populated. | `tests/pipeline/test_layer3_*.py` | M | sequential (after 1C.2, 1C.4) | `[ ]` |
| 1C.6 | **Wire `StockPulseDataTool` into `main.py`** — pass to `DeepAnalyzer` constructor. | `src/main.py` | S | sequential (after 1C.2) | `[ ]` |

---

### Workstream 1D: Agent Results Flow Back to StockPulse

When tuJanalyst produces analysis, push summaries back to StockPulse.

| # | Task | Files | Est | Parallel? | Status |
|---|------|-------|-----|-----------|--------|
| 1D.1 | **Create `StockPulseNotifier` service** — uses `StockPulseClient` to post notes and update colors. Methods: `post_investigation_note(investigation)` formats and posts executive summary as agent-authored note. `post_recommendation_event(assessment)` creates an `AI_RECOMMENDATION_CHANGE` event. `update_color_from_assessment(assessment)` updates color classification (Blue for good results, Red for bad). | `src/integrations/stockpulse_notifier.py` (new) | M | cross-dep (after 1A.1) | `[ ]` |
| 1D.2 | **Hook notifier into pipeline orchestrator** — after Layer 5 report delivery, call `StockPulseNotifier.post_investigation_note()` and `post_recommendation_event()`. After Layer 4 assessment, call `update_color_from_assessment()` for buy/sell changes. | `src/pipeline/orchestrator.py` | S | sequential (after 1D.1) | `[ ]` |
| 1D.3 | **Write tests** — test note formatting, event payload construction, orchestrator integration. | `tests/integrations/test_stockpulse_notifier.py` (new) | S | sequential (after 1D.1, 1D.2) | `[ ]` |

**Notes:**
- The `AI_RECOMMENDATION_CHANGE` event in StockPulse requires StockPulse to recognize this event type. If StockPulse doesn't support custom event types yet, we'll POST it as a note with a structured format instead, and track a follow-up task for StockPulse to add the event type.
- Color updates are direct (not suggestions) per founder decision.

---

### Workstream 1E: Result Date Awareness

Query StockPulse for upcoming result dates to inform analysis.

| # | Task | Files | Est | Parallel? | Status |
|---|------|-------|-----|-----------|--------|
| 1E.1 | **Add result date fields to `TechnicalContext`** — `days_to_result`, `result_within_7d/10d/15d`, `result_declared_10d` are already in StockPulse indicators response. Ensure `StockPulseDataTool.get_technical_context()` includes these. | `src/models/technical_context.py`, `src/agents/tools/stockpulse_data.py` | S | cross-dep (after 1B.1, 1B.2) | `[ ]` |

**Notes:**
- This is mostly "already done" if the indicator response is fully parsed in 1B.1. Task exists to ensure nothing is dropped.

---

### Phase 1 Execution Strategy

**Maximum parallelism:** 5 sub-agents

```
Agent 1: 1A.1 (StockPulseClient)
Agent 2: 1A.2 (Response models)
Agent 3: 1A.3 (Configuration)
Agent 4: 1B.2 (TechnicalContext model)
Agent 5: (idle, or start on 1D.1 shell)
         ↓ (1A.1, 1A.2, 1A.3 complete)
Agent 1: 1A.4 (Client tests)
Agent 2: 1A.5 (Wire into main.py)
Agent 3: 1B.1 (StockPulseDataTool) — needs 1A.1 + 1A.2
Agent 4: 1B.3 (Tool tests)
Agent 5: 1C.1 (Investigation model update)
         ↓ (1B.1 complete)
Agent 1: 1C.2 (DeepAnalyzer update)
Agent 2: 1C.3 (DSPy signatures)
Agent 3: 1D.1 (StockPulseNotifier)
Agent 4: 1E.1 (Result date fields)
         ↓
Agent 1: 1C.4 (Pipeline forward)
Agent 2: 1C.5 (Tests)
Agent 3: 1C.6 (Wire into main.py)
Agent 4: 1D.2 (Orchestrator hook)
Agent 5: 1D.3 (Notifier tests)
```

**Phase 1 Definition of Done:**
- [ ] Layer 3 analysis includes full technical context from StockPulse
- [ ] Investigation reports reference DMA signals, volume breakouts, 52W status, screener membership
- [ ] After report generation, executive summary posted as note on StockPulse stock page
- [ ] AI recommendation changes create events visible in StockPulse
- [ ] Color classifications updated by agents (Blue/Red for results quality)
- [ ] All new code has unit tests
- [ ] Graceful degradation: if StockPulse is unreachable, pipeline continues with yfinance data only

---

## Phase 2: Smart Gate + Technical Event Triggers

**Goal:** The gate uses technical context for better filtering. StockPulse technical events can trigger fundamental investigations.
**Prerequisite:** Phase 1 complete (StockPulseClient and StockPulseDataTool working).

---

### Workstream 2A: Technical Context in Gate (Layer 2)

| # | Task | Files | Est | Parallel? | Status |
|---|------|-------|-----|-----------|--------|
| 2A.1 | **Update `GateClassification` signature** — add `technical_context` input field. Update prompt instruction: "Consider the stock's technical state when assessing whether this announcement warrants investigation. A stock already showing technical strength (52W high, DMA hold signals, volume breakout) with a fundamental catalyst is higher priority." | `src/dspy_modules/signatures.py` | S | parallel | `[ ]` |
| 2A.2 | **Update `GateModule.forward()`** — accept optional `technical_context` parameter, pass to classifier. | `src/dspy_modules/gate.py` | S | parallel with 2A.1 | `[ ]` |
| 2A.3 | **Update `GateClassifier.classify()`** — accept optional `technical_context` string parameter. Before LLM call, fetch technical context from StockPulseDataTool if symbol is resolved and tool is available. Pass to GateModule. | `src/pipeline/layer2_gate/gate_classifier.py` | M | sequential (after 2A.1, 2A.2) | `[ ]` |
| 2A.4 | **Wire StockPulseDataTool into GateClassifier** — pass tool reference through orchestrator or DI. | `src/pipeline/orchestrator.py`, `src/main.py` | S | sequential (after 2A.3) | `[ ]` |
| 2A.5 | **Update gate tests** — test with and without technical context. Verify prompt includes technical data when available. | `tests/pipeline/test_layer2_*.py` | M | sequential (after 2A.3) | `[ ]` |

**Notes:**
- Gate call should remain cheap and fast. Technical context fetch adds one API call (~50ms local network). Gate LLM call (Haiku) remains the bottleneck at ~1-2 seconds.
- If StockPulse is unreachable, gate falls back to current behavior (content-only).

---

### Workstream 2B: Technical Event → Trigger Bridge (Webhook Receiver)

| # | Task | Files | Est | Parallel? | Status |
|---|------|-------|-----|-----------|--------|
| 2B.1 | **Add `TECHNICAL_EVENT` to `TriggerSource` enum** — new source type for triggers originating from StockPulse webhook events. | `src/models/trigger.py` | S | parallel | `[ ]` |
| 2B.2 | **Create webhook receiver endpoint** — `POST /api/v1/triggers/webhook` accepts StockPulse webhook payload format (`{event_id, event_type, stock_id, payload, created_at}`). Validates `X-StockPulse-Signature` HMAC if secret configured. Creates `TriggerEvent` with source=`TECHNICAL_EVENT`. Constructs `raw_content` from event payload as readable text. | `src/api/triggers.py` | M | parallel with 2B.1 | `[ ]` |
| 2B.3 | **Add webhook secret config** — `TUJ_STOCKPULSE_WEBHOOK_SECRET` for HMAC validation. | `src/config.py` | S | parallel | `[ ]` |
| 2B.4 | **Create event-to-trigger content formatter** — converts StockPulse event payloads into human-readable trigger content. E.g., `"INOXWIND triggered 52W_CLOSING_HIGH: price ₹550.25 (prev 52W high: ₹548.00). VOLUME_BREAKOUT: volume 2.1M vs 21d-max 1.8M."` | `src/integrations/event_formatter.py` (new) | S | parallel | `[ ]` |
| 2B.5 | **Implement flood detection** — count incoming webhook triggers per time window. If > N events in M minutes (configurable: `TUJ_TECHNICAL_EVENT_FLOOD_THRESHOLD`, `TUJ_TECHNICAL_EVENT_FLOOD_WINDOW_MINUTES`), suspend technical event processing and log macro-event alert. Resume when rate normalizes. | `src/integrations/flood_detector.py` (new) | M | parallel | `[ ]` |
| 2B.6 | **Configure gate bypass rules for compound signals** — certain event type combinations auto-pass the gate (e.g., `52W_CLOSING_HIGH` + `VOLUME_BREAKOUT` on same stock within 24h). Config-driven list of auto-pass event patterns. | `src/pipeline/layer2_gate/gate_classifier.py`, `src/config.py` | M | sequential (after 2B.2) | `[ ]` |
| 2B.7 | **Write tests** — webhook endpoint (valid/invalid signature, payload parsing), flood detection (threshold behavior), event formatting, gate bypass rules. | `tests/api/test_webhook_receiver.py` (new), `tests/integrations/test_flood_detector.py` (new) | M | sequential (after 2B.2, 2B.5) | `[ ]` |

**Notes:**
- This workstream requires a **corresponding task on the StockPulse side**: register a webhook pointing at `http://<tuJanalyst-host>:8000/api/v1/triggers/webhook` with desired event types. This can be done via StockPulse's `POST /api/webhooks` endpoint — no code change needed on StockPulse.
- Flood detection directly implements the founder's decision: "too many events simultaneously = macro event, not fundamentals."

---

### Workstream 2C: Screener Membership as Analysis Input

| # | Task | Files | Est | Parallel? | Status |
|---|------|-------|-----|-----------|--------|
| 2C.1 | **Add `get_screener_membership(symbol)` to `StockPulseClient`** — fetches all screeners, then checks which ones the stock appears in. Returns list of screener names. (Note: StockPulse may need a dedicated endpoint for this in future; for now, iterate over screener results.) | `src/agents/tools/stockpulse_client.py` | M | parallel | `[ ]` |
| 2C.2 | **Add screener membership to `TechnicalContext`** — `screener_names: list[str]` field, included in `to_prompt_text()`. | `src/models/technical_context.py` | S | parallel with 2C.1 | `[ ]` |
| 2C.3 | **Update `StockPulseDataTool.get_technical_context()`** — call `get_screener_membership()` as part of the parallel fetch. | `src/agents/tools/stockpulse_data.py` | S | sequential (after 2C.1, 2C.2) | `[ ]` |
| 2C.4 | **Write tests** | `tests/tools/test_stockpulse_client.py` | S | sequential (after 2C.1) | `[ ]` |

**Notes:**
- Screener membership check is expensive if done naively (iterate all 79 screeners). Optimization: StockPulse could add a `GET /api/stocks/{symbol}/screeners` endpoint. Track as a follow-up improvement task for StockPulse.
- For MVP: query only high-signal screeners (52W high + volume, DMA hold combos, etc.) — maybe 10-15 key screeners, not all 79.

---

### Phase 2 Execution Strategy

**Maximum parallelism:** 5 sub-agents

```
Agent 1: 2A.1 (Gate signature)
Agent 2: 2A.2 (GateModule update)
Agent 3: 2B.1 (TriggerSource enum)
Agent 4: 2B.2 (Webhook endpoint)
Agent 5: 2B.3 + 2B.4 + 2B.5 (Config, formatter, flood detector)
         ↓
Agent 1: 2A.3 (GateClassifier update)
Agent 2: 2B.6 (Gate bypass rules)
Agent 3: 2C.1 (Screener membership client)
Agent 4: 2C.2 (TechnicalContext update)
         ↓
Agent 1: 2A.4 + 2A.5 (Wire + tests)
Agent 2: 2B.7 (Webhook tests)
Agent 3: 2C.3 + 2C.4 (Wire + tests)
```

**Phase 2 Definition of Done:**
- [ ] Gate prompt includes technical context for stocks with StockPulse data
- [ ] StockPulse webhook events create triggers in tuJanalyst
- [ ] Flood detection suspends processing during market-wide events
- [ ] Compound technical signals (e.g., 52W high + volume breakout) auto-pass the gate
- [ ] Investigation synthesis references screener membership
- [ ] Webhook endpoint validates HMAC signatures
- [ ] All new code has unit tests

---

## Phase 3: Unified Experience + Performance Tracking

**Goal:** Single dashboard experience. Recommendation performance measured against price history.
**Prerequisite:** Phase 2 complete.

---

### Workstream 3A: Performance Feedback Loop

| # | Task | Files | Est | Parallel? | Status |
|---|------|-------|-----|-----------|--------|
| 3A.1 | **Design performance tracking data model** — `RecommendationOutcome` model: assessment_id, symbol, recommendation, confidence, entry_price, entry_date, prices at 1w/1m/3m checkpoints, return percentages, outcome classification (win/loss/neutral). Store in MongoDB `recommendation_outcomes` collection. | `src/models/performance.py` (new) | M | parallel | `[ ]` |
| 3A.2 | **Create `PerformanceTracker` service** — on recommendation change, record entry price from StockPulse. Scheduled job (daily) checks all open recommendations, fetches current price from StockPulse, updates checkpoint prices when milestones reached (7d, 30d, 90d post-recommendation). | `src/services/performance_tracker.py` (new) | L | parallel with 3A.1 | `[ ]` |
| 3A.3 | **Create performance repository** — MongoDB CRUD for `RecommendationOutcome`. Indexes on symbol, assessment_id, entry_date. | `src/repositories/performance_repo.py` (new) | S | parallel | `[ ]` |
| 3A.4 | **Create performance API endpoints** — `GET /api/v1/performance/outcomes` (list all with stats), `GET /api/v1/performance/summary` (win rate, avg return, by timeframe), `GET /api/v1/performance/company/{symbol}` (per-company track record). | `src/api/performance.py` (new) | M | sequential (after 3A.1, 3A.3) | `[ ]` |
| 3A.5 | **Add scheduled job for price checkpoints** — APScheduler job runs daily at 5 PM IST (after market close), iterates open recommendations, fetches prices from StockPulse, updates outcomes. | `src/main.py` | S | sequential (after 3A.2) | `[ ]` |
| 3A.6 | **Wire into pipeline orchestrator** — after Layer 4 recommendation change, call `PerformanceTracker.record_entry()` with current price. | `src/pipeline/orchestrator.py` | S | sequential (after 3A.2) | `[ ]` |
| 3A.7 | **Write tests** | `tests/services/test_performance_tracker.py` (new) | M | sequential (after 3A.2) | `[ ]` |

**Notes:**
- Performance definition is deliberately simple for now (price change at checkpoints). The "what constitutes correct" question remains open — this tracks raw data that can be analyzed with different definitions later.
- Entry price comes from StockPulse `current_price` at time of recommendation.

---

### Workstream 3B: Sector Technical Pulse Tool

| # | Task | Files | Est | Parallel? | Status |
|---|------|-------|-----|-----------|--------|
| 3B.1 | **Add sector query methods to `StockPulseClient`** — `get_stocks_by_sector(sector)` returns all stocks in a sector with latest indicators. | `src/agents/tools/stockpulse_client.py` | S | parallel | `[ ]` |
| 3B.2 | **Create `SectorPulseTool`** — aggregates sector-level technical state. Method `get_sector_pulse(sector) -> SectorPulse` returns: count of stocks at 52W high, volume breakout count, average DMA signal distribution, stocks in key screeners, sector-wide momentum score. | `src/agents/tools/sector_pulse.py` (new) | M | sequential (after 3B.1) | `[ ]` |
| 3B.3 | **Create `SectorPulse` model** — sector name, stock count, 52W high count, volume breakout count, avg price change, momentum indicators, top movers list. With `to_prompt_text()`. | `src/models/sector_pulse.py` (new) | S | parallel with 3B.2 | `[ ]` |
| 3B.4 | **Wire into Layer 3** — when analyzing a stock, also fetch sector pulse. Include in DSPy synthesis prompt. Add `sector_pulse` field to Investigation. | `src/pipeline/layer3_analysis/analyzer.py`, `src/models/investigation.py`, `src/dspy_modules/signatures.py` | M | sequential (after 3B.2, 3B.3) | `[ ]` |
| 3B.5 | **Write tests** | `tests/tools/test_sector_pulse.py` (new) | S | sequential (after 3B.2) | `[ ]` |

---

### Workstream 3C: Unified Dashboard Views (StockPulse Side)

**Note:** This workstream requires changes to the StockPulse repo (`/Users/rahulv/projects/tuJanChart`), not tuJanalyst. Documented here for completeness and coordination.

| # | Task | Repo | Files | Est | Parallel? | Status |
|---|------|------|-------|-----|-----------|--------|
| 3C.1 | **Create tuJanalyst API client in StockPulse** — Flask service that calls tuJanalyst's FastAPI endpoints. Methods: `get_investigations(symbol)`, `get_reports(limit)`, `get_position(symbol)`, `get_performance_summary()`. | tuJanChart | `stockpulse/integrations/tujanalyst_client.py` (new) | M | parallel | `[ ]` |
| 3C.2 | **Add AI section to stock detail template** — HTMX partial that loads latest investigation summary, current recommendation badge (BUY/SELL/HOLD with confidence %), recommendation history timeline. | tuJanChart | `stockpulse/web/templates/stocks/detail.html`, `stockpulse/web/views.py` | M | sequential (after 3C.1) | `[ ]` |
| 3C.3 | **Add AI dashboard cards** — "Active AI Recommendations" count card, "Recent Reports" card on main dashboard. HTMX auto-refresh. | tuJanChart | `stockpulse/web/templates/dashboard.html`, `stockpulse/web/views.py` | M | parallel with 3C.2 | `[ ]` |
| 3C.4 | **Create AI Reports page** — browse all generated reports, filter by company/recommendation/date. Click to view full report markdown. | tuJanChart | `stockpulse/web/templates/reports/` (new), `stockpulse/web/views.py` | M | parallel with 3C.2 | `[ ]` |
| 3C.5 | **Create performance dashboard page** — win rate, returns by timeframe, per-company track record. Data from tuJanalyst performance API. | tuJanChart | `stockpulse/web/templates/performance/` (new), `stockpulse/web/views.py` | M | sequential (after 3A.4) | `[ ]` |

---

### Phase 3 Execution Strategy

**Maximum parallelism:** 5 sub-agents (across both repos)

```
Agent 1: 3A.1 (Performance model)
Agent 2: 3A.2 (PerformanceTracker)
Agent 3: 3A.3 (Performance repo)
Agent 4: 3B.1 (Sector query methods)
Agent 5: 3C.1 (tuJanalyst client in StockPulse)
         ↓
Agent 1: 3A.4 (Performance API)
Agent 2: 3A.5 + 3A.6 (Scheduled job + orchestrator)
Agent 3: 3B.2 (SectorPulseTool)
Agent 4: 3B.3 (SectorPulse model)
Agent 5: 3C.2 + 3C.3 (Stock detail AI section + dashboard cards)
         ↓
Agent 1: 3A.7 (Performance tests)
Agent 2: 3B.4 (Wire sector pulse into Layer 3)
Agent 3: 3B.5 (Sector pulse tests)
Agent 4: 3C.4 (Reports page)
Agent 5: 3C.5 (Performance page)
```

**Phase 3 Definition of Done:**
- [ ] Recommendation outcomes tracked with entry price and checkpoint prices
- [ ] Performance API returns win rate, average returns, per-company stats
- [ ] Sector pulse context included in Layer 3 analysis
- [ ] StockPulse stock detail page shows AI recommendations and investigation summaries
- [ ] StockPulse dashboard shows AI recommendation counts and recent reports
- [ ] Dedicated AI reports page in StockPulse
- [ ] Performance dashboard in StockPulse

---

## Phase 4: Advanced Intelligence

**Goal:** Convergence/divergence detection, earnings automation, watchlist sync, promise tracking.
**Prerequisite:** Phase 3 complete.

---

### Workstream 4A: Convergence / Divergence Detection

| # | Task | Files | Est | Parallel? | Status |
|---|------|-------|-----|-----------|--------|
| 4A.1 | **Create `ConvergenceDetector` service** — runs after Layer 4 assessment. Compares AI recommendation vs. technical state. Flags convergence (buy + bullish technicals) and divergence (buy + bearish technicals, or sell + bullish technicals). Produces `ConvergenceAlert` with classification and explanation. | `src/services/convergence_detector.py` (new) | M | parallel | `[ ]` |
| 4A.2 | **Create `ConvergenceAlert` model** — company_symbol, ai_recommendation, technical_state_summary, alert_type (convergence/divergence), explanation, severity (high/medium/low). | `src/models/convergence.py` (new) | S | parallel with 4A.1 | `[ ]` |
| 4A.3 | **Add convergence alerts to report delivery** — when divergence detected, add warning section to Slack notification. When convergence detected, add "high conviction" badge. | `src/pipeline/layer5_report/deliverer.py` | S | sequential (after 4A.1) | `[ ]` |
| 4A.4 | **Add convergence API endpoint** — `GET /api/v1/convergence/alerts` lists recent convergence/divergence alerts. | `src/api/convergence.py` (new) | S | sequential (after 4A.1, 4A.2) | `[ ]` |
| 4A.5 | **Write tests** | `tests/services/test_convergence_detector.py` (new) | S | sequential (after 4A.1) | `[ ]` |

---

### Workstream 4B: Earnings Season Automation

| # | Task | Files | Est | Parallel? | Status |
|---|------|-------|-----|-----------|--------|
| 4B.1 | **Create `EarningsMonitor` scheduled service** — daily job queries StockPulse for all watchlist companies with `result_within_7d = true`. Pre-stages triggers with `priority: HIGH` and `source: EARNINGS_WATCH`. After results declared (`result_declared_10d` transitions to true), checks for post-result technical signals (gap, volume) and auto-triggers investigation. | `src/services/earnings_monitor.py` (new) | L | parallel | `[ ]` |
| 4B.2 | **Add `EARNINGS_WATCH` to `TriggerSource` enum** | `src/models/trigger.py` | S | parallel with 4B.1 | `[ ]` |
| 4B.3 | **Add earnings monitor config** — `TUJ_ENABLE_EARNINGS_MONITOR`, `TUJ_EARNINGS_PRE_RESULT_DAYS` (how many days before results to heighten sensitivity). | `src/config.py` | S | parallel | `[ ]` |
| 4B.4 | **Wire into main.py** — add APScheduler job for earnings monitor, daily at 6 PM IST. | `src/main.py` | S | sequential (after 4B.1) | `[ ]` |
| 4B.5 | **Write tests** | `tests/services/test_earnings_monitor.py` (new) | M | sequential (after 4B.1) | `[ ]` |

---

### Workstream 4C: Watchlist / Universe Sync

| # | Task | Files | Est | Parallel? | Status |
|---|------|-------|-----|-----------|--------|
| 4C.1 | **Create `UniverseSyncService`** — periodically queries StockPulse for stocks classified Pink (portfolio), Orange, Yellow. Compares with tuJanalyst watchlist. Suggests additions for companies in StockPulse but not in watchlist. Can auto-add if configured. | `src/services/universe_sync.py` (new) | M | parallel | `[ ]` |
| 4C.2 | **Add `request_universe_addition()` to `StockPulseClient`** — calls `POST /api/universe` when tuJanalyst discovers a company not yet tracked by StockPulse. | `src/agents/tools/stockpulse_client.py` | S | parallel with 4C.1 | `[ ]` |
| 4C.3 | **Wire into main.py** — APScheduler job, daily. | `src/main.py` | S | sequential (after 4C.1) | `[ ]` |
| 4C.4 | **Write tests** | `tests/services/test_universe_sync.py` (new) | S | sequential (after 4C.1) | `[ ]` |

---

### Workstream 4D: Unified Notifications

| # | Task | Files | Est | Parallel? | Status |
|---|------|-------|-----|-----------|--------|
| 4D.1 | **Enhance Slack message with technical context** — when delivering reports, include a "Technical State" section in the Slack Block Kit message showing DMA signals, 52W status, volume, and screener count. | `src/pipeline/layer5_report/deliverer.py` | S | parallel | `[ ]` |
| 4D.2 | **Add convergence/divergence badge to Slack** — when convergence alert exists for the same stock, add "High Conviction" or "Divergence Warning" badge to Slack message. | `src/pipeline/layer5_report/deliverer.py` | S | sequential (after 4A.1) | `[ ]` |

---

### Phase 4 Execution Strategy

```
Agent 1: 4A.1 (ConvergenceDetector)
Agent 2: 4A.2 (ConvergenceAlert model)
Agent 3: 4B.1 (EarningsMonitor)
Agent 4: 4B.2 + 4B.3 (Enum + config)
Agent 5: 4C.1 + 4C.2 (UniverseSync + client method)
         ↓
Agent 1: 4A.3 (Convergence in reports)
Agent 2: 4A.4 + 4A.5 (API + tests)
Agent 3: 4B.4 + 4B.5 (Wire + tests)
Agent 4: 4C.3 + 4C.4 (Wire + tests)
Agent 5: 4D.1 + 4D.2 (Slack enhancements)
```

**Phase 4 Definition of Done:**
- [ ] Convergence/divergence alerts generated and included in Slack notifications
- [ ] Earnings season fully automated: pre-result awareness → post-result technical reaction → auto-investigation
- [ ] Watchlist syncs with StockPulse color classifications
- [ ] Agents can request stocks be added to StockPulse universe
- [ ] Slack messages include technical state and conviction badges

---

## StockPulse-Side Tasks (tuJanChart repo)

These tasks must be done in the StockPulse codebase to support integration. They can be executed independently of tuJanalyst work.

| # | Task | Description | Phase Needed By | Status |
|---|------|-------------|-----------------|--------|
| SP.1 | **Register webhook for tuJanalyst** | `POST /api/webhooks` with tuJanalyst URL and desired event types. No code change — API call only. | Phase 2 | `[ ]` |
| SP.2 | **Add `AI_RECOMMENDATION_CHANGE` event type** | Add to event type constants. Allow external systems to create events via API (new endpoint or extend existing). | Phase 1 | `[ ]` |
| SP.3 | **Add `GET /api/stocks/{symbol}/screeners` endpoint** | Returns list of screeners the stock currently matches. More efficient than checking all screeners individually. | Phase 2 | `[ ]` |
| SP.4 | **Add service-to-service auth support** | Allow a configured internal token to bypass user-based API key auth. Simple middleware check for `X-Internal-Token` header. | Phase 1 | `[ ]` |
| SP.5 | **Add intraday data API** | Endpoint serving latest available data (intraday during market hours, EOD otherwise). May already be served by existing indicators endpoint if intraday polling writes to same table. Verify and document. | Phase 1 | `[ ]` |
| SP.6 | **Dashboard: AI integration views** | Workstream 3C tasks (stock detail AI section, dashboard cards, reports page, performance page). | Phase 3 | `[ ]` |

---

## Progress Tracker

### Phase 1: Foundation
| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| 1A.1 | StockPulseClient class | `[x]` | `src/agents/tools/stockpulse_client.py` |
| 1A.2 | Pydantic response models | `[x]` | `src/models/stockpulse.py` |
| 1A.3 | Configuration (Settings) | `[x]` | `src/config.py` |
| 1A.4 | Client tests | `[x]` | 10 tests pass |
| 1A.5 | Wire into main.py | `[x]` | Instantiation + cleanup |
| 1B.1 | StockPulseDataTool | `[x]` | `src/agents/tools/stockpulse_data.py` |
| 1B.2 | TechnicalContext model | `[x]` | `src/models/technical_context.py` with `to_prompt_text()` |
| 1B.3 | Data tool tests | `[ ]` | |
| 1C.1 | Investigation model update | `[x]` | `technical_context` field added |
| 1C.2 | DeepAnalyzer update | `[x]` | Parallel fetch with asyncio.gather |
| 1C.3 | DSPy signatures update | `[x]` | `InvestigationSynthesis` updated |
| 1C.4 | Pipeline forward update | `[x]` | `SynthesisModule` + `DeepAnalysisPipeline` updated |
| 1C.5 | Layer 3 tests update | `[ ]` | |
| 1C.6 | Wire tool into main.py | `[x]` | DeepAnalyzer + Orchestrator wired |
| 1D.1 | StockPulseNotifier service | `[x]` | `src/integrations/stockpulse_notifier.py` |
| 1D.2 | Orchestrator hook | `[x]` | Post-L3 notes + post-L4 recommendation/color |
| 1D.3 | Notifier tests | `[ ]` | |
| 1E.1 | Result date fields | `[x]` | Included in indicator parsing |
| SP.2 | AI event type (StockPulse) | `[ ]` | |
| SP.4 | Service-to-service auth (StockPulse) | `[ ]` | |
| SP.5 | Intraday data API (StockPulse) | `[ ]` | |

### Phase 2: Smart Gate + Event Triggers
| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| 2A.1 | Gate signature update | `[ ]` | |
| 2A.2 | GateModule update | `[ ]` | |
| 2A.3 | GateClassifier update | `[ ]` | |
| 2A.4 | Wire into orchestrator | `[ ]` | |
| 2A.5 | Gate tests | `[ ]` | |
| 2B.1 | TECHNICAL_EVENT source enum | `[ ]` | |
| 2B.2 | Webhook receiver endpoint | `[ ]` | |
| 2B.3 | Webhook secret config | `[ ]` | |
| 2B.4 | Event-to-trigger formatter | `[ ]` | |
| 2B.5 | Flood detector | `[ ]` | |
| 2B.6 | Gate bypass rules | `[ ]` | |
| 2B.7 | Webhook + flood tests | `[ ]` | |
| 2C.1 | Screener membership client | `[ ]` | |
| 2C.2 | TechnicalContext screener fields | `[ ]` | |
| 2C.3 | Wire screener fetch | `[ ]` | |
| 2C.4 | Screener tests | `[ ]` | |
| SP.1 | Register webhook (StockPulse) | `[ ]` | |
| SP.3 | Screener membership endpoint (StockPulse) | `[ ]` | |

### Phase 3: Unified Experience + Performance
| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| 3A.1 | Performance data model | `[ ]` | |
| 3A.2 | PerformanceTracker service | `[ ]` | |
| 3A.3 | Performance repository | `[ ]` | |
| 3A.4 | Performance API endpoints | `[ ]` | |
| 3A.5 | Scheduled price checkpoint job | `[ ]` | |
| 3A.6 | Orchestrator entry recording | `[ ]` | |
| 3A.7 | Performance tests | `[ ]` | |
| 3B.1 | Sector query methods | `[ ]` | |
| 3B.2 | SectorPulseTool | `[ ]` | |
| 3B.3 | SectorPulse model | `[ ]` | |
| 3B.4 | Wire into Layer 3 | `[ ]` | |
| 3B.5 | Sector pulse tests | `[ ]` | |
| 3C.1 | tuJanalyst client (StockPulse) | `[ ]` | |
| 3C.2 | Stock detail AI section (StockPulse) | `[ ]` | |
| 3C.3 | Dashboard AI cards (StockPulse) | `[ ]` | |
| 3C.4 | Reports page (StockPulse) | `[ ]` | |
| 3C.5 | Performance page (StockPulse) | `[ ]` | |

### Phase 4: Advanced Intelligence
| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| 4A.1 | ConvergenceDetector | `[ ]` | |
| 4A.2 | ConvergenceAlert model | `[ ]` | |
| 4A.3 | Convergence in reports | `[ ]` | |
| 4A.4 | Convergence API | `[ ]` | |
| 4A.5 | Convergence tests | `[ ]` | |
| 4B.1 | EarningsMonitor service | `[ ]` | |
| 4B.2 | EARNINGS_WATCH source enum | `[ ]` | |
| 4B.3 | Earnings config | `[ ]` | |
| 4B.4 | Wire earnings monitor | `[ ]` | |
| 4B.5 | Earnings tests | `[ ]` | |
| 4C.1 | UniverseSyncService | `[ ]` | |
| 4C.2 | Universe addition client method | `[ ]` | |
| 4C.3 | Wire universe sync | `[ ]` | |
| 4C.4 | Universe sync tests | `[ ]` | |
| 4D.1 | Slack technical context section | `[ ]` | |
| 4D.2 | Slack convergence badges | `[ ]` | |

---

## Task Size Legend

| Size | Meaning |
|------|---------|
| **S** | Small — single file, < 100 lines, straightforward. ~15-30 min with Claude Code. |
| **M** | Medium — 1-3 files, 100-300 lines, some design decisions. ~30-60 min with Claude Code. |
| **L** | Large — multiple files, 300+ lines, complex logic or coordination. ~60-120 min with Claude Code. |

## Total Task Count

| Phase | tuJanalyst Tasks | StockPulse Tasks | Total |
|-------|-----------------|-----------------|-------|
| Phase 1 | 18 | 3 | 21 |
| Phase 2 | 16 | 2 | 18 |
| Phase 3 | 12 + 5 (StockPulse UI) | 5 | 17 |
| Phase 4 | 16 | 0 | 16 |
| **Total** | **62** | **10** | **72** |
