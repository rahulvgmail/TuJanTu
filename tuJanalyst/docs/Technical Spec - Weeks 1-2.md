# tuJanalyst: Technical Specification — Weeks 1-2

## Overview

This spec covers the first two weeks of MVP development. By the end of Week 2, the system should:
- Poll NSE RSS feeds and detect new announcements
- Download and extract text from linked documents (PDF, HTML)
- Accept human-triggered investigations via API
- Filter triggers through a configurable watchlist (sector, company, keywords)
- Run a cheap LLM gate classification on filtered triggers
- Store all data in MongoDB with vector embeddings in ChromaDB
- Have a basic health check and status API

---

## 1. Project Structure

```
tuJanalyst/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml                  # uv/poetry project config
├── .env.example
├── README.md
│
├── config/
│   ├── watchlist.yaml              # Sectors, companies, keywords
│   ├── settings.yaml               # App settings (polling interval, models, etc.)
│   └── logging.yaml                # Logging configuration
│
├── src/
│   ├── __init__.py
│   ├── main.py                     # FastAPI app entry point
│   ├── config.py                   # Settings loader (Pydantic Settings)
│   │
│   ├── models/                     # Pydantic data models (shared across layers)
│   │   ├── __init__.py
│   │   ├── trigger.py              # TriggerEvent, TriggerSource, TriggerStatus
│   │   ├── document.py             # RawDocument, ProcessedDocument
│   │   ├── investigation.py        # Investigation, Finding, RedFlag
│   │   ├── decision.py             # DecisionAssessment, Recommendation
│   │   ├── report.py               # AnalysisReport
│   │   └── company.py              # Company, Sector, Watchlist
│   │
│   ├── repositories/               # Data access layer
│   │   ├── __init__.py
│   │   ├── base.py                 # Repository protocols (interfaces)
│   │   ├── mongo.py                # MongoDB implementations
│   │   └── vector.py               # ChromaDB implementations
│   │
│   ├── pipeline/                   # The 5-layer processing pipeline
│   │   ├── __init__.py
│   │   ├── orchestrator.py         # Main pipeline runner
│   │   ├── layer1_triggers/        # Trigger ingestion
│   │   │   ├── __init__.py
│   │   │   ├── rss_poller.py       # NSE/BSE RSS feed polling
│   │   │   ├── document_fetcher.py # Download linked documents
│   │   │   └── text_extractor.py   # PDF/HTML text extraction
│   │   ├── layer2_gate/            # Worth reviewing filter
│   │   │   ├── __init__.py
│   │   │   ├── watchlist_filter.py # Company/sector/keyword filter
│   │   │   └── gate_classifier.py  # DSPy LLM classification
│   │   ├── layer3_analysis/        # Deep analysis (Week 3)
│   │   ├── layer4_decision/        # Decision assessment (Week 4)
│   │   └── layer5_report/          # Report generation (Week 4)
│   │
│   ├── agents/                     # Pydantic AI agent definitions (grows over time)
│   │   ├── __init__.py
│   │   └── tools/                  # Agent tools
│   │       ├── __init__.py
│   │       ├── web_search.py       # Web search tool
│   │       └── market_data.py      # Market data tool
│   │
│   ├── dspy_modules/               # DSPy signatures and modules
│   │   ├── __init__.py
│   │   ├── signatures.py           # All DSPy signatures
│   │   ├── gate.py                 # Gate classification module
│   │   ├── analysis.py             # Analysis pipeline module (Week 3)
│   │   ├── decision.py             # Decision module (Week 4)
│   │   └── report.py               # Report generation module (Week 4)
│   │
│   ├── api/                        # FastAPI routes
│   │   ├── __init__.py
│   │   ├── triggers.py             # Human trigger endpoint, trigger status
│   │   ├── investigations.py       # Investigation queries (Week 3+)
│   │   ├── reports.py              # Report queries (Week 4+)
│   │   └── health.py               # Health check, system status
│   │
│   └── scheduler/                  # Background task scheduling
│       ├── __init__.py
│       └── jobs.py                 # RSS polling job, embedding jobs
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Shared fixtures (test DB, mock LLM)
│   ├── test_models/
│   ├── test_repositories/
│   ├── test_pipeline/
│   │   ├── test_rss_poller.py
│   │   ├── test_document_fetcher.py
│   │   ├── test_text_extractor.py
│   │   ├── test_watchlist_filter.py
│   │   └── test_gate_classifier.py
│   └── test_api/
│
└── scripts/
    ├── seed_watchlist.py           # Populate initial watchlist
    └── backfill_rss.py             # Backfill historical RSS items
```

---

## 2. Data Models

### 2.1 Trigger Event

```python
# src/models/trigger.py
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from typing import Optional

class TriggerSource(str, Enum):
    NSE_RSS = "nse_rss"
    BSE_RSS = "bse_rss"
    HUMAN = "human"

class TriggerStatus(str, Enum):
    PENDING = "pending"               # Just ingested, not yet filtered
    FILTERED_OUT = "filtered_out"     # Dropped by Layer 2 gate
    GATE_PASSED = "gate_passed"       # Passed Layer 2, awaiting analysis
    ANALYZING = "analyzing"           # Layer 3 in progress
    ANALYZED = "analyzed"             # Layer 3 complete
    ASSESSING = "assessing"           # Layer 4 in progress
    ASSESSED = "assessed"             # Layer 4 complete
    REPORTED = "reported"             # Layer 5 complete, report delivered
    ERROR = "error"                   # Processing failed

class TriggerPriority(str, Enum):
    NORMAL = "normal"
    HIGH = "high"                     # Human triggers get this by default

class TriggerEvent(BaseModel):
    trigger_id: str = Field(default_factory=lambda: str(uuid4()))
    source: TriggerSource
    source_url: Optional[str] = None
    source_feed_title: Optional[str] = None       # RSS item title
    source_feed_published: Optional[datetime] = None  # RSS publish date

    company_symbol: Optional[str] = None           # NSE/BSE symbol if identified
    company_name: Optional[str] = None
    sector: Optional[str] = None

    raw_content: str                               # Announcement text or human input
    document_ids: list[str] = Field(default_factory=list)  # Linked document IDs

    priority: TriggerPriority = TriggerPriority.NORMAL
    triggered_by: Optional[str] = None             # Username for human triggers
    human_notes: Optional[str] = None              # Optional context from human

    status: TriggerStatus = TriggerStatus.PENDING
    status_history: list[dict] = Field(default_factory=list)  # [{status, timestamp, reason}]

    # Gate results (populated by Layer 2)
    gate_result: Optional[dict] = None             # {passed: bool, reason: str, method: str}

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        # MongoDB collection name
        collection_name = "triggers"
```

