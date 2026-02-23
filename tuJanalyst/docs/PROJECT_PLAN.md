# tuJanalyst — Project Execution Plan

> **Last updated**: 2026-02-23
> **Team**: 2-3 developers
> **Timeline**: 6 weeks (MVP)
> **Sector**: Capital Goods — Electrical Equipment

---

## Status Legend

| Symbol | Meaning |
|--------|---------|
| `⬜` | Not started |
| `🔵` | In progress |
| `✅` | Complete |
| `🔴` | Blocked |

---

## Week 1: Foundation + Trigger Ingestion

### T-101: Project Scaffolding

| Field | Detail |
|-------|--------|
| **ID** | T-101 |
| **Name** | Project Scaffolding |
| **Status** | ✅ |
| **Prerequisites** | None |
| **Description** | Create the project directory structure, Docker Compose file, Dockerfile, pyproject.toml with all dependencies, .env.example, and basic configuration loading. This is the foundation everything else builds on. |

**TODOs**:
- [x] Create directory structure as defined in Technical Spec Weeks 1-2 §1
- [x] Write `pyproject.toml` with all dependencies (FastAPI, motor, chromadb, dspy-ai, pydantic-ai, anthropic, pdfplumber, httpx, feedparser, apscheduler, etc.)
- [x] Write `Dockerfile` (Python 3.11+, multi-stage build)
- [x] Write `docker-compose.yml` (app + MongoDB 7)
- [x] Write `.env.example` with all required env vars
- [x] Create empty `__init__.py` files in all packages

**Definition of Done**:
- `docker-compose up` starts the app container and MongoDB container without errors
- `docker-compose exec app python -c "import fastapi; import motor; import chromadb; import dspy; print('OK')"` succeeds
- Project structure matches spec §1

**Testing Steps**:
1. Run `docker-compose build` — should complete without errors
2. Run `docker-compose up -d` — both containers should be healthy
3. Verify MongoDB is reachable: `docker-compose exec mongodb mongosh --eval "db.runCommand({ping:1})"`
4. Verify Python imports work inside app container

**Files Created/Modified**:
- `tuJanalyst/pyproject.toml` — Project config with all dependencies
- `tuJanalyst/Dockerfile` — Multi-stage build (Python 3.11-slim)
- `tuJanalyst/docker-compose.yml` — app + MongoDB 7
- `tuJanalyst/.env.example` — All TUJ_ prefixed env vars
- `tuJanalyst/.gitignore` — Standard Python/Docker ignores
- `tuJanalyst/src/main.py` — FastAPI app with lifespan, /health endpoint
- `tuJanalyst/config/watchlist.yaml` — 5 companies, Capital Goods sector
- `tuJanalyst/config/settings.yaml` — Non-secret tunable parameters
- `tuJanalyst/config/logging.yaml` — Structured logging config
- `tuJanalyst/tests/conftest.py` — Test fixture placeholder
- 18 `__init__.py` files across all packages

**Test Cases Written**: None yet (testing infrastructure comes with T-102+)

---

### T-102: Settings & Configuration Loading

| Field | Detail |
|-------|--------|
| **ID** | T-102 |
| **Name** | Settings & Configuration Loading |
| **Status** | ⬜ |
| **Prerequisites** | T-101 |
| **Description** | Implement Pydantic Settings for app configuration (env vars + .env file) and YAML config loading for the watchlist. All settings should be typed and validated at startup. |

**TODOs**:
- [ ] Implement `src/config.py` with `Settings` class (Pydantic Settings) as defined in Spec §3.1
- [ ] Create `config/watchlist.yaml` with initial structure (can have placeholder companies)
- [ ] Create `config/settings.yaml` if needed for non-secret settings
- [ ] Implement watchlist YAML loading into `WatchlistConfig` model
- [ ] Add config validation at app startup (fail fast on missing required settings)

**Definition of Done**:
- `Settings()` loads from `.env` file and environment variables
- Missing required settings (e.g., `ANTHROPIC_API_KEY`) cause a clear startup error
- `WatchlistConfig` loads and validates from `config/watchlist.yaml`
- All settings are accessible as typed Python attributes

**Testing Steps**:
1. Create `.env` with test values, verify `Settings()` loads correctly
2. Remove a required setting, verify startup fails with clear error message
3. Load `watchlist.yaml` with sample data, verify parsing

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-103: Core Data Models

| Field | Detail |
|-------|--------|
| **ID** | T-103 |
| **Name** | Core Data Models (Trigger, Document, Company) |
| **Status** | ⬜ |
| **Prerequisites** | T-101 |
| **Description** | Define the Pydantic models for TriggerEvent, RawDocument, Company, and WatchlistConfig. These are the shared data structures used across all layers. |

**TODOs**:
- [ ] Implement `src/models/trigger.py` — TriggerEvent, TriggerSource, TriggerStatus, TriggerPriority enums and model as per Spec §2.1
- [ ] Implement `src/models/document.py` — RawDocument, DocumentType, ProcessingStatus as per Spec §2.2
- [ ] Implement `src/models/company.py` — Company, WatchlistConfig as per Spec §2.3
- [ ] Ensure all models have sensible defaults and use `Field(default_factory=...)` for mutable defaults
- [ ] Add `uuid4` import and default ID generation for `trigger_id`, `document_id`

**Definition of Done**:
- All models instantiate with required fields and generate UUIDs for IDs
- All enums serialize/deserialize correctly to/from strings (for MongoDB storage)
- `TriggerEvent` status history tracks transitions
- Models pass type checking with mypy

**Testing Steps**:
1. Instantiate each model with minimal required fields — verify defaults are populated
2. Serialize to dict (`model_dump()`), verify all fields present
3. Round-trip test: create → dump → reconstruct from dict
4. Test enum serialization (value should be string, not enum object)

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-104: MongoDB Connection & Repository Base

| Field | Detail |
|-------|--------|
| **ID** | T-104 |
| **Name** | MongoDB Connection & Repository Protocols |
| **Status** | ⬜ |
| **Prerequisites** | T-101, T-103 |
| **Description** | Set up the async MongoDB connection using Motor, define repository Protocol classes (interfaces), and create the MongoDB database initialization. |

**TODOs**:
- [ ] Implement `src/repositories/base.py` — Protocol classes for TriggerRepository, DocumentRepository, VectorRepository as per Spec §4.1
- [ ] Create MongoDB connection helper (async client factory)
- [ ] Create MongoDB index setup function (run at startup):
  - `triggers`: index on `trigger_id` (unique), `source_url`, `status`, `company_symbol`, `created_at`
  - `documents`: index on `document_id` (unique), `trigger_id`, `company_symbol`
- [ ] Verify connection works with Docker Compose MongoDB

**Definition of Done**:
- Protocol classes define all required methods with correct type hints
- MongoDB client connects successfully at app startup
- Indexes are created automatically on first startup
- Connection errors produce clear error messages

**Testing Steps**:
1. Start MongoDB via Docker Compose
2. Run index creation function — verify indexes exist in MongoDB
3. Test connection with a simple insert/find round-trip
4. Test connection failure handling (stop MongoDB, verify error message)

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-105: MongoDB Repository Implementations

| Field | Detail |
|-------|--------|
| **ID** | T-105 |
| **Name** | MongoTriggerRepository & MongoDocumentRepository |
| **Status** | ⬜ |
| **Prerequisites** | T-104 |
| **Description** | Implement the MongoDB-backed repositories for triggers and documents. These handle all CRUD operations and queries. |

**TODOs**:
- [ ] Implement `src/repositories/mongo.py` — `MongoTriggerRepository`:
  - `save(trigger)` — insert new trigger
  - `get(trigger_id)` — find by ID
  - `update_status(trigger_id, status, reason)` — update status + append to status_history
  - `get_pending(limit)` — find triggers with status="pending", ordered by created_at
  - `get_by_company(company_symbol, limit)` — find by company
  - `exists_by_url(source_url)` — dedup check for RSS
