"""tuJanalyst — FastAPI application entry point."""

import logging
import logging.config
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from src.agents.tools import MarketDataTool, TickerWebLookup, WebSearchTool
from src.agents.tools.stockpulse_client import StockPulseClient
from src.agents.tools.sector_pulse import SectorPulseTool
from src.agents.tools.stockpulse_data import StockPulseDataTool
from src.integrations.stockpulse_notifier import StockPulseNotifier
from src.api import (
    costs,
    health,
    investigations,
    notes,
    notifications,
    performance,
    positions,
    reports,
    symbols,
    triggers,
    watchlist,
)
from src.config import get_settings, load_watchlist_config
from src.logging_setup import configure_structured_logging
from src.pipeline.layer1_triggers.document_fetcher import DocumentFetcher
from src.pipeline.layer1_triggers.dspy_ticker_fallback import DspyTickerFallbackResolver
from src.pipeline.layer1_triggers.rss_poller import ExchangeRSSPoller
from src.pipeline.layer1_triggers.symbol_master_sync import SymbolMasterSync
from src.pipeline.layer1_triggers.ticker_resolver import TickerResolver
from src.pipeline.layer1_triggers.text_extractor import TextExtractor
from src.pipeline.layer2_gate.gate_classifier import GateClassifier
from src.pipeline.layer2_gate.watchlist_filter import WatchlistFilter
from src.pipeline.layer3_analysis import DeepAnalyzer
from src.pipeline.layer4_decision import DecisionAssessor
from src.pipeline.layer5_report import ReportDeliverer, ReportGenerator
from src.pipeline.orchestrator import PipelineOrchestrator
from src.repositories import (
    ChromaVectorRepository,
    MongoAssessmentRepository,
    MongoCompanyMasterRepository,
    MongoInvestigationRepository,
    MongoPositionRepository,
    MongoReportRepository,
)
from src.repositories.mongo import (
    MongoDocumentRepository,
    MongoTriggerRepository,
    create_mongo_client,
    ensure_indexes,
    get_database,
)
from src.repositories.performance_repo import MongoPerformanceRepository
from src.services.performance_tracker import PerformanceTracker

logger = logging.getLogger(__name__)
_TRIGGER_PROCESSOR_BATCH_LIMIT = 5


class _NoopWebSearchTool:
    """Fallback web-search tool when enrichment is disabled."""

    async def search(self, query: str, *, max_results: int | None = None) -> list[dict[str, str]]:
        del query, max_results
        return []

    async def close(self) -> None:
        return None