### 2.2 Raw Document

```python
# src/models/document.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from enum import Enum

class DocumentType(str, Enum):
    PDF = "pdf"
    HTML = "html"
    EXCEL = "excel"
    TEXT = "text"
    UNKNOWN = "unknown"

class ProcessingStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    EMBEDDING = "embedding"
    COMPLETE = "complete"
    ERROR = "error"

class RawDocument(BaseModel):
    document_id: str = Field(default_factory=lambda: str(uuid4()))
    trigger_id: str                                # Which trigger this came from
    source_url: str                                # Original download URL
    file_path: Optional[str] = None                # Local storage path (GridFS ID or filesystem)

    document_type: DocumentType = DocumentType.UNKNOWN
    content_type: Optional[str] = None             # HTTP content-type header
    file_size_bytes: Optional[int] = None

    # Extracted content
    extracted_text: Optional[str] = None           # Full extracted text
    extraction_method: Optional[str] = None        # "pdfplumber", "beautifulsoup", etc.
    extraction_metadata: dict = Field(default_factory=dict)  # Page count, tables found, etc.

    # Company association
    company_symbol: Optional[str] = None
    company_name: Optional[str] = None

    processing_status: ProcessingStatus = ProcessingStatus.PENDING
    processing_errors: list[str] = Field(default_factory=list)

    # Vector embedding reference
    vector_id: Optional[str] = None                # ChromaDB/Weaviate ID after embedding

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        collection_name = "documents"
```

### 2.3 Company & Watchlist

```python
# src/models/company.py
from pydantic import BaseModel, Field
from typing import Optional

class Company(BaseModel):
    symbol: str                                    # NSE/BSE symbol (e.g., "INOXWIND")
    name: str
    sector: str
    industry: Optional[str] = None
    market_cap_category: Optional[str] = None      # "small_cap", "mid_cap", "large_cap"
    bse_code: Optional[str] = None
    nse_listed: bool = True
    bse_listed: bool = False
    priority: str = "normal"                       # "normal" | "high"
    monitoring_active: bool = True
    metadata: dict = Field(default_factory=dict)   # Flexible extra fields

    class Config:
        collection_name = "companies"

class WatchlistConfig(BaseModel):
    """Loaded from watchlist.yaml at startup."""
    sectors: list[dict]       # [{name, keywords}]
    companies: list[dict]     # [{symbol, name, priority}]
    global_keywords: list[str] = Field(default_factory=list)
```

---

## 3. Configuration

### 3.1 Application Settings

```python
# src/config.py
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "tuJanalyst"

    # ChromaDB
    chromadb_persist_dir: str = "./data/chromadb"
    embedding_model: str = "all-MiniLM-L6-v2"     # sentence-transformers model

    # LLM
    anthropic_api_key: str
    gate_model: str = "claude-haiku"               # Cheap/fast for gate
    analysis_model: str = "claude-sonnet"           # Quality for analysis
    decision_model: str = "claude-sonnet"           # Quality for decisions

    # RSS Polling
    nse_rss_url: str = "https://www.nseindia.com/api/corporat-announcements?index=equities"
    polling_interval_seconds: int = 300             # 5 minutes
    polling_enabled: bool = True

    # Processing
    max_document_size_mb: int = 50
    text_extraction_timeout_seconds: int = 60

    # Notifications
    notification_method: str = "slack"              # "slack" | "email" | "none"
    slack_webhook_url: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    notification_email: str = ""

    class Config:
        env_file = ".env"
        env_prefix = "TUJ_"
```

### 3.2 Watchlist YAML

```yaml
# config/watchlist.yaml

sectors:
  - name: "Capital Goods - Electrical Equipment"
    nse_industry_code: "ELECTRICALEQUIP"   # For RSS filtering
    keywords:
      - "quarterly results"
      - "financial results"
      - "order book"
      - "order win"
      - "acquisition"
      - "expansion"
      - "capacity"
      - "board meeting outcome"
      - "dividend"
      - "stock split"
      - "rights issue"
      - "demerger"
      - "merger"
      - "preferential allotment"
      - "annual general meeting"
      - "credit rating"
      - "SEBI"

companies:
  - symbol: "INOXWIND"
    name: "Inox Wind Limited"
    priority: "high"
    aliases: ["Inox Wind", "INOX WIND"]

  - symbol: "SUZLON"
    name: "Suzlon Energy Limited"
    priority: "high"
    aliases: ["Suzlon Energy", "SUZLON ENERGY"]

  - symbol: "SIEMENS"
    name: "Siemens Limited"
    priority: "normal"
    aliases: ["Siemens"]

  - symbol: "ABB"
    name: "ABB India Limited"
    priority: "normal"
    aliases: ["ABB India"]

  - symbol: "BHEL"
    name: "Bharat Heavy Electricals Limited"
    priority: "normal"
    aliases: ["BHEL"]

  # Add more companies as needed

global_keywords:
  - "insider trading"
  - "SEBI order"
  - "fraud"
  - "default"
  - "bankruptcy"
```

### 3.3 Docker Compose

