# tuJanalyst UI Specification

## Document Purpose

This document defines the user interface for tuJanalyst's web dashboard. It covers two primary interfaces — **Admin** and **Investor/Analyst** — grounded in the existing 5-layer pipeline architecture, current API endpoints, and data models. The spec is designed for the MVP (Streamlit or FastAPI + HTMX), with notes on what evolves when the React frontend arrives in Iteration 3.

---

## Roles and Access

### MVP (Weeks 5-6)

Two logical views with explicit roles. Authentication and strict RBAC are deferred unless there is a low-effort implementation that materially improves delivery.

| Role | Description | Access |
|------|-------------|--------|
| Admin | System operator. Monitors pipeline health, manages configuration, reviews costs. | Full admin + investor/analyst visibility |
| Analyst | Investment team member operating the workflow. | Investor/Analyst views and actions |
| Investor | Investment team member consuming and annotating outputs. | Same permissions as Analyst in MVP |

For MVP, role handling is "soft": UI-level role switch and trusted-team operation, with hard auth/RBAC deferred.

### Agent Access (MVP)

Agent permissions are defined in configuration (not UI) using both:
- data domains (`triggers`, `documents`, `reports`, `notes`, `users`, `licenses`)
- actions (`read`, `create`, `update`, `delete`)

Admin UI includes a placeholder view that shows active policy source/path, but policy editing remains config-driven in MVP.

### Iteration 3+

When PostgreSQL control plane and React frontend arrive:

| Role | Description |
|------|-------------|
| Admin | User management, licence keys, system config, full audit logs |
| Analyst | Creates manual triggers, annotates, reviews all investigations, curates recommendations |
| Investor (read-mostly) | Consumes recommendations, views reports, sets watchlists and notification preferences |

In later iterations, Analyst and Investor permissions can diverge without changing page IA.

---

## Navigation Structure

```
tuJanalyst
├── Admin
│   ├── Pipeline Dashboard (default admin view)
│   ├── Gate Performance
│   ├── Cost & Usage
│   ├── Data Sources
│   ├── Watchlist Management + Agent Policy Placeholder
│   └── System Settings (Iteration 3)
│
└── Investor/Analyst
    ├── Command Center (default view)
    ├── Company Positions
    ├── Investigation Explorer
    ├── Chat (Iteration 1+)
    ├── Manual Trigger
    ├── Performance Tracker
    └── Notifications
```

---

## Admin Interface

### 1. Pipeline Dashboard

**Purpose:** Real-time view of what the system is doing. The single screen an admin checks first thing in the morning.

**Layout:** Header stats row + two-column body (left: trigger flow, right: activity feed).

#### Header Stats (KPI Cards)

MVP-required KPI set:

| KPI | Definition | Source | Refresh |
|-----|------------|--------|---------|
| Total Triggers Processed | Count in selected date range | `GET /api/v1/triggers/stats?since=...` | 30s auto |
| Trigger Distribution by Source/Type | Count split by `nse_rss` / `bse_rss` / `human` | Existing triggers + aggregation endpoint extension | 30s auto |
| Stage Conversion Funnel | Progression across pipeline stages | `GET /api/v1/triggers/stats` → `counts_by_status` | 30s auto |
| Failure Rate by Stage/Reason | `% error` and top reasons from gate/pipeline failures | Trigger detail/status history endpoint extension | 30s auto |
| Cost per Completed Report | `(LLM + web search costs) / completed reports` | Cost aggregation endpoint | 5m auto |

Secondary indicator (non-KPI card): `System Status` from `GET /api/v1/health`.

#### Trigger Flow Visualization

A horizontal funnel or Sankey diagram showing trigger progression through the 5-layer pipeline:

```
[Ingested] → [Gate Passed] → [Analyzed] → [Assessed] → [Reported]
    ↓              ↓              ↓
[Filtered Out]  [Not Significant] [No Change]
```

Data: `GET /api/v1/triggers/stats` → `counts_by_status`. Map each `TriggerStatus` enum value to a pipeline stage.

