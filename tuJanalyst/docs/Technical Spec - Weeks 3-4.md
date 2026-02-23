# tuJanalyst: Technical Specification — Weeks 3-4

## Overview

This spec covers Weeks 3-4 of MVP development — the LLM-heavy analytical layers. By the end of Week 4, the system should:
- Take gate-passed triggers and run deep analysis (Layer 3)
- Gather historical context, web search results, and market data
- Assess whether findings warrant a buy/sell recommendation change (Layer 4)
- Generate human-readable reports and deliver via Slack/email (Layer 5)
- Complete the end-to-end pipeline: trigger → gate → analysis → decision → report

**Prerequisite**: Weeks 1-2 deliverables working (RSS polling, document ingestion, gate, vector embeddings).

---

## 1. New Data Models

### 1.1 Investigation (Layer 3 Output)

```python
# src/models/investigation.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from enum import Enum

class SignificanceLevel(str, Enum):
    HIGH = "high"           # Likely material impact on investment thesis
    MEDIUM = "medium"       # Notable but may not change recommendation
    LOW = "low"             # Minor, worth recording but not acting on
    NOISE = "noise"         # Passed the gate but analysis found nothing meaningful

class ExtractedMetric(BaseModel):
    """A single financial metric extracted from a document."""
    name: str                           # e.g., "Revenue", "EBITDA", "Order Book"
    value: float | str                  # Numeric or text (e.g., "₹1,200 Cr")
    raw_value: str                      # Original text from document
    unit: str = ""                      # "Cr", "%", "MW", etc.
    period: str = ""                    # "Q3 FY26", "FY25", "H1 FY26"
    yoy_change: Optional[float] = None  # Year-over-year change if calculable
    qoq_change: Optional[float] = None  # Quarter-over-quarter change
    confidence: float = 0.8             # How confident the extraction is

class ForwardStatement(BaseModel):
    """A forward-looking statement or promise extracted from a document."""
    statement: str                      # The actual statement
    target_metric: Optional[str] = None # What metric it relates to
    target_value: Optional[str] = None  # Target value if mentioned
    target_date: Optional[str] = None   # When they expect to achieve it
    category: str = "general"           # "revenue", "capacity", "order_book", "margin", "general"

class WebSearchResult(BaseModel):
    """A summarized web search finding."""
    query: str                          # The search query used
    source: str                         # URL or source name
    title: str
    summary: str                        # LLM-generated summary of the finding
    relevance: str                      # "high", "medium", "low"
    sentiment: str = "neutral"          # "positive", "negative", "neutral"

class MarketDataSnapshot(BaseModel):
    """Market data for the company at time of analysis."""
    current_price: Optional[float] = None
    market_cap_cr: Optional[float] = None       # Market cap in crores
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    avg_volume_30d: Optional[int] = None
    price_change_1d: Optional[float] = None     # % change
    price_change_1w: Optional[float] = None
    price_change_1m: Optional[float] = None
    sector_pe_avg: Optional[float] = None
    fii_holding_pct: Optional[float] = None     # Latest available
    dii_holding_pct: Optional[float] = None
    promoter_holding_pct: Optional[float] = None
    promoter_pledge_pct: Optional[float] = None
    data_source: str = "yfinance"
    data_timestamp: Optional[datetime] = None

class HistoricalContext(BaseModel):
    """Past analyses and data retrieved for context."""
    past_investigations: list[dict] = Field(default_factory=list)  # Summaries of past investigations
    past_recommendations: list[dict] = Field(default_factory=list) # Past buy/sell recommendations
    past_promises: list[dict] = Field(default_factory=list)        # Forward statements we've tracked
    similar_documents: list[dict] = Field(default_factory=list)    # Vector search results
    total_past_investigations: int = 0

class Investigation(BaseModel):
    investigation_id: str = Field(default_factory=lambda: str(uuid4()))
    trigger_id: str
    company_symbol: str
    company_name: str

    # Layer 3 analysis components
    extracted_metrics: list[ExtractedMetric] = Field(default_factory=list)
    forward_statements: list[ForwardStatement] = Field(default_factory=list)
    management_highlights: list[str] = Field(default_factory=list)
    web_search_results: list[WebSearchResult] = Field(default_factory=list)
    market_data: Optional[MarketDataSnapshot] = None
    historical_context: Optional[HistoricalContext] = None

    # LLM synthesis
    synthesis: str = ""                  # Full LLM synthesis narrative
    key_findings: list[str] = Field(default_factory=list)   # Top findings
    red_flags: list[str] = Field(default_factory=list)      # Concerns
    positive_signals: list[str] = Field(default_factory=list)
    significance: SignificanceLevel = SignificanceLevel.MEDIUM
    significance_reasoning: str = ""
    is_significant: bool = False         # Should this proceed to Layer 4?

    # Metadata
    llm_model_used: str = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    processing_time_seconds: float = 0.0

    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        collection_name = "investigations"
```

### 1.2 Decision Assessment (Layer 4 Output)

```python
# src/models/decision.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from enum import Enum

class Recommendation(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    NONE = "none"          # No recommendation yet (new company)

class RecommendationTimeframe(str, Enum):
    SHORT_TERM = "short_term"     # Days to weeks
    MEDIUM_TERM = "medium_term"   # Weeks to months
    LONG_TERM = "long_term"       # Months to years

class DecisionAssessment(BaseModel):
    assessment_id: str = Field(default_factory=lambda: str(uuid4()))
    investigation_id: str
    trigger_id: str
    company_symbol: str
    company_name: str

    # Current state (before this assessment)
    previous_recommendation: Recommendation = Recommendation.NONE
    previous_recommendation_date: Optional[datetime] = None
    previous_recommendation_basis: str = ""

    # Decision
    recommendation_changed: bool = False
    new_recommendation: Recommendation = Recommendation.NONE
    timeframe: RecommendationTimeframe = RecommendationTimeframe.MEDIUM_TERM
    confidence: float = 0.0                    # 0.0 - 1.0

    # Reasoning
    reasoning: str = ""                        # Full reasoning narrative
    key_factors_for: list[str] = Field(default_factory=list)    # Factors supporting the recommendation
    key_factors_against: list[str] = Field(default_factory=list) # Factors against / risks
    risks: list[str] = Field(default_factory=list)

    # Context used
    past_investigations_used: list[str] = Field(default_factory=list)  # IDs
    past_inconclusive_resurrected: list[str] = Field(default_factory=list)  # IDs of past investigations that were inconclusive but now contribute

    # Metadata
    llm_model_used: str = ""
    processing_time_seconds: float = 0.0

    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        collection_name = "assessments"
```

### 1.3 Company Position (Current Recommendation State)

```python
# src/models/company.py (add to existing file)

class CompanyPosition(BaseModel):
    """
    Tracks our current investment stance on a company.
    One document per company in MongoDB. Updated when Layer 4 changes a recommendation.
    """
    company_symbol: str                        # Primary key
    company_name: str

    current_recommendation: Recommendation = Recommendation.NONE
    recommendation_date: Optional[datetime] = None
    recommendation_basis: str = ""             # Summary of why
    recommendation_assessment_id: Optional[str] = None  # Which assessment set this

    # History
    recommendation_history: list[dict] = Field(default_factory=list)
    # [{recommendation, date, assessment_id, confidence}]

    total_investigations: int = 0
    last_investigation_date: Optional[datetime] = None

    class Config:
        collection_name = "positions"
```

