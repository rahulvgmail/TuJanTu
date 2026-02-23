# tuJanalyst: Technology Decisions Analysis

## Purpose

This document analyzes key technology choices for tuJanalyst, weighing trade-offs for MVP and long-term evolution. Each section covers what the choice is, the options, a recommendation, and what changes across iterations.

---

## 1. Agent & LLM Framework: Pydantic AI + DSPy

### The Question
How do we structure the LLM-powered reasoning and agent behavior?

### The Two Frameworks

**Pydantic AI** excels at:
- Defining agents with typed tools and structured outputs
- LLM-provider agnosticism (swap Claude for GPT or local models without code changes)
- Type-safe agent communication via Pydantic models
- Tool integration (web search, DB queries, API calls)
- Agent-level orchestration — an agent decides which tool to use when

**DSPy** excels at:
- Declarative LLM pipelines — define what you want (input/output signatures), not how to prompt
- Prompt optimization — automatically improve prompts using training examples and optimizers (BootstrapFewShot, MIPROv2, COPRO)
- Composable modules — chain reasoning steps like function composition
- Evaluation-driven development — define metrics, optimize against them
- Reproducibility — same pipeline, same inputs, deterministic behavior

### How They Fit Together

These aren't competing frameworks — they solve different problems and compose naturally:

```
┌─────────────────────────────────────────────────────────┐
│                    Pydantic AI Layer                      │
│  (Agent structure, tools, orchestration, typed I/O)      │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │                   DSPy Layer                        │  │
│  │  (LLM reasoning chains, prompt optimization,       │  │
│  │   composable modules, evaluation)                   │  │
│  └────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

**Pydantic AI** is the outer shell: it defines agents, their tools, their structured inputs/outputs, and how agents interact with the world (APIs, databases, each other).

**DSPy** is the reasoning engine inside each agent: it defines how the LLM thinks through a problem as a composable pipeline of modules, and those modules can be optimized over time.

### Mapping to the 5 Layers

| Layer | Pydantic AI Role | DSPy Role |
|-------|-----------------|-----------|
| **Layer 1: Triggers** | Agent with tools (RSS parser, HTTP client, document downloader) | Minimal — mostly tool use, not reasoning |
| **Layer 2: Gate** | Agent receives trigger, returns pass/fail decision | `dspy.Signature` for classification: `(announcement_text, company) -> (is_worth_reviewing: bool, reason: str)`. Prime candidate for prompt optimization. |
| **Layer 3: Deep Analysis** | Agent with tools (vector search, web search, market data API, database queries) | Chain of DSPy modules: `ExtractMetrics >> SearchContext >> SynthesizeFindings >> AssessSignificance`. Each module has a signature that can be independently optimized. |
| **Layer 4: Decision** | Agent retrieves past investigations, current positions | DSPy module: `(current_findings, past_investigations, current_recommendation) -> (should_update: bool, new_recommendation, reasoning, confidence)`. Optimizable against historical accuracy. |
| **Layer 5: Report** | Agent generates and delivers report | DSPy module for report generation with structured output. Template-driven, optimizable for clarity/usefulness ratings. |

### DSPy-Specific Design Patterns for tuJanalyst

**Signatures** (define what each reasoning step does):
```python
class GateClassification(dspy.Signature):
    """Decide if a corporate announcement is worth investigating for investment decisions."""
    announcement_text: str = dspy.InputField(desc="The corporate announcement text")
    company_name: str = dspy.InputField(desc="Company name")
    sector: str = dspy.InputField(desc="Company's sector")
    is_worth_investigating: bool = dspy.OutputField(desc="Whether this warrants deeper analysis")
    reason: str = dspy.OutputField(desc="Brief explanation")

