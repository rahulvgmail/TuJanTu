# tuJanalyst MVP Definition

## Executive Summary

This document defines the Minimum Viable Product for tuJanalyst — an AI-driven system that automates stock analysis for small and medium cap companies listed on the Indian stock market.

The MVP targets the **Capital Goods - Electrical Equipment** sector on NSE/BSE, with two trigger sources: exchange press releases and human-initiated investigations. The goal is to prove the core thesis: that an AI pipeline can identify actionable news, assess its significance, and produce investment-quality analysis reports faster and more reliably than manual processes.

**Team**: 2-3 developers
**Timeline**: 4-6 weeks
**Primary users**: Internal investment team
**Tech stack**: Python (FastAPI), MongoDB, ChromaDB (vector store), minimal web UI

---

## What the MVP Is NOT

Before defining what we build, let's be explicit about what we're cutting:

- **No Twitter/Reddit triggers** — social media integration comes in Iteration 1
- **No graph database** — company-sector relationships stored as MongoDB documents
- **No Kafka/event bus** — direct function calls in a processing pipeline
- **No Kubernetes/EKS** — Docker Compose on a single server
- **No multi-agent orchestration framework** — sequential pipeline with a simple orchestrator
- **No React frontend** — lightweight Streamlit dashboard or FastAPI + HTMX
- **No automated trading signals** — reports for human review only
- **No multi-sector support** — Capital Goods - Electrical Equipment only
- **No agent-level access control** — config-based company/sector filtering
- **No performance tracking/feedback loops** — manual feedback initially

These are all valuable and part of the north star vision. They're deferred because they don't help prove the core thesis.

---

## Architecture Overview

The MVP is a **single Python application** with a processing pipeline, a web API, and a simple dashboard.

```
┌─────────────────────────────────────────────────────────────────┐
│                        tuJanalyst MVP                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐   │
│  │  Triggers     │──▶│  Gate        │──▶│  Deep Analysis   │   │
│  │  (RSS+Human)  │   │  (Filter+AI) │   │  (LLM+Context)   │   │
│  └──────────────┘   └──────────────┘   └──────────────────┘   │
│                                                │                │
│                                                ▼                │
│                     ┌──────────────┐   ┌──────────────────┐   │
│                     │  Report      │◀──│  Decision        │   │
│                     │  (Output)    │   │  Assessment      │   │
│                     └──────────────┘   └──────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Storage: MongoDB (docs, state) + ChromaDB (vectors)    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Web UI: Streamlit dashboard / FastAPI + HTMX           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Why This Stack

| Choice | Rationale |
|--------|-----------|
| **FastAPI** | Team knows Python. Fast to build APIs. Good async support for polling and LLM calls. |
| **MongoDB** | Flexible schema for varied document types. No migrations needed as data model evolves. Good for the "we don't have full clarity" stage. |
| **ChromaDB** | Simplest vector store to get running. Embeds in the application process. No separate server needed for MVP scale. Can migrate to Weaviate later. |
| **Streamlit or HTMX** | Internal use doesn't need a polished React app. Streamlit gets a functional dashboard in hours. HTMX with FastAPI templates is another lightweight option. |
| **Docker Compose** | Single command deployment. No cloud orchestration overhead. Can run on a single EC2 instance or local server. |

### What About Weaviate?

ChromaDB is suggested for MVP because it's zero-config — runs embedded in your Python process, no separate server. At MVP scale (one sector, hundreds of documents), this is fine. When you expand to multiple sectors and thousands of documents, migrate to Weaviate for better scaling, filtering, and hybrid search. The vector store interface should be abstracted behind a simple repository class so this swap is painless.

---

## Pipeline Design: The 5 Layers

### Layer 1: Trigger Ingestion

**What it does**: Detects new information that might be worth investigating.

**MVP scope**:
- **NSE/BSE RSS feed poller**: Scheduled task (every 5-10 minutes during market hours) that checks NSE corporate announcements RSS feed. Downloads the announcement metadata and linked documents (PDFs, HTML).
- **Human trigger endpoint**: API endpoint + simple web form where a team member can paste a URL, upload a document, or type a free-text observation to trigger an investigation. Human triggers are tagged with `priority: high` and bypass Layer 2.

**Data model** (MongoDB):
```python
class TriggerEvent:
    trigger_id: str              # UUID
    source: str                  # "nse_rss" | "bse_rss" | "human"
    source_url: str | None       # Original URL
    company_symbol: str | None   # NSE/BSE symbol if identifiable
    company_name: str | None
    raw_content: str             # Announcement text or human input
    documents: list[str]         # List of document IDs (downloaded files)
    created_at: datetime
    triggered_by: str | None     # Username for human triggers
    priority: str                # "normal" | "high"
    status: str                  # "pending" | "filtered_out" | "reviewing" | "analyzed" | "reported"
