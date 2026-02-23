# ADR-002: Background Task Scheduler

| Field | Value |
|-------|-------|
| **Status** | Open |
| **Owner** | TBD |
| **Decision needed by** | Week 1 (T-105: RSS Poller depends on this) |
| **Affects tasks** | T-105, T-106, T-108 |

## Context

The RSS poller needs to run on a schedule (every 5 minutes during market hours). We need a mechanism for recurring background tasks.

## Options

### Option A: APScheduler (Recommended in MVP Definition)
- Runs in-process with FastAPI (no extra infrastructure)
- Simple API: `scheduler.add_job(poll_rss, 'interval', seconds=300)`
- Cron-like scheduling supported
- No message broker needed
- Limitation: tasks don't survive process crashes (no persistence by default)
- Limitation: single-process only (can't distribute across workers)

### Option B: Celery + Redis
- Battle-tested for production task queues
- Persistent: tasks survive crashes, retries built in
- Distributed: can run multiple workers
- Overhead: requires Redis container, Celery worker process, configuration
- Overkill for MVP scale (one poller, one pipeline)

### Option C: Simple asyncio background task in FastAPI
- Zero dependency: `asyncio.create_task()` in the lifespan handler
- Most lightweight option
- No scheduling DSL — you write the loop yourself
- Fragile: no retry logic, no monitoring

## Recommendation

APScheduler for MVP. It's the right balance — scheduling DSL without infrastructure overhead. If task reliability becomes an issue during live testing (Week 6), evaluate Celery.

## Decision

_Not yet decided. Must be resolved before T-105 implementation._