Status mapping:
- **Layer 1 (Ingestion):** `pending`
- **Layer 2 (Gate):** `gate_passed`, `filtered_out`
- **Layer 3 (Analysis):** `analyzing`, `analyzed`
- **Layer 4 (Assessment):** `assessing`, `assessed`
- **Layer 5 (Report):** `reported`
- **Error:** `error` (shown as separate indicator)

For admin KPI consistency, funnel conversion and gate-pass views should exclude `human` triggers by default, with a toggle to include them.

#### Trigger Distribution by Source

Pie or donut chart breaking down triggers by `TriggerSource`:
- `nse_rss` — automated NSE feed
- `bse_rss` — automated BSE feed
- `human` — manual submissions

Time filter: Today / Last 7 days / Last 30 days / Custom range.

#### Recent Activity Feed

Reverse-chronological list of recent system events:
- "SUZLON trigger ingested from NSE RSS" (Layer 1)
- "INOXWIND passed gate — keyword match: quarterly results" (Layer 2)
- "SUZLON investigation complete — significance: HIGH" (Layer 3)
- "SUZLON recommendation changed: HOLD → BUY (confidence: 80%)" (Layer 4)
- "SUZLON report delivered via Slack" (Layer 5)

Data: Query `triggers` collection sorted by `updated_at` desc, show latest 50. Each entry shows the trigger's current status + last status transition reason from `status_history`.

#### Trigger Table (MVP + Extended)

Below the visualization, a filterable data table:

| Column (MVP) | Source Field |
|-------------|-------------|
| Time | `created_at` |
| Trigger ID | `trigger_id` |
| Company | `company_symbol` / `company_name` |
| Source | `source` (badge: RSS / Human) |
| Status | `status` (color-coded badge) |

Filters: Status, Source, Company, Date Range.
Pagination: 20 per page (matches existing API `limit` default).
Extended row details (content preview, gate reason, full status timeline) require a trigger detail endpoint/contract extension.

---

### 2. Gate Performance

**Purpose:** Monitor the quality and accuracy of Layer 2 filtering. ADR-003 sets a threshold: if gate accuracy drops below 80%, escalate to a more capable model.

#### Gate Metrics

| Metric | Calculation |
|--------|-------------|
| Total Evaluated | Count of triggers that reached Layer 2 (not human triggers) |
| Passed | Count with `gate_result.passed = true` |
| Filtered | Count with `gate_result.passed = false` |
| Pass Rate | Passed / Total |
| Filter Breakdown | Count by `gate_result.method`: `watchlist_filter`, `keyword_filter`, `llm_classification` |

#### Filter Funnel

Three-stage funnel showing where triggers drop out:

```
[All Triggers] → [Passed Watchlist] → [Passed Keywords] → [Passed LLM Gate]
     100              70                   35                  15
```

Data: Derived from `gate_result.method` field on filtered triggers.

#### Gate Decision Log

Table of recent gate decisions:

| Column | Data |
|--------|------|
| Time | `created_at` |
| Company | `company_symbol` |
| Content | `raw_content` (truncated) |
| Decision | Passed / Filtered (badge) |
| Method | Which filter caught it |
| Reason | `gate_result.reason` |

**Human Review Feature (MVP stretch):** Admin can flag a gate decision as "correct" or "incorrect." This builds the labeled dataset needed for DSPy optimization (per the prompt optimization strategy in the technical spec). Store as a simple annotation on the trigger document.

---

### 3. Cost & Usage

**Purpose:** Track `LLM + web search` API spend for operations control.

**Note:** There is a known P0 bug where token counts are always reported as zero (`total_input_tokens`, `total_output_tokens` on Investigation model). This must be fixed before this dashboard is meaningful. The UI should be built regardless — show zeros with a warning banner until the bug is resolved.

#### Cost Overview

| Metric | Source |
|--------|--------|
| Estimated Cost Today | Sum of LLM + web search costs over today's completed pipeline runs |
| Estimated Cost This Month | Same, monthly aggregate |
| Cost per Completed Report (avg) | `(LLM + web search total cost) / delivered reports` |
| Cost Split by Provider | LLM vs web search share (%) |

