"""FastAPI route modules."""

from src.api import health, investigations, positions, reports, triggers

__all__ = ["health", "investigations", "positions", "reports", "triggers"]
