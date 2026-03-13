# Platform Integration Analysis: tuJanalyst x StockPulse (tuJanChart)

## Purpose

This document is a product-level analysis of how the two TuJan platform components — **tuJanalyst** (AI-powered news analysis) and **StockPulse/tuJanChart** (technical screening) — can integrate to create a system greater than the sum of its parts. It covers all identified integration surfaces, data flows, new capabilities unlocked by combining the two, and a view on what the unified platform could become.

---

## Current State Summary

### tuJanalyst — "The Fundamental Brain"
An AI-driven pipeline that monitors NSE/BSE announcements, runs them through a 5-layer agentic pipeline (Trigger → Gate → Deep Analysis → Decision → Report), and produces buy/sell/hold recommendations. Currently covers 32 companies in the Capital Goods - Electrical Equipment sector.

**What it knows well:**
- Corporate announcements and press releases
- Extracted financial metrics (revenue, EBITDA, PAT, order books, margins)
- Management forward guidance and promises
- Web-sourced validation and sentiment
- Historical investigation context per company
- Recommendation state and history per company

**What it lacks:**
- Rich technical/price data (only has basic yfinance snapshot: price, PE, market cap, 52W high/low)
- No awareness of DMA/WMA signals, volume breakouts, gaps, screener membership
- No technical event history (52W highs, crossovers, breakouts)
- No view of how the broader universe of 1,600+ stocks is behaving
- No analyst color classifications or technical notes
- No chart or visual context

### StockPulse (tuJanChart) — "The Technical Eye"
A technical screening platform that computes 40+ indicators daily for ~1,633 Indian equities, runs 79+ screeners, detects 12 types of technical events, and exposes everything via REST API and webhooks.

**What it knows well:**
- Daily price action (OHLCV) with 1+ year history
- Moving average signals (5 DMAs, 4 WMAs) with touch/hold/reverse detection
- 52-week high tracking (intraday and closing)
- Volume analytics (21d max, 140d/280d averages, breakout detection)
- Gap-up/gap-down detection
- 90-day extremes
- Result date proximity (7d/10d/15d windows)
- Biweekly and weekly breakout patterns
- 79 screeners combining these signals in meaningful ways
- Color classifications (fund member annotations: Pink/Yellow/Orange/Blue/Red/Green)
- Corporate action data (board meetings, result dates, ASM stages, circuit bands)

**What it lacks:**
- No understanding of what announcements mean
- No ability to analyze press releases, quarterly results, or earnings calls
- No recommendation engine
- No web search or external validation
- No AI-powered reasoning about cause and effect
- No forward guidance tracking

---

## Integration Thesis

These two systems are complementary halves of the same investment analysis process. StockPulse sees the **price action** — what the market is doing. tuJanalyst understands the **narrative** — why the market might move. Combining them creates a platform where:

1. Technical signals provide context for fundamental analysis ("this stock is already showing strength")
2. Fundamental analysis explains technical signals ("this breakout happened because of strong results")
3. The gate becomes smarter (technical strength + announcement = higher priority)
4. Decisions become more informed (fundamentals + technicals = higher confidence)
5. Reports become more complete (narrative + price context = actionable)
6. New trigger sources emerge (technical events can initiate fundamental analysis)

---

## Integration Opportunities

### 1. Technical Data as Agent Context (High Impact, Low Effort)

**The problem:** When tuJanalyst's Layer 3 (Deep Analysis) runs, it fetches a basic yfinance snapshot — price, PE, market cap, 52W high/low. This is a fraction of what's available.

**The opportunity:** Replace or augment the `MarketDataTool` with a `StockPulseDataTool` that queries StockPulse's API. The analyst agents would then have access to:

| Data Point | Current (yfinance) | With StockPulse |
|---|---|---|
| Price | Current price only | Full OHLCV + historical |
| Moving Averages | None | 5 DMAs + 4 WMAs with hold/reverse signals |
| Trend Signals | None | DMA touch detection, crossover events |
| 52W Context | Just high/low numbers | Is at 52W high today? Yesterday? Date achieved? |
| Volume | 30d average only | 21d max, 140d/280d avg, breakout flag |
| Gaps | None | Gap-up/down percentage and flag |
| 90D Extremes | None | At 90D high or low? |
| Result Proximity | None | Days to next result, within 7/10/15d windows |
| Breakout Status | None | Biweekly and weekly breakout flags |
| Fund Classification | None | Color tag (Pink=portfolio, Orange=post-result breakout, etc.) |
| Fund Notes | None | Historical technical annotations |
| Screener Membership | None | Which of 79 screeners the stock currently appears in |
| Recent Events | None | Last N technical events (crossovers, breakouts, etc.) |

**Why this matters for analysis quality:**

Consider an analyst agent processing a quarterly results announcement for INOXWIND:
- **Today:** Agent sees "current_price: 550, pe: 25, market_cap: 8000 Cr"
- **With StockPulse:** Agent sees "stock is at 52W closing high, DMA-10 Hold signal, volume breakout detected, classified Orange (post-result breakout pattern), appears in 6 screeners including '52W High + Volume Breakout + Gap Up', 3 DMA crossover events in last 5 days"

The second scenario gives the agent enormously richer context to assess whether this announcement is accelerating an existing trend or represents a new development.

---

### 2. Smarter Gate with Technical Context (High Impact, Medium Effort)

**The problem:** The Layer 2 gate currently uses keyword matching + a cheap LLM call to decide "is this worth investigating?" It has no awareness of the stock's technical state.

**The opportunity:** Before the LLM gate call, query StockPulse for the company's current state. Add technical context to the gate prompt:

**Current gate input:**
```
announcement_text: "Board meeting on 15th March to consider quarterly results"
company_name: "Inox Wind Limited"
sector: "Capital Goods - Electrical Equipment"
```

**Enhanced gate input:**
```
announcement_text: "Board meeting on 15th March to consider quarterly results"
company_name: "Inox Wind Limited"
sector: "Capital Goods - Electrical Equipment"
technical_context: "Stock at 52W closing high. DMA-10 and DMA-20 Hold signals active.
  Volume breakout detected. Classified Orange (post-result breakout pattern).
  Result date in 2 days. Currently in 8 active screeners."
```

**Impact on gate decisions:**
- "Board meeting to consider quarterly results" for a stock at 52W high with volume breakout → almost certainly worth investigating (pass)
- Same announcement for a stock at 90D low with no volume → less likely to move the needle (might still pass, but lower priority)
- "Routine compliance filing" for a stock showing massive gap-up → investigate anyway, something is happening

This converts the gate from a **content-only filter** to a **content + context filter**. The gate can now assess not just "is this news important?" but "is this news important for a stock that is already showing X pattern?"

---

### 3. Technical Events as Trigger Sources (High Impact, Medium Effort)

**The problem:** tuJanalyst triggers only from RSS feeds and human input. StockPulse detects 12 types of technical events (52W highs, DMA crossovers, volume breakouts, gaps) every day but has no way to initiate fundamental analysis.

**The opportunity:** StockPulse's webhook system can fire events to tuJanalyst's trigger endpoint. This creates a new class of triggers: **technically-triggered fundamental investigations**.

**Event types that should trigger investigations:**

| StockPulse Event | Investigation Rationale |
|---|---|
| 52W_HIGH_CLOSING + VOLUME_BREAKOUT | Stock making new highs on high volume — what's driving it? |
| GAP_UP > 5% | Sudden large move — search for unreported news |
| DMA_200 crossover (Hold) | Major trend change — review fundamental thesis |
| Multiple DMA crossovers in one day | Technical breakout pattern — validate with fundamentals |
| SCREENER_ENTRY on "52W High + Volume + Gap Up" | Compound signal — high probability of material event |

