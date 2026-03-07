# NSE/BSE Ticker Resolution Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a deterministic-first ticker resolution layer that maps NSE/BSE announcement inputs to canonical company identifiers, with web and DSPy fallbacks, starting with public sector banks.

**Architecture:** Introduce a `CompanyMaster` data model + repository, a staged `TickerResolver` service (deterministic -> web -> DSPy), and integrate it into Layer 1 ingestion, manual trigger UX, and downstream symbol consumers. Persist resolution metadata for observability and controlled fallback behavior.

**Tech Stack:** FastAPI, Pydantic, MongoDB (Motor), ChromaDB (optional assistive vector lookup), DSPy, Streamlit, pytest/httpx.

**Locked Decisions:**
- `company_symbol` is canonical NSE symbol when resolvable.
- Unresolved/low-confidence cases continue through pipeline with manual-review flags.
- Lookup source order is NSE/BSE official first, then controlled external fallback.

---

### Task 1: Add Canonical Company Master Models

**Files:**
- Create: `src/models/symbol_resolution.py`
- Modify: `src/models/trigger.py`
- Test: `tests/test_models/test_symbol_resolution_models.py`

**Step 1: Write failing model tests**

```python

def test_company_master_normalizes_identifiers():
    master = CompanyMaster(nse_symbol=" sbin ", bse_scrip_code="500112", company_name="State Bank of India")
    assert master.nse_symbol == "SBIN"


def test_resolution_result_requires_method_and_confidence_bounds():
    with pytest.raises(ValueError):
        ResolutionResult(method="exact_symbol", confidence=1.5)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_models/test_symbol_resolution_models.py -v`  
Expected: FAIL (missing model definitions/validation)

**Step 3: Add new models + trigger resolution metadata fields**

Add:
- `CompanyMaster`
- `ResolutionInput`
- `ResolutionResult`
- `ResolutionMethod` enum
- `TriggerEvent` fields: `resolved_nse_symbol`, `resolved_bse_scrip_code`, `resolved_isin`, `resolution_method`, `resolution_confidence`

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_models/test_symbol_resolution_models.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add src/models/symbol_resolution.py src/models/trigger.py tests/test_models/test_symbol_resolution_models.py
git commit -m "feat(models): add canonical symbol resolution models"
```

### Task 2: Add Repository Contract + Mongo Collection

**Files:**
- Modify: `src/repositories/base.py`
- Modify: `src/repositories/mongo.py`
- Test: `tests/test_repositories/test_symbol_master_repository.py`

**Step 1: Write failing repository tests**

```python

async def test_symbol_master_upsert_and_lookup_by_symbol(repo):
    await repo.upsert(master)
    item = await repo.get_by_nse_symbol("SBIN")
    assert item is not None
```

**Step 2: Run test to verify failure**

Run: `uv run pytest -q tests/test_repositories/test_symbol_master_repository.py -v`  
Expected: FAIL (interface/repository missing)

**Step 3: Implement repository + indexes**

- Add `CompanyMasterRepository` protocol
- Add `MongoCompanyMasterRepository`
- Add indexes on `nse_symbol`, `bse_scrip_code`, `isin`, `aliases`, `tags`

**Step 4: Re-run tests**

Run: `uv run pytest -q tests/test_repositories/test_symbol_master_repository.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add src/repositories/base.py src/repositories/mongo.py tests/test_repositories/test_symbol_master_repository.py
git commit -m "feat(repo): add mongo company master repository and indexes"
```

### Task 3: Add Seed + Refresh Ingestion for Exchange Master Data

**Files:**
- Create: `src/pipeline/layer1_triggers/symbol_master_sync.py`
- Create: `config/public_sector_banks_seed.yaml`
- Create: `tests/test_pipeline/test_symbol_master_sync.py`

**Step 1: Write failing sync tests**

```python

def test_sync_loads_seed_and_writes_company_master(syncer, repo):
    count = await syncer.sync_from_seed("config/public_sector_banks_seed.yaml")
    assert count >= 10