### 1.4 Analysis Report (Layer 5 Output)

```python
# src/models/report.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class ReportDeliveryStatus(str, Enum):
    GENERATED = "generated"
    DELIVERED = "delivered"
    DELIVERY_FAILED = "delivery_failed"

class AnalysisReport(BaseModel):
    report_id: str = Field(default_factory=lambda: str(uuid4()))
    assessment_id: str
    investigation_id: str
    trigger_id: str
    company_symbol: str
    company_name: str

    # Report content (markdown)
    title: str = ""
    executive_summary: str = ""              # 2-3 sentences
    report_body: str = ""                    # Full markdown report
    recommendation_summary: str = ""         # Quick recommendation + confidence

    # Delivery
    delivery_status: ReportDeliveryStatus = ReportDeliveryStatus.GENERATED
    delivered_via: list[str] = Field(default_factory=list)  # ["slack", "email"]
    delivered_at: Optional[datetime] = None

    # Human feedback
    feedback_rating: Optional[int] = None    # 1-5 or thumbs up/down (1 or 0)
    feedback_comment: Optional[str] = None
    feedback_by: Optional[str] = None
    feedback_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        collection_name = "reports"
```

---

## 2. New Repository Methods

```python
# src/repositories/base.py (additions)

class InvestigationRepository(Protocol):
    async def save(self, investigation: Investigation) -> str: ...
    async def get(self, investigation_id: str) -> Optional[Investigation]: ...
    async def get_by_company(self, company_symbol: str, limit: int = 20) -> list[Investigation]: ...
    async def get_past_inconclusive(self, company_symbol: str) -> list[Investigation]:
        """Get investigations that were significant but didn't lead to recommendation changes."""
        ...

class AssessmentRepository(Protocol):
    async def save(self, assessment: DecisionAssessment) -> str: ...
    async def get(self, assessment_id: str) -> Optional[DecisionAssessment]: ...
    async def get_by_company(self, company_symbol: str, limit: int = 10) -> list[DecisionAssessment]: ...

class PositionRepository(Protocol):
    async def get_position(self, company_symbol: str) -> Optional[CompanyPosition]: ...
    async def upsert_position(self, position: CompanyPosition) -> None: ...

class ReportRepository(Protocol):
    async def save(self, report: AnalysisReport) -> str: ...
    async def get(self, report_id: str) -> Optional[AnalysisReport]: ...
    async def get_recent(self, limit: int = 20) -> list[AnalysisReport]: ...
    async def update_feedback(self, report_id: str, rating: int, comment: str, by: str) -> None: ...
```

---

## 3. DSPy Signatures and Modules

### 3.1 All New Signatures

```python
# src/dspy_modules/signatures.py (additions)

class MetricsExtraction(dspy.Signature):
    """Extract key financial metrics from a corporate document.

    You are an expert financial analyst specializing in Indian markets.
    Extract all quantitative financial metrics mentioned in the document.
    For each metric, capture the exact value, unit, and time period.
    Calculate YoY and QoQ changes if comparative data is provided.
    Flag any metrics that seem unusual or noteworthy."""

    document_text: str = dspy.InputField(desc="Full extracted text of the financial document")
    company_name: str = dspy.InputField(desc="Company name for context")
    document_type: str = dspy.InputField(desc="Type: quarterly_results, press_release, annual_report, etc.")
    metrics_json: str = dspy.OutputField(desc="JSON array of extracted metrics: [{name, value, raw_value, unit, period, yoy_change, qoq_change, confidence}]")
    forward_statements_json: str = dspy.OutputField(desc="JSON array of forward-looking statements: [{statement, target_metric, target_value, target_date, category}]")
    management_highlights: str = dspy.OutputField(desc="JSON array of key management commentary highlights as strings")


class WebSearchQueryGeneration(dspy.Signature):
    """Generate targeted web search queries to investigate a corporate announcement.

    Given an announcement and preliminary analysis, generate 3-5 search queries
    that would help validate, contextualize, or deepen understanding of the news.
    Focus on queries that would surface: corroborating evidence, contradicting information,
    sector context, analyst opinions, and related recent developments."""

    announcement_summary: str = dspy.InputField(desc="Summary of the corporate announcement")
    company_name: str = dspy.InputField(desc="Company name")
    sector: str = dspy.InputField(desc="Company's sector")
    preliminary_findings: str = dspy.InputField(desc="Key metrics and highlights already extracted")
    search_queries: str = dspy.OutputField(desc="JSON array of 3-5 search query strings, most important first")


class WebResultSynthesis(dspy.Signature):
    """Synthesize web search results into relevant findings for financial analysis.

    Given search results about a company, extract and summarize the most relevant
    information for investment decision-making. Ignore irrelevant results.
    Flag anything that contradicts the original announcement."""

    company_name: str = dspy.InputField(desc="Company name")
    search_query: str = dspy.InputField(desc="The search query that produced these results")
    search_results_text: str = dspy.InputField(desc="Raw text from search results (titles + snippets)")
    summary: str = dspy.OutputField(desc="Concise summary of relevant findings")
    relevance: str = dspy.OutputField(desc="high, medium, or low")
    sentiment: str = dspy.OutputField(desc="positive, negative, or neutral for the company")


class InvestigationSynthesis(dspy.Signature):
    """Synthesize all analysis components into a comprehensive investigation assessment.

    You are a senior financial analyst. Given all the data gathered about a corporate
    announcement — extracted metrics, forward-looking statements, web search results,
    market data, and historical context — produce a comprehensive synthesis.

    Be specific and quantitative. Don't just say "revenue grew" — say "revenue grew 23% YoY
    to ₹850 Cr, beating the ₹780 Cr consensus estimate." Reference actual numbers.

    Explicitly identify what's NEW and DIFFERENT from what we already knew.
    Flag any contradictions between what the company says and what the data shows."""

    company_name: str = dspy.InputField(desc="Company name")
    sector: str = dspy.InputField(desc="Company's sector")
    trigger_content: str = dspy.InputField(desc="Original trigger/announcement content")
    extracted_metrics: str = dspy.InputField(desc="JSON of extracted financial metrics")
    forward_statements: str = dspy.InputField(desc="JSON of forward-looking statements")
    web_findings: str = dspy.InputField(desc="Summarized web search findings")
    market_data: str = dspy.InputField(desc="Current market data snapshot")
    historical_context: str = dspy.InputField(desc="Past investigations, recommendations, and promises")

    synthesis: str = dspy.OutputField(desc="Comprehensive narrative synthesis (3-5 paragraphs)")
    key_findings: str = dspy.OutputField(desc="JSON array of top 3-5 key findings as strings")
    red_flags: str = dspy.OutputField(desc="JSON array of concerns or red flags (empty array if none)")
    positive_signals: str = dspy.OutputField(desc="JSON array of positive signals (empty array if none)")
    significance: str = dspy.OutputField(desc="high, medium, low, or noise")
    significance_reasoning: str = dspy.OutputField(desc="Why this significance level")
    is_significant: bool = dspy.OutputField(desc="True if this should proceed to decision assessment")


class DecisionEvaluation(dspy.Signature):
    """Evaluate whether new information warrants changing an investment recommendation.

    You are the head of research at an investment firm. Given a new investigation and
    all historical context for this company, decide whether the investment thesis has changed.

    Consider:
    - Does the new information confirm or contradict the existing thesis?
    - Are there past investigations that were individually inconclusive but, combined
      with this new information, now paint a clearer picture?
    - What is the risk/reward of acting vs. not acting?
    - What is the appropriate time horizon for this recommendation?

    Be decisive but honest about uncertainty. A 'hold' is also a valid decision.
    If confidence is below 0.5, lean toward 'hold' and explain what additional
    information would increase confidence."""

    company_name: str = dspy.InputField(desc="Company name")
    current_recommendation: str = dspy.InputField(desc="Current recommendation: buy, sell, hold, or none")
    current_recommendation_basis: str = dspy.InputField(desc="Why the current recommendation was set")
    investigation_synthesis: str = dspy.InputField(desc="Full synthesis from the current investigation")
    investigation_key_findings: str = dspy.InputField(desc="Key findings from the current investigation")
    past_investigations_summary: str = dspy.InputField(desc="Summaries of past investigations for this company")
    past_inconclusive_summary: str = dspy.InputField(desc="Past investigations that were significant but didn't change recommendation")
    market_data: str = dspy.InputField(desc="Current market data for context")

    should_change: bool = dspy.OutputField(desc="True if recommendation should change")
    new_recommendation: str = dspy.OutputField(desc="buy, sell, or hold")
    timeframe: str = dspy.OutputField(desc="short_term, medium_term, or long_term")
    confidence: float = dspy.OutputField(desc="Confidence score 0.0-1.0")
    reasoning: str = dspy.OutputField(desc="Detailed reasoning for the decision (3-5 paragraphs)")
    key_factors_for: str = dspy.OutputField(desc="JSON array of factors supporting this recommendation")
    key_factors_against: str = dspy.OutputField(desc="JSON array of factors against / risks")
    past_investigations_that_contributed: str = dspy.OutputField(desc="JSON array of past investigation IDs that influenced this decision")


class ReportGeneration(dspy.Signature):
    """Generate a professional investment analysis report for human review.

    You are writing for experienced investors who need to make a decision quickly.
    The report should be scannable — lead with the verdict, then provide supporting detail.

    Structure:
    1. Title: [Company] — [One-line verdict]
    2. Executive Summary (2-3 sentences: what happened, what it means, what we recommend)
    3. The Trigger (what new information came in)
    4. Key Findings (bullet points with specific numbers)
    5. Historical Context (how this relates to what we already knew)
    6. Market Context (current valuation and positioning)
    7. Recommendation (buy/sell/hold + confidence + timeframe + reasoning)
    8. Risks (what could make this recommendation wrong)
    9. Sources

    Use markdown formatting. Be concise but precise. Every claim should reference
    a specific number or source. Don't pad with generic statements."""

    company_name: str = dspy.InputField(desc="Company name")
    company_symbol: str = dspy.InputField(desc="NSE/BSE symbol")
    trigger_summary: str = dspy.InputField(desc="What triggered this investigation")
    investigation_synthesis: str = dspy.InputField(desc="Full investigation synthesis")
    key_findings: str = dspy.InputField(desc="Key findings list")
    red_flags: str = dspy.InputField(desc="Red flags list")
    positive_signals: str = dspy.InputField(desc="Positive signals list")
    market_data: str = dspy.InputField(desc="Market data snapshot")
    historical_context: str = dspy.InputField(desc="Relevant historical context")
    recommendation: str = dspy.InputField(desc="buy, sell, or hold")
    recommendation_reasoning: str = dspy.InputField(desc="Full reasoning for recommendation")
    confidence: float = dspy.InputField(desc="Confidence score")
    risks: str = dspy.InputField(desc="Key risks")

    report_title: str = dspy.OutputField(desc="Report title: [Company] — [one-line verdict]")
    executive_summary: str = dspy.OutputField(desc="2-3 sentence executive summary")
    report_body: str = dspy.OutputField(desc="Full markdown report following the structure above")
```