```yaml
# docker-compose.yml
version: "3.8"

services:
  app:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./config:/app/config
      - ./data:/app/data           # ChromaDB persistence, downloaded docs
    depends_on:
      - mongodb

  mongodb:
    image: mongo:7
    ports:
      - "27017:27017"
    volumes:
      - mongo_data:/data/db
    environment:
      MONGO_INITDB_DATABASE: tuJanalyst

volumes:
  mongo_data:
```

---

## 4. Repository Layer (Data Access)

### 4.1 Repository Protocols

```python
# src/repositories/base.py
from typing import Protocol, Optional
from src.models.trigger import TriggerEvent, TriggerStatus
from src.models.document import RawDocument

class TriggerRepository(Protocol):
    async def save(self, trigger: TriggerEvent) -> str: ...
    async def get(self, trigger_id: str) -> Optional[TriggerEvent]: ...
    async def update_status(self, trigger_id: str, status: TriggerStatus, reason: str = "") -> None: ...
    async def get_pending(self, limit: int = 50) -> list[TriggerEvent]: ...
    async def get_by_company(self, company_symbol: str, limit: int = 20) -> list[TriggerEvent]: ...
    async def exists_by_url(self, source_url: str) -> bool: ...  # Dedup RSS items

class DocumentRepository(Protocol):
    async def save(self, document: RawDocument) -> str: ...
    async def get(self, document_id: str) -> Optional[RawDocument]: ...
    async def get_by_trigger(self, trigger_id: str) -> list[RawDocument]: ...
    async def update_extracted_text(self, document_id: str, text: str, method: str, metadata: dict) -> None: ...

class VectorRepository(Protocol):
    async def add_document(self, document_id: str, text: str, metadata: dict) -> str: ...
    async def search(self, query: str, n_results: int = 5, where: dict | None = None) -> list[dict]: ...
    async def delete_document(self, document_id: str) -> None: ...
```

### 4.2 MongoDB Implementation

```python
# src/repositories/mongo.py
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from src.models.trigger import TriggerEvent, TriggerStatus
from datetime import datetime

class MongoTriggerRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db["triggers"]

    async def save(self, trigger: TriggerEvent) -> str:
        doc = trigger.model_dump()
        await self.collection.insert_one(doc)
        return trigger.trigger_id

    async def get(self, trigger_id: str) -> TriggerEvent | None:
        doc = await self.collection.find_one({"trigger_id": trigger_id})
        return TriggerEvent(**doc) if doc else None

    async def update_status(self, trigger_id: str, status: TriggerStatus, reason: str = "") -> None:
        await self.collection.update_one(
            {"trigger_id": trigger_id},
            {
                "$set": {"status": status.value, "updated_at": datetime.utcnow()},
                "$push": {"status_history": {
                    "status": status.value,
                    "timestamp": datetime.utcnow(),
                    "reason": reason
                }}
            }
        )

    async def exists_by_url(self, source_url: str) -> bool:
        return await self.collection.count_documents({"source_url": source_url}) > 0

    async def get_pending(self, limit: int = 50) -> list[TriggerEvent]:
        cursor = self.collection.find({"status": "pending"}).sort("created_at", 1).limit(limit)
        return [TriggerEvent(**doc) async for doc in cursor]
```

### 4.3 ChromaDB Implementation

```python
# src/repositories/vector.py
import chromadb
from sentence_transformers import SentenceTransformer

class ChromaVectorRepository:
    def __init__(self, persist_dir: str, embedding_model: str = "all-MiniLM-L6-v2"):
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(
            name="documents",
            metadata={"hnsw:space": "cosine"}
        )
        self.embedder = SentenceTransformer(embedding_model)

    async def add_document(self, document_id: str, text: str, metadata: dict) -> str:
        # Chunk long documents (simple fixed-size chunking for MVP)
        chunks = self._chunk_text(text, chunk_size=1000, overlap=200)
        for i, chunk in enumerate(chunks):
            chunk_id = f"{document_id}_chunk_{i}"
            embedding = self.embedder.encode(chunk).tolist()
            self.collection.add(
                ids=[chunk_id],
                embeddings=[embedding],
                documents=[chunk],
                metadatas=[{**metadata, "document_id": document_id, "chunk_index": i}]
            )
        return document_id

    async def search(self, query: str, n_results: int = 5, where: dict | None = None) -> list[dict]:
        query_embedding = self.embedder.encode(query).tolist()
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"]
        )
        return [
            {
                "id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            }
            for i in range(len(results["ids"][0]))
        ]

    def _chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end])
            start = end - overlap
        return chunks
```

---

## 5. Layer 1: Trigger Ingestion

### 5.1 RSS Poller