**How this works:**
1. StockPulse detects event → fires webhook
2. tuJanalyst receives webhook as a new trigger (source: `TECHNICAL_EVENT`)
3. Trigger includes the event payload (what technical signal fired, current indicators)
4. Gate can be configured to auto-pass certain compound technical events
5. Layer 3 deep analysis runs with full technical context already attached
6. Web search queries are informed by the technical event ("why is INOXWIND at 52-week high?")
7. Layer 4 decision has both the fundamental findings and the technical state

**New trigger types this enables:**
- **Unusual Activity Triggers**: Volume breakout with no corresponding news → agent searches for unreported developments
- **Trend Reversal Triggers**: DMA-200 crossover → agent reviews if fundamental thesis still holds
- **Compound Signal Triggers**: Multiple technical events firing simultaneously → high-priority investigation
- **Sector Sweep Triggers**: Multiple stocks in same sector showing breakouts → sector-level investigation

This directly addresses the North Star Vision's "Iteration 1" goal of "Unusual market activity detection (price/volume anomalies)" — StockPulse already detects these; we just need to bridge them.

---

### 4. Analysis Results Flowing Back to StockPulse (Medium Impact, Low Effort)

**The problem:** StockPulse has a notes system and color classification, but these are updated only by human fund members. The analyst agents produce rich analysis that lives only in MongoDB.

**The opportunity:** After tuJanalyst completes an analysis, push results back to StockPulse:

**Notes integration:**
- When Layer 5 generates a report → POST executive summary as a note on the stock's StockPulse page
- Author type: "agent" (StockPulse already supports this)
- Fund members see AI analysis alongside their own technical notes on the same stock page
- Creates a unified timeline of technical observations + fundamental analysis

**Color classification suggestions:**
- When Layer 4 produces a "buy" with high confidence → suggest Orange or Yellow classification
- When Layer 4 produces a "sell" or flags red flags → suggest Red classification
- "Blue" for good quarterly results, "Red" for bad — these are exactly what tuJanalyst detects
- Note: don't auto-update colors (humans own this) but surface recommendations prominently

**Event creation:**
- tuJanalyst can create custom events in StockPulse when it produces a recommendation change
- Event type: `AI_RECOMMENDATION_CHANGE`
- Payload: recommendation, confidence, key factors
- These events appear in StockPulse's event feed and can trigger StockPulse webhooks to other systems

---

### 5. Unified Dashboard (Medium Impact, High Effort)

**The problem:** StockPulse has a production-quality web dashboard (Flask + HTMX + Alpine.js). tuJanalyst has a Streamlit MVP dashboard being extracted to a separate app (ADR-006). Two separate UIs for one team is fragmented.

**The opportunity:** Use StockPulse as the unified frontend, extending it to display tuJanalyst data:

**Stock Detail Page enrichment:**
- Current: technical indicators, price data, color, notes, events
- Added: latest AI investigation summary, recommendation (buy/sell/hold badge), confidence score, key findings, red flags, link to full report
- Added: recommendation history timeline (when did AI change its view?)
- Added: investigation count and last analysis date

**New Dashboard Cards:**
- "AI Recommendations" card: count of active buy/sell/hold positions from tuJanalyst
- "Recent Reports" card: latest AI-generated reports with executive summaries
- "Pending Analysis" card: triggers currently being processed

**New Pages:**
- AI Reports list: browse all generated reports, filter by company/recommendation/date
- Recommendation tracker: all current AI positions with confidence and age
- Investigation feed: stream of AI investigations with significance ratings

**Screener + AI intersection views:**
- "52W High stocks with AI Buy recommendation" — screener results annotated with AI view
- "AI flagged Red Flags" — stocks where AI found concerns, cross-referenced with technical state
- "Technical breakout + no AI coverage" — gaps in analysis coverage

**Why StockPulse is the right host:**
- Already has user auth, roles, API key management
- HTMX architecture makes adding new data sources easy (just call tuJanalyst API endpoints)
- 4-person team doesn't need two separate login flows
- StockPulse already covers 1,633 stocks — AI analysis is enrichment on a subset

