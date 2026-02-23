# tuJanalyst — Implementation Audit Report

> **Date**: 2026-02-24
> **Reviewer**: Claude (automated code review)
> **Scope**: All source code in `src/` and `tests/` against `docs/PROJECT_PLAN.md`
> **Files reviewed**: ~50 source files, ~33 test files (~139 test functions)

---

## Executive Summary

**Overall assessment: Solid B+.** The codebase is well-structured, covers all 5 pipeline layers end-to-end, and has good test coverage for an MVP. The architecture follows the project plan faithfully. However, there are several issues ranging from correctness bugs to operational gaps that should be addressed before production use.

**Completion status**: 41 of 51 tasks marked ✅. The remaining 10 are Week 5-6 tasks (dashboard, scheduling polish, end-to-end integration tests, deployment hardening). All Weeks 1-4 tasks are marked complete and the code exists to back that up.

---

## Severity Legend

| Level | Meaning |
|-------|---------|
| **P0 — Bug** | Correctness issue that will cause wrong behavior at runtime |
| **P1 — Risk** | Will cause problems under real-world load or edge cases |
| **P2 — Improvement** | Code quality, maintainability, or operational observability gap |
| **P3 — Nit** | Style, naming, or minor cleanup |

---

## P0 — Bugs

### 1. `retry_sync` used for DSPy calls blocks the async event loop

**Files**: `src/pipeline/layer3_analysis/analyzer.py`, `src/pipeline/layer4_decision/assessor.py`, `src/pipeline/layer5_report/generator.py`, `src/pipeline/layer2_gate/gate_classifier.py`

All Layer 2-5 DSPy calls use `retry_sync()` which calls `time.sleep()` inside an `async` context. This blocks the entire event loop for the duration of each LLM call (potentially 5-30 seconds per call, with up to 3 retries). Under concurrent trigger processing, this will freeze the FastAPI server and APScheduler.

**Fix**: Either:
- Use `retry_async` + `asyncio.to_thread()` to wrap the synchronous DSPy calls
- Or run DSPy calls in a thread pool executor

### 2. `watchlist_filter.check()` returns a dict, but code treats it inconsistently

**File**: `src/pipeline/layer2_gate/watchlist_filter.py` returns a `FilterResult` dataclass, but `orchestrator.py` line 238 calls `filter_result.get("passed")` — treating it as a dict.

Looking more closely, `WatchlistFilter.check()` returns a `dict` (via `asdict(FilterResult(...))` or similar). This works but the contract is fragile — the docstring says `FilterResult` but the return type annotation says `dict`. Should pick one and be consistent.

### 3. Token counts always reported as 0

**Files**: `analyzer.py:93-94`, `assessor.py:88-89`, `generator.py:105-106`

All Layer 3-5 components log `input_tokens=0` and `output_tokens=0`. The token tracking fields exist in the Investigation and DecisionAssessment models, but actual token counts from DSPy/LLM responses are never captured. This makes cost tracking and monitoring impossible.

**Fix**: Extract token usage from DSPy prediction metadata (if available) or from the LM provider's response headers.

---

## P1 — Risks

### 4. RSS poller has no deduplication persistence

**File**: `src/pipeline/layer1_triggers/rss_poller.py`

The poller calls `trigger_repo.exists_by_url()` to skip duplicates, but the URL-based dedup has gaps:
- Synthetic URLs (SHA256 hashes) will never match across restarts if the hash inputs change
- If the RSS feed returns the same announcement with a slightly different URL (query params, trailing slash), it creates duplicate triggers
- No TTL or bloom filter — the dedup check hits MongoDB on every single feed item

### 5. Vector chunking is character-based, not token-based

**File**: `src/repositories/vector.py:88-101`

The `ChromaVectorRepository` chunks text by character count (default 1000 chars, 200 overlap). This can split mid-word or mid-sentence, degrading retrieval quality. Token-based or sentence-boundary-aware chunking would produce much better embeddings.

### 6. No circuit breaker on external API calls

**Files**: `src/agents/tools/web_search.py`, `src/agents/tools/market_data.py`

Both tools catch exceptions and return empty/fallback results, which is good. But there's no circuit breaker pattern — if Brave/Tavily is down, every trigger will still attempt the call (and wait for timeout). Under high volume this wastes time and could hit rate limits faster.