```

**Key implementation notes**:
- Use `feedparser` for RSS parsing
- Use `httpx` for async document downloads
- PDF text extraction via `pdfplumber` (more reliable than PyPDF2 for Indian financial docs)
- Store raw documents in MongoDB GridFS or local filesystem with MongoDB metadata

---

### Layer 2: Worth Reviewing (The Gate)

**What it does**: Cheaply decides whether a trigger deserves expensive LLM analysis or should be dropped.

**MVP scope**:
- **Company/sector filter**: Config file (`watchlist.yaml`) defines companies and sectors we care about. If the announcement maps to a company not in our watchlist, drop it.
- **Keyword pre-filter**: Quick keyword check against a configurable list (e.g., "quarterly results", "order book", "acquisition", "board meeting outcome"). Passes if any keyword matches.
- **LLM quick classification**: For triggers that pass the keyword filter, make a cheap, fast LLM call (use a smaller/faster model like Claude Haiku or GPT-4o-mini) with a prompt like: "Given this announcement about [company], is this worth investigating for investment decisions? Reply YES or NO with a one-line reason."
- **Human bypass**: If `source == "human"`, skip all filtering and pass directly to Layer 3.

**Cost optimization note**: This layer exists specifically to avoid expensive Layer 3 analysis on noise. The keyword filter is free. The LLM classification should use the cheapest/fastest model available. Budget roughly: for every 100 triggers, maybe 20-30 pass the keyword filter, and 10-15 pass the LLM gate.

**Config** (`watchlist.yaml`):
```yaml
sectors:
  - name: "Capital Goods - Electrical Equipment"
    keywords:
      - "quarterly results"
      - "order book"
      - "acquisition"
      - "expansion"
      - "board meeting"
      - "dividend"
      - "stock split"
      - "rights issue"

companies:
  - symbol: "INOXWIND"
    name: "Inox Wind Limited"
    priority: "high"
  - symbol: "SUZLON"
    name: "Suzlon Energy Limited"
    priority: "normal"
  # ... more companies
```

---

### Layer 3: Deep Analysis (Anything Significant)

**What it does**: The core analytical engine. Takes a trigger that passed the gate and investigates it thoroughly using LLM analysis, historical context, and web search.

**MVP scope**:

1. **Document analysis**: Full LLM analysis of the trigger document. Extract:
   - Key financial metrics (revenue, EBITDA, PAT, order book, margins)
   - Forward-looking statements and promises
   - Management commentary highlights
   - Any material changes or announcements

2. **Historical context retrieval**: Query ChromaDB for past analyses and documents about this company. Provide the LLM with relevant historical context:
   - Previous quarterly results summaries
   - Past promises and commitments we've tracked
   - Previous investigation results (including inconclusive ones)

3. **Web search enrichment**: Use a web search API (Brave Search, Tavily, or SerpAPI) to find:
   - Recent news about the company
   - Sector-level developments
   - Analyst opinions or reports (publicly available)
   - Any corroborating or contradicting information

4. **Market data lookup**: Pull basic market data via a free/affordable API (e.g., Yahoo Finance via `yfinance`, or NSE's own data):
   - Current price and recent price action
   - P/E ratio, market cap
   - FII/DII holding patterns (from quarterly shareholding data)
   - Sector benchmark comparison

5. **Synthesis**: Combine all the above into a structured analysis using a capable LLM (Claude Sonnet or Opus). The prompt should ask the LLM to:
   - Summarize the new information
   - Compare against historical data and past promises
   - Identify what's significant and why
   - Flag any red flags or inconsistencies
   - Assess whether this information is material for investment decisions

**Output** (stored in MongoDB):
```python
class Investigation:
    investigation_id: str
    trigger_id: str
    company_symbol: str
    company_name: str
    created_at: datetime

    # Analysis components
    document_analysis: dict       # Extracted metrics, statements, highlights
    historical_context: dict      # Past analyses, promises, patterns
    web_search_results: list      # Summarized web findings
    market_data: dict             # Current market metrics

    # Synthesis
    significance_assessment: str  # LLM's assessment of significance
    key_findings: list[str]       # Bullet-point findings
    red_flags: list[str]         # Concerns or inconsistencies
    is_significant: bool          # Binary: should this proceed to Layer 4?
    confidence: float             # 0.0 - 1.0

    # Metadata
    llm_model_used: str
    total_tokens_used: int
    processing_time_seconds: float