Cost calculation (MVP):
- Claude Haiku (gate): ~$0.01 per call
- Claude Sonnet (analysis/decision/report): ~$0.05-0.15 per call depending on context length
- Brave/Tavily: include per-request pricing from configured provider

#### Usage Charts

- **Daily API calls** (line chart, last 30 days): Broken down by layer (Gate / Analysis / Decision / Report)
- **Token usage** (stacked bar chart): Input vs output tokens per day
- **Cost trend** (line chart): Daily estimated cost with 7-day moving average

#### Model Usage Breakdown

Table showing per-model stats:

| Model | Calls | Input Tokens | Output Tokens | Est. Cost |
|-------|-------|-------------|---------------|-----------|
| claude-haiku | 150 | 45,000 | 3,000 | $1.50 |
| claude-sonnet | 45 | 180,000 | 90,000 | $12.00 |

Data: Aggregate from `llm_model_used`, `total_input_tokens`, `total_output_tokens` across investigations, assessments (when model is added), and reports.

---

### 4. Data Sources

**Purpose:** Monitor the health and status of all external data feeds and APIs.

#### Source Health Cards

| Source | Health Check | Metrics |
|--------|-------------|---------|
| NSE RSS Feed | Last successful poll time, HTTP status | Triggers/day, avg items/poll |
| BSE RSS Feed | Last successful poll time, HTTP status | Triggers/day, avg items/poll |
| Brave/Tavily Search API | Last successful call, error rate | Calls/day, failures |
| yfinance (Market Data) | Last successful fetch, error rate | Lookups/day, failures |
| Slack Webhook | Last delivery, failures | Messages sent/day |

Data: Derived from scheduler job status (`GET /api/v1/health` → `scheduler_jobs`) and aggregating from logs/trigger metadata.

#### Document Processing Stats

| Metric | Description |
|--------|-------------|
| Documents Downloaded | Count of `RawDocument` with status `complete` |
| Download Failures | Count with status indicating download error |
| PDF Extraction Success Rate | Successful extractions / total PDFs (target: >90% per MVP checklist) |
| ChromaDB Embeddings | Count of embedded documents vs total documents |

---

### 5. Watchlist Management + Agent Policy Placeholder

**Purpose:** View watchlist state and surface agent access policy source in one admin location.

**Current state:** Watchlist is a static YAML file (`config/watchlist.yaml`) loaded at startup. This page provides a UI for viewing and eventually editing it.

#### Tracked Companies Table

| Column | Source |
|--------|--------|
| Symbol | `watchlist.yaml` → `companies[].symbol` |
| Name | `companies[].name` |
| Sector | Derived from sector membership |
| Priority | `companies[].priority` (high/normal) |
| Aliases | `companies[].aliases` |
| Status | Active / Paused |
| Last Trigger | Most recent trigger date for this company |
| Total Investigations | Count from investigations collection |
| Current Recommendation | From `positions` collection |

#### Tracked Sectors

| Column | Source |
|--------|--------|
| Sector Name | `watchlist.yaml` → `sectors[].name` |
| Keywords | `sectors[].keywords` |
| Companies Count | Number of companies in this sector |

#### MVP Actions
- View watchlist (read-only from YAML)
- Show which companies have active recommendations
- Show agent policy source/path and last reload timestamp (read-only placeholder)

#### Iteration 2+ Actions
- Add/remove companies (persists to database, hot-reloads watchlist)
- Add/remove sectors
- Toggle company monitoring on/off
- Change company priority
- Edit sector keywords

---

### 6. System Settings (Iteration 3)

Deferred to when PostgreSQL control plane is available:
- User management (add/remove users, assign roles)
- Password reset
- Licence key management
- LLM model configuration (which model for which layer)
- Notification channel configuration (Slack webhook URL, email SMTP)
- Processing thresholds (gate confidence threshold, significance threshold)
- Audit log viewer

---

## Investor / Analyst Interface

### 1. Command Center (Default View)

**Purpose:** The analyst's home screen. Shows what needs attention right now.