class MetricsExtraction(dspy.Signature):
    """Extract key financial metrics from a corporate document."""
    document_text: str = dspy.InputField(desc="Full text of the financial document")
    company_name: str = dspy.InputField(desc="Company name")
    metrics: list[dict] = dspy.OutputField(desc="List of extracted metrics with name, value, period, unit")
    forward_looking_statements: list[str] = dspy.OutputField(desc="Promises and projections")
    key_highlights: list[str] = dspy.OutputField(desc="Most important points")

class InvestmentDecision(dspy.Signature):
    """Assess whether new information warrants changing an investment recommendation."""
    current_findings: str = dspy.InputField(desc="Current investigation synthesis")
    past_investigations: str = dspy.InputField(desc="Summaries of past investigations")
    current_recommendation: str = dspy.InputField(desc="Current buy/sell/hold stance")
    should_update: bool = dspy.OutputField(desc="Whether to update the recommendation")
    new_recommendation: str = dspy.OutputField(desc="Updated recommendation if changed")
    reasoning: str = dspy.OutputField(desc="Detailed reasoning for the decision")
    confidence: float = dspy.OutputField(desc="Confidence score 0.0-1.0")
```

**Modules** (composable processing steps):
```python
class DeepAnalysisPipeline(dspy.Module):
    def __init__(self):
        self.extract_metrics = dspy.ChainOfThought(MetricsExtraction)
        self.assess_significance = dspy.ChainOfThought(SignificanceAssessment)
        self.synthesize = dspy.ChainOfThought(AnalysisSynthesis)

    def forward(self, document_text, company_name, historical_context, market_data):
        metrics = self.extract_metrics(document_text=document_text, company_name=company_name)
        significance = self.assess_significance(
            metrics=metrics.metrics,
            highlights=metrics.key_highlights,
            historical_context=historical_context,
            market_data=market_data
        )
        synthesis = self.synthesize(
            metrics=metrics,
            significance=significance,
            historical_context=historical_context
        )
        return synthesis