```

**Step 2: Run failing tests**

Run: `uv run pytest -q tests/test_pipeline/test_symbol_master_sync.py -v`  
Expected: FAIL

**Step 3: Implement syncer**

- Seed loader for PSU banks
- Optional exchange fetch adapters (pluggable, retriable)
- Merge policy preserving high-confidence existing rows

**Step 4: Re-run tests**

Run: `uv run pytest -q tests/test_pipeline/test_symbol_master_sync.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add src/pipeline/layer1_triggers/symbol_master_sync.py config/public_sector_banks_seed.yaml tests/test_pipeline/test_symbol_master_sync.py
git commit -m "feat(symbol-master): add seed-based sync for initial PSU bank universe"
```

### Task 4: Implement Deterministic Resolver Core

**Files:**
- Create: `src/pipeline/layer1_triggers/ticker_resolver.py`
- Create: `tests/test_pipeline/test_ticker_resolver.py`

**Step 1: Write failing resolver tests**

```python

async def test_resolver_prefers_exact_symbol_match(resolver):
    result = await resolver.resolve(ResolutionInput(raw_symbol="SBIN"))
    assert result.method == "exact_symbol"
    assert result.confidence == 1.0


async def test_resolver_maps_bse_scrip_to_nse_symbol(resolver):
    result = await resolver.resolve(ResolutionInput(raw_symbol="500112", source_exchange="bse"))
    assert result.nse_symbol == "SBIN"
```

**Step 2: Run failing tests**

Run: `uv run pytest -q tests/test_pipeline/test_ticker_resolver.py -v`  
Expected: FAIL

**Step 3: Implement deterministic stages**

- Exact symbol/scrip/isin map
- Exact normalized name/alias map
- Bounded fuzzy score stage (threshold-configurable)

**Step 4: Re-run tests**

Run: `uv run pytest -q tests/test_pipeline/test_ticker_resolver.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add src/pipeline/layer1_triggers/ticker_resolver.py tests/test_pipeline/test_ticker_resolver.py
git commit -m "feat(resolver): add deterministic ticker resolution pipeline"
```

### Task 5: Integrate Resolver into RSS Poller

**Files:**
- Modify: `src/pipeline/layer1_triggers/rss_poller.py`
- Modify: `src/main.py`
- Modify: `tests/test_pipeline/test_rss_poller.py`

**Step 1: Add failing poller integration tests**

```python

async def test_poller_uses_resolver_for_missing_symbol(...):
    ...
    assert created[0].company_symbol == "SBIN"
    assert created[0].resolved_bse_scrip_code == "500112"
```

**Step 2: Run failing tests**

Run: `uv run pytest -q tests/test_pipeline/test_rss_poller.py -v`  
Expected: FAIL

**Step 3: Wire resolver in poller path**

- Inject resolver dependency
- Feed row/title/url/raw text into resolver
- Persist resolution metadata on triggers
- Keep legacy heuristics as fallback input signals only

**Step 4: Re-run tests**

Run: `uv run pytest -q tests/test_pipeline/test_rss_poller.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add src/pipeline/layer1_triggers/rss_poller.py src/main.py tests/test_pipeline/test_rss_poller.py
git commit -m "feat(layer1): resolve canonical symbols during rss ingestion"
```

### Task 6: Add Web Fallback Resolver Stage

**Files:**
- Create: `src/agents/tools/ticker_web_lookup.py`
- Modify: `src/agents/tools/__init__.py`
- Modify: `src/pipeline/layer1_triggers/ticker_resolver.py`
- Create: `tests/test_agents/test_ticker_web_lookup.py`
- Modify: `tests/test_pipeline/test_ticker_resolver.py`

**Step 1: Write failing web-lookup tests**

```python

async def test_web_lookup_extracts_symbol_from_exchange_result(...):
    row = await lookup.lookup("State Bank of India")
    assert row["nse_symbol"] == "SBIN"
