"""Sync helpers for canonical company master data."""

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path
from typing import Any

import httpx
import yaml

from src.models.symbol_resolution import CompanyMaster
from src.repositories.base import CompanyMasterRepository

_DEFAULT_TIMEOUT_SECONDS = 30.0


class SymbolMasterSync:
    """Seed and refresh company master records used by ticker resolver."""

    def __init__(self, *, company_master_repo: CompanyMasterRepository, session: httpx.AsyncClient | None = None):
        self.company_master_repo = company_master_repo
        self.session = session

    async def sync_from_seed(self, seed_path: str | Path) -> int:
        """Load and upsert company master rows from a YAML seed file."""
        path = Path(seed_path)
        if not path.exists():
            raise FileNotFoundError(f"Symbol master seed not found: {path}")

        with path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        if not isinstance(payload, dict):
            raise ValueError(f"Seed YAML must be a mapping: {path}")

        rows = payload.get("companies")
        if not isinstance(rows, list):
            raise ValueError(f"Seed YAML must include a companies list: {path}")

        upserted = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            await self._upsert_exchange_row(self._normalize_row(row), source="seed")
            upserted += 1
        return upserted

    async def sync_from_exchange_sources(
        self,
        *,
        nse_url: str | None = None,
        bse_url: str | None = None,
    ) -> int:
        """Fetch and merge company master rows from NSE/BSE source endpoints."""
        if not nse_url and not bse_url:
            return 0

        owned_session = self.session is None
        session = self.session or httpx.AsyncClient(
            timeout=_DEFAULT_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "application/json,text/csv,text/plain,*/*",
                "Referer": "https://www.bseindia.com/",
            },
        )
        upserted = 0
        try:
            if nse_url:
                nse_text = await self._fetch_text(session, nse_url)
                for row in self._parse_nse_master_csv(nse_text):
                    await self._upsert_exchange_row(row, source="nse_master")
                    upserted += 1
            if bse_url:
                bse_text = await self._fetch_text(session, bse_url)
                bse_rows = self._parse_bse_master(bse_text)
                for row in bse_rows:
                    await self._upsert_exchange_row(row, source="bse_master")
                    upserted += 1
        finally:
            if owned_session:
                await session.aclose()
        return upserted

    def _normalize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        aliases = row.get("aliases")
        if not isinstance(aliases, list):
            aliases = []
        tags = row.get("tags")
        if not isinstance(tags, list):
            tags = []
        metadata = row.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        return {
            "canonical_id": row.get("canonical_id"),
            "nse_symbol": row.get("nse_symbol"),
            "bse_scrip_code": row.get("bse_scrip_code"),
            "isin": row.get("isin"),
            "company_name": row.get("company_name"),
            "aliases": aliases,
            "description": str(row.get("description") or ""),
            "nse_listed": bool(row.get("nse_listed", True)),
            "bse_listed": bool(row.get("bse_listed", False)),
            "sector": row.get("sector"),
            "industry": row.get("industry"),
            "tags": tags,
            "metadata": metadata,
        }

    async def _fetch_text(self, session: httpx.AsyncClient, url: str) -> str:
        response = await session.get(url)
        response.raise_for_status()
        return response.text

    def _parse_nse_master_csv(self, text: str) -> list[dict[str, Any]]:
        rows = self._read_csv_rows(text)
        parsed: list[dict[str, Any]] = []
        for row in rows:
            nse_symbol = self._pick(row, ["SYMBOL", "NSE_SYMBOL", "Security Id", "Security ID"])
            company_name = self._pick(
                row,
                [
                    "NAME OF COMPANY",
                    "Company Name",
                    "Issuer Name",
                    "Security Name",
                    "SM_NAME",
                ],
            )
            isin = self._pick(row, ["ISIN NUMBER", "ISIN NO", "ISIN", "ISIN No"])
            if not nse_symbol and not company_name:
                continue
            parsed.append(
                {
                    "nse_symbol": nse_symbol,
                    "company_name": company_name or nse_symbol or "Unknown Company",
                    "isin": isin,
                    "nse_listed": True,
                    "bse_listed": False,
                    "tags": ["exchange_master", "nse_listed"],
                    "metadata": {"nse_series": self._pick(row, ["SERIES", "Series"])},
                }
            )
        return parsed

    def _parse_bse_master(self, text: str) -> list[dict[str, Any]]:
        """Parse BSE master data from JSON (API) or CSV format."""
        stripped = text.strip()
        if stripped.startswith("[") or stripped.startswith("{"):
            return self._parse_bse_master_json(stripped)
        return self._parse_bse_master_csv(text)

    def _parse_bse_master_json(self, text: str) -> list[dict[str, Any]]:
        """Parse BSE ListofScripData JSON API response."""
        data = json.loads(text)
        if not isinstance(data, list):
            return []
        parsed: list[dict[str, Any]] = []
        for row in data:
            if not isinstance(row, dict):
                continue
            bse_scrip_code = str(row.get("SCRIP_CD") or "").strip()
            company_name = (
                str(row.get("Issuer_Name") or row.get("Scrip_Name") or "").strip()
            )
            nse_symbol = str(row.get("scrip_id") or "").strip() or None
            isin = str(row.get("ISIN_NUMBER") or "").strip() or None
            if not bse_scrip_code and not company_name:
                continue
            parsed.append(
                {
                    "nse_symbol": nse_symbol,
                    "bse_scrip_code": bse_scrip_code,
                    "company_name": company_name or nse_symbol or bse_scrip_code or "Unknown Company",
                    "isin": isin,
                    "nse_listed": bool(nse_symbol),
                    "bse_listed": True,
                    "tags": ["exchange_master", "bse_listed"],
                    "metadata": {
                        "bse_group": str(row.get("GROUP") or ""),
                        "bse_segment": str(row.get("Segment") or ""),
                    },
                }
            )
        return parsed

    def _parse_bse_master_csv(self, text: str) -> list[dict[str, Any]]:
        rows = self._read_csv_rows(text)
        parsed: list[dict[str, Any]] = []
        for row in rows:
            bse_scrip_code = self._pick(
                row,
                ["Security Code", "SCRIP CODE", "SCRIP_CD", "SC_CODE", "BSE Code"],
            )
            company_name = self._pick(
                row,
                ["Security Name", "Company Name", "Issuer Name", "NAME OF COMPANY"],
            )
            nse_symbol = self._pick(row, ["NSE Symbol", "SYMBOL", "Security Id", "Security ID"])
            isin = self._pick(row, ["ISIN No", "ISIN NUMBER", "ISIN", "ISIN NO"])
            if not bse_scrip_code and not company_name and not nse_symbol:
                continue
            parsed.append(
                {
                    "nse_symbol": nse_symbol,
                    "bse_scrip_code": bse_scrip_code,
                    "company_name": company_name or nse_symbol or bse_scrip_code or "Unknown Company",
                    "isin": isin,
                    "nse_listed": bool(nse_symbol),
                    "bse_listed": True,
                    "tags": ["exchange_master", "bse_listed"],
                    "metadata": {},
                }
            )
        return parsed

    def _read_csv_rows(self, text: str) -> list[dict[str, str]]:
        stream = StringIO(text)
        reader = csv.DictReader(stream)
        result: list[dict[str, str]] = []
        for row in reader:
            normalized: dict[str, str] = {}
            for key, value in row.items():
                if key is None:
                    continue
                normalized[key.strip()] = str(value or "").strip()
            if any(value for value in normalized.values()):
                result.append(normalized)
        return result

    def _pick(self, row: dict[str, str], keys: list[str]) -> str | None:
        if not row:
            return None
        normalized_map = {self._normalize_key(key): value for key, value in row.items()}
        for key in keys:
            value = normalized_map.get(self._normalize_key(key), "").strip()
            if value:
                return value
        return None

    def _normalize_key(self, key: str) -> str:
        return "".join(ch for ch in str(key).strip().lower() if ch.isalnum())

    async def _upsert_exchange_row(self, row: dict[str, Any], *, source: str) -> None:
        normalized = self._normalize_row(row)
        existing = await self._find_existing_company(
            nse_symbol=normalized.get("nse_symbol"),
            bse_scrip_code=normalized.get("bse_scrip_code"),
            isin=normalized.get("isin"),
            company_name=normalized.get("company_name"),
        )

        if existing is None:
            metadata = dict(normalized.get("metadata") or {})
            metadata["source"] = source
            normalized["metadata"] = metadata
            company = CompanyMaster.model_validate(normalized)
            await self.company_master_repo.upsert(company)
            return

        merged = existing.model_dump()
        for key in ("nse_symbol", "bse_scrip_code", "isin", "company_name", "description", "sector", "industry"):
            new_value = normalized.get(key)
            if isinstance(new_value, str) and new_value.strip():
                merged[key] = new_value

        merged["nse_listed"] = bool(existing.nse_listed or normalized.get("nse_listed"))
        merged["bse_listed"] = bool(existing.bse_listed or normalized.get("bse_listed"))
        merged["aliases"] = self._merge_str_lists(existing.aliases, normalized.get("aliases"))
        merged["tags"] = self._merge_str_lists(existing.tags, normalized.get("tags"), lower=True)
        metadata = dict(existing.metadata)
        for key, value in dict(normalized.get("metadata") or {}).items():
            metadata[str(key)] = value
        metadata["source"] = source
        merged["metadata"] = metadata

        company = CompanyMaster.model_validate(merged)
        await self.company_master_repo.upsert(company)

    async def _find_existing_company(
        self,
        *,
        nse_symbol: Any,
        bse_scrip_code: Any,
        isin: Any,
        company_name: Any,
    ) -> CompanyMaster | None:
        if isinstance(nse_symbol, str) and nse_symbol.strip():
            found = await self.company_master_repo.get_by_nse_symbol(nse_symbol)
            if found is not None:
                return found
        if isinstance(bse_scrip_code, str) and bse_scrip_code.strip():
            found = await self.company_master_repo.get_by_bse_scrip_code(bse_scrip_code)
            if found is not None:
                return found
        if isinstance(isin, str) and isin.strip():
            found = await self.company_master_repo.get_by_isin(isin)
            if found is not None:
                return found
        if isinstance(company_name, str) and company_name.strip():
            normalized_name = self._normalize_name(company_name)
            candidates = await self.company_master_repo.search_by_name(company_name, limit=20)
            for candidate in candidates:
                for name_value in [candidate.company_name, *candidate.aliases]:
                    if self._normalize_name(name_value) == normalized_name:
                        return candidate
        return None

    def _merge_str_lists(self, a: list[str], b: Any, *, lower: bool = False) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for value in [*a, *(b if isinstance(b, list) else [])]:
            text = str(value).strip()
            if not text:
                continue
            key = text.lower() if lower else text.upper()
            if key in seen:
                continue
            seen.add(key)
            merged.append(text.lower() if lower else text.upper())
        return merged

    def _normalize_name(self, value: str) -> str:
        return " ".join(ch for ch in value.lower().strip() if ch.isalnum() or ch.isspace()).strip()