---

### 6. Screener-Aware Analysis (Medium Impact, Medium Effort)

**The problem:** tuJanalyst's agents don't know about screeners. They can't tell whether a stock is showing a specific technical pattern that has historically preceded big moves.

**The opportunity:** When Layer 3 runs, query StockPulse for which screeners the stock currently appears in. This becomes a structured input to the analysis:

```
screener_membership: [
  "52W Closing High Today",
  "Volume Breakout",
  "10 DMA Hold",
  "Orange + 10 DMA Hold",
  "52W High + Gap Up + Volume Breakout"
]
```

**Why this matters:**
- Screener names encode domain knowledge ("52W High + Gap Up + Volume Breakout" is a known compound signal)
- A stock appearing in many screeners simultaneously = technical strength convergence
- Screener membership provides a concise summary of technical state without the agent needing to interpret raw indicators
- The decision agent can weigh "stock appears in 8 bullish screeners" as a positive factor

---

### 7. Historical Technical Context for Investigations (Medium Impact, Medium Effort)

**The problem:** When tuJanalyst evaluates a recommendation change (Layer 4), it considers past investigations but has no view of what the stock's technical state was during those past investigations.

**The opportunity:** Store the StockPulse indicator snapshot at the time of each investigation. Then when Layer 4 reviews past investigations, it can see:

```
Past Investigation #1 (2 months ago):
  Finding: "Strong quarterly results, order book grew 40%"
  Decision: "Hold (inconclusive - waiting for confirmation)"
  Technical state at time: "Stock at DMA-50, no volume breakout, classified Yellow"

Current Investigation:
  Finding: "Order execution accelerating, margins expanding"
  Technical state now: "Stock at 52W high, volume breakout, classified Orange"
```

This enables the "past investigation resurrection" feature described in the North Star Vision with much richer context. The agent can now reason: "Two months ago we found strong results but stock hadn't confirmed technically. Now technical breakout confirms the fundamental thesis. Upgrade to Buy."

---

### 8. Cross-System Watchlist and Universe Alignment (Low Impact, Low Effort)

**The problem:** tuJanalyst tracks 32 companies via `watchlist.yaml`. StockPulse tracks ~1,633 stocks. These are managed independently.

**The opportunity:**
- StockPulse's color classification can drive tuJanalyst's watchlist: Pink (portfolio) + Orange + Yellow stocks = automatic watchlist candidates
- When a fund member changes a stock's color in StockPulse → tuJanalyst watchlist auto-updates
- tuJanalyst can suggest adding companies to StockPulse's universe when it discovers relevant companies through web search
- Single source of truth for "which companies do we care about" lives in StockPulse (it has more granular management)

**Watchlist expansion path:**
- Currently tuJanalyst covers 1 sector (32 companies)
- StockPulse covers 1,633 stocks across all sectors
- As tuJanalyst expands to more sectors (Iteration 2 roadmap), StockPulse already has the technical data ready
- The expansion path becomes: pick a new sector in StockPulse → colors already assigned → feed those to tuJanalyst → agents start analyzing

---

### 9. Result Date Intelligence (Low Impact, Low Effort)

**The problem:** tuJanalyst doesn't know when quarterly results are coming. StockPulse tracks result dates for all companies and knows exactly which stocks have results approaching in 7/10/15 days.

**The opportunity:**
- Before earnings season, query StockPulse for all tracked companies with results approaching
- Pre-position the gate to be more lenient for these companies (results announcements are almost always worth analyzing)
- After results are declared (StockPulse tracks this), auto-trigger an investigation if the stock shows post-result technical signals (gap-up, volume breakout)
- Layer 3 can reference the exact result date in its analysis context

---

### 10. Corporate Action Awareness (Low Impact, Low Effort)

**The problem:** tuJanalyst has no awareness of corporate actions — board meetings, ASM stages, circuit bands. StockPulse tracks all of these.

