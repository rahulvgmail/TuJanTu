# tuJanalyst: North Star Vision

## Purpose of This Document

This document captures the full product vision for tuJanalyst — where the system is heading over the next 6-12 months. It reconciles the original BRD and architecture documents with the founder's updated thinking (Feb 2026 brain dump). This is NOT the build plan. The MVP Definition document defines what we build first. This document is the "where are we going" reference.

---

## The Core Thesis

Most of the human work in small/mid-cap stock analysis — scanning news, reading press releases, deciding what's worth investigating, doing deep dives, and forming investment opinions — can be mapped to AI agents with LLMs and tools at their disposal. The traditional investment research chain (junior analysts → senior analysts → sector specialists → portfolio managers) can be replicated with an agentic pipeline that is faster, more consistent, and never forgets.

The opportunity: small and mid-cap stocks on NSE/BSE are under-covered because human capital is expensive and limited. Whoever can analyze these stocks systematically has an information advantage. tuJanalyst automates this analysis, letting a small team cover the market like a much larger organization.

---

## The 5-Layer Processing Model

The system processes information through 5 distinct layers, each representing a decision point. This model is the backbone of all architectural decisions.

### Layer 1: Trigger Events
**"Something happened that might matter."**

Sources (in order of implementation priority):
1. **NSE/BSE press releases** (MVP) — Automated RSS feed monitoring
2. **Human triggers** (MVP) — Team members can inject events manually, bypassing the gate
3. **Social media** (Iteration 1) — Pre-configured Twitter accounts and Reddit subreddits
4. **News aggregators** (Iteration 2) — Financial news sources, Google News alerts
5. **Unusual market activity** (Iteration 2) — Price/volume anomalies detected from market data (not event-specific, but pattern-triggered)

Key design principle: Human triggers are treated with higher priority because human intuition catches things AI might miss. Human-triggered events bypass Layer 2.

### Layer 2: Worth Reviewing (The Gate)
**"Is this noise or signal? Should we spend compute on this?"**

This layer exists for cost optimization and noise reduction. It should be cheap and fast.

Processing chain:
1. **Company/sector filter** — Is this about a company or sector we're tracking? (Config-based, instant)
2. **Keyword match** — Does it contain keywords suggesting material information? (Rule-based, instant)
3. **AI quick classification** — Fast, cheap LLM call: "Is this worth investigating?" (Haiku-class model, <2 seconds)

Rules:
- Human triggers always bypass this layer
- Unknown companies in tracked sectors still pass (might be new entrants or supply chain signals)
- The gate should err on the side of passing — false negatives (missing important news) are worse than false positives (wasting compute on unimportant news)

### Layer 3: Anything Significant (Deep Analysis)
**"What does this mean and what else do we know?"**

This is the core analytical engine. It combines the new trigger with everything the system knows.

Information sources:
- The trigger document itself (full LLM analysis)
- Past data releases for this company (from storage)
- Previous recommendations and summaries
- Web search results based on questions derived from the trigger content
- Sector/industry analysis reports
- Market data: P/E ratios, FII/DII holdings, technical indicators
- Past investigations that were inconclusive (important — see Layer 4 note)

Output: A structured investigation containing key findings, red flags, significance assessment, and confidence score.

### Layer 4: Financial Decision Impact
**"Does this change what we should do with our money?"**

This layer combines the current investigation with the full history of analysis for this company and makes a recommendation.

Critical design element: **Past investigation resurrection.** Previous investigations that were "significant but didn't change the recommendation" should be retrieved and reconsidered alongside new information. The accumulation of individually inconclusive signals may collectively warrant action.

Output: Buy/sell/hold recommendation with confidence, reasoning, key factors, and risks.

### Layer 5: The Verdict (Human Report)
**"Here's what we found. Your call."**

A human-readable report delivered to the investment team. The system recommends; humans decide.

Report includes: executive summary, trigger details, key findings, historical context, market context, recommendation with reasoning, confidence level, risks, and sources.

---

## Storage Architecture (Full Vision)

The storage layer evolves through iterations:

### MVP: Simple
- **MongoDB**: Documents, investigations, reports, state, configurations
- **ChromaDB**: Vector embeddings for semantic search (embedded, no separate server)

### Iteration 2: Rich
- **MongoDB**: Same role, expanded schemas
- **Weaviate**: Replaces ChromaDB for better scaling, hybrid search, and filtering
- **Neo4j**: Graph database for company-sector-industry ontology, relationships, and traversals

### Full Vision: Polyglot
- **MongoDB**: Document storage, processing state
- **Weaviate**: Vector search and semantic retrieval
- **Neo4j**: Knowledge graph (companies, sectors, people, promises, events, relationships)
- **Time-series store**: Financial metrics history (InfluxDB or TimescaleDB)
- **Redis**: Caching, session state, task queues
- **PostgreSQL**: Control plane only (users, access control, audit logs, system config)

### Key Principle
SQL (PostgreSQL) is limited to the control plane. The data layer stays flexible with document and graph stores because the domain model is still evolving. This avoids schema lock-in during the exploration phase.

### Graph Database Rationale
The financial domain has a rich, well-defined ontology: companies belong to sectors, sectors belong to industries, companies compete with and supply to each other, people lead companies, companies make promises, promises have outcomes. A graph database is the natural representation. This becomes critical when:
- Analyzing sector-wide events (traverse all companies in a sector)
- Finding supply chain impacts (Company A's news affects Company B's stock)
- Tracking management changes across companies
- Building the institutional memory of promises and outcomes