### 3.2 DSPy Modules

```python
# src/dspy_modules/analysis.py
import dspy
import json
from src.dspy_modules.signatures import (
    MetricsExtraction,
    WebSearchQueryGeneration,
    WebResultSynthesis,
    InvestigationSynthesis,
)

class MetricsExtractionModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.extract = dspy.ChainOfThought(MetricsExtraction)

    def forward(self, document_text, company_name, document_type="corporate_announcement"):
        result = self.extract(
            document_text=document_text[:8000],  # Limit for token management
            company_name=company_name,
            document_type=document_type,
        )
        return result


class WebSearchModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.generate_queries = dspy.Predict(WebSearchQueryGeneration)
        self.synthesize_result = dspy.Predict(WebResultSynthesis)

    def forward(self, announcement_summary, company_name, sector, preliminary_findings):
        queries = self.generate_queries(
            announcement_summary=announcement_summary,
            company_name=company_name,
            sector=sector,
            preliminary_findings=preliminary_findings,
        )
        return queries


class SynthesisModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.synthesize = dspy.ChainOfThought(InvestigationSynthesis)

    def forward(self, company_name, sector, trigger_content, extracted_metrics,
                forward_statements, web_findings, market_data, historical_context):
        return self.synthesize(
            company_name=company_name,
            sector=sector,
            trigger_content=trigger_content,
            extracted_metrics=extracted_metrics,
            forward_statements=forward_statements,
            web_findings=web_findings,
            market_data=market_data,
            historical_context=historical_context,
        )


class DeepAnalysisPipeline(dspy.Module):
    """
    Complete Layer 3 reasoning pipeline.
    Composes: MetricsExtraction → WebSearch → Synthesis
    """
    def __init__(self):
        super().__init__()
        self.extract_metrics = MetricsExtractionModule()
        self.web_search = WebSearchModule()
        self.synthesize = SynthesisModule()

    def forward(self, document_text, company_name, sector, trigger_content,
                web_findings_text, market_data_text, historical_context_text):
        # Step 1: Extract metrics and statements
        metrics = self.extract_metrics(
            document_text=document_text,
            company_name=company_name,
        )

        # Step 2: Synthesize everything
        synthesis = self.synthesize(
            company_name=company_name,
            sector=sector,
            trigger_content=trigger_content,
            extracted_metrics=metrics.metrics_json,
            forward_statements=metrics.forward_statements_json,
            web_findings=web_findings_text,
            market_data=market_data_text,
            historical_context=historical_context_text,
        )

        return dspy.Prediction(
            metrics=metrics,
            synthesis=synthesis,
        )


# src/dspy_modules/decision.py
import dspy
from src.dspy_modules.signatures import DecisionEvaluation

class DecisionModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.evaluate = dspy.ChainOfThought(DecisionEvaluation)

    def forward(self, company_name, current_recommendation, current_recommendation_basis,
                investigation_synthesis, investigation_key_findings,
                past_investigations_summary, past_inconclusive_summary, market_data):
        return self.evaluate(
            company_name=company_name,
            current_recommendation=current_recommendation,
            current_recommendation_basis=current_recommendation_basis,
            investigation_synthesis=investigation_synthesis,
            investigation_key_findings=investigation_key_findings,
            past_investigations_summary=past_investigations_summary,
            past_inconclusive_summary=past_inconclusive_summary,
            market_data=market_data,
        )


# src/dspy_modules/report.py
import dspy
from src.dspy_modules.signatures import ReportGeneration

class ReportModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.generate = dspy.Predict(ReportGeneration)

    def forward(self, **kwargs):
        return self.generate(**kwargs)
```

