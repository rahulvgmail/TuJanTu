# ADR-006: Extract Dashboard into a Separate Top-Level App

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Owner** | Rahul |
| **Date** | 2026-03-07 |
| **Affects** | `tuJanalyst/src/dashboard/`, `docker-compose.yml`, repo structure |

## Context

The TuJan repo is structured as a monorepo that can host multiple apps:

```
TuJan/
├── tuJanalyst/          <- backend (FastAPI + analysis pipeline)
└── (future apps)
```

The Streamlit dashboard currently lives inside `tuJanalyst/src/dashboard/` (3 source files, ~955 lines) with its tests in `tuJanalyst/tests/test_dashboard/`. However, the dashboard is already architecturally independent from the backend:

1. **Separate process** — runs as its own container on port 8501, does not share the FastAPI process.
2. **API-only coupling** — communicates with the backend exclusively via HTTP (`httpx` calls to `/api/v1/*`). No shared imports from `src.models`, `src.pipeline`, or any backend module.
3. **Separate dependency profile** — needs `streamlit` + `httpx` but none of the backend's ML/pipeline dependencies (DSPy, Pydantic AI, MongoDB drivers, etc.).
4. **Planned migration** — per ADR-001, the UI will migrate to React in a future iteration, which will require its own project structure (`package.json`, build tooling, etc.).

Despite this independence, the dashboard currently:
- Ships inside the backend's Docker image (unnecessarily bloating it with `streamlit`).
- Lives under `tuJanalyst/src/`, implying it is part of the backend package.
- Cannot have its own `pyproject.toml`, Dockerfile, or dependency set.

## Decision

Extract the dashboard into a separate top-level app within the TuJan monorepo.

### Target structure

```
TuJan/
├── tuJanalyst/                  <- backend (unchanged)
│   ├── src/
│   ├── tests/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── docker-compose.yml       <- updated: dashboard service points to ../tuJanDashboard
│
├── tuJanDashboard/              <- new top-level app
│   ├── app.py                   <- from src/dashboard/app.py
│   ├── manual_trigger_utils.py  <- from src/dashboard/manual_trigger_utils.py
│   ├── recommendation_utils.py  <- from src/dashboard/recommendation_utils.py
│   ├── tests/
│   │   ├── test_manual_trigger_utils.py
│   │   └── test_recommendation_utils.py
│   ├── Dockerfile               <- lightweight image (streamlit + httpx only)
│   ├── pyproject.toml            <- own dependencies
│   └── README.md
```

### Migration steps

1. Create `tuJanDashboard/` at the repo root with its own `pyproject.toml` and `Dockerfile`.
2. Move the 3 source files from `tuJanalyst/src/dashboard/` and update imports (change `from src.dashboard.` to local imports).
3. Move test files from `tuJanalyst/tests/test_dashboard/` into `tuJanDashboard/tests/`.
4. Update `tuJanalyst/docker-compose.yml` — change the `dashboard` service build context to `../tuJanDashboard`.
5. Remove `streamlit` from `tuJanalyst/pyproject.toml` dependencies.
6. Delete the now-empty `tuJanalyst/src/dashboard/` directory.

## Rationale

- **Separation of concerns** — the dashboard is a consumer of the API, not part of the backend.
- **Smaller backend image** — removing `streamlit` and its transitive dependencies reduces the backend Docker image.
- **Independent iteration** — the dashboard can be versioned, deployed, and tested independently.
- **Smoother React migration** — when the React frontend replaces Streamlit, it drops into the same `tuJanDashboard/` slot without touching the backend at all.
- **Monorepo consistency** — follows the pattern of separate top-level apps under `TuJan/`, which was the intended repo structure.

## Risks

- **Docker Compose paths** — the `dashboard` service build context changes from `.` to `../tuJanDashboard`. Needs testing.
- **CI updates** — any CI jobs that run dashboard tests will need path updates.
- **Minimal code change** — the only code change is updating 2 import paths in `app.py` (from `src.dashboard.X` to local `.X`). Low risk.