```

**Step 2: Run failing tests**

Run: `uv run pytest -q tests/test_agents/test_ticker_web_lookup.py tests/test_pipeline/test_ticker_resolver.py -v`  
Expected: FAIL

**Step 3: Implement tool + resolver stage**

- Reuse existing web-search provider client patterns
- Domain allowlist (`nseindia.com`, `bseindia.com` first)
- Parse symbol/scrip candidates + confidence scoring

**Step 4: Re-run tests**

Run: `uv run pytest -q tests/test_agents/test_ticker_web_lookup.py tests/test_pipeline/test_ticker_resolver.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add src/agents/tools/ticker_web_lookup.py src/agents/tools/__init__.py src/pipeline/layer1_triggers/ticker_resolver.py tests/test_agents/test_ticker_web_lookup.py tests/test_pipeline/test_ticker_resolver.py
git commit -m "feat(resolver): add web fallback stage with exchange-domain parsing"
```

### Task 7: Add DSPy Fallback Resolution Module

**Files:**
- Modify: `src/dspy_modules/signatures.py`
- Create: `src/dspy_modules/symbol_resolution.py`
- Modify: `src/pipeline/layer1_triggers/ticker_resolver.py`
- Create: `tests/test_pipeline/test_symbol_resolution_dspy.py`

**Step 1: Write failing DSPy fallback tests**

```python

def test_dspy_fallback_returns_structured_resolution_when_invoked(...):
    result = resolver._run_dspy_fallback(...)
    assert result.method == "dspy"
```

**Step 2: Run failing tests**

Run: `uv run pytest -q tests/test_pipeline/test_symbol_resolution_dspy.py -v`  
Expected: FAIL

**Step 3: Implement signature + module + guarded invocation**

- Signature outputs strict JSON fields
- Invoke only if deterministic + web confidence below threshold
- Parse with strict validation and confidence cap

**Step 4: Re-run tests**

Run: `uv run pytest -q tests/test_pipeline/test_symbol_resolution_dspy.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add src/dspy_modules/signatures.py src/dspy_modules/symbol_resolution.py src/pipeline/layer1_triggers/ticker_resolver.py tests/test_pipeline/test_symbol_resolution_dspy.py
git commit -m "feat(dspy): add low-confidence fallback symbol resolver module"
```

### Task 8: Add Symbol Resolution API

**Files:**
- Create: `src/api/symbols.py`
- Modify: `src/main.py`
- Create: `tests/test_api/test_symbols.py`

**Step 1: Write failing API tests**

```python

def test_resolve_symbol_endpoint_returns_ranked_matches(client):
    resp = client.get("/api/v1/symbols/resolve", params={"q": "state bank"})
    assert resp.status_code == 200
    assert resp.json()["matches"][0]["nse_symbol"] == "SBIN"
```

**Step 2: Run failing tests**

Run: `uv run pytest -q tests/test_api/test_symbols.py -v`  
Expected: FAIL

**Step 3: Implement endpoint + dependency wiring**

- `GET /api/v1/symbols/resolve?q=...`
- optional `scope=public_sector_bank`
- return ranked matches + confidence + method

**Step 4: Re-run tests**

Run: `uv run pytest -q tests/test_api/test_symbols.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add src/api/symbols.py src/main.py tests/test_api/test_symbols.py
git commit -m "feat(api): add symbol resolution endpoint"
```

### Task 9: Add Dashboard Manual Trigger Assisted Lookup

**Files:**
- Modify: `src/dashboard/app.py`
- Modify: `src/dashboard/manual_trigger_utils.py`
- Modify: `tests/test_dashboard/test_manual_trigger_utils.py`

**Step 1: Write failing helper/UI behavior tests**

```python

def test_manual_payload_uses_resolved_symbol_when_selected():
    ...
```

**Step 2: Run failing tests**

Run: `uv run pytest -q tests/test_dashboard/test_manual_trigger_utils.py -v`  
Expected: FAIL

**Step 3: Implement UI changes**

- Add company search field in Manual Trigger tab
- Query `/api/v1/symbols/resolve`
- Let user select a suggested match before submit
- Keep free-text fallback

**Step 4: Re-run tests**

Run: `uv run pytest -q tests/test_dashboard/test_manual_trigger_utils.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add src/dashboard/app.py src/dashboard/manual_trigger_utils.py tests/test_dashboard/test_manual_trigger_utils.py
git commit -m "feat(dashboard): add assisted symbol lookup for manual triggers"
```

### Task 10: Persist Resolution Metadata and Use in Layer 3

**Files:**
- Modify: `src/pipeline/layer3_analysis/analyzer.py`
- Modify: `tests/test_pipeline/test_deep_analyzer.py`
- Modify: `tests/test_pipeline/test_orchestrator.py`

**Step 1: Write failing downstream behavior tests**

```python

async def test_analyzer_prefers_resolved_nse_symbol_for_market_data(...):
    ...