---

## Agent Architecture (Full Vision)

### MVP: Pipeline
A single Python application with sequential processing. Each "layer" is a module with functions. No agent autonomy, no message passing, no orchestration framework.

### Full Vision: Layered Multi-Agent System

Each layer has a **coordinator agent** that:
- Receives work from the previous layer's coordinator
- Decomposes the work into tasks for specialist agents within its layer
- Aggregates results from specialist agents
- Passes synthesized output to the next layer's coordinator

Within each layer, specialist agents have:
- Defined tools and data access permissions
- The ability to query agents in lower layers (e.g., Layer 3 agents can query Layer 1 data)
- Shared access to the knowledge layer (graph DB, vector store) through a controlled interface

### Agent Communication Patterns
- **Within a layer**: Agents communicate via the layer coordinator (hub-and-spoke)
- **Between layers**: Coordinators pass structured messages (input/output contracts)
- **To storage**: All agents access storage through a data access layer that enforces permissions
- **Cross-layer queries**: Agents can query data from previous layers but not bypass the pipeline flow

### Control Plane
A dedicated control plane manages:
- **Access control**: Which agents can access which data stores and with what permissions
- **Configuration**: Watchlists, thresholds, model selections, notification preferences
- **Logging**: All agent actions, LLM calls, and decisions are logged for audit and debugging
- **Feedback loops**: Human feedback on reports flows back to improve agent behavior
- **Static data**: Sector classifications, company master data, financial calendar

The control plane is the only component that uses PostgreSQL, keeping it separate from the dynamic data layer.

---

## Sector-Wide and Market-Wide Events

Open question from the brain dump: "How do we decide the flow of events or news that could affect the entire sector or the market?"

### Approach
1. **Detection**: When Layer 3 analysis identifies that a trigger affects the sector (not just one company), it flags the investigation as `scope: sector` or `scope: market`.
2. **Propagation**: Sector-scoped investigations trigger a secondary analysis for all tracked companies in that sector. Market-scoped events trigger analysis for all tracked companies.
3. **Deduplication**: If the same event triggers multiple investigations (e.g., a policy change affecting 10 companies), these are linked and analyzed together rather than independently.
4. **Implementation**: In MVP, this is manual — the team sees the sector flag and decides whether to trigger investigations for related companies. In the full vision, the sector coordinator agent handles propagation automatically.

---

## Iteration Roadmap

### MVP (Weeks 1-6): Prove the Thesis
- NSE/BSE RSS + human triggers
- Simple gate (config + keyword + cheap LLM)
- LLM-powered deep analysis with web search and market data
- Decision assessment with past investigation context
- Report generation + delivery
- Simple web dashboard
- One sector: Capital Goods - Electrical Equipment

### Iteration 1: Expand Inputs + Improve Quality (Weeks 7-12)
- Twitter monitoring for pre-configured accounts
- Reddit monitoring for relevant subreddits
- Promise tracking (extract, store, compare against actuals)
- Basic performance tracking (signal accuracy)
- Improved prompts based on team feedback
- Unusual market activity detection (price/volume anomalies)
- BSE integration (if not already covered by NSE)

### Iteration 2: Multi-Sector + Rich Storage (Weeks 13-20)
- Expand to 2-3 additional sectors
- Migrate ChromaDB → Weaviate
- Add Neo4j for knowledge graph
- Sector-wide event detection and propagation
- Company relationship mapping
- Comparative analysis across companies in a sector
- Enhanced market data integration

### Iteration 3: Platform Maturity (Weeks 21-30)
- React frontend (replaces Streamlit)
- Control plane with PostgreSQL
- Agent-level access control
- Multi-agent architecture (refactor pipeline into autonomous agents)
- Event-driven messaging (Kafka or similar)
- Advanced financial models (DCF, peer comparison, DuPont analysis)
- Performance feedback loops
- Cloud deployment with container orchestration

### Iteration 4: Scale (Weeks 31+)
- Full NSE/BSE coverage across all sectors
- Automated feedback loops (system learns from signal accuracy)
- News aggregator integration
- Mobile notifications
- API for external system integration
- Consider external user access

---

## Key Differences from Original Architecture Docs

For transparency, here's what changed between the original BRD/architecture docs and this north star vision:

1. **Implementation approach**: Original assumed building the full architecture from day one. Now following progressive enhancement from a simple pipeline to multi-agent system.
2. **Agent framework**: Original specified Pydantic AI agent framework. Now starting with simple functions, introducing agent framework when complexity warrants it.
3. **Database**: Original specified Neptune (AWS). Now favoring Neo4j for graph (more flexibility, can self-host). ChromaDB added as stepping stone before Weaviate.
4. **Infrastructure**: Original specified EKS, MSK (Kafka), full AWS. Now starting with Docker Compose on a single server, evolving infrastructure with the product.
5. **Trigger sources**: Original focused almost exclusively on NSE RSS. Now explicitly includes social media, human triggers, and market activity.
6. **Gate layer**: Original had filtering but not as a distinct architectural boundary. Now the "Worth Reviewing" gate is a first-class design element with explicit cost-optimization purpose.
7. **Past investigation resurrection**: Original tracked history but didn't explicitly combine past inconclusive analyses with new triggers. Now this is a core feature of Layer 4.
8. **Frontend**: Original specified React from day one. Now starting with Streamlit/HTMX, React comes in Iteration 3.