**Layout:** Three-column layout — Left: active alerts, Center: recent reports, Right: market snapshot.

#### Active Alerts Panel

Items requiring analyst attention, sorted by priority:
- New reports not yet reviewed (no feedback submitted)
- Recommendation changes in the last 24 hours
- High-significance investigations
- Failed deliveries (reports that didn't reach Slack/email)

Each alert shows: Company symbol, headline, significance/confidence, time, and quick action buttons (View Report, Dismiss).

Data: Query reports where `feedback_rating IS NULL` and `created_at` in last 7 days. Query assessments where `recommendation_changed = true` and `created_at` in last 24 hours.

#### Recent Reports Feed

Scrollable list of the latest reports (`GET /api/v1/reports/?limit=20`):

| Element | Source |
|---------|--------|
| Company Badge | `company_symbol` |
| Title | `title` (e.g., "Suzlon Energy — Upgrade to BUY") |
| Recommendation | Extracted from `recommendation_summary` |
| Confidence | From linked assessment |
| Time | `created_at` (relative: "2 hours ago") |
| Feedback | Thumbs up/down indicator, or "Awaiting review" |

Default sort for this feed and recommendation list: highest expected impact first, then recency.

Click → opens full report view.

#### Market Snapshot (Compact)

Mini cards for each tracked company showing:
- Symbol + Name
- Current recommendation (BUY/SELL/HOLD badge)
- Confidence score
- Price + 1-day change (from most recent `MarketDataSnapshot`)
- Last analysis date

---

### 2. Company Positions

**Purpose:** The portfolio view. All tracked companies with current recommendations.

**Data:** `GET /api/v1/positions/`

#### Position Board

Three columns (Kanban-style):

**BUY** | **HOLD** | **SELL**

Each card shows:
- Company symbol + name
- Confidence score (progress bar)
- Timeframe (Short/Medium/Long badge)
- Recommendation basis (truncated, from `recommendation_basis`)
- Last updated date
- Number of total investigations
- Click → Company Detail Page

#### Company Detail Page

Accessed by clicking a company card or from any company link.

**Header:** Company name, symbol, sector, current recommendation (large badge), confidence, timeframe.

**Tabs:**

##### Overview Tab
- Current recommendation card with full reasoning
- Key factors for and against (from latest assessment)
- Risks
- Market data snapshot (price, P/E, market cap, holdings)

##### Investigations Tab
Historical list of all investigations for this company (`GET /api/v1/investigations/company/{symbol}`):

| Column | Data |
|--------|------|
| Date | `created_at` |
| Trigger Source | Linked trigger's `source` |
| Significance | Badge (HIGH/MEDIUM/LOW/NOISE) |
| Key Findings | First 2-3 findings |
| Recommendation Impact | Changed / No Change |

Click → Investigation Detail View (see Investigation Explorer below).

##### Reports Tab
All generated reports for this company.

##### Notes Tab
Analyst notes associated with this company (see Notes feature below).

##### Recommendation History Tab
Timeline visualization showing every recommendation change:
```
[2026-01-15] NONE → HOLD (Confidence: 60%) — "Initial coverage, order book uncertain"
[2026-02-25] HOLD → BUY (Confidence: 80%) — "Strong Q3 + record order book"
```

Data: `recommendation_history` array from `CompanyPosition` model.

---

### 3. Investigation Explorer

**Purpose:** Deep-dive into the evidence behind any investigation. This is the "show me the work" view.

**Data:** `GET /api/v1/investigations/{investigation_id}`

#### Investigation Detail View

**Header:** Company, trigger source, date, significance badge, processing time.

**Sections:**

##### Trigger Context
What triggered this investigation:
- Source (RSS / Human)
- Raw content (full text)
- Source URL (clickable)
- Linked documents (PDF/HTML downloads)

##### Extracted Metrics
Table of financial metrics pulled from the trigger document:

| Metric | Value | Unit | Period | YoY Change | QoQ Change | Confidence |
|--------|-------|------|--------|------------|------------|------------|
| Revenue | 1,200 | Cr | Q3 FY26 | +23% | +8% | 0.95 |
| EBITDA | 300 | Cr | Q3 FY26 | +30% | +12% | 0.90 |

Data: `extracted_metrics` array.

##### Forward Statements
Management promises and guidance:

| Statement | Target Metric | Target Value | Target Date | Category |
|-----------|--------------|-------------|-------------|----------|
| "Expect 50% revenue growth" | Revenue | 50% growth | FY27 | guidance |

Data: `forward_statements` array. In Iteration 1, these feed into promise tracking.

##### Web Search Findings
What the system found online:

| Source | Title | Summary | Relevance | Sentiment |
|--------|-------|---------|-----------|-----------|
| Economic Times | "Wind sector order book..." | Sector seeing strong... | High | Positive |

Data: `web_search_results` array.

##### Market Data Snapshot
Two-column layout:

| Metric | Value |
|--------|-------|
| Price | ₹85.00 |
| Market Cap | ₹12,000 Cr |
| P/E Ratio | 18.0x |
| Sector Avg P/E | 22.0x |
| 52-Week High | ₹95.00 |
| 52-Week Low | ₹42.00 |
| FII Holding | 12.5% |
| DII Holding | 18.3% |
| Promoter Holding | 45.2% |

Plus: Price change badges (1d, 1w, 1m).

##### Historical Context Used
What past data the system pulled in for this analysis:
- Past investigations referenced (linked, clickable)
- Past recommendations at the time
- Similar documents found via vector search (with similarity scores)

Data: `historical_context` object.

##### AI Synthesis
The LLM's narrative analysis (`synthesis` field). Rendered as formatted text (3-5 paragraphs).

##### Key Findings, Red Flags, Positive Signals
Three collapsible sections with bullet lists from `key_findings`, `red_flags`, `positive_signals`.

##### Significance Assessment
- Level: HIGH / MEDIUM / LOW / NOISE (large badge)
- Reasoning: `significance_reasoning` (paragraph)
- Proceeds to Layer 4? `is_significant` (Yes/No)

---

### 4. Chat Interface (Deferred to Iteration 1+)

**Purpose:** Conversational interface for asking questions about a company's analysis history.

**Scope:** Company-scoped conversations. The analyst selects a company, and the chat has access to all investigations, assessments, reports, and notes for that company.

**Status:** Deferred from Weeks 5-6 scope. Keep this section as forward design only.

**Initial Implementation (Iteration 1+):** Simple chat UI backed by an LLM call that receives:
- All investigations for the selected company (summaries)
- Current position and recommendation history
- Recent market data
- Analyst notes

This is NOT a general-purpose chatbot. It's a contextual Q&A interface where the context is everything the system knows about one company.

**Example interactions:**
- "What were the key findings from the last three quarterly results?"
- "How has the order book trended over the past year?"
- "What risks have we identified that haven't materialized?"
- "Compare the current valuation to when we first started coverage"
- "What forward statements has management made that we haven't verified yet?"

**UI Elements:**
- Company selector (dropdown or search)
- Chat history (scrollable, persisted per company)
- Message input with send button
- "Context loaded" indicator showing how many investigations/reports are in context
- Quick prompts (suggested questions based on available data)

**New API Required:**
```
POST /api/v1/chat
{
  "company_symbol": "SUZLON",
  "message": "What were the key findings from the last quarter?",
  "session_id": "uuid"  // optional, for conversation continuity
}
```

---

### 5. Manual Trigger

**Purpose:** Allow analysts to submit investigation triggers manually.

**Existing API:** `POST /api/v1/triggers/human`

**Form Fields:**

| Field | Type | Required | Maps To |
|-------|------|----------|---------|
| Company Symbol | Dropdown (from watchlist) + free text | Yes | `company_symbol` |
| Company Name | Auto-filled from symbol, editable | No | `company_name` |
| Event Summary | Large text area | Yes | `content` |
| Source URL | URL input | No | `source_url` |
| Your Name | Text input (remembered) | No | `triggered_by` |
| Notes | Text area | No | `notes` |

**Behavior:**
- Human triggers bypass Layer 2 gate (status immediately set to `gate_passed`)
- After submission, show confirmation with `trigger_id` and link to track progress
- Optional: Upload a document (PDF/HTML) alongside the text content — this requires a new file upload endpoint

**Status Tracker:**
After submitting, the analyst can track their trigger's progress through the pipeline. Show a progress indicator:
```
[✓ Submitted] → [✓ Gate Bypassed] → [⟳ Analyzing...] → [ Assessing ] → [ Report ]
```

Poll `GET /api/v1/triggers/{trigger_id}` every 10 seconds until status reaches `reported` or `error`.

---

### 6. Notes

**Purpose:** Analysts and investors can attach shared notes to a company or a specific investigation. Notes become part of the system's memory — they get embedded in ChromaDB and influence future Layer 3 analyses.

**This is a new feature requiring new API endpoints and data model.**

#### Data Model (New)

```python
class AnalystNote(BaseModel):
    note_id: str  # UUID
    company_symbol: str
    investigation_id: str | None  # Optional link to specific investigation
    content: str  # The note text
    tags: list[str]  # User-defined tags (e.g., "risk", "thesis", "management")
    created_by: str
    created_at: datetime
    updated_at: datetime
```

#### New API Endpoints

```
POST /api/v1/notes
GET /api/v1/notes?company={symbol}&tag={tag}&limit=20
GET /api/v1/notes/{note_id}
PUT /api/v1/notes/{note_id}
DELETE /api/v1/notes/{note_id}
```

#### UI

- Add note from: Company Detail Page (Notes tab), Investigation Detail View (inline), or dedicated notes panel
- Note editor: Text area + tag selector + optional investigation link
- Notes list: Filterable by company, tag, date, author
- Inline display: Notes appear alongside relevant investigations when viewing company history

#### ChromaDB Integration

When a note is saved:
1. Embed the note content using the same sentence-transformers pipeline
2. Store in ChromaDB with metadata: `company_symbol`, `note_id`, `source: "analyst_note"`
3. Layer 3's historical context retrieval will now pull relevant analyst notes alongside past investigations

This means an analyst writing "Management seems overly optimistic on order guidance — track carefully" will surface when the next quarterly results come in and the system is gathering historical context.

---

### 7. Performance Tracker

**Purpose:** Track whether the system's recommendations were right. This is the "signal accuracy" view referenced in the North Star Vision and Iteration 1 roadmap.

#### MVP Version (Simple)

For each recommendation change, track what happened to the stock price afterward:

| Column | Data |
|--------|------|
| Date | When recommendation changed |
| Company | Symbol + Name |
| Action | The recommendation (BUY/SELL/HOLD) |
| Price at Recommendation | From `MarketDataSnapshot` at time of assessment |
| Price Now | Current price (live from yfinance) |
| Return | % change since recommendation |
| Timeframe | SHORT/MEDIUM/LONG |
| Status | Within timeframe / Expired |

#### Aggregate Metrics

| Metric | Calculation |
|--------|-------------|
| Total Recommendations | Count of recommendation changes |
| Win Rate | % of BUY recommendations with positive return / SELL with negative return |
| Avg Return (BUY) | Average % return on BUY recommendations |
| Avg Return (SELL) | Average % return on SELL recommendations |
| Best Call | Highest returning recommendation |
| Worst Call | Worst returning recommendation |

#### Iteration 1+ Enhancements
- Time-weighted returns
- Benchmark comparison (vs Nifty, sector index)
- Confidence calibration (do high-confidence calls perform better?)
- Promise tracking accuracy (did management deliver on forward statements?)

**New API Required:**
```
GET /api/v1/performance/summary
GET /api/v1/performance/recommendations
```

---

### 8. Notifications

**Purpose:** In-app notification center for investor/analyst users.

#### MVP (Simple)

A notification bell icon in the top navigation bar with an unread count badge.

Dropdown shows recent notifications:
- "New report: Suzlon Energy — Upgrade to BUY" (link to report)
- "INOXWIND investigation complete — significance: HIGH" (link to investigation)
- "3 new triggers processed since this session started"

Data: Derived from reports and investigations created since client session start timestamp. No separate notifications table needed for MVP.

#### Iteration 2+
- Notification preferences (which events to be notified about)
- Email digest option (daily summary)
- Push notifications (when mobile app exists in Iteration 4)
- Separate notifications data model with read/unread tracking

---

## Shared Components

### Top Navigation Bar

```
[tuJanalyst Logo] [Admin | Investor/Analyst] toggle    [🔔 Notifications] [User Menu]
```

- Logo links to the default view for the current role
- Admin/Investor-Analyst toggle switches between the two interfaces
- Notification bell with unread count (Analyst view only)
- User menu: profile, preferences, logout (Iteration 3)

### Company Badge Component

Reusable component appearing throughout the UI:

```
[SUZLON] Suzlon Energy Ltd — Capital Goods
   BUY (80%) ↑ ₹85.00 (+2.3%)
```

Elements: Symbol badge, company name, sector, recommendation badge with confidence, price with change.

### Status Badge Component

Color-coded badges for trigger statuses:
- `pending` → Gray
- `filtered_out` → Light red
- `gate_passed` → Blue
- `analyzing` / `assessing` → Yellow (animated pulse)
- `analyzed` / `assessed` → Green
- `reported` → Dark green
- `error` → Red

### Recommendation Badge Component

- `BUY` → Green badge
- `HOLD` → Amber/Yellow badge
- `SELL` → Red badge
- `NONE` → Gray badge

Includes confidence as a small percentage next to the badge.

### Significance Badge Component

- `HIGH` → Red badge
- `MEDIUM` → Orange badge
- `LOW` → Yellow badge
- `NOISE` → Gray badge

---

## API Gap Analysis

Features in this spec that require new API endpoints or response-contract extensions:

| Feature | Required Endpoint | Priority |
|---------|------------------|----------|
| Trigger detail enrichment | Extend `GET /api/v1/triggers` and `GET /api/v1/triggers/{id}` to include `updated_at`, `status_history`, `gate_result`, and optional content preview | P1 — needed for admin table and failure analysis |
| Trigger source/type distribution | `GET /api/v1/triggers/stats?group_by=source` (or equivalent) | P1 — required admin KPI |
| Cost KPI endpoint | `GET /api/v1/costs/summary` with LLM + web search cost fields and cost/report | P1 — required admin KPI |
| Notes CRUD | `POST/GET/PUT/DELETE /api/v1/notes` | P1 — feeds back into analysis |
| Notes embedding | ChromaDB integration for notes | P1 — the point of notes |
| Performance tracking | `GET /api/v1/performance/*` | P2 — valuable but not blocking |
| Chat | `POST /api/v1/chat` | P3 — deferred from MVP |
| Gate human review | `POST /api/v1/triggers/{id}/gate-review` | P2 — builds DSPy training data |
| Watchlist edit | `PUT /api/v1/watchlist/companies`, `PUT /api/v1/watchlist/sectors` | P3 — YAML works for MVP |
| Auth + RBAC | Auth endpoints and role claims/session model | P3 — deferred unless low-friction |
| Notification preferences | `GET/PUT /api/v1/notifications/preferences` | P3 — deferred |

Existing endpoints that partially support this spec today:
- `GET /api/v1/health` and `/health/stats` — system health and basic counts
- `GET/POST /api/v1/triggers/*` — manual trigger and lightweight status views
- `GET /api/v1/investigations/*` — Investigation Explorer
- `GET /api/v1/reports/*` and feedback — Reports feed, feedback
- `GET /api/v1/positions/*` — Company Positions

---

## Data Flow: UI ↔ Backend

```
┌──────────────────────────────────────────────────┐
│                  Frontend (UI)                    │
├──────────────────────────────────────────────────┤
│                                                   │
│  Admin Views          Analyst Views               │
│  ┌──────────┐        ┌──────────────┐            │
│  │ Pipeline │        │ Command Ctr  │            │
│  │ Gate     │        │ Positions    │            │
│  │ Cost     │        │ Investig.    │            │
│  │ Sources  │        │ Chat (I1+)   │            │
│  │ Watchlist│        │ Trigger      │            │
│  └────┬─────┘        │ Notes        │            │
│       │              │ Performance  │            │
│       │              └──────┬───────┘            │
│       │                     │                     │
└───────┼─────────────────────┼─────────────────────┘
        │                     │
        ▼                     ▼
┌──────────────────────────────────────────────────┐
│              FastAPI Backend                      │
├──────────────────────────────────────────────────┤
│  /api/v1/health/*      /api/v1/triggers/*        │
│  /api/v1/triggers/stats /api/v1/investigations/* │
│  (new) /api/v1/watchlist/* /api/v1/reports/*     │
│  (new I1+) /api/v1/chat /api/v1/positions/*      │
│  (new) /api/v1/notes/* (new) /api/v1/performance│
└──────────────────┬───────────────────────────────┘
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
   ┌────────┐ ┌────────┐ ┌────────┐
   │MongoDB │ │ChromaDB│ │External│
   │        │ │        │ │APIs    │
   │Triggers│ │Vectors │ │yfinance│
   │Investig│ │+Notes  │ │Brave   │
   │Reports │ │        │ │Slack   │
   │Positions│ │       │ │        │
   └────────┘ └────────┘ └────────┘
```

---

## MVP Build Priority

Recommended implementation order for Weeks 5-6:

### Week 5

1. **Pipeline Dashboard** — Most value for admin; includes required KPI cards and funnel
2. **Company Positions** — Core analyst view, uses existing `/positions` API
3. **Manual Trigger Form** — Uses existing `/triggers/human` API
4. **Reports Feed + Detail View** — Uses existing `/reports` API

### Week 6

5. **Investigation Explorer** — Uses existing `/investigations` API
6. **Gate Performance** — Derived from existing trigger data
7. **Notes** (basic) — Requires new API + model, but high impact
8. **Notifications** (simple) — Derived from existing data, no new API
9. **Performance Tracker** (basic) — Recommendation outcome view via new `/performance` APIs

### Deferred to Iteration 1+

- Chat Interface (needs new API, LLM integration design)
- Auth + strict RBAC (unless low-friction implementation is available earlier)
- Cost & Usage full page (advanced charts; basic cost/report KPI stays in admin dashboard)
- Watchlist Management (editing — read-only view is Week 5)
- Data Sources monitoring (needs logging/metrics infrastructure)
- System Settings (needs PostgreSQL control plane)

---

## Technology Notes for MVP

### Streamlit Path
- Use `st.tabs()` for Admin/Analyst toggle
- `st.metric()` for KPI cards
- `st.dataframe()` for tables with filtering
- `st.plotly_chart()` or `st.altair_chart()` for visualizations
- `st.form()` for manual trigger submission
- `st.chat_input()` / `st.chat_message()` for chat (Iteration 1)
- Auto-refresh via `st.rerun()` with timer or `streamlit-autorefresh`

### FastAPI + HTMX Path
- Jinja2 templates with HTMX for partial page updates
- `hx-get` with `hx-trigger="every 30s"` for auto-refreshing stats
- `hx-post` for form submissions
- Alpine.js for client-side interactivity (dropdowns, toggles)
- Chart.js or Plotly.js for visualizations

### React Path (Iteration 3)
- React + TypeScript
- TanStack Query for API data fetching with caching
- Recharts or Visx for visualizations
- Tailwind CSS for styling
- React Router for navigation
- WebSocket for real-time updates (replace polling)

---

## Open Questions

1. **Chat persistence (Iteration 1+):** Should chat conversations be saved and searchable, or ephemeral per session?
2. **Soft-role implementation detail:** Should MVP role switching come from a URL/query param, env flag, or local session setting?
3. **Report approval workflow:** Should reports require human approval before delivery, or is auto-deliver + feedback sufficient?
4. **Mobile access:** Is mobile browser access sufficient for MVP, or do we need responsive-first behavior from day one?
5. **Dark mode:** Should the dashboard support dark mode? (Analyst preference for long screen time.)