```

**Step 2: Run failing tests**

Run: `uv run pytest -q tests/test_pipeline/test_deep_analyzer.py tests/test_pipeline/test_orchestrator.py -v`  
Expected: FAIL

**Step 3: Implement symbol preference order**

- `resolved_nse_symbol` -> `company_symbol` -> fallback
- include resolution metadata in logs

**Step 4: Re-run tests**

Run: `uv run pytest -q tests/test_pipeline/test_deep_analyzer.py tests/test_pipeline/test_orchestrator.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add src/pipeline/layer3_analysis/analyzer.py tests/test_pipeline/test_deep_analyzer.py tests/test_pipeline/test_orchestrator.py
git commit -m "feat(layer3): consume resolved symbols for market data and context"
```

### Task 11: Add Configuration + Runtime Wiring

**Files:**
- Modify: `src/config.py`
- Modify: `.env.example`
- Modify: `config/settings.yaml`
- Modify: `tests/test_config.py`

**Step 1: Add failing config tests**

```python

def test_symbol_resolver_config_defaults():
    ...
```

**Step 2: Run failing tests**

Run: `uv run pytest -q tests/test_config.py -v`  
Expected: FAIL

**Step 3: Add config knobs**

- enable/disable web fallback
- enable/disable dspy fallback
- confidence thresholds
- universe scope tags

**Step 4: Re-run tests**

Run: `uv run pytest -q tests/test_config.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add src/config.py .env.example config/settings.yaml tests/test_config.py
git commit -m "feat(config): add symbol resolver runtime configuration"
```

### Task 12: Verification, Docs, and Rollout Controls

**Files:**
- Modify: `README.md`
- Modify: `docs/PROJECT_PLAN.md`
- Create: `docs/operations/symbol-resolution-runbook.md`

**Step 1: Run full targeted verification suite**

Run:

```bash
uv run pytest -q \
  tests/test_models/test_symbol_resolution_models.py \
  tests/test_repositories/test_symbol_master_repository.py \
  tests/test_pipeline/test_symbol_master_sync.py \
  tests/test_pipeline/test_ticker_resolver.py \
  tests/test_pipeline/test_rss_poller.py \
  tests/test_pipeline/test_symbol_resolution_dspy.py \
  tests/test_api/test_symbols.py \
  tests/test_dashboard/test_manual_trigger_utils.py \
  tests/test_pipeline/test_deep_analyzer.py \
  tests/test_pipeline/test_orchestrator.py \
  tests/test_config.py -v
```

Expected: PASS

**Step 2: Document operations + rollback**

Include:
- seed/update commands
- endpoint health checks
- unresolved trigger triage flow
- disable switches for web/DSPy fallback

**Step 3: Commit**

```bash
git add README.md docs/PROJECT_PLAN.md docs/operations/symbol-resolution-runbook.md
git commit -m "docs: add symbol resolution operations and rollout guide"
```

### Task 13: Optional Backfill Job for Existing Triggers (Post-MVP)

**Files:**
- Create: `scripts/backfill_trigger_symbols.py`
- Create: `tests/test_pipeline/test_symbol_backfill.py`

**Step 1: Write failing backfill test**

**Step 2: Implement idempotent backfill**

- re-resolve unresolved/legacy triggers
- preserve original raw values in audit fields

**Step 3: Run test**

Run: `uv run pytest -q tests/test_pipeline/test_symbol_backfill.py -v`  
Expected: PASS

**Step 4: Commit**

```bash
git add scripts/backfill_trigger_symbols.py tests/test_pipeline/test_symbol_backfill.py
git commit -m "feat(migration): add trigger symbol backfill utility"
```

## Rollout Sequence

1. Deploy with deterministic resolver + seeded PSU bank universe only.
2. Enable web fallback with strict domain allowlist and metrics watch.
3. Enable DSPy fallback after evaluating unresolved rate and precision.
4. Expand universe tags beyond PSU banks once precision target is met.

## Success Criteria

- `>=95%` of PSU-bank announcements resolve to correct NSE/BSE IDs without DSPy fallback.
- `>=80%` of all symbol resolutions are deterministic (non-LLM).
- Market data unavailable errors due to bad symbols drop materially from baseline.
- Manual trigger UX no longer requires prior exact symbol knowledge.