**The opportunity:**
- When analyzing a stock, the agent knows if a board meeting is upcoming (and its purpose)
- ASM stage is material context: a stock on ASM Stage III has trading restrictions — different analysis needed
- Circuit band information tells the agent about regulatory constraints on price movement
- This data is already in StockPulse; it just needs to be exposed to the agents

---

### 11. Sector-Level Technical Pulse (Medium Impact, High Effort)

**The problem:** The North Star Vision identifies sector-wide event analysis as important but not yet implemented in either system.

**The opportunity:** StockPulse has technical data for 1,633 stocks. It can answer sector-level questions that tuJanalyst's agents currently cannot:
- "How many stocks in Capital Goods - Electrical Equipment are at 52W highs?"
- "Is this a sector-wide breakout or company-specific?"
- "What's the sector's average volume trend?"
- "Are other companies in this sector showing similar DMA signals?"

This becomes a new tool for Layer 3: `SectorTechnicalPulseTool` that queries StockPulse for sector-wide aggregates. When analyzing INOXWIND's results, the agent can determine:
- "3 of 8 high-priority companies in this sector are at 52W highs" → sector tailwind
- "Only INOXWIND is breaking out, rest are flat" → company-specific catalyst

This directly enables the "sector-wide event detection and propagation" goal from Iteration 2.

---

### 12. Promise Tracking with Technical Validation (Medium Impact, High Effort)

**The problem:** The North Star Vision describes "promise tracking" — when management says "we'll achieve X revenue by Y date," the system should track and validate this. tuJanalyst extracts forward statements but has no automated validation mechanism.

**The opportunity:** StockPulse's price and indicator history provides indirect validation signals:
- Management promised strong results → StockPulse shows whether the stock's price action reflects market belief (pre-result breakout vs. no interest)
- Management promised growth → StockPulse can show if P/E ratio expanded (market pricing in growth)
- After result declaration (tracked by StockPulse), price reaction (gap-up/down, volume breakout) is immediate market verdict on whether promises were met
- The agent can compare: "Management promised 40% order book growth. Post-result, stock gapped up 8% with volume breakout. Market validates."

This creates a feedback loop: Promise made (tuJanalyst extracts) → Time passes → Result announced (RSS trigger) → Technical reaction measured (StockPulse) → Promise validated or broken (tuJanalyst agent reasons)

---

### 13. Unified Notification and Alerting (Low Impact, Medium Effort)

**The problem:** StockPulse has webhooks for technical events. tuJanalyst has Slack delivery for reports. These are separate notification streams.

**The opportunity:**
- Merge notifications into a single Slack channel with contextual richness
- Technical alert (StockPulse): "INOXWIND 52W High + Volume Breakout"
  → followed by (tuJanalyst): "AI Investigation initiated. Results in ~15 min."
  → followed by (tuJanalyst): "BUY recommendation (Confidence: 82%). Strong Q3 results + order book growth."
- Single notification thread per company per day (avoid noise)
- Priority routing: compound technical + fundamental signals → high-priority channel; routine updates → daily digest

---

### 14. Performance Feedback Loop (High Impact, High Effort)

**The problem:** tuJanalyst makes buy/sell/hold recommendations but has no way to measure if they were correct. StockPulse has price history that can retroactively validate recommendations.

**The opportunity:**
- When tuJanalyst issues a "Buy" recommendation on date D at price P, record it
- StockPulse's price history can show: what happened to the stock 1 week, 1 month, 3 months later?
- Did the stock hit the agent's target? Did it underperform? Did a red flag materialize?
- This creates the data needed for:
  - **Agent accuracy tracking**: "Layer 4 Buy recommendations were correct 68% of the time (price +10% within 3 months)"
  - **Prompt optimization**: identify which types of analyses lead to better predictions
  - **Confidence calibration**: are high-confidence recommendations actually more accurate?
  - **DSPy optimization**: use performance data as training signal for prompt optimization