```python
# src/pipeline/layer1_triggers/rss_poller.py
import httpx
import feedparser
from datetime import datetime
from typing import Optional
import logging

from src.models.trigger import TriggerEvent, TriggerSource, TriggerPriority
from src.repositories.base import TriggerRepository

logger = logging.getLogger(__name__)

class NSERSSPoller:
    """
    Polls NSE corporate announcements RSS feed.

    NSE provides announcements at:
    - https://www.nseindia.com/api/corporate-announcements?index=equities
    - Returns JSON with announcement metadata and PDF links

    Note: NSE's API requires specific headers (User-Agent, Accept) and
    may use cookies. We need to handle this carefully.

    Alternative: BSE has a more traditional RSS feed at
    https://www.bseindia.com/corporates/ann.html (scraping may be needed)
    """

    def __init__(
        self,
        trigger_repo: TriggerRepository,
        nse_url: str,
        session: Optional[httpx.AsyncClient] = None
    ):
        self.trigger_repo = trigger_repo
        self.nse_url = nse_url
        self.session = session or httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            },
            timeout=30.0,
            follow_redirects=True,
        )

    async def poll(self) -> list[TriggerEvent]:
        """
        Fetch latest announcements and create trigger events for new ones.
        Returns list of newly created triggers.
        """
        try:
            announcements = await self._fetch_announcements()
            new_triggers = []

            for ann in announcements:
                source_url = ann.get("link") or ann.get("attchmntFile")
                if not source_url:
                    continue

                # Dedup: skip if we've already seen this URL
                if await self.trigger_repo.exists_by_url(source_url):
                    continue

                trigger = TriggerEvent(
                    source=TriggerSource.NSE_RSS,
                    source_url=source_url,
                    source_feed_title=ann.get("desc", ""),
                    source_feed_published=self._parse_date(ann.get("an_dt")),
                    company_symbol=ann.get("symbol"),
                    company_name=ann.get("sm_name"),
                    sector=ann.get("industry"),       # May or may not be present
                    raw_content=ann.get("desc", ""),
                    priority=TriggerPriority.NORMAL,
                )

                await self.trigger_repo.save(trigger)
                new_triggers.append(trigger)
                logger.info(f"New trigger: {trigger.company_symbol} - {trigger.source_feed_title[:80]}")

            logger.info(f"Poll complete: {len(new_triggers)} new triggers from {len(announcements)} announcements")
            return new_triggers

        except Exception as e:
            logger.error(f"RSS poll failed: {e}")
            return []

    async def _fetch_announcements(self) -> list[dict]:
        """
        Fetch announcements from NSE API.

        IMPORTANT: NSE's API is not a standard RSS feed. It returns JSON.
        The exact endpoint and format may change. This needs testing with
        real NSE responses and may need adjustment.

        TODO: Implement cookie handling if NSE requires session cookies.
        TODO: Add BSE feed as secondary source.
        """
        response = await self.session.get(self.nse_url)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else data.get("data", [])

    def _parse_date(self, date_str: str | None) -> datetime | None:
        if not date_str:
            return None
        try:
            # NSE date format: "15-Jan-2026" or similar
            return datetime.strptime(date_str, "%d-%b-%Y")
        except ValueError:
            return None
```

### 5.2 Document Fetcher

```python
# src/pipeline/layer1_triggers/document_fetcher.py
import httpx
from pathlib import Path
from urllib.parse import urlparse
import logging

from src.models.document import RawDocument, DocumentType, ProcessingStatus
from src.repositories.base import DocumentRepository

logger = logging.getLogger(__name__)

class DocumentFetcher:
    """Downloads documents linked from trigger events."""

    def __init__(
        self,
        doc_repo: DocumentRepository,
        download_dir: str = "./data/documents",
        max_size_mb: int = 50,
    ):
        self.doc_repo = doc_repo
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.session = httpx.AsyncClient(
            timeout=60.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"}
        )

    async def fetch(self, trigger_id: str, url: str, company_symbol: str | None = None) -> RawDocument | None:
        """Download a document and create a RawDocument record."""
        try:
            doc = RawDocument(
                trigger_id=trigger_id,
                source_url=url,
                company_symbol=company_symbol,
                processing_status=ProcessingStatus.DOWNLOADING,
            )
            await self.doc_repo.save(doc)

            response = await self.session.get(url)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            doc.content_type = content_type
            doc.document_type = self._detect_type(url, content_type)
            doc.file_size_bytes = len(response.content)

            if doc.file_size_bytes > self.max_size_bytes:
                logger.warning(f"Document too large ({doc.file_size_bytes} bytes): {url}")
                doc.processing_status = ProcessingStatus.ERROR
                doc.processing_errors.append(f"File too large: {doc.file_size_bytes} bytes")
                await self.doc_repo.save(doc)
                return doc

            # Save to disk
            filename = f"{doc.document_id}.{doc.document_type.value}"
            file_path = self.download_dir / filename
            file_path.write_bytes(response.content)
            doc.file_path = str(file_path)
            doc.processing_status = ProcessingStatus.DOWNLOADED

            await self.doc_repo.save(doc)
            logger.info(f"Downloaded: {url} -> {file_path} ({doc.file_size_bytes} bytes)")
            return doc

        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            if doc:
                doc.processing_status = ProcessingStatus.ERROR
                doc.processing_errors.append(str(e))
                await self.doc_repo.save(doc)
            return None

    def _detect_type(self, url: str, content_type: str) -> DocumentType:
        url_lower = url.lower()
        if ".pdf" in url_lower or "pdf" in content_type:
            return DocumentType.PDF
        elif ".xls" in url_lower or "spreadsheet" in content_type:
            return DocumentType.EXCEL
        elif ".htm" in url_lower or "html" in content_type:
            return DocumentType.HTML
        elif ".txt" in url_lower or "text/plain" in content_type:
            return DocumentType.TEXT
        return DocumentType.UNKNOWN
```

### 5.3 Text Extractor

```python
# src/pipeline/layer1_triggers/text_extractor.py
import pdfplumber
from bs4 import BeautifulSoup
from pathlib import Path
import logging

from src.models.document import RawDocument, DocumentType, ProcessingStatus
from src.repositories.base import DocumentRepository

logger = logging.getLogger(__name__)

class TextExtractor:
    """Extracts text content from downloaded documents."""

    def __init__(self, doc_repo: DocumentRepository):
        self.doc_repo = doc_repo

    async def extract(self, document: RawDocument) -> str | None:
        """Extract text from a document. Returns extracted text or None on failure."""
        if not document.file_path:
            return None

        try:
            file_path = Path(document.file_path)

            if document.document_type == DocumentType.PDF:
                text, metadata = self._extract_pdf(file_path)
            elif document.document_type == DocumentType.HTML:
                text, metadata = self._extract_html(file_path)
            elif document.document_type == DocumentType.TEXT:
                text = file_path.read_text(encoding="utf-8", errors="replace")
                metadata = {"method": "direct_read"}
            else:
                logger.warning(f"Unsupported document type: {document.document_type}")
                return None

            await self.doc_repo.update_extracted_text(
                document_id=document.document_id,
                text=text,
                method=metadata.get("method", "unknown"),
                metadata=metadata,
            )

            logger.info(f"Extracted {len(text)} chars from {document.document_id}")
            return text

        except Exception as e:
            logger.error(f"Extraction failed for {document.document_id}: {e}")
            document.processing_status = ProcessingStatus.ERROR
            document.processing_errors.append(f"Extraction failed: {e}")
            return None

    def _extract_pdf(self, file_path: Path) -> tuple[str, dict]:
        """Extract text from PDF using pdfplumber."""
        pages_text = []
        table_count = 0

        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                pages_text.append(text)

                # Also extract tables
                tables = page.extract_tables()
                table_count += len(tables)
                for table in tables:
                    # Convert table to text representation
                    table_text = "\n".join([" | ".join([str(cell or "") for cell in row]) for row in table])
                    pages_text.append(f"\n[TABLE]\n{table_text}\n[/TABLE]\n")

            metadata = {
                "method": "pdfplumber",
                "page_count": len(pdf.pages),
                "table_count": table_count,
            }

        return "\n".join(pages_text), metadata

    def _extract_html(self, file_path: Path) -> tuple[str, dict]:
        """Extract text from HTML using BeautifulSoup."""
        html = file_path.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")

        # Remove script and style elements
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()

        text = soup.get_text(separator="\n", strip=True)
        metadata = {"method": "beautifulsoup"}
        return text, metadata
```