```

---

### Layer 4: Decision Assessment

**What it does**: Takes significant investigations and determines whether they warrant updating a buy/sell recommendation.

**MVP scope**:

1. **Past investigation retrieval**: Pull all past investigations for this company, including ones that were significant but didn't change a recommendation. This is the "resurrection of past analysis" concept — maybe a piece of news that was inconclusive 3 months ago becomes relevant when combined with today's announcement.

2. **Current position context**: What is our current view on this company? (Stored in MongoDB as a simple document: current recommendation, basis for it, date of last update.)

3. **Decision LLM call**: Using a capable model (Claude Sonnet/Opus), provide:
   - Current investigation synthesis (from Layer 3)
   - All past investigations for this company
   - Current recommendation and its basis
   - Ask: "Given all this information, should we update our buy/sell recommendation for [company]? If yes, what should the new recommendation be and why? If no, explain why this doesn't change the picture."

4. **Output**:
```python
class DecisionAssessment:
    assessment_id: str
    investigation_id: str
    company_symbol: str

    # Decision
    recommendation_change: bool       # Does this warrant a change?
    current_recommendation: str       # "buy" | "sell" | "hold" | "none"
    proposed_recommendation: str      # What should it be now?
    recommendation_reasoning: str     # Detailed reasoning
    confidence: float                 # 0.0 - 1.0

    # Supporting evidence
    key_factors: list[str]           # What drove this assessment
    supporting_investigations: list[str]  # IDs of past investigations that contributed
    risks: list[str]                 # Risks to this assessment

    created_at: datetime