---

## 4. Agent Tools

### 4.1 Web Search Tool

```python
# src/agents/tools/web_search.py
import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class WebSearchTool:
    """
    Web search tool for enriching investigations.
    Uses Brave Search API (or Tavily as alternative).

    Brave Search: https://api.search.brave.com/
    Tavily: https://tavily.com/
    """

    def __init__(self, api_key: str, provider: str = "brave"):
        self.api_key = api_key
        self.provider = provider
        self.session = httpx.AsyncClient(timeout=15.0)

    async def search(self, query: str, num_results: int = 5) -> list[dict]:
        """
        Execute a web search and return results.
        Returns: [{title, url, snippet}]
        """
        try:
            if self.provider == "brave":
                return await self._brave_search(query, num_results)
            elif self.provider == "tavily":
                return await self._tavily_search(query, num_results)
            else:
                raise ValueError(f"Unknown search provider: {self.provider}")
        except Exception as e:
            logger.error(f"Web search failed for '{query}': {e}")
            return []

    async def _brave_search(self, query: str, num_results: int) -> list[dict]:
        response = await self.session.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": num_results},
            headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"},
        )
        response.raise_for_status()
        data = response.json()
        results = []
        for item in data.get("web", {}).get("results", [])[:num_results]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
            })
        return results

    async def _tavily_search(self, query: str, num_results: int) -> list[dict]:
        response = await self.session.post(
            "https://api.tavily.com/search",
            json={
                "api_key": self.api_key,
                "query": query,
                "max_results": num_results,
                "search_depth": "basic",
            },
        )
        response.raise_for_status()
        data = response.json()
        results = []
        for item in data.get("results", [])[:num_results]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
            })
        return results
```

### 4.2 Market Data Tool

```python
# src/agents/tools/market_data.py
import logging
from typing import Optional
from datetime import datetime
from src.models.investigation import MarketDataSnapshot

logger = logging.getLogger(__name__)

class MarketDataTool:
    """
    Fetches market data for Indian stocks.

    Primary: yfinance (free, covers NSE/BSE)
    NSE symbols in yfinance use .NS suffix (e.g., "INOXWIND.NS")
    BSE symbols use .BO suffix (e.g., "INOXWIND.BO")

    Limitations of yfinance for Indian stocks:
    - FII/DII holding data is NOT available via yfinance
    - Promoter holding data is NOT available via yfinance
    - For these, we'll need to scrape NSE/BSE or use a paid API later

    For MVP, we get what yfinance gives us and fill in the rest as "None".
    """

    def __init__(self):
        # Import here to avoid slow startup
        pass

    async def get_snapshot(self, symbol: str) -> MarketDataSnapshot:
        """Get current market data for a company."""
        try:
            import yfinance as yf

            # Try NSE first, then BSE
            nse_symbol = f"{symbol}.NS"
            ticker = yf.Ticker(nse_symbol)
            info = ticker.info

            if not info or info.get("regularMarketPrice") is None:
                # Try BSE
                bse_symbol = f"{symbol}.BO"
                ticker = yf.Ticker(bse_symbol)
                info = ticker.info

            if not info or info.get("regularMarketPrice") is None:
                logger.warning(f"No market data found for {symbol}")
                return MarketDataSnapshot(data_source="yfinance_unavailable")

            snapshot = MarketDataSnapshot(
                current_price=info.get("regularMarketPrice") or info.get("currentPrice"),
                market_cap_cr=self._to_crores(info.get("marketCap")),
                pe_ratio=info.get("trailingPE"),
                pb_ratio=info.get("priceToBook"),
                week_52_high=info.get("fiftyTwoWeekHigh"),
                week_52_low=info.get("fiftyTwoWeekLow"),
                avg_volume_30d=info.get("averageVolume"),
                price_change_1d=info.get("regularMarketChangePercent"),
                sector_pe_avg=None,          # Not available in yfinance
                fii_holding_pct=None,        # Not available in yfinance
                dii_holding_pct=None,        # Not available in yfinance
                promoter_holding_pct=None,   # Not available in yfinance
                promoter_pledge_pct=None,    # Not available in yfinance
                data_source="yfinance",
                data_timestamp=datetime.utcnow(),
            )

            # Try to get price changes from history
            try:
                hist = ticker.history(period="1mo")
                if len(hist) > 0:
                    current = hist.iloc[-1]["Close"]
                    if len(hist) >= 5:
                        snapshot.price_change_1w = ((current / hist.iloc[-5]["Close"]) - 1) * 100
                    if len(hist) >= 20:
                        snapshot.price_change_1m = ((current / hist.iloc[0]["Close"]) - 1) * 100
            except Exception:
                pass

            return snapshot

        except Exception as e:
            logger.error(f"Market data fetch failed for {symbol}: {e}")
            return MarketDataSnapshot(data_source=f"error: {e}")

    def _to_crores(self, value: Optional[float]) -> Optional[float]:
        """Convert raw number (in local currency) to crores."""
        if value is None:
            return None
        return round(value / 10_000_000, 2)
```

---

## 5. Layer 3: Deep Analysis Implementation