### 5.4 Human Trigger API

```python
# src/api/triggers.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from src.models.trigger import TriggerEvent, TriggerSource, TriggerPriority, TriggerStatus
from src.repositories.base import TriggerRepository

router = APIRouter(prefix="/api/v1/triggers", tags=["triggers"])

class HumanTriggerRequest(BaseModel):
    company_symbol: Optional[str] = None
    company_name: Optional[str] = None
    content: str                                   # Free text or URL
    notes: Optional[str] = None                    # Additional context
    triggered_by: str                              # Username

class TriggerStatusResponse(BaseModel):
    trigger_id: str
    source: str
    company_symbol: Optional[str]
    status: str
    created_at: str
    gate_result: Optional[dict]

@router.post("/human", response_model=dict)
async def create_human_trigger(
    request: HumanTriggerRequest,
    trigger_repo: TriggerRepository,  # Injected via FastAPI dependency
):
    """Submit a human-initiated investigation trigger."""
    trigger = TriggerEvent(
        source=TriggerSource.HUMAN,
        company_symbol=request.company_symbol,
        company_name=request.company_name,
        raw_content=request.content,
        human_notes=request.notes,
        triggered_by=request.triggered_by,
        priority=TriggerPriority.HIGH,       # Human triggers are always high priority
        status=TriggerStatus.GATE_PASSED,    # Bypass gate
    )
    await trigger_repo.save(trigger)
    return {"trigger_id": trigger.trigger_id, "status": "accepted"}

@router.get("/{trigger_id}", response_model=TriggerStatusResponse)
async def get_trigger_status(
    trigger_id: str,
    trigger_repo: TriggerRepository,
):
    """Get the current status of a trigger."""
    trigger = await trigger_repo.get(trigger_id)
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")
    return TriggerStatusResponse(
        trigger_id=trigger.trigger_id,
        source=trigger.source.value,
        company_symbol=trigger.company_symbol,
        status=trigger.status.value,
        created_at=trigger.created_at.isoformat(),
        gate_result=trigger.gate_result,
    )

@router.get("/", response_model=list[TriggerStatusResponse])
async def list_triggers(
    status: Optional[str] = None,
    company: Optional[str] = None,
    limit: int = 50,
    trigger_repo: TriggerRepository = None,
):
    """List recent triggers with optional filtering."""
    # Implementation: query MongoDB with filters
    pass
```

---

## 6. Layer 2: Gate (Worth Reviewing)

### 6.1 Watchlist Filter

```python
# src/pipeline/layer2_gate/watchlist_filter.py
import yaml
from pathlib import Path
from src.models.trigger import TriggerEvent
from src.models.company import WatchlistConfig
import logging

logger = logging.getLogger(__name__)

class WatchlistFilter:
    """
    First-pass filter: is this trigger about a company/sector we care about?
    This is a cheap, instant check — no LLM calls.
    """

    def __init__(self, config_path: str = "config/watchlist.yaml"):
        self.config = self._load_config(config_path)
        self._build_lookup_tables()

    def _load_config(self, path: str) -> WatchlistConfig:
        with open(path) as f:
            data = yaml.safe_load(f)
        return WatchlistConfig(**data)

    def _build_lookup_tables(self):
        """Pre-compute lookup sets for fast filtering."""
        self.watched_symbols = {c["symbol"].upper() for c in self.config.companies}
        self.watched_names = set()
        for c in self.config.companies:
            self.watched_names.add(c["name"].lower())
            for alias in c.get("aliases", []):
                self.watched_names.add(alias.lower())
        self.watched_sectors = {s["name"].lower() for s in self.config.sectors}
        self.keywords = set()
        for s in self.config.sectors:
            self.keywords.update(kw.lower() for kw in s.get("keywords", []))
        self.keywords.update(kw.lower() for kw in self.config.global_keywords)

    def check(self, trigger: TriggerEvent) -> dict:
        """
        Returns: {passed: bool, reason: str, method: str}
        """
        # Check 1: Company symbol match
        if trigger.company_symbol and trigger.company_symbol.upper() in self.watched_symbols:
            return {"passed": True, "reason": f"Watched company: {trigger.company_symbol}", "method": "symbol_match"}

        # Check 2: Company name match (fuzzy via aliases)
        if trigger.company_name:
            name_lower = trigger.company_name.lower()
            for watched_name in self.watched_names:
                if watched_name in name_lower or name_lower in watched_name:
                    return {"passed": True, "reason": f"Company name match: {trigger.company_name}", "method": "name_match"}

        # Check 3: Sector match
        if trigger.sector and trigger.sector.lower() in self.watched_sectors:
            # Sector matches, but check keywords for relevance
            return self._check_keywords(trigger, f"Sector match: {trigger.sector}")

        # Check 4: No company/sector identified — check content keywords as last resort
        content_lower = (trigger.raw_content or "").lower()
        for name in self.watched_names:
            if name in content_lower:
                return {"passed": True, "reason": f"Company mentioned in content: {name}", "method": "content_scan"}

        return {"passed": False, "reason": "No match to watchlist", "method": "watchlist_filter"}

    def _check_keywords(self, trigger: TriggerEvent, context: str) -> dict:
        """Check if trigger content matches any keywords."""
        content_lower = f"{trigger.raw_content} {trigger.source_feed_title or ''}".lower()
        matched = [kw for kw in self.keywords if kw in content_lower]
        if matched:
            return {"passed": True, "reason": f"{context}, keywords: {matched[:3]}", "method": "keyword_match"}
        return {"passed": False, "reason": f"{context}, but no keyword match", "method": "keyword_filter"}
```