```

**Optimization** (the killer feature of DSPy):
```python
# After collecting examples of good/bad gate decisions from team feedback
optimizer = dspy.MIPROv2(metric=gate_accuracy_metric, num_candidates=10)
optimized_gate = optimizer.compile(
    GateModule(),
    trainset=labeled_gate_examples,  # From team feedback
    max_bootstrapped_demos=4,
    max_labeled_demos=8
)
# The optimized gate has better prompts, automatically discovered
```

This is where DSPy really shines for tuJanalyst: as your team gives feedback on reports (thumbs up/down), you accumulate training data. DSPy can then automatically optimize the prompts in each module to improve accuracy. This directly addresses the "continuous improvement" business requirement without building custom ML infrastructure.

### Recommendation

**MVP**: Use both from day one. The overhead is minimal:
- Pydantic AI for agent structure and tool integration
- DSPy for all LLM reasoning chains (gate classification, analysis, decision, report generation)
- Start with `dspy.ChainOfThought` for each reasoning step (adds chain-of-thought reasoning automatically)
- Collect feedback from day one (even simple thumbs up/down)
- Run DSPy optimization once you have 20-30 labeled examples (probably after 2-3 weeks of use)

**Why not wait?** Because DSPy's signatures and modules are a better way to organize LLM calls than raw prompts regardless of whether you optimize. They're declarative, testable, and composable. You get cleaner code even before optimization kicks in.

---

## 2. LLM Strategy

### The Question
Which LLM provider(s), which models, and how do we manage costs?

### Provider Choice

Since Pydantic AI is provider-agnostic and DSPy supports multiple backends, you're not locked in. But you need a primary provider.

**Recommendation: Anthropic Claude as primary**

| Model | Use Case | Cost Rationale |
|-------|----------|----------------|
| **Claude Haiku** | Layer 2 gate classification | Cheapest, fastest. Gate needs speed, not depth. |
| **Claude Sonnet** | Layer 3 analysis, Layer 5 reports | Best quality/cost balance for most analytical work. |
| **Claude Opus** | Layer 4 decision assessment (selectively) | When the stakes are high and you need the deepest reasoning. Optional — Sonnet may be sufficient. |

### Multi-Provider Considerations

For MVP, stick to one provider. Multi-provider adds complexity (different prompt behaviors, different output formats, different rate limits). Pydantic AI makes switching easy later if needed.

When to consider alternatives:
- **OpenAI GPT-4o**: If Claude has downtime. Good fallback.
- **Google Gemini**: If you need very long context windows (1M+ tokens for analyzing multiple quarterly reports simultaneously).
- **Local models (Llama, Mistral)**: If you want to reduce cost for the gate or run sensitive analysis on-premise. DSPy makes this easy — same signatures, different backend.

### Cost Management Strategy

The biggest cost driver is Layer 3 (deep analysis) because it processes the most tokens. Strategies:

1. **Gate aggressively** — The better your Layer 2 filtering, the fewer expensive Layer 3 calls you make
2. **Cache embeddings** — Don't re-embed documents that haven't changed
3. **Summarize before comparing** — Store summaries of past investigations, pass summaries (not full text) to Layer 4
4. **Use the right model for each task** — Don't use Opus for classification
5. **Monitor token usage** — Log tokens per investigation, set alerts for anomalies

### DSPy Cost Benefit

DSPy's optimization can actually reduce costs: optimized prompts are typically shorter and more focused, leading to lower token usage for the same quality output. MIPROv2 optimization can also find that a cheaper model performs well enough for specific tasks, enabling model downgrades without quality loss.

---

## 3. Storage Layer

### The Question
What databases, how many, and when to introduce each?

### Philosophy (from your brain dump)
> "I want to limit Postgres or SQL only for the control plane because most of the things are dynamic... Starting with SQL usually means getting tied down to what your storage layer looks like."

This is sound thinking. The data model WILL evolve significantly in the first few months as you learn what matters for analysis. Schema flexibility is more important than query optimization at this stage.

### The Storage Stack

#### MVP (Weeks 1-6)

| Store | Technology | Purpose |
|-------|-----------|---------|
| **Document store** | MongoDB | Triggers, investigations, reports, documents, company data, configs |
| **Vector store** | ChromaDB (embedded) | Document and passage embeddings for semantic search |

**Why MongoDB over alternatives?**
- Flexible schema — add fields without migrations
- Good enough for time-series queries at MVP scale (thousands of records, not millions)
- Native Python driver is excellent
- GridFS handles document storage
- Aggregation pipeline covers most analytical queries

**Why ChromaDB over Weaviate for MVP?**
- Zero infrastructure — runs embedded in your Python process
- Good enough for MVP scale (hundreds to low thousands of documents)
- Simple API, fast to integrate
- Easy to abstract behind a repository interface for later migration

**What about the graph DB?**
Skip it for MVP. Here's why: with one sector and ~20-30 companies, you can represent relationships as MongoDB documents:
```python
class CompanyRelationship:
    company_a: str
    company_b: str
    relationship_type: str  # "competes_with", "supplies_to", "subsidiary_of"
    metadata: dict