```python
# src/pipeline/layer3_analysis/analyzer.py
import json
import time
import logging
import dspy

from src.models.trigger import TriggerEvent
from src.models.investigation import (
    Investigation, ExtractedMetric, ForwardStatement,
    WebSearchResult, HistoricalContext, SignificanceLevel,
)
from src.dspy_modules.analysis import DeepAnalysisPipeline, WebSearchModule
from src.dspy_modules.signatures import WebResultSynthesis
from src.agents.tools.web_search import WebSearchTool
from src.agents.tools.market_data import MarketDataTool
from src.repositories.base import (
    InvestigationRepository, VectorRepository, DocumentRepository
)

logger = logging.getLogger(__name__)

class DeepAnalyzer:
    """
    Layer 3: Deep Analysis.
    Takes a gate-passed trigger and produces a comprehensive Investigation.
    """

    def __init__(
        self,
        investigation_repo: InvestigationRepository,
        vector_repo: VectorRepository,
        doc_repo: DocumentRepository,
        web_search: WebSearchTool,
        market_data: MarketDataTool,
        analysis_model: str = "claude-sonnet",
    ):
        self.investigation_repo = investigation_repo
        self.vector_repo = vector_repo
        self.doc_repo = doc_repo
        self.web_search = web_search
        self.market_data = market_data
        self.lm = dspy.LM(f"anthropic/{analysis_model}")
        self.pipeline = DeepAnalysisPipeline()
        self.web_module = WebSearchModule()
        self.web_synth = dspy.Predict(WebResultSynthesis)

    async def analyze(self, trigger: TriggerEvent) -> Investigation:
        """Run full Layer 3 analysis on a trigger."""
        start_time = time.time()

        investigation = Investigation(
            trigger_id=trigger.trigger_id,
            company_symbol=trigger.company_symbol or "UNKNOWN",
            company_name=trigger.company_name or "Unknown Company",
        )

        with dspy.context(lm=self.lm):

            # Step 1: Get document text
            doc_text = trigger.raw_content
            if trigger.document_ids:
                docs = []
                for doc_id in trigger.document_ids:
                    doc = await self.doc_repo.get(doc_id)
                    if doc and doc.extracted_text:
                        docs.append(doc.extracted_text)
                if docs:
                    doc_text = "\n\n---\n\n".join(docs)

            # Step 2: Gather historical context
            historical = await self._gather_historical_context(
                trigger.company_symbol or ""
            )
            investigation.historical_context = historical

            # Step 3: Fetch market data
            if trigger.company_symbol:
                market_snapshot = await self.market_data.get_snapshot(trigger.company_symbol)
                investigation.market_data = market_snapshot

            # Step 4: Generate and execute web searches
            web_findings = await self._run_web_search(
                trigger, doc_text[:2000]
            )
            investigation.web_search_results = web_findings

            # Step 5: Run the DSPy analysis pipeline
            result = self.pipeline(
                document_text=doc_text,
                company_name=investigation.company_name,
                sector=trigger.sector or "Capital Goods - Electrical Equipment",
                trigger_content=trigger.raw_content[:2000],
                web_findings_text=self._format_web_findings(web_findings),
                market_data_text=self._format_market_data(investigation.market_data),
                historical_context_text=self._format_historical_context(historical),
            )

            # Step 6: Parse structured outputs
            investigation.extracted_metrics = self._parse_metrics(result.metrics.metrics_json)
            investigation.forward_statements = self._parse_forward_statements(result.metrics.forward_statements_json)
            investigation.management_highlights = self._parse_json_array(result.metrics.management_highlights)

            investigation.synthesis = result.synthesis.synthesis
            investigation.key_findings = self._parse_json_array(result.synthesis.key_findings)
            investigation.red_flags = self._parse_json_array(result.synthesis.red_flags)
            investigation.positive_signals = self._parse_json_array(result.synthesis.positive_signals)
            investigation.significance = SignificanceLevel(result.synthesis.significance)
            investigation.significance_reasoning = result.synthesis.significance_reasoning
            investigation.is_significant = result.synthesis.is_significant

        investigation.llm_model_used = "claude-sonnet"
        investigation.processing_time_seconds = time.time() - start_time

        # Save
        await self.investigation_repo.save(investigation)
        logger.info(
            f"Investigation complete: {investigation.company_symbol} "
            f"significance={investigation.significance.value} "
            f"({investigation.processing_time_seconds:.1f}s)"
        )

        return investigation

    async def _gather_historical_context(self, company_symbol: str) -> HistoricalContext:
        """Pull all relevant historical data for context."""
        context = HistoricalContext()

        if not company_symbol:
            return context

        # Past investigations
        past = await self.investigation_repo.get_by_company(company_symbol, limit=10)
        context.total_past_investigations = len(past)
        context.past_investigations = [
            {
                "investigation_id": inv.investigation_id,
                "date": inv.created_at.isoformat(),
                "significance": inv.significance.value,
                "key_findings": inv.key_findings[:3],
                "synthesis_summary": inv.synthesis[:500],
            }
            for inv in past
        ]

        # Past inconclusive (significant but didn't change recommendation)
        inconclusive = await self.investigation_repo.get_past_inconclusive(company_symbol)
        context.past_investigations.extend([
            {
                "investigation_id": inv.investigation_id,
                "date": inv.created_at.isoformat(),
                "significance": inv.significance.value,
                "key_findings": inv.key_findings[:3],
                "synthesis_summary": inv.synthesis[:500],
                "was_inconclusive": True,
            }
            for inv in inconclusive
        ])

        # Vector search for similar content
        similar = await self.vector_repo.search(
            query=company_symbol,
            n_results=5,
            where={"company_symbol": company_symbol} if company_symbol else None,
        )
        context.similar_documents = similar

        return context

    async def _run_web_search(self, trigger: TriggerEvent, doc_summary: str) -> list[WebSearchResult]:
        """Generate search queries and execute them."""
        results = []

        with dspy.context(lm=self.lm):
            # Generate search queries
            queries_result = self.web_module(
                announcement_summary=doc_summary,
                company_name=trigger.company_name or "Unknown",
                sector=trigger.sector or "Unknown",
                preliminary_findings="Initial analysis in progress",
            )

            queries = self._parse_json_array(queries_result.search_queries)[:4]  # Max 4 searches

        for query in queries:
            raw_results = await self.web_search.search(query, num_results=3)
            if raw_results:
                # Combine snippets for synthesis
                combined_text = "\n".join([
                    f"- {r['title']}: {r['snippet']}" for r in raw_results
                ])

                with dspy.context(lm=self.lm):
                    synth = self.web_synth(
                        company_name=trigger.company_name or "Unknown",
                        search_query=query,
                        search_results_text=combined_text,
                    )

                results.append(WebSearchResult(
                    query=query,
                    source=raw_results[0]["url"] if raw_results else "",
                    title=raw_results[0]["title"] if raw_results else "",
                    summary=synth.summary,
                    relevance=synth.relevance,
                    sentiment=synth.sentiment,
                ))

        return results

    # --- Formatting helpers ---

    def _format_web_findings(self, findings: list[WebSearchResult]) -> str:
        if not findings:
            return "No web search results available."
        parts = []
        for f in findings:
            parts.append(f"[{f.relevance.upper()}] {f.query}: {f.summary} (Sentiment: {f.sentiment})")
        return "\n".join(parts)

    def _format_market_data(self, data) -> str:
        if not data:
            return "Market data not available."
        parts = []
        if data.current_price: parts.append(f"Price: ₹{data.current_price}")
        if data.market_cap_cr: parts.append(f"Market Cap: ₹{data.market_cap_cr} Cr")
        if data.pe_ratio: parts.append(f"P/E: {data.pe_ratio:.1f}")
        if data.pb_ratio: parts.append(f"P/B: {data.pb_ratio:.1f}")
        if data.week_52_high: parts.append(f"52W High: ₹{data.week_52_high}")
        if data.week_52_low: parts.append(f"52W Low: ₹{data.week_52_low}")
        if data.price_change_1w: parts.append(f"1W Change: {data.price_change_1w:.1f}%")
        if data.price_change_1m: parts.append(f"1M Change: {data.price_change_1m:.1f}%")
        if data.promoter_holding_pct: parts.append(f"Promoter: {data.promoter_holding_pct:.1f}%")
        if data.fii_holding_pct: parts.append(f"FII: {data.fii_holding_pct:.1f}%")
        return " | ".join(parts) if parts else "Market data limited."

    def _format_historical_context(self, ctx: HistoricalContext) -> str:
        if not ctx or ctx.total_past_investigations == 0:
            return "No historical context available. This is the first investigation for this company."
        parts = [f"Total past investigations: {ctx.total_past_investigations}"]
        for inv in ctx.past_investigations[:5]:
            was_inconcl = " [PREVIOUSLY INCONCLUSIVE]" if inv.get("was_inconclusive") else ""
            parts.append(
                f"- {inv['date']}: Significance={inv['significance']}{was_inconcl}. "
                f"Findings: {', '.join(inv.get('key_findings', []))}"
            )
        return "\n".join(parts)

    # --- JSON parsing helpers ---

    def _parse_json_array(self, text: str) -> list:
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, list) else [str(parsed)]
        except (json.JSONDecodeError, TypeError):
            # DSPy might return a plain string; wrap it
            if isinstance(text, str) and text.strip():
                return [text.strip()]
            return []

    def _parse_metrics(self, text: str) -> list[ExtractedMetric]:
        try:
            data = json.loads(text)
            return [ExtractedMetric(**m) for m in data if isinstance(m, dict)]
        except Exception:
            return []

    def _parse_forward_statements(self, text: str) -> list[ForwardStatement]:
        try:
            data = json.loads(text)
            return [ForwardStatement(**s) for s in data if isinstance(s, dict)]
        except Exception:
            return []
```

