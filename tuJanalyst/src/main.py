"""tuJanalyst — FastAPI application entry point."""

import logging
import logging.config
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI

logger = logging.getLogger(__name__)


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
        logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    setup_logging()
    logger.info("tuJanalyst starting up...")

    # TODO (T-102): Load settings and validate
    # TODO (T-103): Initialize MongoDB connection
    # TODO (T-108): Initialize ChromaDB client
    # TODO (T-105): Start RSS polling scheduler

    logger.info("tuJanalyst ready.")
    yield

    # Shutdown
    logger.info("tuJanalyst shutting down...")
    # TODO: Close DB connections, stop scheduler


app = FastAPI(
    title="tuJanalyst",
    description="AI-powered stock analysis system for NSE/BSE listed companies",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy", "version": "0.1.0"}
