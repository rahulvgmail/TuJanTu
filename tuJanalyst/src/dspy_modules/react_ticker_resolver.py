"""DSPy ReAct agent for ticker resolution with web search tool.

Last-resort resolver that uses an LLM agent with web search to identify
NSE/BSE company identifiers from partial trigger metadata. The agent can
search the web, reason about results, and extract structured ticker info.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import dspy

logger = logging.getLogger(__name__)


class TickerReActResolver(dspy.Module):
    """ReAct agent that uses web search to resolve company tickers."""

    def __init__(self, search_fn: Any = None):
        super().__init__()
        tools = []
        if search_fn is not None:
            tools.append(search_fn)
        self.react = dspy.ReAct(
            TickerReActSignature,
            tools=tools,
            max_iters=3,
        )

    def forward(
        self,
        company_name: str,
        raw_content: str,
        source_url: str,
    ) -> dspy.Prediction:
        return self.react(
            company_name=company_name,
            raw_content=raw_content,
            source_url=source_url,
        )


class TickerReActSignature(dspy.Signature):
    """Identify the NSE symbol and company name for an Indian stock exchange filing.

    You are given partial metadata from a corporate filing. Your task is to determine
    the exact NSE (National Stock Exchange of India) trading symbol and full company name.

    Strategy:
    1. First check the source_url — NSE URLs often contain the symbol before the date
       (e.g., /corporate/SADBHAV_01042026... means NSE symbol is SADBHAV).
    2. If the company_name or raw_content mentions a company, search the web for
       "<company name> NSE symbol" or "<company name> BSE" to find the ticker.
    3. Look for the NSE symbol, BSE scrip code, and ISIN in search results.

    Return the results as a JSON object. If you cannot determine the symbol with
    reasonable confidence, set nse_symbol to empty string and confidence to 0.
    """

    company_name: str = dspy.InputField(desc="Company name from trigger (may be empty)")
    raw_content: str = dspy.InputField(desc="Raw trigger content (first 500 chars)")
    source_url: str = dspy.InputField(desc="Source URL of the filing")

    resolution_json: str = dspy.OutputField(
        desc='JSON object with keys: nse_symbol, bse_scrip_code, isin, company_name, confidence (0-1), reason'
    )


def make_web_search_tool(search_tool: Any) -> Any:
    """Create a synchronous web search function compatible with dspy.ReAct.

    The search_tool is an async WebSearchTool/MultiProviderWebSearch instance.
    ReAct needs a plain sync function, so we bridge via asyncio.
    """
    import asyncio

    def search_web(query: str) -> str:
        """Search the web for information about an Indian company's stock ticker.

        Use queries like "<company name> NSE symbol" or "<company name> BSE listing"
        to find the trading symbol. Returns search results as text.
        """
        try:
            # Try to get existing event loop (if running in async context)
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                # We're inside an async context — run in a new thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    results = pool.submit(
                        asyncio.run,
                        search_tool.search(query, max_results=5),
                    ).result(timeout=20)
            else:
                results = asyncio.run(search_tool.search(query, max_results=5))

            if not results:
                return "No results found."

            lines = []
            for r in results[:5]:
                title = r.get("title", "")
                snippet = r.get("snippet", "")
                url = r.get("url", "")
                lines.append(f"- {title}\n  {snippet}\n  {url}")
            return "\n\n".join(lines)
        except Exception as exc:
            logger.warning("ReAct web search failed: %s", exc)
            return f"Search failed: {exc}"

    return search_web