This is the single most important long-term integration. Without it, the agents are making recommendations in the dark. With StockPulse price data, we close the feedback loop.

---

## New Capabilities Unlocked by Integration

These are things neither system can do alone, but become possible when combined:

### A. "Why is this stock moving?" Auto-Investigation
**Trigger:** StockPulse detects unusual price/volume activity (gap-up > 5%, volume breakout with no screener entry)
**Action:** tuJanalyst runs web search + news scan for the company
**Output:** "INOXWIND gapped up 7% at open. Investigation found: analyst upgrade by Motilal Oswal initiated coverage with Buy target 650."
**Value:** The team learns about market-moving events they might have missed.

### B. Technical-Fundamental Convergence Alerts
**Trigger:** Stock simultaneously (a) appears in multiple bullish screeners AND (b) has a recent high-confidence Buy from tuJanalyst
**Action:** Flag as "high conviction" opportunity
**Value:** Convergence of independent signals (price-based + news-based) is a stronger signal than either alone.

### C. Divergence Detection
**Trigger:** tuJanalyst says "Buy" (strong fundamentals) but StockPulse shows "DMA-200 Reverse, declining volume, 90D low"
**Action:** Flag divergence for human attention — "Fundamentals positive but technicals weak. Possible value trap or early entry?"
**Value:** Prevents acting on one-dimensional signals.

### D. Earnings Season Automation
**Trigger:** StockPulse's result date calendar shows earnings approaching
**Action:** Pre-stage tuJanalyst pipeline: increase gate sensitivity for that company, prepare historical context
**Post-result trigger:** StockPulse detects post-result technical reaction → auto-triggers deep analysis
**Value:** Fully automated quarterly earnings coverage without human intervention.

### E. Sector Rotation Detection
**Trigger:** StockPulse shows multiple stocks in a sector simultaneously breaking out (52W highs, volume)
**Action:** tuJanalyst runs sector-level analysis instead of company-level
**Output:** "Capital Goods sector showing broad technical breakout. 5 of 8 high-priority stocks at 52W highs. Possible drivers: government capex push, order book visibility improving."
**Value:** Catches sector-level themes that company-level analysis misses.

### F. Portfolio Monitoring
**Trigger:** StockPulse marks Pink stocks (current portfolio) showing DMA reversal or gap-down
**Action:** tuJanalyst runs defensive analysis: "Is this a temporary pullback or thesis broken?"
**Value:** Automated portfolio risk monitoring — the system watches your holdings while you sleep.

---

## Unified Platform Vision

When fully integrated, the TuJan platform becomes:

```
                    ┌──────────────────────────────────────────┐
                    │            UNIFIED WEB DASHBOARD          │
                    │      (StockPulse frontend + tuJanalyst   │
                    │       API calls via HTMX partials)        │
                    └────────────┬─────────────┬───────────────┘
                                 │             │
                    ┌────────────▼──┐   ┌──────▼───────────────┐
                    │  StockPulse   │   │    tuJanalyst         │
                    │  (Technical)  │   │    (Fundamental)      │
                    │               │   │                       │
                    │  PostgreSQL   │   │  MongoDB + ChromaDB   │
                    │  1,633 stocks │   │  32→1,633 companies   │
                    │  40+ indicators│  │  5-layer pipeline     │
                    │  79 screeners │   │  DSPy agents          │
                    │  12 event types│  │  Buy/Sell/Hold recs   │
                    └───────┬───────┘   └───────┬───────────────┘
                            │                   │
                            └─────────┬─────────┘
                                      │
                    ┌─────────────────▼─────────────────────────┐
                    │          INTEGRATION LAYER                 │
                    │                                            │
                    │  StockPulse → tuJanalyst:                  │
                    │    • Technical indicators as agent context │
                    │    • Event webhooks as triggers            │
                    │    • Result dates for earnings automation  │
                    │    • Screener membership for analysis      │
                    │    • Price history for recommendation      │
                    │      performance tracking                  │
                    │    • Sector aggregates for macro context   │
                    │                                            │
                    │  tuJanalyst → StockPulse:                  │
                    │    • Agent notes on stock pages            │
                    │    • Color classification suggestions      │
                    │    • AI recommendation events              │
                    │    • Investigation summaries               │
                    │    • Watchlist expansion suggestions       │
                    │                                            │
                    │  Bidirectional:                             │
                    │    • Unified notifications (Slack)         │
                    │    • Watchlist/universe sync               │
                    │    • Performance feedback loop             │
                    │    • Convergence/divergence alerts         │
                    └───────────────────────────────────────────┘
```