```
This is "good enough" for 6 weeks. The graph becomes essential when you need multi-hop traversals across hundreds of companies ("find all companies that supply to companies in the wind energy supply chain that recently reported declining order books").

#### Iteration 2 (Weeks 13-20)

| Store | Technology | Purpose | Migration Path |
|-------|-----------|---------|----------------|
| **Document store** | MongoDB | Same, expanded schemas | No migration needed |
| **Vector store** | Weaviate | Replaces ChromaDB | Reindex documents; swap the repository implementation |
| **Graph store** | Neo4j | Company-sector-industry ontology, relationships | New; populate from MongoDB relationship data |

**Why Weaviate over Pinecone, Qdrant, or Milvus?**
- Hybrid search (vector + keyword) out of the box — crucial for financial docs where exact terms matter
- Multi-tenancy support for when you want per-sector or per-user isolation
- Good filtering capabilities (filter by company, date range, document type before doing vector search)
- Active Python client and good docs
- Can self-host or use managed service

**Why Neo4j over Neptune?**
- Not locked to AWS — can run locally for development
- Cypher query language is more expressive than Gremlin for the types of queries you'll need
- Mature Python driver (neo4j-python-driver)
- Better tooling for visualization and exploration (Neo4j Browser)
- Community edition is free for self-hosting

#### Full Vision (Iteration 3+)

| Store | Technology | Purpose |
|-------|-----------|---------|
| **Document store** | MongoDB | Documents, state, investigations |
| **Vector store** | Weaviate | Semantic search, embeddings |
| **Graph store** | Neo4j | Knowledge graph, ontology |
| **Time-series** | TimescaleDB or InfluxDB | Financial metrics history, market data |
| **Cache** | Redis | Hot data, task queues, session state |
| **Control plane** | PostgreSQL | Users, access control, audit logs, system config |

**Time-series: TimescaleDB vs InfluxDB**
- TimescaleDB is PostgreSQL-based, so if you're already running Postgres for the control plane, it's one less database to operate. It also handles hybrid queries well (join time-series with relational data).
- InfluxDB is purpose-built and faster for pure time-series workloads.
- **Recommendation**: TimescaleDB, because you're already running Postgres for the control plane. One less operational burden.

### Data Access Layer Design

Your brain dump asked: "How does data get accessed from the storage layer?"

**Recommendation: Repository pattern with a unified data access service.**

```
┌─────────────────────────────────────────────────┐
│            Data Access Service (DAS)              │
│                                                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ Document  │ │ Vector   │ │ Graph            │ │
│  │ Repo      │ │ Repo     │ │ Repo             │ │
│  │ (MongoDB) │ │ (Chroma/ │ │ (MongoDB/Neo4j)  │ │
│  │           │ │  Weaviate)│ │                  │ │
│  └──────────┘ └──────────┘ └──────────────────┘ │
│                                                   │
│  ┌──────────────────────────────────────────────┐│
│  │ Access Control (future: per-agent perms)      ││
│  └──────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
```

Each repository is a Python class with a clean interface:
```python
class DocumentRepository(Protocol):
    async def save_investigation(self, investigation: Investigation) -> str: ...
    async def get_investigation(self, investigation_id: str) -> Investigation: ...
    async def get_investigations_for_company(self, company_symbol: str, limit: int = 10) -> list[Investigation]: ...
    async def get_past_inconclusive(self, company_symbol: str) -> list[Investigation]: ...

class VectorRepository(Protocol):
    async def embed_and_store(self, document_id: str, text: str, metadata: dict) -> None: ...
    async def search_similar(self, query: str, filters: dict | None = None, limit: int = 5) -> list[SearchResult]: ...

class GraphRepository(Protocol):
    async def get_related_companies(self, company_symbol: str, relationship_type: str | None = None) -> list[Company]: ...
    async def get_sector_companies(self, sector: str) -> list[Company]: ...
```

Using `Protocol` (structural typing) means the implementation can swap from MongoDB-backed to Neo4j-backed without changing any calling code. This is how you start with MongoDB for everything and migrate specific concerns to specialized databases later.

---

## 4. Agent & Pipeline Architecture

### The Question
Single agent per layer vs multiple agents? Master agent pattern? How do layers communicate?

### MVP Architecture: DSPy Modules in a Pydantic AI Shell

For MVP, the architecture is straightforward:

```
┌─────────────────────────────────────────────────────────┐
│                   Orchestrator                           │
│  (Simple async function that runs the pipeline)          │
│                                                          │
│  trigger = await ingest(rss_item)                        │
│  if await gate(trigger):                 # DSPy module   │
│      investigation = await analyze(trigger)  # DSPy pipeline │
│      decision = await assess(investigation)  # DSPy module   │
│      report = await generate_report(decision)# DSPy module   │
│      await deliver(report)                               │
└─────────────────────────────────────────────────────────┘
```

Each function is a Pydantic AI agent (for tool access) that internally uses DSPy modules (for reasoning):

```python
from pydantic_ai import Agent
import dspy