---

## 6. Layer 4: Decision Assessment Implementation

```python
# src/pipeline/layer4_decision/assessor.py
import json
import time
import logging
import dspy

from src.models.investigation import Investigation
from src.models.decision import (
    DecisionAssessment, Recommendation, RecommendationTimeframe
)
from src.models.company import CompanyPosition
from src.dspy_modules.decision import DecisionModule
from src.repositories.base import (
    AssessmentRepository, InvestigationRepository, PositionRepository
)

logger = logging.getLogger(__name__)

class DecisionAssessor:
    """
    Layer 4: Decision Assessment.
    Determines whether an investigation warrants a recommendation change.
    """

    def __init__(
        self,
        assessment_repo: AssessmentRepository,
        investigation_repo: InvestigationRepository,
        position_repo: PositionRepository,
        decision_model: str = "claude-sonnet",
    ):
        self.assessment_repo = assessment_repo
        self.investigation_repo = investigation_repo
        self.position_repo = position_repo
        self.lm = dspy.LM(f"anthropic/{decision_model}")
        self.decision_module = DecisionModule()

    async def assess(self, investigation: Investigation) -> DecisionAssessment:
        """Run Layer 4 decision assessment."""
        start_time = time.time()

        # Get current position
        position = await self.position_repo.get_position(investigation.company_symbol)

        # Get past investigations (including inconclusive ones)
        past_investigations = await self.investigation_repo.get_by_company(
            investigation.company_symbol, limit=15
        )
        past_inconclusive = await self.investigation_repo.get_past_inconclusive(
            investigation.company_symbol
        )

        # Build assessment
        assessment = DecisionAssessment(
            investigation_id=investigation.investigation_id,
            trigger_id=investigation.trigger_id,
            company_symbol=investigation.company_symbol,
            company_name=investigation.company_name,
            previous_recommendation=position.current_recommendation if position else Recommendation.NONE,
            previous_recommendation_date=position.recommendation_date if position else None,
            previous_recommendation_basis=position.recommendation_basis if position else "",
        )

        with dspy.context(lm=self.lm):
            result = self.decision_module(
                company_name=investigation.company_name,
                current_recommendation=(position.current_recommendation.value if position else "none"),
                current_recommendation_basis=(position.recommendation_basis if position else "No prior recommendation"),
                investigation_synthesis=investigation.synthesis,
                investigation_key_findings=json.dumps(investigation.key_findings),
                past_investigations_summary=self._format_past_investigations(past_investigations),
                past_inconclusive_summary=self._format_past_investigations(past_inconclusive, label="inconclusive"),
                market_data=self._format_market_data(investigation.market_data),
            )

        assessment.recommendation_changed = result.should_change
        assessment.new_recommendation = Recommendation(result.new_recommendation)
        assessment.timeframe = RecommendationTimeframe(result.timeframe)
        assessment.confidence = min(max(result.confidence, 0.0), 1.0)
        assessment.reasoning = result.reasoning
        assessment.key_factors_for = self._parse_json_array(result.key_factors_for)
        assessment.key_factors_against = self._parse_json_array(result.key_factors_against)
        assessment.risks = assessment.key_factors_against  # Alias for now
        assessment.past_investigations_used = [inv.investigation_id for inv in past_investigations[:5]]
        assessment.past_inconclusive_resurrected = self._parse_json_array(result.past_investigations_that_contributed)

        assessment.llm_model_used = "claude-sonnet"
        assessment.processing_time_seconds = time.time() - start_time

        # Save assessment
        await self.assessment_repo.save(assessment)

        # Update company position if recommendation changed
        if assessment.recommendation_changed:
            await self._update_position(investigation, assessment, position)

        logger.info(
            f"Decision assessment: {investigation.company_symbol} "
            f"changed={assessment.recommendation_changed} "
            f"rec={assessment.new_recommendation.value} "
            f"conf={assessment.confidence:.2f}"
        )

        return assessment

    async def _update_position(
        self, investigation: Investigation,
        assessment: DecisionAssessment,
        existing_position: CompanyPosition | None
    ):
        """Update the company's position record."""
        position = existing_position or CompanyPosition(
            company_symbol=investigation.company_symbol,
            company_name=investigation.company_name,
        )

        # Add current to history before updating
        if position.current_recommendation != Recommendation.NONE:
            position.recommendation_history.append({
                "recommendation": position.current_recommendation.value,
                "date": position.recommendation_date.isoformat() if position.recommendation_date else None,
                "assessment_id": position.recommendation_assessment_id,
            })

        position.current_recommendation = assessment.new_recommendation
        position.recommendation_date = assessment.created_at
        position.recommendation_basis = assessment.reasoning[:500]
        position.recommendation_assessment_id = assessment.assessment_id
        position.total_investigations = (position.total_investigations or 0) + 1
        position.last_investigation_date = assessment.created_at

        await self.position_repo.upsert_position(position)

    def _format_past_investigations(self, investigations: list[Investigation], label: str = "") -> str:
        if not investigations:
            return f"No past {label} investigations." if label else "No past investigations."
        parts = []
        for inv in investigations[:10]:
            parts.append(
                f"- [{inv.created_at.strftime('%Y-%m-%d')}] "
                f"Significance: {inv.significance.value}. "
                f"Findings: {'; '.join(inv.key_findings[:3])}"
            )
        return "\n".join(parts)

    def _format_market_data(self, data) -> str:
        if not data:
            return "Market data not available."
        parts = []
        if data.current_price: parts.append(f"Price: ₹{data.current_price}")
        if data.pe_ratio: parts.append(f"P/E: {data.pe_ratio:.1f}")
        if data.market_cap_cr: parts.append(f"MCap: ₹{data.market_cap_cr} Cr")
        return " | ".join(parts) if parts else "Limited market data."

    def _parse_json_array(self, text) -> list:
        try:
            parsed = json.loads(text) if isinstance(text, str) else text
            return parsed if isinstance(parsed, list) else [str(parsed)]
        except (json.JSONDecodeError, TypeError):
            return [str(text)] if text else []
```

---

## 7. Layer 5: Report Generation + Delivery