- [ ] Implement `MongoDocumentRepository`:
  - `save(document)` — insert/upsert document
  - `get(document_id)` — find by ID
  - `get_by_trigger(trigger_id)` — find all docs for a trigger
  - `update_extracted_text(document_id, text, method, metadata)` — update after extraction
- [ ] Handle `_id` field mapping (MongoDB uses `_id`, our models use custom IDs)

**Definition of Done**:
- All repository methods work against a real MongoDB instance
- `exists_by_url` correctly prevents duplicate trigger creation
- `update_status` appends to status_history array atomically
- `get_pending` returns triggers in creation order

**Testing Steps**:
1. Save a trigger, retrieve by ID — verify all fields match
2. Save 5 triggers, call `get_pending(3)` — verify returns 3 oldest
3. Update status twice, verify `status_history` has 2 entries
4. Save trigger with URL, call `exists_by_url` — verify returns True
5. Call `exists_by_url` with unknown URL — verify returns False
6. Save document, update extracted text, retrieve — verify text is updated

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-106: NSE RSS Feed Poller

| Field | Detail |
|-------|--------|
| **ID** | T-106 |
| **Name** | NSE RSS Feed Poller |
| **Status** | ⬜ |
| **Prerequisites** | T-105 |
| **Description** | Implement the RSS feed poller that fetches corporate announcements from NSE, parses them, deduplicates against existing triggers, and creates new TriggerEvent records. |

**TODOs**:
- [ ] Implement `src/pipeline/layer1_triggers/rss_poller.py` — `NSERSSPoller` as per Spec §5.1
- [ ] Research and validate the actual NSE corporate announcements API endpoint
  - Test manually with curl/httpx: what headers are needed? Does it require cookies?
  - Document the response format (JSON structure, field names)