class AnalysisAgent:
    """Layer 3: Deep Analysis. Uses Pydantic AI for tools, DSPy for reasoning."""

    def __init__(self, doc_repo, vector_repo, web_search_tool, market_data_tool):
        # Pydantic AI agent with tools
        self.agent = Agent(
            model="claude-sonnet",
            tools=[web_search_tool, market_data_tool]
        )
        # DSPy reasoning pipeline
        self.analysis_pipeline = DeepAnalysisPipeline()
        # Repositories for data access
        self.doc_repo = doc_repo
        self.vector_repo = vector_repo

    async def analyze(self, trigger: TriggerEvent) -> Investigation:
        # 1. Use tools (Pydantic AI) to gather data
        historical = await self.vector_repo.search_similar(trigger.raw_content)
        market_data = await self.agent.run_tool("market_data", symbol=trigger.company_symbol)
        web_results = await self.agent.run_tool("web_search", query=f"{trigger.company_name} latest news")

        # 2. Use DSPy pipeline for reasoning
        analysis = self.analysis_pipeline(
            document_text=trigger.raw_content,
            company_name=trigger.company_name,
            historical_context=format_historical(historical),
            market_data=format_market_data(market_data)
        )

        # 3. Return typed output
        return Investigation(
            trigger_id=trigger.trigger_id,
            company_symbol=trigger.company_symbol,
            significance_assessment=analysis.assessment,
            key_findings=analysis.findings,
            # ...
        )
```

### Why Not Full Multi-Agent From Day One?

The multi-agent pattern (20 agents, coordinator per layer, message passing) adds significant complexity:
- Agent lifecycle management
- Message serialization/deserialization
- Coordination logic (what if one agent fails?)
- Debugging (tracing a decision across 5 agents is hard)
- Infrastructure (message broker, agent registry)

None of this helps prove the core thesis. A pipeline with DSPy modules gives you the same logical decomposition with dramatically less infrastructure.

### Evolution to Multi-Agent (Iteration 3+)

When to introduce proper multi-agent architecture:
1. **When you need parallelism** — multiple companies being analyzed simultaneously need independent agent instances
2. **When you need specialization** — different analysis approaches for different document types (quarterly reports vs. M&A announcements)
3. **When you need autonomy** — agents that proactively monitor and trigger investigations without explicit orchestration

The migration path is clean because of the separation between Pydantic AI (agent structure) and DSPy (reasoning):
- Each DSPy module becomes the "brain" of a Pydantic AI agent
- Each agent gets its own tool set and data access permissions
- Layer coordinators become Pydantic AI agents that dispatch to specialist agents
- The event bus (Kafka or similar) replaces direct function calls

### The Master Agent Pattern (Your Question)

> "Does it make sense to have a master agent that receives the query from the earlier layer and engages the agents in this layer and passes control to the master agent of next layer?"

**Yes, this is the right pattern for the full vision.** It maps cleanly to your 5-layer model:

```
Layer 1 Master ──▶ Layer 2 Master ──▶ Layer 3 Master ──▶ Layer 4 Master ──▶ Layer 5 Master
     │                   │                   │                   │                   │
     ▼                   ▼                   ▼                   ▼                   ▼
  RSS Agent          Filter Agent      Metrics Agent      Decision Agent     Report Agent
  Human Input        AI Classifier     Narrative Agent    History Agent      Delivery Agent
  Doc Downloader                       Web Search Agent
                                       Market Data Agent
