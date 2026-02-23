# ADR-001: Dashboard UI Framework

| Field | Value |
|-------|-------|
| **Status** | Open |
| **Owner** | TBD |
| **Decision needed by** | Week 5 start (before dashboard work begins) |
| **Affects tasks** | T-501, T-502, T-503, T-504, T-505 |

## Context

The MVP needs an internal dashboard for viewing triggers, investigations, reports, and submitting human triggers. The MVP Definition lists two options: Streamlit or FastAPI + HTMX.

## Options

### Option A: Streamlit (Recommended in MVP Definition)
- Fastest to build (~hours for a functional dashboard)
- Built-in data tables, charts, forms
- Runs as a separate process (port 8501)
- Limited customization, opinionated layout
- Deployment quirk: needs its own container or process in docker-compose

### Option B: FastAPI + Jinja2 + HTMX
- Runs in the same FastAPI process (no extra container)
- Full control over layout and behavior
- HTMX gives SPA-like interactivity with minimal JS
- More work upfront but cleaner architecture
- Easier to extend toward a React frontend later (API already exists)

### Option C: Skip dashboard entirely for MVP
- Use API endpoints + curl/Postman for demo
- Saves a full week of effort
- Risk: team can't evaluate report quality without a usable interface

## Recommendation

Streamlit for speed. The dashboard is a Week 5-6 concern and the team is small. Migration to React is planned for Iteration 3 regardless.

## Decision

_Not yet decided. To be resolved before Week 5._
