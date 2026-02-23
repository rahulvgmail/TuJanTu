# tuJanalyst — Document Index

> **Single source of truth for what each document means and how they relate.**
> Updated: 2026-02-23

---

## Document Hierarchy

```
                    ┌──────────────────────┐
                    │   North Star Vision   │  ← WHERE WE'RE GOING (long-term)
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   MVP Definition      │  ← WHAT WE'RE BUILDING (scope boundary)
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                 │
   ┌──────────▼─────┐ ┌───────▼───────┐ ┌──────▼──────────┐
   │  Tech Decisions │ │  Tech Specs   │ │  Project Plan   │
   │  (ADRs)         │ │  (Weeks 1-4)  │ │  (living truth) │
   └────────────────┘ └───────────────┘ └─────────────────┘
```

### Tier 1: Vision (read for context, not for build decisions)
| Document | Purpose | Authority |
|----------|---------|-----------|
| **North Star Vision** | Long-term product direction, iteration roadmap, full architecture | Defines what's *possible*, not what's *next* |

### Tier 2: Scope (the MVP contract)
| Document | Purpose | Authority |
|----------|---------|-----------|
| **MVP Definition** | What's IN and OUT of MVP scope, success criteria, cost estimates | **Final word on scope**. If it says "not in MVP", it's not in MVP. |
| **MVP Acceptance Checklist** | Measurable pass/fail criteria for Week 6 sign-off | Gate for declaring MVP "done" |

### Tier 3: Build Truth (what devs code against)
| Document | Purpose | Authority |
|----------|---------|-----------|
| **Technology Decisions** | Rationale for stack choices (Pydantic AI, DSPy, MongoDB, etc.) | Why we chose what we chose. Consult before proposing alternatives. |
| **Technical Spec — Weeks 1-2** | Data models, APIs, repo layer, Layer 1-2 implementation | **Code-level spec** for Weeks 1-2 tasks |
| **Technical Spec — Weeks 3-4** | DSPy modules, Layer 3-5 implementation, evaluation | **Code-level spec** for Weeks 3-4 tasks |
| **PROJECT_PLAN.md** | Task IDs, status, DoD, prerequisites, testing steps | **Living truth**. Updated per merged PR. |
| **ADRs** (`docs/adr/`) | Individual architecture decision records | One ADR per open decision, with owner + date |

### Tier 4: Reference / Archived
| Document | Purpose | Status |
|----------|---------|--------|
| **Brain Dump** | Original product vision transcription | Reference only — ideas absorbed into North Star + MVP Definition |
| ~~Business Requirements Document~~ | Original BRD (20-microservice design) | **⚠️ ARCHIVED** — superseded by MVP Definition |
| ~~Architecture Doc~~ | Original architecture (Kafka, Neptune, EKS) | **⚠️ ARCHIVED** — superseded by Tech Decisions + Tech Specs |
| ~~Planning Discussion~~ | Original agent architecture discussion | **⚠️ ARCHIVED** — superseded by Tech Decisions §4 |

---

## Rules

1. **Scope disputes** → MVP Definition wins.
2. **Technology disputes** → Technology Decisions wins. To change a decision, write an ADR.
3. **Implementation questions** → Technical Specs win. If the spec is silent, check MVP Definition for scope, then decide and document in an ADR.
4. **Task status** → PROJECT_PLAN.md is the single source. Update it when merging PRs.
5. **Archived docs** → Do not reference for build decisions. They exist for historical context only.