```

Each master agent:
- Receives structured input from the previous master
- Decomposes the work into subtasks
- Dispatches to specialist agents
- Aggregates results
- Passes structured output to the next master

**But for MVP, the "masters" are just functions and the "specialists" are DSPy modules within those functions.** The logical decomposition is the same; the infrastructure is simpler.

### Cross-Layer Communication

> "Should agents only talk to agents in the same layer?"

**Rules:**
1. **Forward flow**: Data flows forward through layers (1→2→3→4→5). This is the primary communication path.
2. **Backward queries**: Any layer can *query* data from previous layers (Layer 4 can read Layer 3 investigations, Layer 3 can read Layer 1 trigger data). This is read-only data access, not control flow.
3. **No backward control**: Layer 3 should never tell Layer 1 to fetch more data mid-analysis. Instead, Layer 3 has its own tools (web search, market data API) to get additional information.
4. **Shared storage**: All layers read/write to the same data stores, with access mediated by the data access layer.

This keeps the architecture understandable and debuggable. When something goes wrong, you trace forward through the layers.

---

## 5. Control Plane

### The Question
Should there be a dedicated control plane? What does it manage?

### MVP: Config Files + MongoDB

For internal use with 2-3 people, the control plane is:
- `watchlist.yaml` — sectors, companies, keywords
- `config.yaml` — LLM model selection, polling intervals, notification settings
- MongoDB collections — investigation state, feedback data

### Full Vision: Dedicated Service

When the control plane becomes a proper service (Iteration 3+):

| Responsibility | What It Does |
|---------------|--------------|
| **Access control** | Which agents can read/write which collections. Which humans can see which reports. |
| **Configuration** | Watchlists, model selections, thresholds, notification preferences. Live updates without restart. |
| **Audit logging** | Every LLM call, every decision, every tool invocation. Immutable log for compliance. |
| **Feedback management** | Human feedback on reports flows here, gets routed to DSPy optimization pipeline. |
| **Agent registry** | Which agents exist, their versions, their capabilities, their health status. |
| **Financial calendar** | Expected report dates, earnings seasons, regulatory deadlines. |
| **Static data** | Sector classifications, company master data, market taxonomies. |

**Technology**: PostgreSQL (the only SQL in the system), exposed via FastAPI.

**Why separate?** Because the control plane has different availability requirements (it must always be up), different data characteristics (relational, transactional), and different access patterns (human-driven CRUD) from the analytical data layer.

---

## 6. Deployment Evolution

| Phase | Infrastructure | Justification |
|-------|---------------|---------------|
| **MVP** | Docker Compose on single server (EC2 or equivalent) | Minimal ops overhead. 2-3 people can't maintain Kubernetes. |
| **Iteration 2** | Docker Compose with separate database servers | As data grows, databases need dedicated resources. |
| **Iteration 3** | Kubernetes (EKS or self-managed) | When you have multiple services that need independent scaling. |
| **Full vision** | Managed Kubernetes + managed databases | When reliability and scalability are business-critical. |

---

## Summary: Technology Stack Evolution

```
MVP (Weeks 1-6)
├── App: FastAPI + Pydantic AI + DSPy
├── Storage: MongoDB + ChromaDB (embedded)
├── LLM: Claude Haiku (gate) + Sonnet (analysis)
├── UI: Streamlit
├── Deploy: Docker Compose, single server
└── Config: YAML files

Iteration 2 (Weeks 13-20)
├── App: FastAPI + Pydantic AI + DSPy (optimized prompts)
├── Storage: MongoDB + Weaviate + Neo4j
├── LLM: Claude Haiku/Sonnet/Opus (task-matched)
├── UI: Streamlit (enhanced)
├── Deploy: Docker Compose, multiple servers
└── Config: MongoDB-backed config service

Iteration 3+ (Weeks 21-30)
├── App: FastAPI + Pydantic AI agents + DSPy + event bus
├── Storage: MongoDB + Weaviate + Neo4j + TimescaleDB + Redis
├── LLM: Multi-model, DSPy-optimized
├── UI: React
├── Deploy: Kubernetes
└── Config: PostgreSQL control plane
```