### 6.2 DSPy Gate Classifier

```python
# src/dspy_modules/signatures.py
import dspy

class GateClassification(dspy.Signature):
    """Decide if a corporate announcement warrants deeper investigation for investment decisions.

    You are an experienced financial analyst screening corporate announcements.
    Return True only if this announcement could materially affect investment decisions
    for the company or its sector. Filter out routine/administrative announcements."""

    announcement_text: str = dspy.InputField(desc="The corporate announcement text")
    company_name: str = dspy.InputField(desc="Company name")
    sector: str = dspy.InputField(desc="Company's sector")
    is_worth_investigating: bool = dspy.OutputField(desc="True if this warrants deeper analysis")
    reason: str = dspy.OutputField(desc="One-line explanation of why or why not")


# src/dspy_modules/gate.py
import dspy
from src.dspy_modules.signatures import GateClassification

class GateModule(dspy.Module):
    """Layer 2 gate: cheap LLM classification of trigger relevance."""

    def __init__(self):
        super().__init__()
        self.classify = dspy.Predict(GateClassification)

    def forward(self, announcement_text: str, company_name: str, sector: str) -> dspy.Prediction:
        return self.classify(
            announcement_text=announcement_text,
            company_name=company_name,
            sector=sector,
        )


# src/pipeline/layer2_gate/gate_classifier.py
import dspy
from src.dspy_modules.gate import GateModule
from src.models.trigger import TriggerEvent
import logging

logger = logging.getLogger(__name__)

class GateClassifier:
    """
    LLM-powered gate classification. Uses DSPy for structured, optimizable classification.
    Uses the cheapest/fastest model available (Claude Haiku).
    """

    def __init__(self, model_name: str = "claude-haiku"):
        # Configure DSPy to use the gate model
        self.lm = dspy.LM(f"anthropic/{model_name}")
        self.gate = GateModule()

    async def classify(self, trigger: TriggerEvent) -> dict:
        """
        Returns: {passed: bool, reason: str, method: str, model: str}
        """
        try:
            with dspy.context(lm=self.lm):
                result = self.gate(
                    announcement_text=trigger.raw_content[:2000],  # Limit input size for cost
                    company_name=trigger.company_name or "Unknown",
                    sector=trigger.sector or "Unknown",
                )

            passed = result.is_worth_investigating
            reason = result.reason

            logger.info(f"Gate {'PASSED' if passed else 'REJECTED'}: {trigger.company_symbol} - {reason}")

            return {
                "passed": passed,
                "reason": reason,
                "method": "llm_classification",
                "model": "claude-haiku",
            }

        except Exception as e:
            logger.error(f"Gate classification failed: {e}. Defaulting to PASS.")
            # On error, pass through (fail open — better to waste compute than miss something)
            return {
                "passed": True,
                "reason": f"Classification error, defaulting to pass: {e}",
                "method": "error_fallthrough",
            }
```

---

## 7. Pipeline Orchestrator

```python
# src/pipeline/orchestrator.py
from src.models.trigger import TriggerEvent, TriggerSource, TriggerStatus
from src.pipeline.layer1_triggers.document_fetcher import DocumentFetcher
from src.pipeline.layer1_triggers.text_extractor import TextExtractor
from src.pipeline.layer2_gate.watchlist_filter import WatchlistFilter
from src.pipeline.layer2_gate.gate_classifier import GateClassifier
from src.repositories.base import TriggerRepository, DocumentRepository, VectorRepository
import logging

logger = logging.getLogger(__name__)

class PipelineOrchestrator:
    """
    Runs triggers through the processing pipeline.

    Week 1-2: Layers 1 and 2 only (ingest + gate)
    Week 3: Add Layer 3 (deep analysis)
    Week 4: Add Layers 4 and 5 (decision + report)
    """

    def __init__(
        self,
        trigger_repo: TriggerRepository,
        doc_repo: DocumentRepository,
        vector_repo: VectorRepository,
        document_fetcher: DocumentFetcher,
        text_extractor: TextExtractor,
        watchlist_filter: WatchlistFilter,
        gate_classifier: GateClassifier,
    ):
        self.trigger_repo = trigger_repo
        self.doc_repo = doc_repo
        self.vector_repo = vector_repo
        self.document_fetcher = document_fetcher
        self.text_extractor = text_extractor
        self.watchlist_filter = watchlist_filter
        self.gate_classifier = gate_classifier

    async def process_trigger(self, trigger: TriggerEvent) -> None:
        """Process a single trigger through the pipeline."""

        # --- Layer 1: Document Ingestion ---
        if trigger.source_url and not trigger.document_ids:
            doc = await self.document_fetcher.fetch(
                trigger_id=trigger.trigger_id,
                url=trigger.source_url,
                company_symbol=trigger.company_symbol,
            )
            if doc:
                trigger.document_ids.append(doc.document_id)
                # Extract text
                text = await self.text_extractor.extract(doc)
                if text:
                    # Update trigger content with extracted text
                    trigger.raw_content = f"{trigger.raw_content}\n\n--- Extracted Document ---\n{text}"
                    # Embed in vector store
                    await self.vector_repo.add_document(
                        document_id=doc.document_id,
                        text=text,
                        metadata={
                            "company_symbol": trigger.company_symbol or "",
                            "trigger_id": trigger.trigger_id,
                            "source": trigger.source.value,
                        }
                    )

        # --- Layer 2: Gate ---
        if trigger.source == TriggerSource.HUMAN:
            # Human triggers bypass the gate
            gate_result = {"passed": True, "reason": "Human trigger — auto-pass", "method": "human_bypass"}
        else:
            # Step 1: Watchlist filter (free, instant)
            gate_result = self.watchlist_filter.check(trigger)

            # Step 2: If watchlist passed, run LLM classification
            if gate_result["passed"]:
                llm_result = await self.gate_classifier.classify(trigger)
                gate_result = llm_result  # LLM result overrides

        trigger.gate_result = gate_result
        if gate_result["passed"]:
            await self.trigger_repo.update_status(trigger.trigger_id, TriggerStatus.GATE_PASSED, gate_result["reason"])
        else:
            await self.trigger_repo.update_status(trigger.trigger_id, TriggerStatus.FILTERED_OUT, gate_result["reason"])
            return  # Stop processing

        # --- Layers 3-5: TODO (Weeks 3-4) ---
        logger.info(f"Trigger {trigger.trigger_id} passed gate. Awaiting Layer 3 implementation.")

    async def process_pending_triggers(self) -> int:
        """Process all pending triggers. Called by scheduler."""
        pending = await self.trigger_repo.get_pending(limit=50)
        processed = 0
        for trigger in pending:
            await self.process_trigger(trigger)
            processed += 1
        return processed
```