- [ ] Handle NSE-specific quirks (cookie requirements, rate limiting, User-Agent)
- [ ] Parse response: extract company_symbol, company_name, description, document links, dates
- [ ] Dedup: skip announcements where `source_url` already exists in triggers collection
- [ ] Create `TriggerEvent` for each new announcement
- [ ] Handle pagination if NSE API paginates results
- [ ] Implement error handling with logging (don't crash on transient errors)

**Definition of Done**:
- Poller successfully fetches real NSE announcements (test with live API)
- New announcements create trigger records in MongoDB
- Duplicate announcements are skipped (dedup works)
- Network errors are caught and logged, not propagated
- Response format is documented in code comments

**Testing Steps**:
1. Run poller against live NSE API — verify it fetches data and creates triggers
2. Run poller again immediately — verify no duplicate triggers created
3. Disconnect network, run poller — verify graceful error handling
4. Verify trigger records have correct fields (symbol, name, URL, content)
5. Save a real NSE API response as a test fixture for offline testing

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-107: Document Fetcher

| Field | Detail |
|-------|--------|
| **ID** | T-107 |
| **Name** | Document Fetcher (Download linked documents) |
| **Status** | ⬜ |
| **Prerequisites** | T-105 |
| **Description** | Implement the document downloader that fetches PDFs, HTML pages, and other files linked from NSE announcements. Stores files locally and creates RawDocument records. |

**TODOs**:
- [ ] Implement `src/pipeline/layer1_triggers/document_fetcher.py` — `DocumentFetcher` as per Spec §5.2
- [ ] Create `data/documents/` directory for downloaded files
- [ ] Detect document type from URL extension and Content-Type header
- [ ] Enforce max file size limit (configurable, default 50MB)
- [ ] Save file to disk with document_id-based filename
- [ ] Create `RawDocument` record with metadata (file path, size, type, status)
- [ ] Handle redirects, timeouts, and download errors gracefully
- [ ] Handle NSE-specific download quirks (some PDFs require specific headers)

**Definition of Done**:
- Given a URL to an NSE PDF, downloads and stores the file
- `RawDocument` record contains correct file path, size, and type
- Oversized files are rejected with clear error in `processing_errors`
- Failed downloads set status to `ERROR` with error message
- Downloaded files are readable from disk

**Testing Steps**:
1. Download a real NSE announcement PDF — verify file exists and is valid PDF
2. Download an HTML announcement page — verify file exists and contains HTML
3. Test with a URL that returns 404 — verify graceful error handling
4. Test with a file > max size limit — verify rejection
5. Verify RawDocument record in MongoDB has correct metadata

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-108: Text Extractor

| Field | Detail |
|-------|--------|
| **ID** | T-108 |
| **Name** | Text Extractor (PDF + HTML) |
| **Status** | ⬜ |
| **Prerequisites** | T-107 |
| **Description** | Implement text extraction from downloaded documents. PDF extraction via pdfplumber (including tables). HTML extraction via BeautifulSoup. Updates RawDocument with extracted text. |

**TODOs**:
- [ ] Implement `src/pipeline/layer1_triggers/text_extractor.py` — `TextExtractor` as per Spec §5.3
- [ ] PDF extraction:
  - Extract text page by page using `pdfplumber`
  - Extract tables and format as text with `[TABLE]...[/TABLE]` markers
  - Capture metadata: page count, table count
- [ ] HTML extraction:
  - Parse with BeautifulSoup, remove script/style/nav/footer elements
  - Extract clean text with newline separation
- [ ] Plain text: direct file read
- [ ] Update `RawDocument` with extracted text, method, and metadata via repository
- [ ] Handle extraction failures gracefully (log error, set status to ERROR)

**Definition of Done**:
- Given a real NSE quarterly results PDF, extracts readable text including financial tables
- Given an HTML announcement, extracts clean text without HTML tags
- Extracted text is stored in `RawDocument.extracted_text` via repository
- Extraction metadata (page count, table count, method) is captured
- Failed extractions set document status to ERROR

**Testing Steps**:
1. Extract text from 3 different real NSE PDFs — verify text is readable and complete
2. Verify tables are extracted and formatted (spot check key financial numbers)
3. Extract from an HTML file — verify clean text output
4. Test with a corrupted/empty PDF — verify graceful error
5. Test with a scanned/image-only PDF — verify it handles gracefully (returns empty or minimal text)

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-109: Human Trigger API Endpoint

| Field | Detail |
|-------|--------|
| **ID** | T-109 |
| **Name** | Human Trigger API Endpoint |
| **Status** | ⬜ |
| **Prerequisites** | T-105 |
| **Description** | Implement the FastAPI endpoint for team members to manually submit investigation triggers. Human triggers are created with high priority and bypass the Layer 2 gate. |

**TODOs**:
- [ ] Implement `src/api/triggers.py` — router with endpoints as per Spec §5.4:
  - `POST /api/v1/triggers/human` — create human trigger
  - `GET /api/v1/triggers/{trigger_id}` — get trigger status
  - `GET /api/v1/triggers/` — list triggers with optional filters (status, company)
- [ ] Implement FastAPI dependency injection for repositories
- [ ] Human triggers: set `source=HUMAN`, `priority=HIGH`, `status=GATE_PASSED`
- [ ] Validate request body (content is required, company_symbol is optional)
- [ ] Return trigger_id in response

**Definition of Done**:
- `POST /api/v1/triggers/human` creates a trigger and returns `{trigger_id, status: "accepted"}`
- Created trigger has `source="human"`, `priority="high"`, `status="gate_passed"`
- `GET /api/v1/triggers/{id}` returns trigger status
- `GET /api/v1/triggers/` returns list of recent triggers
- Invalid requests return 422 with clear validation errors

**Testing Steps**:
1. POST a human trigger with company_symbol and content — verify 200 response with trigger_id
2. GET the trigger by ID — verify all fields correct, status is "gate_passed"
3. POST without required `content` field — verify 422 error
4. POST without `company_symbol` (optional) — verify it still works
5. GET list of triggers — verify it returns recent triggers

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-110: Health Check Endpoint & App Wiring

| Field | Detail |
|-------|--------|
| **ID** | T-110 |
| **Name** | Health Check Endpoint & FastAPI App Wiring |
| **Status** | ⬜ |
| **Prerequisites** | T-104, T-105, T-106 |
| **Description** | Wire up the FastAPI application with lifespan management (startup/shutdown), dependency injection for repositories, health check endpoint, and basic system stats. |

**TODOs**:
- [ ] Implement `src/main.py` — FastAPI app with lifespan context manager as per Spec §8:
  - Startup: create MongoDB client, init repositories, init pipeline components, store in `app.state`
  - Shutdown: close MongoDB client, stop scheduler
- [ ] Implement `src/api/health.py`:
  - `GET /api/v1/health` — returns MongoDB connection status, ChromaDB status, scheduler status
  - `GET /api/v1/health/stats` — returns counts (triggers today, gate pass rate, etc.)
- [ ] Include all routers (triggers, health)
- [ ] Implement FastAPI dependency injection (repositories accessible in route handlers)
- [ ] Configure CORS if needed for future frontend

**Definition of Done**:
- `uvicorn src.main:app` starts without errors
- `/api/v1/health` returns `{status: "healthy", mongodb: "connected", ...}`
- `/docs` shows Swagger UI with all endpoints documented
- Repositories are properly injected into route handlers
- App shuts down cleanly (no hanging connections)

**Testing Steps**:
1. Start app, hit `/api/v1/health` — verify healthy response
2. Stop MongoDB, hit `/api/v1/health` — verify it reports unhealthy
3. Verify Swagger UI at `/docs` shows all endpoints
4. Create a trigger via API, verify it's stored in MongoDB

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-111: Week 1 Integration Test & Fixtures

| Field | Detail |
|-------|--------|
| **ID** | T-111 |
| **Name** | Week 1 Integration Tests & Test Fixtures |
| **Status** | ⬜ |
| **Prerequisites** | T-105, T-106, T-107, T-108, T-109, T-110 |
| **Description** | Write integration tests for all Week 1 components. Collect real NSE data as test fixtures for offline testing. Set up the test infrastructure (conftest, test DB). |

**TODOs**:
- [ ] Set up `tests/conftest.py`:
  - Test MongoDB connection (use a separate test database or mongomock)
  - Repository fixtures
  - Sample data factories (create_test_trigger, create_test_document)
- [ ] Collect and save test fixtures in `tests/fixtures/`:
  - 3-5 real NSE API responses (JSON files)
  - 3-5 real corporate announcement PDFs
  - 1-2 HTML announcement pages
- [ ] Write tests for:
  - `test_repositories/test_mongo_trigger.py` — CRUD operations
  - `test_repositories/test_mongo_document.py` — CRUD operations
  - `test_pipeline/test_rss_poller.py` — parse fixtures, dedup logic
  - `test_pipeline/test_document_fetcher.py` — download mock, type detection
  - `test_pipeline/test_text_extractor.py` — extract from fixture PDFs/HTML
  - `test_api/test_triggers.py` — API endpoint tests
  - `test_api/test_health.py` — health check tests

**Definition of Done**:
- All tests pass with `pytest`
- Test fixtures cover representative NSE documents
- Tests run in < 30 seconds (no live API calls in tests)
- Coverage > 70% for Week 1 code

**Testing Steps**:
1. `pytest tests/ -v` — all tests pass
2. `pytest tests/ --cov=src --cov-report=term-missing` — verify coverage

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

## Week 2: Gate + Vector Storage

### T-201: Watchlist Filter

| Field | Detail |
|-------|--------|
| **ID** | T-201 |
| **Name** | Watchlist Filter Implementation |
| **Status** | ⬜ |
| **Prerequisites** | T-102, T-103 |
| **Description** | Implement the first-pass filter that checks triggers against the configured watchlist. Matches by company symbol, company name/aliases, sector, and keywords. No LLM calls — this is a fast, free filter. |

**TODOs**:
- [ ] Implement `src/pipeline/layer2_gate/watchlist_filter.py` — `WatchlistFilter` as per Spec §6.1
- [ ] Build lookup tables at init: watched_symbols (set), watched_names (set with aliases), watched_sectors (set), keywords (set)
- [ ] Implement `check(trigger)` method with matching cascade:
  1. Symbol match (exact, case-insensitive)
  2. Name match (substring, case-insensitive, includes aliases)
  3. Sector match → then keyword check
  4. Content scan (company name mentioned in raw_content)
- [ ] Return structured result: `{passed: bool, reason: str, method: str}`
- [ ] Populate `config/watchlist.yaml` with real Capital Goods - Electrical Equipment companies (research from NSE)

**Definition of Done**:
- Filter correctly passes triggers for watched companies/sectors
- Filter correctly rejects triggers for unwatched companies
- Aliases work (e.g., "Inox Wind" matches "INOXWIND")
- Keywords are checked for sector-matched triggers
- Content scanning catches company mentions in announcement text
- Result includes clear reason for pass/reject

**Testing Steps**:
1. Trigger with watched company symbol → passes with "symbol_match"
2. Trigger with company alias in name → passes with "name_match"
3. Trigger with watched sector + keyword → passes with "keyword_match"
4. Trigger with watched sector but no keyword → rejected
5. Trigger with unwatched company → rejected
6. Trigger with watched company name in raw_content but no symbol → passes with "content_scan"

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-202: DSPy Setup & Gate Signature

| Field | Detail |
|-------|--------|
| **ID** | T-202 |
| **Name** | DSPy Setup & Gate Classification Signature |
| **Status** | ⬜ |
| **Prerequisites** | T-101 |
| **Description** | Set up DSPy integration, configure it with Anthropic Claude, and implement the GateClassification signature and GateModule. This is the first DSPy component in the system. |

**TODOs**:
- [ ] Verify DSPy works with Anthropic Claude in the project environment
  - Test: `dspy.LM("anthropic/claude-haiku")` initializes successfully
  - Test: a simple `dspy.Predict` call returns structured output
- [ ] Implement `src/dspy_modules/signatures.py` — `GateClassification` signature as per Spec §6.2
- [ ] Implement `src/dspy_modules/gate.py` — `GateModule` wrapping the signature with `dspy.Predict`
- [ ] Test with real announcement text — verify sensible pass/reject decisions
- [ ] Document any DSPy configuration needed (API key, model config)

**Definition of Done**:
- DSPy initializes with Anthropic Claude Haiku without errors
- `GateModule` accepts announcement text + company name + sector
- Returns typed `is_worth_investigating: bool` and `reason: str`
- Correctly classifies obvious cases (quarterly results = pass, routine compliance = reject)

**Testing Steps**:
1. Call GateModule with a quarterly results announcement — should return `is_worth_investigating=True`
2. Call with a routine "board meeting notice" — should return `is_worth_investigating=False`
3. Call with a major acquisition announcement — should return True
4. Call with garbled/empty text — should handle gracefully (not crash)
5. Mock the LLM for unit tests; use real LLM for manual validation

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-203: Gate Classifier (Wraps DSPy Module)

| Field | Detail |
|-------|--------|
| **ID** | T-203 |
| **Name** | Gate Classifier Service |
| **Status** | ⬜ |
| **Prerequisites** | T-202 |
| **Description** | Implement the GateClassifier that wraps the DSPy GateModule, handles errors with fail-open policy, manages input truncation, and returns structured gate results. |

**TODOs**:
- [ ] Implement `src/pipeline/layer2_gate/gate_classifier.py` — `GateClassifier` as per Spec §6.2
- [ ] Truncate input to 2000 chars to control LLM costs
- [ ] Implement fail-open error handling: if LLM call fails, default to PASS (don't silently drop triggers)
- [ ] Return structured result: `{passed: bool, reason: str, method: str, model: str}`
- [ ] Log each classification result (PASSED/REJECTED with reason)

**Definition of Done**:
- Classifier calls DSPy GateModule and returns structured result
- Input is truncated to control costs
- On LLM error, returns `passed=True` with `method="error_fallthrough"`
- Results are logged at INFO level

**Testing Steps**:
1. Classify a real announcement — verify structured result
2. Force an LLM error (invalid API key) — verify fail-open behavior
3. Pass text > 2000 chars — verify truncation (no error)
4. Verify logging output contains classification results

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-204: ChromaDB Vector Repository

| Field | Detail |
|-------|--------|
| **ID** | T-204 |
| **Name** | ChromaDB Vector Repository Implementation |
| **Status** | ⬜ |
| **Prerequisites** | T-101 |
| **Description** | Implement the vector store using ChromaDB in embedded (persistent) mode. Handles document chunking, embedding, storage, and semantic search. |

**TODOs**:
- [ ] Implement `src/repositories/vector.py` — `ChromaVectorRepository` as per Spec §4.3
- [ ] Initialize ChromaDB PersistentClient with configurable persist directory
- [ ] Create/get collection with cosine similarity
- [ ] Initialize SentenceTransformer embedding model (`all-MiniLM-L6-v2`)
- [ ] Implement `add_document(document_id, text, metadata)`:
  - Chunk text (fixed-size: 1000 chars with 200 char overlap)
  - Generate embeddings for each chunk
  - Store with metadata (document_id, company_symbol, chunk_index)
- [ ] Implement `search(query, n_results, where)`:
  - Embed query
  - Search with optional metadata filter
  - Return list of {id, text, metadata, distance}
- [ ] Implement `delete_document(document_id)` for cleanup

**Definition of Done**:
- Documents can be embedded and stored in ChromaDB
- Semantic search returns relevant results
- Metadata filtering works (e.g., filter by company_symbol)
- Data persists across app restarts (persist directory works)
- Chunking handles edge cases (very short text, very long text)

**Testing Steps**:
1. Add a document, search with related query — verify relevant result returned
2. Add documents for two companies, search with company filter — verify only matching company returned
3. Add a long document (10000+ chars) — verify multiple chunks created
4. Restart the process, search again — verify data persisted
5. Delete a document, search again — verify it's gone

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-205: Document Embedding Pipeline

| Field | Detail |
|-------|--------|
| **ID** | T-205 |
| **Name** | Document Embedding Pipeline |
| **Status** | ⬜ |
| **Prerequisites** | T-108, T-204 |
| **Description** | Connect text extraction output to the vector store. After a document's text is extracted, automatically chunk and embed it in ChromaDB for future semantic search. |

**TODOs**:
- [ ] Add embedding step after text extraction in the pipeline:
  - After `TextExtractor.extract()` succeeds, call `VectorRepository.add_document()`
  - Pass metadata: company_symbol, trigger_id, document_type, source
- [ ] Update `RawDocument.vector_id` after successful embedding
- [ ] Update `RawDocument.processing_status` to `COMPLETE` after embedding
- [ ] Handle embedding failures gracefully (document is still usable without embeddings)

**Definition of Done**:
- Extracted documents are automatically embedded in ChromaDB
- Document record is updated with vector_id and status=COMPLETE
- Embedding failure doesn't block the pipeline (text is still available)
- Embedded documents are searchable via vector repo

**Testing Steps**:
1. Process a trigger with a PDF → verify document ends up embedded in ChromaDB
2. Search ChromaDB for content from the PDF → verify it's found
3. Simulate embedding failure → verify document status shows error but text is preserved
4. Process 5 documents → verify all are searchable

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-206: Pipeline Orchestrator (Layer 1 + 2)

| Field | Detail |
|-------|--------|
| **ID** | T-206 |
| **Name** | Pipeline Orchestrator (Layers 1 + 2 Wired) |
| **Status** | ⬜ |
| **Prerequisites** | T-201, T-203, T-205 |
| **Description** | Implement the PipelineOrchestrator that processes triggers through Layer 1 (document fetch + extract + embed) and Layer 2 (watchlist filter + LLM gate). Wire all components together. |

**TODOs**:
- [ ] Implement `src/pipeline/orchestrator.py` — `PipelineOrchestrator` as per Spec §7
- [ ] `process_trigger(trigger)` method:
  1. Layer 1: Fetch documents → extract text → embed in vector store
  2. Layer 2: If human trigger → bypass gate. Else: watchlist filter → LLM gate
  3. Update trigger status at each step
  4. Stop processing if gate rejects
- [ ] `process_pending_triggers()` method: fetch pending triggers, process each
- [ ] Inject all dependencies (repos, fetcher, extractor, filter, classifier)
- [ ] Add logging at each pipeline step

**Definition of Done**:
- A trigger flows through: fetch → extract → embed → filter → gate → status update
- Human triggers skip the gate (status goes directly to GATE_PASSED)
- Filtered-out triggers have status FILTERED_OUT with reason
- Gate-passed triggers have status GATE_PASSED
- All transitions are logged

**Testing Steps**:
1. Process an NSE trigger for a watched company — verify it passes gate
2. Process an NSE trigger for an unwatched company — verify it's filtered out
3. Process a human trigger — verify it bypasses gate
4. Verify status transitions in MongoDB for each case
5. Verify documents are embedded after processing

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-207: APScheduler Integration

| Field | Detail |
|-------|--------|
| **ID** | T-207 |
| **Name** | Background Scheduler (RSS Polling + Trigger Processing) |
| **Status** | ⬜ |
| **Prerequisites** | T-206 |
| **Description** | Integrate APScheduler to run the RSS poller on a schedule (every 5 min) and process pending triggers (every 30 sec). |

**TODOs**:
- [ ] Add `AsyncIOScheduler` to app lifespan (start on startup, shutdown on cleanup)
- [ ] Schedule RSS poller: `interval`, configurable `polling_interval_seconds`
- [ ] Schedule trigger processor: `interval`, every 30 seconds
- [ ] Make scheduling configurable (enable/disable via `polling_enabled` setting)
- [ ] Add scheduler status to health check endpoint

**Definition of Done**:
- RSS poller runs automatically every 5 minutes (or configured interval)
- Pending triggers are processed every 30 seconds
- Scheduler can be disabled via config (for testing)
- Health check shows scheduler status (running/stopped, next run time)

**Testing Steps**:
1. Start app with polling enabled — verify RSS poll happens on schedule
2. Create a pending trigger, wait 30 seconds — verify it gets processed
3. Start with `polling_enabled=false` — verify no scheduled jobs run
4. Check `/api/v1/health` — verify scheduler status shown

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-208: Trigger List API + Status Filtering

| Field | Detail |
|-------|--------|
| **ID** | T-208 |
| **Name** | Trigger List API with Filtering |
| **Status** | ⬜ |
| **Prerequisites** | T-109 |
| **Description** | Enhance the trigger list endpoint with filtering by status, company, date range, and source. Add pagination. |

**TODOs**:
- [ ] Enhance `GET /api/v1/triggers/`:
  - Query params: `status`, `company`, `source`, `since` (datetime), `limit`, `offset`
  - Sort by `created_at` descending (newest first)
  - Return total count in response
- [ ] Add counts endpoint: `GET /api/v1/triggers/stats` — counts by status

**Definition of Done**:
- Filtering works for all supported params
- Pagination via limit/offset works
- Stats endpoint returns correct counts

**Testing Steps**:
1. Create triggers with different statuses — filter by status, verify correct results
2. Create triggers for different companies — filter by company, verify
3. Test pagination: limit=2, offset=0 then offset=2
4. Test stats endpoint — verify counts match

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-209: Populate Initial Watchlist

| Field | Detail |
|-------|--------|
| **ID** | T-209 |
| **Name** | Populate Watchlist with Real Companies |
| **Status** | ⬜ |
| **Prerequisites** | T-201 |
| **Description** | Research and populate the watchlist.yaml with actual companies in the Capital Goods — Electrical Equipment sector from NSE. Include accurate symbols, names, aliases. |

**TODOs**:
- [ ] Pull current NSE sector classification for Capital Goods — Electrical Equipment
- [ ] Identify 20-40 companies in this sector
- [ ] For each company: NSE symbol, full name, common aliases
- [ ] Set priority: "high" for 5-10 core companies, "normal" for rest
- [ ] Verify sector-specific keywords are comprehensive
- [ ] Save as `config/watchlist.yaml`

**Definition of Done**:
- Watchlist contains 20+ real companies with correct NSE symbols
- At least INOXWIND, SUZLON, SIEMENS, ABB, BHEL are included
- All company names and aliases are accurate
- Keywords cover common announcement types for this sector

**Testing Steps**:
1. Load watchlist, verify all symbols are valid NSE symbols
2. Spot-check 5 company names against NSE website
3. Run watchlist filter against recent NSE announcements — verify sensible pass/reject

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-210: Week 2 End-to-End Test

| Field | Detail |
|-------|--------|
| **ID** | T-210 |
| **Name** | Week 2 End-to-End Test with Real NSE Data |
| **Status** | ⬜ |
| **Prerequisites** | T-206, T-207, T-209 |
| **Description** | Run the complete Layer 1 + Layer 2 pipeline against live NSE data. Verify triggers are ingested, filtered, and classified correctly. Review gate decisions with the team. |

**TODOs**:
- [ ] Start full system against live NSE feed
- [ ] Let it run for 1-2 hours during market hours
- [ ] Review all triggers created: verify company identification, document downloads, text extraction
- [ ] Review gate decisions: are the right triggers passing? Are noise triggers being rejected?
- [ ] Document any issues found
- [ ] Fix critical issues

**Definition of Done**:
- System runs for 2+ hours without crashes
- Triggers are created for real NSE announcements
- Documents are downloaded and text extracted
- Gate makes sensible pass/reject decisions
- No duplicate triggers
- All issues documented

**Testing Steps**:
1. Start system, monitor logs for 2 hours
2. Query MongoDB: count triggers by status
3. Review 10 PASSED triggers — are they genuinely worth investigating?
4. Review 10 FILTERED_OUT triggers — were they correctly rejected?
5. Check for any ERROR status triggers — investigate root cause

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-211: Week 2 Unit Tests

| Field | Detail |
|-------|--------|
| **ID** | T-211 |
| **Name** | Week 2 Unit Tests |
| **Status** | ⬜ |
| **Prerequisites** | T-201, T-202, T-203, T-204 |
| **Description** | Write unit tests for all Week 2 components: watchlist filter, gate module (mocked LLM), vector repository. |

**TODOs**:
- [ ] `test_pipeline/test_watchlist_filter.py` — all 6 matching scenarios from T-201
- [ ] `test_pipeline/test_gate_classifier.py` — mock DSPy LLM, test pass/fail/error cases
- [ ] `test_repositories/test_vector.py` — ChromaDB add/search/delete (use in-memory mode)
- [ ] `test_pipeline/test_orchestrator.py` — integration test with mocked dependencies

**Definition of Done**:
- All tests pass
- Gate classifier tests use mocked LLM (no real API calls)
- Vector repo tests use ChromaDB in-memory (no disk persistence needed)
- Coverage > 70% for Week 2 code

**Testing Steps**:
1. `pytest tests/ -v` — all pass
2. `pytest tests/ --cov=src` — verify coverage

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

## Week 3: Deep Analysis (Layer 3)

### T-301: Layer 3+ Data Models

| Field | Detail |
|-------|--------|
| **ID** | T-301 |
| **Name** | Investigation, Assessment, Position, Report Data Models |
| **Status** | ⬜ |
| **Prerequisites** | T-103 |
| **Description** | Define all Pydantic models for Layers 3-5: Investigation (with sub-models for metrics, statements, search results, market data), DecisionAssessment, CompanyPosition, AnalysisReport. |

**TODOs**:
- [ ] Implement `src/models/investigation.py` as per Weeks 3-4 Spec §1.1:
  - SignificanceLevel enum
  - ExtractedMetric, ForwardStatement, WebSearchResult, MarketDataSnapshot, HistoricalContext
  - Investigation (main model)
- [ ] Implement `src/models/decision.py` as per Spec §1.2:
  - Recommendation enum, RecommendationTimeframe enum
  - DecisionAssessment
- [ ] Add `CompanyPosition` to `src/models/company.py` as per Spec §1.3
- [ ] Implement `src/models/report.py` as per Spec §1.4:
  - ReportDeliveryStatus enum
  - AnalysisReport (with feedback fields)

**Definition of Done**:
- All models instantiate correctly with defaults
- Sub-models (ExtractedMetric, etc.) serialize/deserialize cleanly
- Enum values are string-compatible for MongoDB
- Models pass mypy type checking

**Testing Steps**:
1. Create Investigation with all sub-models populated — verify serialization
2. Create minimal Investigation (required fields only) — verify defaults
3. Round-trip each model: create → dump → reconstruct
4. Test all enum values serialize as strings

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-302: Layer 3+ Repository Implementations

| Field | Detail |
|-------|--------|
| **ID** | T-302 |
| **Name** | MongoDB Repositories for Investigation, Assessment, Position, Report |
| **Status** | ⬜ |
| **Prerequisites** | T-301, T-104 |
| **Description** | Implement MongoDB repositories for all new data models. Include the critical `get_past_inconclusive` query for Layer 4's past investigation resurrection. |

**TODOs**:
- [ ] `MongoInvestigationRepository`:
  - save, get, get_by_company(symbol, limit)
  - `get_past_inconclusive(symbol)` — find investigations where `is_significant=True` but no linked assessment changed the recommendation
- [ ] `MongoAssessmentRepository`:
  - save, get, get_by_company(symbol, limit)
- [ ] `MongoPositionRepository`:
  - get_position(symbol), upsert_position(position)
- [ ] `MongoReportRepository`:
  - save, get, get_recent(limit), update_feedback(report_id, rating, comment, by)
- [ ] Add MongoDB indexes:
  - investigations: company_symbol, created_at, is_significant
  - assessments: company_symbol, created_at
  - positions: company_symbol (unique)
  - reports: created_at, company_symbol

**Definition of Done**:
- All CRUD operations work
- `get_past_inconclusive` correctly identifies investigations that were significant but didn't lead to recommendation changes
- `upsert_position` creates on first call, updates on subsequent calls
- `update_feedback` updates feedback fields atomically
- Indexes are created at startup

**Testing Steps**:
1. Save and retrieve each model type
2. Create 5 investigations, 2 significant + no recommendation change → verify `get_past_inconclusive` returns those 2
3. Upsert position twice — verify it updates (not duplicates)
4. Update feedback on a report — verify fields updated

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-303: Web Search Tool

| Field | Detail |
|-------|--------|
| **ID** | T-303 |
| **Name** | Web Search Tool (Brave/Tavily) |
| **Status** | ⬜ |
| **Prerequisites** | T-101 |
| **Description** | Implement web search integration for investigation enrichment. Support Brave Search API and Tavily as providers. |

**TODOs**:
- [ ] Implement `src/agents/tools/web_search.py` — `WebSearchTool` as per Weeks 3-4 Spec §4.1
- [ ] Implement Brave Search API integration
- [ ] Implement Tavily API integration (alternative)
- [ ] Configurable provider selection via settings
- [ ] Return standardized results: `[{title, url, snippet}]`
- [ ] Handle rate limiting, timeouts, and API errors
- [ ] Add search API key to settings

**Definition of Done**:
- Search returns relevant results for financial queries
- Both Brave and Tavily adapters work
- API errors return empty list (don't crash)
- Rate limiting is handled

**Testing Steps**:
1. Search "INOXWIND quarterly results 2026" — verify relevant results
2. Search with empty query — verify no crash
3. Test with invalid API key — verify graceful error
4. Save real API responses as test fixtures

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-304: Market Data Tool

| Field | Detail |
|-------|--------|
| **ID** | T-304 |
| **Name** | Market Data Tool (yfinance) |
| **Status** | ⬜ |
| **Prerequisites** | T-101 |
| **Description** | Implement market data fetching for Indian stocks via yfinance. Returns price, valuation metrics, and recent performance. |

**TODOs**:
- [ ] Implement `src/agents/tools/market_data.py` — `MarketDataTool` as per Spec §4.2
- [ ] Try NSE symbol (.NS suffix), fallback to BSE (.BO suffix)
- [ ] Extract: current price, market cap (convert to Cr), P/E, P/B, 52-week range, volume
- [ ] Calculate price changes: 1-day, 1-week, 1-month from historical data
- [ ] Handle missing data gracefully (return None for unavailable fields)
- [ ] Note: FII/DII/promoter data NOT available in yfinance — return None, document for future

**Definition of Done**:
- Returns MarketDataSnapshot for real NSE stocks
- Price and basic metrics are populated for major stocks (INOXWIND, SUZLON, etc.)
- Missing data fields are None (not errors)
- Symbol not found returns snapshot with data_source="yfinance_unavailable"

**Testing Steps**:
1. Get snapshot for INOXWIND — verify price and P/E are populated
2. Get snapshot for invalid symbol — verify graceful handling
3. Get snapshot for 5 different companies — verify consistency
4. Check that FII/DII fields are None (expected for yfinance)

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-305: Layer 3 DSPy Signatures

| Field | Detail |
|-------|--------|
| **ID** | T-305 |
| **Name** | DSPy Signatures for Layer 3 (Metrics, Search, Synthesis) |
| **Status** | ⬜ |
| **Prerequisites** | T-202 |
| **Description** | Implement DSPy signatures for MetricsExtraction, WebSearchQueryGeneration, WebResultSynthesis, and InvestigationSynthesis. |

**TODOs**:
- [ ] Add to `src/dspy_modules/signatures.py`:
  - `MetricsExtraction` — extracts financial metrics, forward statements, highlights from document text
  - `WebSearchQueryGeneration` — generates 3-5 targeted search queries
  - `WebResultSynthesis` — summarizes web results for relevance
  - `InvestigationSynthesis` — comprehensive synthesis of all analysis components
- [ ] Each signature has detailed docstrings that serve as the system prompt
- [ ] Output fields use JSON string format for structured data (DSPy constraint)

**Definition of Done**:
- All signatures defined with typed input/output fields
- Docstrings provide clear instructions for the LLM
- Output fields that return structured data use JSON string format
- Signatures are importable and usable with `dspy.Predict` and `dspy.ChainOfThought`

**Testing Steps**:
1. Use each signature with `dspy.Predict` and a real LLM — verify output format
2. Verify JSON output fields are parseable as JSON
3. Test with real quarterly results text — verify metrics extraction makes sense

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-306: Layer 3 DSPy Modules

| Field | Detail |
|-------|--------|
| **ID** | T-306 |
| **Name** | DSPy Modules for Layer 3 (Pipeline Composition) |
| **Status** | ⬜ |
| **Prerequisites** | T-305 |
| **Description** | Implement DSPy modules that compose the Layer 3 reasoning pipeline: MetricsExtractionModule, WebSearchModule, SynthesisModule, and the combined DeepAnalysisPipeline. |

**TODOs**:
- [ ] Implement `src/dspy_modules/analysis.py`:
  - `MetricsExtractionModule` — wraps MetricsExtraction with ChainOfThought
  - `WebSearchModule` — wraps WebSearchQueryGeneration
  - `SynthesisModule` — wraps InvestigationSynthesis with ChainOfThought
  - `DeepAnalysisPipeline` — composes all three modules
- [ ] Use `dspy.ChainOfThought` for complex reasoning (metrics, synthesis)
- [ ] Use `dspy.Predict` for simpler tasks (search query generation)

**Definition of Done**:
- Each module runs independently with correct inputs/outputs
- DeepAnalysisPipeline chains all modules together
- Chain of thought improves reasoning quality (compare with/without)
- Pipeline handles partial failures (e.g., web search fails but synthesis still works)

**Testing Steps**:
1. Run MetricsExtractionModule on a real quarterly report — review extracted metrics
2. Run WebSearchModule — verify it generates sensible queries
3. Run SynthesisModule with real inputs — review synthesis quality
4. Run full DeepAnalysisPipeline end-to-end — review complete output

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-307: Deep Analyzer Implementation

| Field | Detail |
|-------|--------|
| **ID** | T-307 |
| **Name** | DeepAnalyzer (Layer 3 Orchestration) |
| **Status** | ⬜ |
| **Prerequisites** | T-302, T-303, T-304, T-306 |
| **Description** | Implement the DeepAnalyzer that orchestrates the complete Layer 3 flow: gather historical context, fetch market data, run web searches, run DSPy analysis pipeline, parse outputs, and store Investigation. |

**TODOs**:
- [ ] Implement `src/pipeline/layer3_analysis/analyzer.py` — `DeepAnalyzer` as per Weeks 3-4 Spec §5
- [ ] Orchestrate:
  1. Get document text (from trigger + linked documents)
  2. Gather historical context from vector search + past investigations
  3. Fetch market data via MarketDataTool
  4. Generate and execute web searches
  5. Run DeepAnalysisPipeline (DSPy)
  6. Parse all outputs (JSON → typed models)
  7. Store Investigation in MongoDB
- [ ] Implement JSON parsing helpers with robust error handling
- [ ] Track token usage and processing time
- [ ] Handle partial failures (analysis continues even if web search fails)

**Definition of Done**:
- Given a gate-passed trigger, produces a complete Investigation
- Historical context is retrieved from past investigations and vector search
- Web search enriches the analysis
- Market data is included
- Significance assessment is reasonable
- Investigation is persisted in MongoDB
- Processing time and token usage are tracked

**Testing Steps**:
1. Run with a real INOXWIND quarterly results trigger — review full Investigation
2. Run with a new company (no history) — verify handles empty context gracefully
3. Disable web search (invalid API key) — verify analysis still completes
4. Disable market data (invalid symbol) — verify analysis still completes
5. Review extracted metrics against actual PDF — spot check accuracy

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-308: Layer 3 Quality Review

| Field | Detail |
|-------|--------|
| **ID** | T-308 |
| **Name** | Layer 3 Output Quality Review & Prompt Tuning |
| **Status** | ⬜ |
| **Prerequisites** | T-307 |
| **Description** | Run Layer 3 against 3-5 real announcements. Review output quality with the team. Iterate on DSPy signature docstrings (prompts) to improve accuracy. |

**TODOs**:
- [ ] Process 3-5 real triggers through Layer 3
- [ ] For each, review: extracted metrics accuracy, synthesis quality, significance assessment
- [ ] Identify patterns in errors or low-quality outputs
- [ ] Refine DSPy signature docstrings based on findings
- [ ] Re-run and compare quality
- [ ] Save good/bad examples as future DSPy training data

**Definition of Done**:
- Team reviewed 3+ Layer 3 outputs
- Major prompt issues identified and fixed
- Metrics extraction accuracy > 80% (spot-checked against source PDFs)
- Synthesis narratives are coherent and reference specific numbers
- Examples saved for future DSPy optimization

**Testing Steps**:
1. Compare extracted metrics against actual PDF values — calculate accuracy
2. Team rates synthesis quality (1-5) for each output
3. Before/after comparison for any prompt changes

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

## Week 4: Decision Assessment + Reports (Layers 4-5)

### T-401: Layer 4 DSPy Signature & Module

| Field | Detail |
|-------|--------|
| **ID** | T-401 |
| **Name** | DSPy Signature & Module for Decision Evaluation |
| **Status** | ⬜ |
| **Prerequisites** | T-305 |
| **Description** | Implement the DecisionEvaluation DSPy signature and DecisionModule. This is the reasoning core of Layer 4. |

**TODOs**:
- [ ] Add `DecisionEvaluation` signature to `src/dspy_modules/signatures.py` as per Spec §3.1
- [ ] Implement `src/dspy_modules/decision.py` — `DecisionModule` using ChainOfThought
- [ ] Signature must explicitly instruct LLM to consider past inconclusive investigations
- [ ] Output includes: should_change, new_recommendation, timeframe, confidence, reasoning, key_factors

**Definition of Done**:
- Module produces well-reasoned buy/sell/hold decisions
- Past inconclusive investigations are referenced in reasoning when relevant
- Confidence scores are calibrated (not always 0.9+)
- Reasoning is specific and references actual findings

**Testing Steps**:
1. Test with strong positive findings — should recommend buy with high confidence
2. Test with ambiguous findings — should recommend hold with moderate confidence
3. Test with no prior recommendation — should establish initial recommendation
4. Test with contradicting new evidence — should recommend changing

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-402: Decision Assessor Implementation

| Field | Detail |
|-------|--------|
| **ID** | T-402 |
| **Name** | DecisionAssessor (Layer 4 Orchestration) |
| **Status** | ⬜ |
| **Prerequisites** | T-302, T-401 |
| **Description** | Implement the DecisionAssessor that pulls historical context, runs the DecisionModule, and updates company positions when recommendations change. |

**TODOs**:
- [ ] Implement `src/pipeline/layer4_decision/assessor.py` — `DecisionAssessor` as per Spec §6
- [ ] Retrieve current CompanyPosition
- [ ] Retrieve past investigations (including inconclusive via `get_past_inconclusive`)
- [ ] Run DecisionModule with all context
- [ ] Parse structured output into DecisionAssessment
- [ ] If recommendation changed: update CompanyPosition with history tracking
- [ ] Track processing time

**Definition of Done**:
- Produces DecisionAssessment with recommendation, confidence, and reasoning
- Past inconclusive investigations are included in context
- CompanyPosition is updated when recommendation changes
- Position history is maintained (previous recommendations preserved)
- First assessment for a company creates the initial position

**Testing Steps**:
1. First assessment for a new company — creates position with initial recommendation
2. Second assessment with confirming evidence — maintains recommendation, updates basis
3. Assessment with contradicting evidence — changes recommendation, old one in history
4. Verify CompanyPosition.recommendation_history tracks all changes

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-403: Layer 5 DSPy Signature & Module

| Field | Detail |
|-------|--------|
| **ID** | T-403 |
| **Name** | DSPy Signature & Module for Report Generation |
| **Status** | ⬜ |
| **Prerequisites** | T-305 |
| **Description** | Implement the ReportGeneration DSPy signature and ReportModule. Produces structured markdown reports from investigation and assessment data. |

**TODOs**:
- [ ] Add `ReportGeneration` signature to `src/dspy_modules/signatures.py` as per Spec §3.1
- [ ] Implement `src/dspy_modules/report.py` — `ReportModule` using Predict
- [ ] Report structure: title, executive summary, trigger, findings, context, recommendation, risks, sources
- [ ] Output is markdown-formatted

**Definition of Done**:
- Generates well-structured markdown reports
- Executive summary is 2-3 sentences and actionable
- Report references specific numbers and sources
- Recommendation section is clear and prominent

**Testing Steps**:
1. Generate report from real investigation + assessment — review quality
2. Verify markdown renders correctly
3. Check that executive summary is concise and useful

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-404: Report Generator Implementation

| Field | Detail |
|-------|--------|
| **ID** | T-404 |
| **Name** | ReportGenerator (Layer 5 Orchestration) |
| **Status** | ⬜ |
| **Prerequisites** | T-302, T-403 |
| **Description** | Implement ReportGenerator that takes an Investigation and DecisionAssessment and produces an AnalysisReport stored in MongoDB. |

**TODOs**:
- [ ] Implement `src/pipeline/layer5_report/generator.py` — `ReportGenerator` as per Spec §7
- [ ] Format all inputs for the DSPy ReportModule
- [ ] Create AnalysisReport with title, executive_summary, report_body, recommendation_summary
- [ ] Store report in MongoDB via ReportRepository

**Definition of Done**:
- Produces AnalysisReport with all fields populated
- Report body is well-formatted markdown
- Recommendation summary is a quick-glance line (e.g., "BUY (Confidence: 78%, Timeframe: medium_term)")
- Report is stored in MongoDB

**Testing Steps**:
1. Generate report from real data — verify all fields populated
2. Render report_body as markdown — verify formatting
3. Retrieve report from MongoDB — verify persistence

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-405: Report Deliverer (Slack + Email)

| Field | Detail |
|-------|--------|
| **ID** | T-405 |
| **Name** | Report Delivery (Slack Webhook) |
| **Status** | ⬜ |
| **Prerequisites** | None |
| **Description** | Implement report delivery via Slack webhook. Send a summary notification with the recommendation when a new report is generated. |

**TODOs**:
- [ ] Implement `src/pipeline/layer5_report/deliverer.py` — `ReportDeliverer` as per Spec §7
- [ ] Slack delivery: format as Block Kit message with header, recommendation, summary
- [ ] Include report ID for dashboard cross-reference
- [ ] Handle delivery failures (log error, don't crash pipeline)
- [ ] Optional: email delivery stub (implement when needed)

**Definition of Done**:
- Slack message appears in configured channel when report is generated
- Message shows: emoji (green/red/yellow), title, recommendation, executive summary
- Delivery failure is logged but doesn't break pipeline

**Testing Steps**:
1. Configure real Slack webhook — send a test report — verify message appears
2. Configure invalid webhook — verify graceful failure
3. Verify message formatting in Slack (Block Kit renders correctly)

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-406: Wire Full Pipeline (Layers 3-5)

| Field | Detail |
|-------|--------|
| **ID** | T-406 |
| **Name** | Update Pipeline Orchestrator (Full Pipeline) |
| **Status** | ⬜ |
| **Prerequisites** | T-307, T-402, T-404, T-405 |
| **Description** | Update the PipelineOrchestrator to include Layers 3-5. A trigger now flows through the complete pipeline: ingest → gate → analyze → decide → report → deliver. |

**TODOs**:
- [ ] Add DeepAnalyzer, DecisionAssessor, ReportGenerator, ReportDeliverer to orchestrator
- [ ] Update `process_trigger()`:
  - After gate passes → Layer 3 (analyze)
  - If significant → Layer 4 (assess)
  - Always after Layer 4 → Layer 5 (generate report + deliver)
  - Update trigger status at each transition
- [ ] Add all new dependencies to app lifespan/startup
- [ ] Inject new repos and tools into orchestrator

**Definition of Done**:
- Complete pipeline runs end-to-end: trigger → report delivery
- Status transitions are tracked: ANALYZING → ANALYZED → ASSESSING → ASSESSED → REPORTED
- Non-significant investigations stop after Layer 3 (don't run Layer 4)
- All components properly initialized at startup

**Testing Steps**:
1. Process a significant trigger end-to-end — verify report generated and delivered
2. Process a non-significant trigger — verify it stops after Layer 3
3. Check MongoDB for all intermediate records (trigger, investigation, assessment, report)
4. Verify status transitions in trigger record

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-407: Layer 3-5 API Endpoints

| Field | Detail |
|-------|--------|
| **ID** | T-407 |
| **Name** | API Endpoints for Investigations, Reports, Positions, Feedback |
| **Status** | ⬜ |
| **Prerequisites** | T-302 |
| **Description** | Add API endpoints to query investigations, view reports, check company positions, and submit feedback on reports. |

**TODOs**:
- [ ] `src/api/investigations.py`:
  - `GET /api/v1/investigations/{id}` — full investigation details
  - `GET /api/v1/investigations/company/{symbol}` — list by company
- [ ] `src/api/reports.py`:
  - `GET /api/v1/reports/` — list recent reports
  - `GET /api/v1/reports/{id}` — full report with markdown body
  - `POST /api/v1/reports/{id}/feedback` — submit thumbs up/down + comment
- [ ] `src/api/positions.py`:
  - `GET /api/v1/positions/` — all current company positions
  - `GET /api/v1/positions/{symbol}` — position with history
- [ ] Include routers in main app

**Definition of Done**:
- All endpoints return correct data from MongoDB
- Feedback endpoint updates report with rating and comment
- Positions endpoint shows current recommendation for each company
- Swagger UI documents all new endpoints

**Testing Steps**:
1. Create investigation via pipeline, query via API — verify data matches
2. Query reports list — verify recent reports returned
3. Submit feedback on a report — verify it's stored
4. Query positions — verify current recommendations shown

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-408: End-to-End Pipeline Test

| Field | Detail |
|-------|--------|
| **ID** | T-408 |
| **Name** | Week 4 Full End-to-End Test |
| **Status** | ⬜ |
| **Prerequisites** | T-406, T-407 |
| **Description** | Run the complete pipeline against real NSE data. Process multiple triggers, review all outputs (investigations, decisions, reports). Verify Slack delivery. |

**TODOs**:
- [ ] Process 5+ triggers through the complete pipeline
- [ ] At least 1 human trigger and 4 RSS triggers
- [ ] Review investigation quality (metrics accuracy, synthesis)
- [ ] Review decision quality (recommendations make sense)
- [ ] Review report quality (readable, specific, actionable)
- [ ] Verify Slack notifications received
- [ ] Time the full pipeline (target: < 5 min per trigger)
- [ ] Document issues and improvements needed

**Definition of Done**:
- 5+ triggers processed end-to-end without crashes
- Reports are delivered to Slack
- Team reviews outputs and rates quality
- Pipeline completes in < 5 min per trigger
- No critical bugs

**Testing Steps**:
1. Submit human trigger for INOXWIND — trace through all 5 layers
2. Let RSS poller pick up real announcements — verify automated pipeline works
3. Review all MongoDB records for consistency
4. Check Slack for delivered reports
5. Time each pipeline run

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-409: Prompt Refinement (Decision + Report)

| Field | Detail |
|-------|--------|
| **ID** | T-409 |
| **Name** | DSPy Prompt Refinement for Decision & Report Quality |
| **Status** | ⬜ |
| **Prerequisites** | T-408 |
| **Description** | Based on end-to-end test results, refine DSPy signature docstrings for DecisionEvaluation and ReportGeneration to improve output quality. |

**TODOs**:
- [ ] Review decision outputs — are recommendations well-reasoned?
- [ ] Review report outputs — are they scannable and actionable?
- [ ] Refine signature docstrings based on patterns found
- [ ] Re-run and compare quality
- [ ] Save good examples as future DSPy training data

**Definition of Done**:
- Decision quality improved (team rates higher after refinement)
- Report quality improved (clearer, more actionable)
- Prompt changes documented

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-410: Error Handling & Retry Logic

| Field | Detail |
|-------|--------|
| **ID** | T-410 |
| **Name** | Error Handling, Retries, and Graceful Degradation |
| **Status** | ⬜ |
| **Prerequisites** | T-406 |
| **Description** | Add robust error handling across the pipeline: LLM call retries, partial failure handling, and clear error status tracking. |

**TODOs**:
- [ ] LLM calls: retry up to 3 times with exponential backoff on transient errors (429, 500, timeout)
- [ ] Web search failure: continue analysis without web results
- [ ] Market data failure: continue analysis without market data
- [ ] Layer 3 failure: mark trigger as ERROR with details
- [ ] Layer 4 failure: mark trigger as ERROR, investigation is still preserved
- [ ] Layer 5 failure: mark delivery as failed, report still stored
- [ ] Add error details to trigger's status_history

**Definition of Done**:
- Pipeline handles all expected failure modes without crashing
- Partial failures allow the pipeline to continue where possible
- Error status includes actionable details for debugging
- Retry logic prevents unnecessary failures from transient errors

**Testing Steps**:
1. Simulate LLM timeout — verify retry and eventual success/failure
2. Simulate web search failure — verify analysis continues
3. Simulate MongoDB write failure — verify error status set
4. Check status_history for error details

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

### T-411: Structured Logging

| Field | Detail |
|-------|--------|
| **ID** | T-411 |
| **Name** | Structured Logging with Pipeline Traceability |
| **Status** | ⬜ |
| **Prerequisites** | T-406 |
| **Description** | Implement structured logging (using structlog) that traces a trigger through the entire pipeline. Every log entry includes trigger_id for correlation. |

**TODOs**:
- [ ] Configure structlog with JSON output
- [ ] Add trigger_id and company_symbol to logging context at pipeline start
- [ ] Log at each pipeline stage: gate decision, analysis start/end, decision, report delivery
- [ ] Log LLM call details: model, tokens used, latency
- [ ] Log errors with full context

**Definition of Done**:
- All pipeline logs include trigger_id for filtering
- Can trace a trigger's full journey by filtering logs on trigger_id
- LLM costs are trackable via token usage logs
- Log format is JSON (machine-parseable)

**Testing Steps**:
1. Process a trigger — filter logs by trigger_id — verify complete trace
2. Verify token usage is logged for each LLM call
3. Verify error logs include trigger_id and error details

**Files Created/Modified**: _(fill when done)_
**Test Cases Written**: _(fill when done)_

---

## Week 5-6: Dashboard + Polish (Outline)

> Detailed specs for Weeks 5-6 will be written after Weeks 3-4 are underway. High-level tasks listed here for planning visibility.

### T-501: Streamlit Dashboard — Trigger View
| **Status** | ⬜ | **Prerequisites** | T-407 |

### T-502: Streamlit Dashboard — Report View
| **Status** | ⬜ | **Prerequisites** | T-407 |

### T-503: Streamlit Dashboard — Human Trigger Form
| **Status** | ⬜ | **Prerequisites** | T-407 |

### T-504: Streamlit Dashboard — Positions Overview
| **Status** | ⬜ | **Prerequisites** | T-407 |

### T-505: Streamlit Dashboard — Feedback Interface
| **Status** | ⬜ | **Prerequisites** | T-407 |

### T-506: Watchlist Management UI
| **Status** | ⬜ | **Prerequisites** | T-501 |

### T-507: Production Deployment (Docker Compose on EC2)
| **Status** | ⬜ | **Prerequisites** | T-408 |

### T-508: Production Monitoring & Alerting
| **Status** | ⬜ | **Prerequisites** | T-507 |

### T-509: Documentation for Team
| **Status** | ⬜ | **Prerequisites** | All |

### T-510: 2-Week Live Validation
| **Status** | ⬜ | **Prerequisites** | T-507 |