```

---

### Layer 5: Report Generation (The Verdict)

**What it does**: Produces a human-readable report for the investment team to review.

**MVP scope**:

1. **Report generation**: Use LLM to create a well-structured report that includes:
   - Executive summary (2-3 sentences)
   - The trigger: what happened
   - Key findings from the investigation
   - Historical context: how this relates to past data
   - Market context: current market metrics
   - Recommendation: buy/sell/hold with reasoning
   - Confidence level and key risks
   - Sources and references

2. **Delivery**: For MVP, two channels:
   - Display on the web dashboard
   - Send notification via email (or Slack webhook if the team uses Slack)

3. **Human feedback capture**: Simple thumbs up/down + optional comment on each report. Stored in MongoDB for future use in improving the system.

**Report format**: Markdown rendered in the web UI. Can later be converted to PDF for formal distribution.

---

## Tech Stack Summary

| Component | Technology | Notes |
|-----------|-----------|-------|
| **Language** | Python 3.11+ | |
| **Web framework** | FastAPI | API + serves the UI templates |
| **Task scheduling** | APScheduler or Celery with Redis | RSS polling, periodic tasks |
| **Document DB** | MongoDB | Documents, state, investigations, reports |
| **Vector store** | ChromaDB (embedded) | Document embeddings for context retrieval |
| **LLM provider** | Anthropic (Claude) | Haiku for gate, Sonnet/Opus for analysis |
| **Web search** | Brave Search API or Tavily | For enrichment in Layer 3 |
| **Market data** | yfinance + NSE Python libraries | Free market data for MVP |
| **PDF processing** | pdfplumber | Text extraction from financial PDFs |
| **Web UI** | Streamlit OR FastAPI + Jinja2 + HTMX | Internal dashboard |
| **Deployment** | Docker Compose | Single server deployment |
| **Notifications** | Email (SMTP) or Slack webhook | Report delivery |

---

## Implementation Plan (4-6 Weeks)

### Week 1: Foundation + Trigger Ingestion
- Project scaffolding: FastAPI app structure, Docker Compose, MongoDB setup
- NSE RSS feed poller implementation
- Document downloader (PDF, HTML)
- Basic text extraction pipeline (pdfplumber)
- MongoDB schemas for triggers and documents
- Human trigger API endpoint
- **Deliverable**: System ingests NSE announcements and stores documents

### Week 2: The Gate + Storage
- Watchlist configuration (YAML-based)
- Company/sector filter implementation
- Keyword pre-filter
- LLM quick classification (Claude Haiku)
- ChromaDB setup and document embedding pipeline
- **Deliverable**: Triggers are filtered; relevant ones proceed, noise is dropped

### Week 3: Deep Analysis (Layer 3)
- Historical context retrieval from ChromaDB
- Web search integration (Brave/Tavily)
- Market data integration (yfinance)
- Main analysis LLM prompt engineering and implementation
- Investigation data model and storage
- **Deliverable**: System produces detailed investigations for filtered triggers

### Week 4: Decision Assessment + Reports (Layers 4 & 5)
- Past investigation retrieval and aggregation
- Decision assessment LLM implementation
- Report generation with LLM
- Report storage and delivery (email/Slack)
- **Deliverable**: End-to-end pipeline: trigger → gate → analysis → decision → report

### Week 5: Dashboard + Polish
- Web dashboard (Streamlit or HTMX)
  - View recent triggers and their status
  - View investigations and reports
  - Human trigger submission form
  - Feedback capture (thumbs up/down)
- Watchlist management UI
- Basic logging and error handling
- **Deliverable**: Usable internal tool

### Week 6: Testing + Hardening
- End-to-end testing with real NSE data
- Prompt refinement based on output quality
- Error handling and retry logic
- Basic monitoring (health checks, error alerts)
- Documentation for the team
- Deploy to production server
- **Deliverable**: Production-ready MVP

---

## Success Criteria for MVP

The MVP is successful if:

1. **Coverage**: Successfully processes >90% of NSE announcements for the target sector within 15 minutes of publication
2. **Gate accuracy**: The filtering layer correctly passes genuinely relevant triggers and drops noise (measured by human review of a week's worth of triggers)
3. **Analysis quality**: The investment team rates >70% of generated reports as "useful" or "very useful" for decision-making
4. **Time savings**: End-to-end time from announcement to report is under 20 minutes (vs. hours for manual analysis)
5. **Uptime**: System runs reliably during market hours with <5% missed announcements

These are measured after 2 weeks of live operation.

---

## What Comes Next (Post-MVP Iterations)

### Iteration 1: Expand Triggers + Improve Intelligence (Weeks 7-10)
- Add Twitter monitoring for pre-configured accounts
- Add Reddit monitoring for relevant subreddits
- Improve LLM prompts based on feedback
- Add promise tracking (extract promises, compare against actuals later)
- Add basic performance tracking (were our assessments right?)

### Iteration 2: Multi-Sector + Better Storage (Weeks 11-16)
- Expand to 2-3 additional sectors
- Migrate from ChromaDB to Weaviate for better scaling
- Add graph database (Neo4j) for company-sector-industry relationships
- Implement sector-wide event detection
- Add comparative analysis across companies in a sector

### Iteration 3: Platform Maturity (Weeks 17-24)
- Proper React frontend
- Control plane with access management
- Multi-agent architecture (refactor pipeline into autonomous agents)
- Event-driven architecture with message queue
- Advanced financial models (DCF, peer comparison)
- Performance feedback loops that improve the system
- Cloud deployment with proper infrastructure (EKS, managed databases)

---

## Open Decisions for the Team

1. **Streamlit vs HTMX**: Streamlit is faster to build but has deployment quirks (separate process, limited customization). HTMX with FastAPI templates gives more control and runs in the same process. **Recommendation**: Start with Streamlit for speed. Migrate to React in Iteration 3.

2. **Celery vs APScheduler**: For RSS polling and background tasks, APScheduler is simpler (runs in-process) but Celery with Redis is more robust for production. **Recommendation**: APScheduler for MVP. Switch to Celery if task reliability becomes an issue.

3. **LLM model selection**: Claude Haiku for the gate (cheap, fast), Claude Sonnet for analysis and reports (good quality/cost balance). Claude Opus for the most critical decision assessments if budget allows. **Recommendation**: Start with Haiku for gate + Sonnet for everything else. Use Opus selectively.

4. **Notification channel**: Email vs Slack. **Recommendation**: Whatever your team already uses for communication. Slack webhook is easier to implement.

---

## Cost Estimates (Monthly, MVP Scale)

| Item | Estimated Cost |
|------|---------------|
| LLM API (Anthropic) | $50-150/month (depends on volume) |
| MongoDB Atlas (M10) | $60/month (or self-hosted: $0) |
| Web search API | $10-30/month |
| Server (EC2 t3.medium or equivalent) | $30-50/month |
| **Total** | **~$150-280/month** |

For a self-hosted setup (MongoDB + app on a single server), costs drop to just LLM API + web search: roughly $60-180/month.