def setup_logging() -> None:
    """Load logging configuration from YAML."""
    log_config_path = Path("config/logging.yaml")
    if log_config_path.exists():
        with open(log_config_path) as f:
            config = yaml.safe_load(f)
        # Ensure log directory exists
        Path("data").mkdir(exist_ok=True)
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
    configure_structured_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    setup_logging()
    logger.info("tuJanalyst starting up...")
    mongo_client = None
    scheduler: AsyncIOScheduler | None = None
    web_search_tool: WebSearchTool | _NoopWebSearchTool | None = None
    stockpulse_client: StockPulseClient | None = None

    try:
        # T-102: fail-fast config validation at startup
        settings = get_settings()
        watchlist = load_watchlist_config(settings.watchlist_config_path)
        logger.info(
            "Configuration loaded successfully (provider=%s, companies=%s, sectors=%s).",
            settings.llm_provider,
            len(watchlist.companies),
            len(watchlist.sectors),
        )

        # T-104: initialize and verify MongoDB connection + indexes
        mongo_client = await create_mongo_client(settings.mongodb_uri)
        mongo_db = get_database(mongo_client, settings.mongodb_database)
        await ensure_indexes(mongo_db)
        app.state.mongo_client = mongo_client
        app.state.mongo_db = mongo_db
        app.state.settings = settings
        app.state.watchlist = watchlist
        app.state.watchlist_path = str(settings.watchlist_config_path)
        app.state.watchlist_loaded_at = datetime.now(UTC)
        app.state.agent_policy_path = os.getenv("TUJ_AGENT_POLICY_PATH", "config/agent_access_policy.yaml")

        trigger_repo = MongoTriggerRepository(mongo_db)
        document_repo = MongoDocumentRepository(mongo_db)
        investigation_repo = MongoInvestigationRepository(mongo_db)
        assessment_repo = MongoAssessmentRepository(mongo_db)
        position_repo = MongoPositionRepository(mongo_db)
        report_repo = MongoReportRepository(mongo_db)
        company_master_repo = MongoCompanyMasterRepository(mongo_db)
        performance_repo = MongoPerformanceRepository(mongo_db)
        await performance_repo.ensure_indexes()
        vector_repo = ChromaVectorRepository(
            persist_dir=settings.chromadb_persist_dir,
            embedding_model=settings.embedding_model,
        )
        symbol_master_sync = SymbolMasterSync(company_master_repo=company_master_repo)
        try:
            upserted = await symbol_master_sync.sync_from_seed(settings.symbol_master_seed_path)
            logger.info("Loaded company master seed rows: count=%s", upserted)
        except FileNotFoundError:
            logger.warning("Company master seed file missing: %s", settings.symbol_master_seed_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed loading company master seed: %s", exc)
        try:
            synced_rows = await symbol_master_sync.sync_from_exchange_sources(
                nse_url=settings.symbol_master_nse_source_url,
                bse_url=settings.symbol_master_bse_source_url,
            )
            if synced_rows:
                logger.info("Synced company master rows from exchange sources: count=%s", synced_rows)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed exchange-source company master sync: %s", exc)

        if settings.web_search_provider == "brave":
            web_search_tool = WebSearchTool(
                provider="brave",
                api_key=settings.brave_api_key or "",
                max_results=settings.web_search_max_results,
                timeout_seconds=settings.web_search_timeout_seconds,
                circuit_breaker_failure_threshold=settings.web_search_circuit_breaker_failure_threshold,
                circuit_breaker_recovery_seconds=settings.web_search_circuit_breaker_recovery_seconds,
            )
        elif settings.web_search_provider == "tavily":
            web_search_tool = WebSearchTool(
                provider="tavily",
                api_key=settings.tavily_api_key or "",
                max_results=settings.web_search_max_results,
                timeout_seconds=settings.web_search_timeout_seconds,
                circuit_breaker_failure_threshold=settings.web_search_circuit_breaker_failure_threshold,
                circuit_breaker_recovery_seconds=settings.web_search_circuit_breaker_recovery_seconds,
            )
        else:
            web_search_tool = _NoopWebSearchTool()

        # StockPulse integration (optional - graceful degradation if not configured)
        stockpulse_data_tool: StockPulseDataTool | None = None
        if settings.stockpulse_base_url and settings.stockpulse_api_key:
            stockpulse_client = StockPulseClient(
                base_url=settings.stockpulse_base_url,
                api_key=settings.stockpulse_api_key,
                timeout_seconds=settings.stockpulse_timeout_seconds,
                circuit_breaker_failure_threshold=settings.stockpulse_circuit_breaker_failure_threshold,
                circuit_breaker_recovery_seconds=settings.stockpulse_circuit_breaker_recovery_seconds,
            )
            stockpulse_data_tool = StockPulseDataTool(client=stockpulse_client)
            logger.info("StockPulse integration enabled: %s", settings.stockpulse_base_url)
        else:
            logger.info("StockPulse integration disabled (TUJ_STOCKPULSE_BASE_URL not configured)")

        sector_pulse_tool: SectorPulseTool | None = None
        if stockpulse_client:
            sector_pulse_tool = SectorPulseTool(client=stockpulse_client)

        stockpulse_notifier = None
        if stockpulse_client:
            stockpulse_notifier = StockPulseNotifier(client=stockpulse_client)

        performance_tracker: PerformanceTracker | None = None
        if stockpulse_client:
            performance_tracker = PerformanceTracker(
                repo=performance_repo,
                stockpulse_client=stockpulse_client,
            )
            logger.info("Performance tracker enabled.")
        else:
            logger.info("Performance tracker disabled (StockPulse client not configured).")

        ticker_web_lookup = None
        if settings.enable_symbol_web_fallback and not isinstance(web_search_tool, _NoopWebSearchTool):
            ticker_web_lookup = TickerWebLookup(search_tool=web_search_tool)
        dspy_ticker_resolver = None
        if settings.enable_symbol_dspy_fallback:
            try:
                dspy_ticker_resolver = DspyTickerFallbackResolver(
                    provider=settings.llm_provider,
                    model=settings.symbol_resolution_model or settings.gate_model,
                    api_key=settings.resolved_llm_api_key,
                    base_url=settings.llm_base_url,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to initialize DSPy ticker fallback resolver: %s", exc)
        ticker_resolver = TickerResolver(
            company_master_repo=company_master_repo,
            web_lookup=ticker_web_lookup,
            dspy_resolver=dspy_ticker_resolver,
            fuzzy_threshold=settings.symbol_fuzzy_threshold,
            review_threshold=settings.symbol_review_threshold,
            enable_web_fallback=settings.enable_symbol_web_fallback,
            enable_dspy_fallback=settings.enable_symbol_dspy_fallback,
        )
        document_fetcher = DocumentFetcher(
            doc_repo=document_repo,
            max_size_mb=settings.max_document_size_mb,
        )
        text_extractor = TextExtractor(
            doc_repo=document_repo,
            vector_repo=vector_repo,
            extraction_timeout_seconds=float(settings.text_extraction_timeout_seconds),
        )
        watchlist_filter = WatchlistFilter(str(settings.watchlist_config_path))
        gate_classifier = GateClassifier(
            model=settings.gate_model,
            provider=settings.llm_provider,
            api_key=settings.resolved_llm_api_key,
            base_url=settings.llm_base_url,
        )
        market_data_tool: MarketDataTool | None = None
        deep_analyzer: DeepAnalyzer | None = None
        decision_assessor: DecisionAssessor | None = None
        report_generator: ReportGenerator | None = None
        report_deliverer: ReportDeliverer | None = None

        if settings.enable_layer3_analysis:
            market_data_tool = MarketDataTool(
                circuit_breaker_failure_threshold=settings.market_data_circuit_breaker_failure_threshold,
                circuit_breaker_recovery_seconds=settings.market_data_circuit_breaker_recovery_seconds,
            )
            deep_analyzer = DeepAnalyzer(
                investigation_repo=investigation_repo,
                vector_repo=vector_repo,
                doc_repo=document_repo,
                web_search=web_search_tool,
                market_data=market_data_tool,
                model_name=settings.analysis_model,
                stockpulse_data=stockpulse_data_tool,
                sector_pulse_tool=sector_pulse_tool,
            )
        else:
            logger.info("Layer 3 analysis disabled by configuration.")

        if settings.enable_layer4_decision and deep_analyzer is not None:
            decision_assessor = DecisionAssessor(
                assessment_repo=assessment_repo,
                investigation_repo=investigation_repo,
                position_repo=position_repo,
                model_name=settings.decision_model,
            )
        elif settings.enable_layer4_decision:
            logger.warning("Layer 4 decision enabled but Layer 3 is unavailable; skipping Layer 4.")
        else:
            logger.info("Layer 4 decision disabled by configuration.")

        if settings.enable_layer5_reporting and decision_assessor is not None:
            report_generator = ReportGenerator(
                report_repo=report_repo,
                model_name=settings.analysis_model,
            )
            smtp_config = {}
            if settings.notification_method == "email":
                smtp_config = {
                    "host": settings.smtp_host,
                    "port": settings.smtp_port,
                    "to": settings.notification_email,
                }
            report_deliverer = ReportDeliverer(
                slack_webhook_url=settings.slack_webhook_url if settings.notification_method == "slack" else None,
                smtp_config=smtp_config,
                report_repo=report_repo,
            )
        elif settings.enable_layer5_reporting:
            logger.warning("Layer 5 reporting enabled but Layer 4 is unavailable; skipping Layer 5.")
        else:
            logger.info("Layer 5 reporting disabled by configuration.")
        orchestrator = PipelineOrchestrator(
            trigger_repo=trigger_repo,
            doc_repo=document_repo,
            vector_repo=vector_repo,
            document_fetcher=document_fetcher,
            text_extractor=text_extractor,
            watchlist_filter=watchlist_filter,
            gate_classifier=gate_classifier,
            deep_analyzer=deep_analyzer,
            decision_assessor=decision_assessor,
            report_generator=report_generator,
            report_deliverer=report_deliverer,
            report_repo=report_repo,
            stockpulse_notifier=stockpulse_notifier,
            stockpulse_data_tool=stockpulse_data_tool,
            performance_tracker=performance_tracker,
        )
        app.state.trigger_repo = trigger_repo
        app.state.document_repo = document_repo
        app.state.investigation_repo = investigation_repo
        app.state.assessment_repo = assessment_repo
        app.state.position_repo = position_repo
        app.state.report_repo = report_repo
        app.state.company_master_repo = company_master_repo
        app.state.vector_repo = vector_repo
        app.state.orchestrator = orchestrator
        app.state.document_fetcher = document_fetcher
        app.state.text_extractor = text_extractor
        app.state.watchlist_filter = watchlist_filter
        app.state.gate_classifier = gate_classifier
        app.state.web_search_tool = web_search_tool
        app.state.market_data_tool = market_data_tool
        app.state.stockpulse_client = stockpulse_client
        app.state.stockpulse_data_tool = stockpulse_data_tool
        app.state.deep_analyzer = deep_analyzer
        app.state.decision_assessor = decision_assessor
        app.state.report_generator = report_generator
        app.state.report_deliverer = report_deliverer
        app.state.ticker_resolver = ticker_resolver
        app.state.symbol_master_sync = symbol_master_sync
        app.state.performance_repo = performance_repo
        app.state.performance_tracker = performance_tracker

        app.state.rss_poller = ExchangeRSSPoller(
            trigger_repo=trigger_repo,
            nse_url=settings.nse_rss_url,
            bse_url=settings.bse_rss_url,
            ticker_resolver=ticker_resolver,
            dedup_cache_ttl_seconds=settings.rss_dedup_cache_ttl_seconds,
            dedup_lookback_days=settings.rss_dedup_lookback_days,
            dedup_recent_limit=settings.rss_dedup_recent_limit,
        )

        scheduler = AsyncIOScheduler()
        app.state.scheduler = scheduler
        if settings.polling_enabled:
            if settings.symbol_master_refresh_enabled:
                scheduler.add_job(
                    symbol_master_sync.sync_from_exchange_sources,
                    trigger="interval",
                    hours=settings.symbol_master_refresh_interval_hours,
                    kwargs={
                        "nse_url": settings.symbol_master_nse_source_url,
                        "bse_url": settings.symbol_master_bse_source_url,
                    },
                    id="symbol_master_refresh",
                    replace_existing=True,
                    coalesce=True,
                    max_instances=1,
                )
            scheduler.add_job(
                app.state.rss_poller.poll,
                trigger="interval",
                seconds=settings.polling_interval_seconds,
                id="rss_poller",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
            )
            scheduler.add_job(
                orchestrator.process_pending_triggers,
                trigger="interval",
                seconds=30,
                kwargs={"limit": _TRIGGER_PROCESSOR_BATCH_LIMIT},
                id="trigger_processor",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
            )
            if performance_tracker is not None:
                scheduler.add_job(
                    performance_tracker.update_checkpoints,
                    trigger="cron",
                    hour=11,
                    minute=30,
                    timezone="UTC",
                    id="performance_checkpoint_updater",
                    replace_existing=True,
                    coalesce=True,
                    max_instances=1,
                )
                logger.info("Performance checkpoint updater scheduled daily at 17:00 IST (11:30 UTC).")
            scheduler.start()
            logger.info(
                "Scheduler started (rss_interval=%ss trigger_processor_interval=30s).",
                settings.polling_interval_seconds,
            )
        else:
            logger.info("Scheduler initialization skipped because polling is disabled.")

        logger.info("MongoDB connection established, repositories and pipeline components initialized.")

        logger.info("tuJanalyst ready.")
        yield
    finally:
        # Shutdown
        logger.info("tuJanalyst shutting down...")
        if scheduler is not None and scheduler.running:
            scheduler.shutdown(wait=False)
        if stockpulse_client is not None:
            await stockpulse_client.close()
        if web_search_tool is not None:
            await web_search_tool.close()
        if mongo_client is not None:
            mongo_client.close()


app = FastAPI(
    title="tuJanalyst",
    description="AI-powered stock analysis system for NSE/BSE listed companies",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(triggers.router)
app.include_router(health.router)
app.include_router(costs.router)
app.include_router(performance.router)
app.include_router(notes.router)
app.include_router(notifications.router)
app.include_router(symbols.router)
app.include_router(watchlist.router)
app.include_router(investigations.router)
app.include_router(reports.router)
app.include_router(positions.router)


@app.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy", "version": "0.1.0"}
