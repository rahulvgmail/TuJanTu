# MVP Acceptance Checklist

> **Purpose**: Measurable pass/fail criteria for declaring the MVP complete at Week 6.
> Each criterion is binary — it either passes or it doesn't.
> The MVP is shippable when all **Required** items pass. **Stretch** items are nice-to-have.

---

## How to Test

Run each test during **two full trading days** with live NSE data. Record results in the table below.

---

## Required: Pipeline End-to-End

| # | Criterion | How to Measure | Pass/Fail |
|---|-----------|---------------|-----------|
| R1 | **RSS poller detects new NSE announcements within 10 minutes of publication** | Compare poller timestamps against NSE RSS feed `pubDate` for 20+ announcements | |
| R2 | **Document fetcher successfully downloads >90% of linked PDFs/HTML** | Count download successes vs failures over a trading day | |
| R3 | **Text extraction produces readable text from >90% of downloaded PDFs** | Manual spot-check of 10 extracted documents | |
| R4 | **Watchlist filter correctly drops out-of-sector triggers** | Feed 10 in-sector and 10 out-of-sector triggers; verify filtering | |
| R5 | **LLM gate correctly classifies >80% of filtered triggers** | Human-review 20 gate decisions (10 passes, 10 drops). Count agreements. | |
| R6 | **Human trigger bypasses gate and reaches Layer 3** | Submit 3 human triggers via API; verify all reach investigation stage | |
| R7 | **Layer 3 produces a structured Investigation for every gate-passed trigger** | Check that investigations are created in MongoDB with all required fields populated | |
| R8 | **Layer 4 produces a DecisionAssessment for every significant investigation** | Check MongoDB for assessment records with recommendation + reasoning | |
| R9 | **Layer 5 produces a readable report for every assessment** | Read 5 generated reports; all must have: summary, findings, recommendation, confidence | |
| R10 | **End-to-end time from announcement to report is under 20 minutes** | Measure wall-clock time for 5 triggers processed during live operation | |

## Required: Data Integrity

| # | Criterion | How to Measure | Pass/Fail |
|---|-----------|---------------|-----------|
| D1 | **No duplicate triggers for the same announcement** | Check MongoDB for duplicate `source_url` values after a full trading day | |
| D2 | **All trigger status transitions are recorded in `status_history`** | Query 10 triggers; verify status_history has entries for each state change | |
| D3 | **ChromaDB contains embeddings for all extracted documents** | Count documents in MongoDB vs vectors in ChromaDB; should match | |
| D4 | **Past investigations are retrievable for Layer 4 context** | Query investigations for a company with 2+ prior entries; verify retrieval | |

## Required: API & Operations

| # | Criterion | How to Measure | Pass/Fail |
|---|-----------|---------------|-----------|
| O1 | **`/health` endpoint returns 200 with status "healthy"** | `curl http://localhost:8000/health` | |
| O2 | **Human trigger API accepts and processes a trigger** | POST to `/api/v1/triggers/human` with valid payload; verify 201 response | |
| O3 | **System runs for 8 hours (one trading day) without crashing** | Start the system at market open, check it's still running at close | |
| O4 | **Docker Compose starts all services with `docker-compose up`** | Fresh clone, `cp .env.example .env`, fill in API key, `docker-compose up` | |
| O5 | **Errors are logged, not swallowed** | Introduce a deliberate failure (bad PDF URL); verify error appears in logs | |

## Required: Notification

| # | Criterion | How to Measure | Pass/Fail |
|---|-----------|---------------|-----------|
| N1 | **Reports are delivered via the chosen notification channel** | Verify Slack message (or email) arrives for at least 3 reports | |
| N2 | **Notification includes a link or summary sufficient to act on** | Read 3 notifications; each must have company name, recommendation, confidence | |

## Stretch: Dashboard

| # | Criterion | How to Measure | Pass/Fail |
|---|-----------|---------------|-----------|
| S1 | **Dashboard shows list of recent triggers with status** | Open dashboard; verify trigger list is populated and filterable | |
| S2 | **Dashboard shows investigation details when clicked** | Click an investigation; verify findings, metrics, and assessment are displayed | |
| S3 | **Dashboard has a human trigger submission form** | Submit a trigger via the dashboard form; verify it enters the pipeline | |
| S4 | **Dashboard captures thumbs up/down feedback on reports** | Click thumbs up on a report; verify feedback is stored in MongoDB | |

## Stretch: Quality

| # | Criterion | How to Measure | Pass/Fail |
|---|-----------|---------------|-----------|
| Q1 | **>70% of reports rated "useful" or "very useful" by the team** | Team reviews 10 reports after 1 week of live operation | |
| Q2 | **<5% of announcements missed during market hours** | Compare NSE RSS feed items against ingested triggers for one week | |

---

## Sign-Off

| Role | Name | Date | Pass/Fail |
|------|------|------|-----------|
| Developer | | | |
| Product Owner | | | |

**MVP is accepted when all Required (R, D, O, N) criteria pass.**