---

## 8. FastAPI Application Entry Point

```python
# src/main.py
from fastapi import FastAPI
from contextlib import asynccontextmanager
from motor.motor_asyncio import AsyncIOMotorClient
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config import Settings
from src.api import triggers, health
from src.repositories.mongo import MongoTriggerRepository, MongoDocumentRepository
from src.repositories.vector import ChromaVectorRepository
from src.pipeline.orchestrator import PipelineOrchestrator
from src.pipeline.layer1_triggers.rss_poller import NSERSSPoller
from src.pipeline.layer1_triggers.document_fetcher import DocumentFetcher
from src.pipeline.layer1_triggers.text_extractor import TextExtractor
from src.pipeline.layer2_gate.watchlist_filter import WatchlistFilter
from src.pipeline.layer2_gate.gate_classifier import GateClassifier

settings = Settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    mongo_client = AsyncIOMotorClient(settings.mongodb_uri)
    db = mongo_client[settings.mongodb_database]

    # Repositories
    trigger_repo = MongoTriggerRepository(db)
    doc_repo = MongoDocumentRepository(db)
    vector_repo = ChromaVectorRepository(settings.chromadb_persist_dir, settings.embedding_model)

    # Pipeline components
    document_fetcher = DocumentFetcher(doc_repo)
    text_extractor = TextExtractor(doc_repo)
    watchlist_filter = WatchlistFilter("config/watchlist.yaml")
    gate_classifier = GateClassifier(settings.gate_model)

    orchestrator = PipelineOrchestrator(
        trigger_repo=trigger_repo,
        doc_repo=doc_repo,
        vector_repo=vector_repo,
        document_fetcher=document_fetcher,
        text_extractor=text_extractor,
        watchlist_filter=watchlist_filter,
        gate_classifier=gate_classifier,
    )

    rss_poller = NSERSSPoller(trigger_repo, settings.nse_rss_url)

    # Store in app state for dependency injection
    app.state.trigger_repo = trigger_repo
    app.state.orchestrator = orchestrator
    app.state.rss_poller = rss_poller

    # Scheduler
    scheduler = AsyncIOScheduler()
    if settings.polling_enabled:
        scheduler.add_job(
            rss_poller.poll,
            "interval",
            seconds=settings.polling_interval_seconds,
            id="rss_poll",
        )
        scheduler.add_job(
            orchestrator.process_pending_triggers,
            "interval",
            seconds=30,  # Process pending triggers every 30 seconds
            id="process_triggers",
        )
        scheduler.start()

    yield

    # Shutdown
    scheduler.shutdown()
    mongo_client.close()

app = FastAPI(title="tuJanalyst", version="0.1.0", lifespan=lifespan)
app.include_router(triggers.router)
app.include_router(health.router)
```

---

## 9. API Endpoints Summary (Weeks 1-2)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/v1/triggers/human` | Submit human-triggered investigation |
| `GET` | `/api/v1/triggers/{trigger_id}` | Get trigger status |
| `GET` | `/api/v1/triggers/` | List triggers (filterable by status, company) |
| `GET` | `/api/v1/health` | Health check (MongoDB, ChromaDB, scheduler status) |
| `GET` | `/api/v1/health/stats` | System stats (triggers today, gate pass rate, etc.) |

---

## 10. Dependencies (pyproject.toml)

```toml
[project]
name = "tuJanalyst"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    # Web framework
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.27.0",

    # Database
    "motor>=3.3.0",                  # Async MongoDB driver
    "pymongo>=4.6.0",

    # Vector store
    "chromadb>=0.4.22",
    "sentence-transformers>=2.3.0",

    # LLM frameworks
    "pydantic-ai>=0.1.0",
    "dspy-ai>=2.4.0",
    "anthropic>=0.18.0",

    # Document processing
    "pdfplumber>=0.10.0",
    "beautifulsoup4>=4.12.0",

    # HTTP client
    "httpx>=0.27.0",
    "feedparser>=6.0.0",

    # Scheduling
    "apscheduler>=3.10.0",

    # Configuration
    "pydantic-settings>=2.1.0",
    "pyyaml>=6.0",

    # Utilities
    "python-dotenv>=1.0.0",
    "structlog>=24.1.0",            # Structured logging
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.2.0",                  # Linting
    "mypy>=1.8.0",
]
```

---

## 11. Task Breakdown for Team

### Week 1 Tasks