### What the Team Experiences

**Morning routine (today):**
1. Open StockPulse → check screener results and events
2. Open Streamlit → check if any AI reports came in overnight
3. Manually cross-reference between the two
4. Manually trigger investigations for interesting technical patterns

**Morning routine (integrated):**
1. Open StockPulse → see technical signals + AI recommendations in one view
2. Stocks showing technical breakout already have AI investigations attached
3. Overnight RSS announcements already processed; reports visible on stock detail pages
4. "High Conviction" alerts where technicals and fundamentals converge
5. Divergence warnings where AI and technicals disagree
6. Earnings season coverage fully automated

---

## Sequencing Recommendation

| Phase | Integration | Effort | Impact | Dependencies |
|-------|------------|--------|--------|-------------|
| 1 | StockPulseDataTool (rich indicators for agents) | Low | High | StockPulse API key |
| 1 | Agent notes flowing back to StockPulse | Low | Medium | StockPulse notes API |
| 1 | Result date awareness in tuJanalyst | Low | Low | StockPulse API |
| 2 | Technical context in gate (enhanced Layer 2) | Medium | High | Phase 1 tool |
| 2 | Webhook bridge (technical events → triggers) | Medium | High | StockPulse webhooks |
| 2 | Screener membership as analysis input | Medium | Medium | Phase 1 tool |
| 3 | Unified dashboard (StockPulse hosts AI views) | High | Medium | Phase 1+2 |
| 3 | Performance feedback loop | High | High | Price history API |
| 3 | Sector-level technical pulse tool | High | Medium | StockPulse sector queries |
| 4 | Convergence/divergence detection | Medium | High | Phase 2+3 |
| 4 | Earnings season automation | Medium | High | Phase 2 |
| 4 | Promise tracking with technical validation | High | Medium | Phase 3 |
| 4 | Watchlist/universe sync | Low | Low | Phase 1 |

---

## Open Questions

1. **Network topology:** Are both services deployed on the same Tailscale network? API latency between them matters for gate enrichment (needs to be fast).

2. **Authentication:** Should tuJanalyst use a dedicated StockPulse API key, or should we implement service-to-service auth?

3. **Data freshness:** StockPulse computes indicators at EOD (4 PM IST). During market hours, should tuJanalyst use intraday data or latest EOD? StockPulse has intraday polling every 3 minutes — can the API serve this?

4. **Universe alignment timing:** As tuJanalyst expands to more sectors, should StockPulse's existing universe be the boundary, or should tuJanalyst be able to request new stocks be added to StockPulse?

5. **Feedback loop scope:** For performance tracking, what constitutes a "correct" recommendation? Need to define: time horizon, price target, benchmark comparison.

6. **Rate limits:** If all 1,633 stocks in StockPulse fire events simultaneously (e.g., market-wide selloff), how does tuJanalyst handle the flood? Need throttling/batching strategy for technical event triggers.

7. **Color classification authority:** Should tuJanalyst agents be allowed to directly update colors, or only suggest? Current assumption: suggest only, humans decide. But for Blue (good results) and Red (bad results), the agent's assessment is arguably more systematic than manual classification.

---

*Document created: 2026-03-13*
*Scope: Product analysis only — no code changes proposed*
