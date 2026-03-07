"""Web lookup helper for extracting NSE/BSE identifiers from search results."""

from __future__ import annotations

import re
from urllib.parse import urlparse

_NSE_PATTERN = re.compile(r"\bNSE\s*[:\-]?\s*([A-Z][A-Z0-9]{1,14})\b", flags=re.IGNORECASE)
_BSE_PATTERN = re.compile(r"\bBSE\s*[:\-]?\s*(\d{5,6})\b", flags=re.IGNORECASE)
_ISIN_PATTERN = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b", flags=re.IGNORECASE)


class TickerWebLookup:
    """Parse symbol candidates from search results with domain scoring."""

    def __init__(self, *, search_tool, preferred_domains: set[str] | None = None):
        self.search_tool = search_tool
        self.preferred_domains = preferred_domains or {
            "nseindia.com",
            "nsearchives.nseindia.com",
            "bseindia.com",
        }

    async def lookup(self, query: str) -> dict[str, str] | None:
        rows = await self.search_tool.search(query, max_results=5)
        best: dict[str, str] | None = None
        best_score = -1

        for row in rows:
            title = str(row.get("title") or "")
            snippet = str(row.get("snippet") or "")
            url = str(row.get("url") or "")
            text = f"{title} {snippet}".strip()
            nse_match = _NSE_PATTERN.search(text)
            bse_match = _BSE_PATTERN.search(text)
            isin_match = _ISIN_PATTERN.search(text)
            if not nse_match and not bse_match and not isin_match:
                continue

            domain_score = self._domain_score(url)
            data: dict[str, str] = {"source_url": url}
            if nse_match:
                data["nse_symbol"] = nse_match.group(1).upper()
            if bse_match:
                data["bse_scrip_code"] = bse_match.group(1)
            if isin_match:
                data["isin"] = isin_match.group(1).upper()

            match_score = domain_score
            if "nse_symbol" in data:
                match_score += 2
            if "bse_scrip_code" in data:
                match_score += 2
            if "isin" in data:
                match_score += 1

            if match_score > best_score:
                best = data
                best_score = match_score

        return best

    def _domain_score(self, url: str) -> int:
        host = urlparse(url).netloc.lower()
        for preferred in self.preferred_domains:
            if host == preferred or host.endswith(f".{preferred}"):
                return 3
        return 1