```python
# src/pipeline/layer5_report/generator.py
import time
import logging
import dspy

from src.models.investigation import Investigation
from src.models.decision import DecisionAssessment
from src.models.report import AnalysisReport, ReportDeliveryStatus
from src.dspy_modules.report import ReportModule
from src.repositories.base import ReportRepository
import json

logger = logging.getLogger(__name__)

class ReportGenerator:
    """Layer 5: Generate and deliver human-readable reports."""

    def __init__(
        self,
        report_repo: ReportRepository,
        analysis_model: str = "claude-sonnet",
    ):
        self.report_repo = report_repo
        self.lm = dspy.LM(f"anthropic/{analysis_model}")
        self.report_module = ReportModule()

    async def generate(
        self,
        investigation: Investigation,
        assessment: DecisionAssessment,
        trigger_summary: str,
    ) -> AnalysisReport:
        """Generate a complete analysis report."""

        with dspy.context(lm=self.lm):
            result = self.report_module(
                company_name=investigation.company_name,
                company_symbol=investigation.company_symbol,
                trigger_summary=trigger_summary,
                investigation_synthesis=investigation.synthesis,
                key_findings=json.dumps(investigation.key_findings),
                red_flags=json.dumps(investigation.red_flags),
                positive_signals=json.dumps(investigation.positive_signals),
                market_data=self._format_market_data(investigation.market_data),
                historical_context=self._format_context(investigation.historical_context),
                recommendation=assessment.new_recommendation.value,
                recommendation_reasoning=assessment.reasoning,
                confidence=assessment.confidence,
                risks=json.dumps(assessment.risks),
            )

        report = AnalysisReport(
            assessment_id=assessment.assessment_id,
            investigation_id=investigation.investigation_id,
            trigger_id=investigation.trigger_id,
            company_symbol=investigation.company_symbol,
            company_name=investigation.company_name,
            title=result.report_title,
            executive_summary=result.executive_summary,
            report_body=result.report_body,
            recommendation_summary=(
                f"{assessment.new_recommendation.value.upper()} "
                f"(Confidence: {assessment.confidence:.0%}, "
                f"Timeframe: {assessment.timeframe.value})"
            ),
        )

        await self.report_repo.save(report)
        logger.info(f"Report generated: {report.report_id} for {investigation.company_symbol}")
        return report

    def _format_market_data(self, data) -> str:
        if not data: return "N/A"
        parts = []
        if data.current_price: parts.append(f"Price: ₹{data.current_price}")
        if data.pe_ratio: parts.append(f"P/E: {data.pe_ratio:.1f}")
        if data.market_cap_cr: parts.append(f"MCap: ₹{data.market_cap_cr} Cr")
        if data.week_52_high: parts.append(f"52W H/L: ₹{data.week_52_high}/₹{data.week_52_low}")
        return " | ".join(parts) if parts else "N/A"

    def _format_context(self, ctx) -> str:
        if not ctx: return "First investigation for this company."
        return f"{ctx.total_past_investigations} past investigations. " + \
               "; ".join([inv.get("synthesis_summary", "")[:200] for inv in (ctx.past_investigations or [])[:3]])


# src/pipeline/layer5_report/deliverer.py
import httpx
import logging
from src.models.report import AnalysisReport, ReportDeliveryStatus

logger = logging.getLogger(__name__)

class ReportDeliverer:
    """Delivers reports via Slack and/or email."""

    def __init__(self, slack_webhook_url: str = "", smtp_config: dict = None):
        self.slack_webhook = slack_webhook_url
        self.smtp_config = smtp_config or {}

    async def deliver(self, report: AnalysisReport) -> list[str]:
        """Deliver report through configured channels. Returns list of channels used."""
        channels = []

        if self.slack_webhook:
            success = await self._deliver_slack(report)
            if success:
                channels.append("slack")

        # Email delivery (implement when needed)
        # if self.smtp_config:
        #     success = await self._deliver_email(report)
        #     if success: channels.append("email")

        return channels

    async def _deliver_slack(self, report: AnalysisReport) -> bool:
        """Send report summary to Slack via webhook."""
        try:
            # Compose Slack message
            emoji = {"buy": "🟢", "sell": "🔴", "hold": "🟡"}.get(
                report.recommendation_summary.split()[0].lower(), "⚪"
            )

            message = {
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": f"{emoji} {report.title}"}
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*{report.recommendation_summary}*"}
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": report.executive_summary}
                    },
                    {"type": "divider"},
                    {
                        "type": "context",
                        "elements": [
                            {"type": "mrkdwn", "text": f"Report ID: `{report.report_id}` | View full report in dashboard"}
                        ]
                    }
                ]
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(self.slack_webhook, json=message)
                response.raise_for_status()

            logger.info(f"Slack delivery successful: {report.report_id}")
            return True

        except Exception as e:
            logger.error(f"Slack delivery failed: {e}")
            return False
```

---

## 8. Updated Pipeline Orchestrator

```python
# src/pipeline/orchestrator.py (Week 3-4 additions)

async def process_trigger(self, trigger: TriggerEvent) -> None:
    """Process a single trigger through the complete pipeline."""

    # --- Layer 1: Document Ingestion (from Weeks 1-2) ---
    # [existing code unchanged]

    # --- Layer 2: Gate (from Weeks 1-2) ---
    # [existing code unchanged]

    # --- Layer 3: Deep Analysis ---
    await self.trigger_repo.update_status(
        trigger.trigger_id, TriggerStatus.ANALYZING, "Starting deep analysis"
    )

    investigation = await self.deep_analyzer.analyze(trigger)

    await self.trigger_repo.update_status(
        trigger.trigger_id, TriggerStatus.ANALYZED,
        f"Analysis complete. Significance: {investigation.significance.value}"
    )

    if not investigation.is_significant:
        logger.info(f"Investigation not significant enough for decision assessment: {trigger.trigger_id}")
        return

    # --- Layer 4: Decision Assessment ---
    await self.trigger_repo.update_status(
        trigger.trigger_id, TriggerStatus.ASSESSING, "Running decision assessment"
    )

    assessment = await self.decision_assessor.assess(investigation)

    await self.trigger_repo.update_status(
        trigger.trigger_id, TriggerStatus.ASSESSED,
        f"Assessment complete. Changed: {assessment.recommendation_changed}, "
        f"Rec: {assessment.new_recommendation.value}"
    )

    # --- Layer 5: Report Generation ---
    report = await self.report_generator.generate(
        investigation=investigation,
        assessment=assessment,
        trigger_summary=trigger.raw_content[:500],
    )

    # Deliver report
    channels = await self.report_deliverer.deliver(report)
    report.delivered_via = channels
    report.delivery_status = ReportDeliveryStatus.DELIVERED if channels else ReportDeliveryStatus.DELIVERY_FAILED

    await self.trigger_repo.update_status(
        trigger.trigger_id, TriggerStatus.REPORTED,
        f"Report delivered via {', '.join(channels) or 'none'}"
    )

    logger.info(
        f"Pipeline complete: {trigger.trigger_id} → "
        f"{investigation.significance.value} → "
        f"{assessment.new_recommendation.value} ({assessment.confidence:.0%}) → "
        f"Report {report.report_id}"
    )
```

---

## 9. New API Endpoints (Weeks 3-4)