### 7. `_persist_delivery_failure` uses fragile `getattr` chain

**File**: `src/pipeline/orchestrator.py:295`

```python
report_repo = getattr(self.report_deliverer, "report_repo", None) or getattr(self.report_generator, "report_repo", None)
```

This reaches into internal attributes of other objects to find a repo instance. If either class refactors its attribute name, delivery failures silently won't be persisted. The report_repo should be injected into the orchestrator directly.

### 8. `gate_classifier.classify()` is synchronous but called from async orchestrator

**File**: `src/pipeline/orchestrator.py:241-246`

The orchestrator calls `self.gate_classifier.classify(...)` which is a sync method. The result is then passed through `_maybe_await()`. But `classify()` internally uses `retry_sync` with `time.sleep`, blocking the event loop. (Related to P0 #1 but specifically the gate path.)

### 9. No rate limiting on API endpoints

**Files**: `src/api/triggers.py`, `src/api/investigations.py`, `src/api/reports.py`, `src/api/positions.py`

The human trigger endpoint (`POST /api/v1/triggers/human`) has no rate limiting. A misbehaving client could flood the system with triggers. For an internal MVP this may be acceptable, but should be noted.

### 10. `main.py` lifespan creates all components even if layers are disabled

**File**: `src/main.py`

The lifespan function always creates DeepAnalyzer, DecisionAssessor, ReportGenerator, and ReportDeliverer regardless of configuration. If the LLM API key is missing or a service isn't needed, this wastes resources and could fail at startup.

---

## P2 — Improvements

### 11. Mixed logging: some modules use `structlog`, others use stdlib `logging`

- `orchestrator.py`, `logging_setup.py` → `structlog`
- `analyzer.py`, `assessor.py`, `generator.py`, `deliverer.py`, `gate_classifier.py`, `web_search.py`, `market_data.py` → stdlib `logging`

This means structured JSON logs from the orchestrator, but unstructured text from the pipeline layers. All modules should use structlog for consistent JSON output.

### 12. Heavy use of `Any` type annotations

**Files**: `analyzer.py`, `assessor.py`, `generator.py`, `orchestrator.py`

Many constructor parameters and method signatures use `Any` instead of proper Protocol types from `repositories/base.py`. This reduces IDE support and makes refactoring riskier. The Protocol classes exist — they should be used.

### 13. No health check for LLM provider connectivity

**File**: `src/api/health.py`

The health endpoint checks MongoDB and ChromaDB status, but not LLM provider availability. Since LLM calls are the most failure-prone external dependency, a lightweight ping (or at least reporting the configured provider/model) would help operations.

### 14. Report feedback uses `int` but API accepts `Literal["up", "down"]`

**Files**: `src/api/reports.py:81`, `src/models/report.py:45`

The API converts "up"→1, "down"→-1, but the model stores `feedback_rating: int | None`. This works but the semantics are unclear — is 1 good? What about a 1-5 scale later? Consider using an enum.

### 15. `_NoopWebSearchTool` fallback in main.py

**File**: `src/main.py`

When no web search API key is configured, a `_NoopWebSearchTool` is used that returns empty results. This is correct fail-safe behavior, but it's defined inline in main.py rather than as a proper class in the tools module.

### 16. Test fixtures duplicate in-memory repos across test files

**Files**: `tests/test_pipeline/test_orchestrator.py`, `tests/test_api/test_triggers.py`

Both files define their own `InMemoryTriggerRepo` with slightly different implementations. These should be extracted to `tests/conftest.py` as shared fixtures.

### 17. No integration test that actually calls a real LLM

The test suite mocks all DSPy/LLM interactions (correctly, for unit tests). But there's no integration test harness for validating that the DSPy signatures actually produce parseable output from a real provider. This should be a separate test category (marked with a custom pytest marker like `@pytest.mark.integration`).

### 18. `document_fetcher` has no user-agent header

**File**: `src/pipeline/layer1_triggers/document_fetcher.py`

HTTP requests to download PDFs/documents don't set a User-Agent header. Some corporate websites and exchange portals reject or rate-limit requests without proper user agents.

---

## P3 — Nits

### 19. `utc_now()` defined in 4 separate files

**Files**: `src/models/report.py`, `src/repositories/mongo.py`, `src/pipeline/layer4_decision/assessor.py`, `src/pipeline/layer5_report/deliverer.py`

Each defines its own `utc_now()` helper. Extract to a shared utility module.

### 20. Inconsistent enum value access patterns

Some code uses `status.value`, others use `str(status)`, and models use `use_enum_values=True`. The `_enum_value()` and `_status_value()` helper methods in orchestrator.py exist because of this inconsistency. A consistent pattern should be established.

### 21. `orchestrator.py` has `_maybe_await()` utility

**File**: `src/pipeline/orchestrator.py:277-280`

This exists because `gate_classifier.classify()` might be sync or async. The underlying issue is that the gate classifier's contract isn't clear about sync vs async. Should be resolved at the interface level.

### 22. Missing `__all__` exports in most `__init__.py` files

Most package `__init__.py` files are empty or have minimal exports. Adding `__all__` would make imports cleaner and IDE auto-complete better.

---

## Test Coverage Assessment

**Strengths**:
- 33 test files with ~139 test functions — good breadth
- Orchestrator tests cover the full happy path through all 5 layers
- Edge cases tested: delivery failure, non-significant investigation stopping at Layer 3, human trigger bypass
- API tests use FastAPI TestClient properly
- Deep analyzer tests cover: web search failures, missing market data, missing company symbol, transient retry behavior
- conftest.py has proper async MongoDB mocking with `mongomock_motor`

**Gaps**:
- No tests for `rss_poller.py` multi-format parsing (JSON vs RSS/feedparser)
- No tests for `text_extractor.py` PDF extraction paths
- No negative tests for malformed DSPy JSON output (e.g., what happens when `extracted_metrics_json` contains invalid JSON — the `_parse_json_list` method handles it, but it's not tested)
- No load/concurrency tests
- No tests for the `MarketDataTool` yfinance integration

---

## Architecture Observations

**What's working well**:
- Clean separation between DSPy modules (reasoning) and pipeline orchestrators (workflow)
- Repository Protocol pattern allows easy testing with in-memory implementations
- Fail-open gate policy (ADR-005) is correctly implemented
- Orchestrator properly chains status transitions with reason tracking
- The 5-layer pipeline flows naturally from trigger → gate → analysis → decision → report

**Architectural concerns**:
- The sync DSPy calls inside async code (P0 #1) is the biggest structural issue — it needs a threading strategy
- The orchestrator processes triggers sequentially (`for trigger in pending: await process_trigger`). Under real load with multiple pending triggers, this could be very slow. Consider `asyncio.gather()` with concurrency limits.
- No dead-letter queue — if a trigger fails processing, it's marked ERROR and stays there. There's no retry mechanism for failed triggers.

---

## Recommended Priority Order for Fixes

1. **P0 #1**: Fix sync-in-async blocking (event loop freezes)
2. **P0 #3**: Implement token count tracking (needed for cost monitoring)
3. **P1 #4**: Improve RSS dedup robustness
4. **P2 #11**: Standardize on structlog everywhere
5. **P1 #7**: Inject report_repo into orchestrator properly
6. **P2 #12**: Replace `Any` with Protocol types
7. **P2 #16**: Consolidate test fixtures
8. **P3 #19**: Extract shared `utc_now()` utility

---

## Completion vs PROJECT_PLAN

| Week | Tasks | Status | Notes |
|------|-------|--------|-------|
| Week 1 | T-101 through T-108 | All ✅ | Foundation, models, repos, Layer 1 complete |
| Week 2 | T-201 through T-207 | All ✅ | Watchlist, gate, orchestrator, API complete |
| Week 3 | T-301 through T-308 | All ✅ | Layer 3 analysis, web search, market data complete |
| Week 4 | T-401 through T-411 | All ✅ | Layer 4 decision, Layer 5 report+delivery, positions API complete |
| Week 5 | T-501 through T-505 | All ⬜ | Dashboard UI, scheduling polish — not started |
| Week 6 | T-601 through T-605 | All ⬜ | Integration tests, deployment, documentation — not started |

All code that exists matches what the plan says should exist. No phantom implementations or missing files for completed tasks.