| # | Task | Effort | Dependencies | Owner |
|---|------|--------|-------------|-------|
| 1.1 | Project scaffolding (structure, Docker Compose, pyproject.toml) | 0.5 day | None | Dev A |
| 1.2 | Settings & config loading (Pydantic Settings, YAML) | 0.5 day | 1.1 | Dev A |
| 1.3 | MongoDB connection + repository base classes | 1 day | 1.1 | Dev A |
| 1.4 | TriggerEvent and RawDocument Pydantic models | 0.5 day | None | Dev B |
| 1.5 | MongoTriggerRepository + MongoDocumentRepository implementations | 1 day | 1.3, 1.4 | Dev B |
| 1.6 | NSE RSS poller (fetch, parse, dedup, create triggers) | 1.5 days | 1.5 | Dev A |
| 1.7 | Document fetcher (download, detect type, store) | 1 day | 1.5 | Dev B |
| 1.8 | Text extractor (PDF via pdfplumber, HTML via BeautifulSoup) | 1 day | 1.7 | Dev B |
| 1.9 | Human trigger API endpoint (`POST /api/v1/triggers/human`) | 0.5 day | 1.5 | Dev A |
| 1.10 | Health check endpoint + basic app wiring (main.py, lifespan) | 0.5 day | 1.3, 1.6 | Dev A |
| 1.11 | Tests: repositories, RSS parser, text extractor | 1 day | 1.5-1.8 | Both |

**Week 1 deliverable**: `docker-compose up` starts the app. RSS poller runs on schedule. Documents get downloaded and text extracted. Triggers are stored in MongoDB. Human trigger API works.

### Week 2 Tasks

| # | Task | Effort | Dependencies | Owner |
|---|------|--------|-------------|-------|
| 2.1 | Watchlist YAML schema + WatchlistFilter implementation | 1 day | 1.4 | Dev A |
| 2.2 | DSPy setup + GateClassification signature + GateModule | 1 day | None | Dev B |
| 2.3 | GateClassifier (wraps DSPy module, handles errors, fail-open) | 0.5 day | 2.2 | Dev B |
| 2.4 | ChromaDB VectorRepository implementation | 1 day | None | Dev A |
| 2.5 | Document embedding pipeline (extract → chunk → embed → store) | 1 day | 1.8, 2.4 | Dev A |
| 2.6 | Pipeline orchestrator (wire Layer 1 + Layer 2 together) | 1 day | 2.1, 2.3, 2.5 | Dev B |
| 2.7 | APScheduler integration (poll → process pending → gate) | 0.5 day | 2.6 | Dev B |
| 2.8 | Trigger list API + status filtering | 0.5 day | 1.9 | Dev A |
| 2.9 | Populate initial watchlist (research companies in Capital Goods - Electrical Equipment) | 0.5 day | 2.1 | Either |
| 2.10 | End-to-end test with real NSE data | 1 day | 2.6, 2.7 | Both |
| 2.11 | Tests: watchlist filter, gate module (mocked LLM), vector repo | 1 day | 2.1-2.5 | Both |

**Week 2 deliverable**: Full Layer 1 + Layer 2 working. Triggers come in, get filtered, get classified by LLM, documents get embedded. Team can see trigger statuses via API.

---

## 12. Testing Strategy (Weeks 1-2)

### What to Test

1. **Repository tests**: CRUD operations against a test MongoDB instance (use `mongomock` or a Docker test container)
2. **RSS parser tests**: Parse sample NSE RSS responses (save real responses as fixtures)
3. **Text extractor tests**: Extract text from sample PDFs (include 2-3 real NSE filings as test fixtures)
4. **Watchlist filter tests**: Test company/sector/keyword matching with edge cases
5. **Gate classifier tests**: Mock the DSPy LLM call, test pass/fail logic and error handling
6. **Vector repo tests**: Test embedding + search with ChromaDB (in-memory mode for tests)
7. **Orchestrator tests**: Integration test of the full pipeline with mocked external calls

### Test Fixtures to Collect (Week 1)

Before writing tests, manually collect:
- 5-10 real NSE RSS feed responses (JSON)
- 3-5 real corporate announcement PDFs from INOXWIND, SUZLON, or similar
- 2-3 HTML announcement pages
- Examples of triggers that SHOULD pass the gate (quarterly results, order wins)
- Examples of triggers that should NOT pass (routine compliance filings, board meeting notices with no outcome)

Store these in `tests/fixtures/`.

---

## 13. Key Risks & Mitigations for Weeks 1-2

| Risk | Impact | Mitigation |
|------|--------|------------|
| NSE API changes format or requires auth | Blocks trigger ingestion | Save real API responses as fixtures; design poller to handle format variations; add BSE as backup source |
| NSE blocks automated requests | Blocks trigger ingestion | Implement proper rate limiting, User-Agent rotation; consider using a headless browser as fallback |
| PDF extraction quality varies | Garbage text in analysis | Test with real NSE PDFs early; have fallback OCR (Tesseract) for image-based PDFs |
| DSPy + Pydantic AI version conflicts | Dev environment issues | Pin exact versions in pyproject.toml; test in Docker early |
| ChromaDB performance at scale | Slow search | Not a risk at MVP scale; monitored for later migration trigger |

---

## 14. Open Items for Team Discussion

1. **NSE API access method**: The exact NSE endpoint for corporate announcements needs validation. NSE has changed their API structure before. Someone should manually test the endpoint and document the response format before Week 1 Day 3.

2. **Company watchlist**: The initial list of companies in "Capital Goods - Electrical Equipment" needs to be compiled. Probably 20-40 companies. Someone should pull the current NSE sector classification.

3. **LLM API key**: Need an Anthropic API key with sufficient quota. Estimate ~$5-10/day for development and testing.

4. **Development environment**: Everyone needs Docker, Python 3.11+, and a local MongoDB. Consider using `uv` for fast Python dependency management.

5. **Git workflow**: Suggest trunk-based development for a 2-3 person team. Short-lived feature branches, merge to main daily.