```python
# src/api/investigations.py
from fastapi import APIRouter, HTTPException
router = APIRouter(prefix="/api/v1/investigations", tags=["investigations"])

@router.get("/{investigation_id}")
async def get_investigation(investigation_id: str): ...

@router.get("/company/{company_symbol}")
async def get_company_investigations(company_symbol: str, limit: int = 20): ...


# src/api/reports.py
from fastapi import APIRouter
router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

@router.get("/")
async def list_reports(limit: int = 20): ...

@router.get("/{report_id}")
async def get_report(report_id: str): ...

@router.post("/{report_id}/feedback")
async def submit_feedback(report_id: str, rating: int, comment: str = "", by: str = ""): ...


# src/api/positions.py
from fastapi import APIRouter
router = APIRouter(prefix="/api/v1/positions", tags=["positions"])

@router.get("/")
async def list_positions(): ...
# Returns all companies and their current buy/sell/hold recommendation

@router.get("/{company_symbol}")
async def get_position(company_symbol: str): ...
# Returns full position with recommendation history
```

---

## 10. New Dependencies

```toml
# Add to pyproject.toml dependencies
"yfinance>=0.2.36",         # Market data
```

---

## 11. Task Breakdown for Team

### Week 3 Tasks

| # | Task | Effort | Dependencies | Owner |
|---|------|--------|-------------|-------|
| 3.1 | Investigation, DecisionAssessment, CompanyPosition, AnalysisReport data models | 1 day | Week 2 done | Dev A |
| 3.2 | New repository interfaces + MongoDB implementations (investigation, assessment, position, report) | 1 day | 3.1 | Dev A |
| 3.3 | WebSearchTool (Brave/Tavily integration) | 0.5 day | None | Dev B |
| 3.4 | MarketDataTool (yfinance wrapper) | 0.5 day | None | Dev B |
| 3.5 | DSPy signatures: MetricsExtraction, WebSearchQueryGeneration, WebResultSynthesis, InvestigationSynthesis | 1 day | None | Dev B |
| 3.6 | DSPy modules: MetricsExtractionModule, WebSearchModule, SynthesisModule, DeepAnalysisPipeline | 1 day | 3.5 | Dev B |
| 3.7 | DeepAnalyzer implementation (Layer 3 orchestration) | 1.5 days | 3.2, 3.3, 3.4, 3.6 | Dev A |
| 3.8 | Test Layer 3 with real NSE data (INOXWIND quarterly results) | 1 day | 3.7 | Both |
| 3.9 | Prompt engineering iteration (review outputs, refine DSPy signatures) | 0.5 day | 3.8 | Both |

**Week 3 deliverable**: Gate-passed triggers produce detailed investigations with extracted metrics, web search context, market data, and LLM synthesis. Team can review investigation quality.

### Week 4 Tasks

| # | Task | Effort | Dependencies | Owner |
|---|------|--------|-------------|-------|
| 4.1 | DSPy signatures: DecisionEvaluation, ReportGeneration | 0.5 day | 3.5 | Dev B |
| 4.2 | DecisionModule + DecisionAssessor implementation | 1 day | 3.2, 4.1 | Dev B |
| 4.3 | ReportModule + ReportGenerator implementation | 1 day | 4.1 | Dev A |
| 4.4 | ReportDeliverer (Slack webhook + optional email) | 0.5 day | None | Dev A |
| 4.5 | Update PipelineOrchestrator to wire Layers 3-5 together | 0.5 day | 4.2, 4.3, 4.4 | Dev A |
| 4.6 | API endpoints: investigations, reports, positions, feedback | 1 day | 3.2 | Dev B |
| 4.7 | End-to-end pipeline test with real data | 1 day | 4.5 | Both |
| 4.8 | Prompt refinement for decision + report quality | 0.5 day | 4.7 | Both |
| 4.9 | Test feedback collection (thumbs up/down via API) | 0.5 day | 4.6 | Dev A |
| 4.10 | Error handling, retry logic, graceful degradation for LLM failures | 0.5 day | 4.5 | Dev B |
| 4.11 | Logging: structured logs for full pipeline traceability (trigger_id → report_id) | 0.5 day | 4.5 | Dev B |

**Week 4 deliverable**: Complete end-to-end pipeline. A trigger comes in, gets analyzed, produces a decision, generates a report, and delivers it via Slack. Feedback can be captured via API.

---

## 12. Testing Strategy (Weeks 3-4)

### Test Fixtures Needed

1. **Real investigation data**: Run Layer 3 against 3-5 real INOXWIND/SUZLON quarterly result PDFs. Save the LLM outputs as golden test fixtures.
2. **Mock web search results**: Save real Brave/Tavily API responses for common queries.
3. **Mock market data**: Save yfinance snapshots for test companies.

### Key Test Cases

| Test | What It Validates |
|------|------------------|
| DeepAnalyzer with a real quarterly report PDF | Metrics extraction accuracy, synthesis quality |
| DeepAnalyzer with no historical context (new company) | Handles first-time analysis gracefully |
| DecisionAssessor with no prior recommendation | Creates initial recommendation |
| DecisionAssessor with existing recommendation + confirming evidence | Maintains recommendation with updated basis |
| DecisionAssessor with contradicting evidence | Changes recommendation |
| DecisionAssessor with inconclusive past + new evidence | Resurrects past investigations |
| ReportGenerator output quality | Report is well-structured markdown |
| Full pipeline end-to-end | Trigger → Report without errors |
| LLM failure in Layer 3 | Graceful error, trigger status shows error |
| Web search failure | Analysis continues without web results |

### DSPy Evaluation Setup

After Week 4, you'll have enough real data to start DSPy optimization:

```python
# scripts/evaluate_gate.py
import dspy

# Collect from team feedback
gate_examples = [
    dspy.Example(
        announcement_text="Board meeting outcome - approved quarterly results...",
        company_name="Inox Wind",
        sector="Capital Goods - Electrical Equipment",
        is_worth_investigating=True,
        reason="Quarterly results with financial data"
    ).with_inputs("announcement_text", "company_name", "sector"),
    # ... more examples from team feedback
]

# Evaluate current gate performance
evaluate = dspy.Evaluate(devset=gate_examples, metric=gate_accuracy)
score = evaluate(GateModule())
print(f"Gate accuracy: {score}")

# Optimize if enough examples (20+)
if len(gate_examples) >= 20:
    optimizer = dspy.BootstrapFewShot(metric=gate_accuracy, max_bootstrapped_demos=4)
    optimized_gate = optimizer.compile(GateModule(), trainset=gate_examples)
    optimized_score = evaluate(optimized_gate)
    print(f"Optimized gate accuracy: {optimized_score}")
```

---

## 13. Key Risks for Weeks 3-4

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM outputs don't parse as valid JSON | Breaks metric extraction pipeline | Use DSPy's structured output; add try/except with fallback to raw text parsing |
| Web search API returns irrelevant results | Wasted tokens on synthesis of garbage | Use the WebResultSynthesis step to filter; set relevance threshold |
| yfinance doesn't cover all NSE stocks | Missing market data for some companies | Fail gracefully (return None fields); log which companies are missing |
| LLM hallucinates financial metrics | Incorrect analysis | Always show extracted metrics alongside source text; include confidence scores; human review |
| Cost overruns from too many LLM calls | Budget exceeded | Monitor token usage per investigation; set daily budget alerts; cache repeated queries |
| DSPy version compatibility with Claude | Framework issues | Pin exact versions; test in Docker; have fallback to raw Anthropic SDK if needed |
