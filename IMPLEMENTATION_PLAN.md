# SST Implementation Plan

This document defines a **step-by-step implementation roadmap** for SST.

It is designed for **AI-driven execution**.

---

# 🧭 Execution Principles

- Follow `CONTRIBUTING.md`
- Follow `AGENT_GUIDE.md`
- Respect all specs in `docs/`
- Never skip validation
- Always produce testable outputs

---

# 🏗️ Phase Overview

| Phase | Goal |
|------|------|
| Phase 0 | Project setup |
| Phase 1 | Core I/O + data model |
| Phase 2 | Identification pipeline |
| Phase 3 | External integrations |
| Phase 4 | Tagging + format conversion |
| Phase 5 | LLM integration |
| Phase 6 | Orchestration (Prefect) |
| Phase 7 | Reliability + retry |
| Phase 8 | Validation + QA |

---

# 🧩 Phase 0: Project Setup

## Tasks

- Create project structure
- Setup Python 3.11+
- Setup dependency manager (uv)
- Setup Docker environment
- Prepare config loader

## Output

- runnable dev environment

---

# 🧩 Phase 1: Core I/O Layer

## Tasks

- Implement worker input parser
- Implement worker output builder
- Implement JSON schema validation

## Requirements

- Must match:
  - `worker_input.schema.json`
  - `worker_output.schema.json`

## Output

- Validated input/output module

---

# 🧩 Phase 2: Identification Pipeline (Core)

## Tasks

- Implement pipeline controller
- Implement step execution order
- Implement state transitions

## Must Follow

- `docs/02_execution/pipeline.md`
- `docs/02_execution/state_machine.md`

## Output

- Deterministic pipeline executor

---

# 🧩 Phase 3: External Integrations

## Tasks

### VGMdb Client
- Use hufman/vgmdb as base implementation
- Wrap with retry + normalization layer
- Retry logic
- Response normalization

### MusicBrainz Client
- Search + lookup
- Rate limit handling

### Steam Metadata
- Fetch title / release date

## Output

- Unified metadata interface

---

# 🧩 Phase 4: Tagging + Format Conversion

## Tasks

- Implement format conversion
- Implement tagging writer (ID3v2.3)
- Implement artwork embedding

## Must Follow

- `docs/01_spec/tagging_spec.md`
- `docs/01_spec/format_spec.md`

## Output

- Tagged audio output

---

# 🧩 Phase 5: LLM Integration

## Tasks

- Implement LLM client abstraction
- Implement dual-provider comparison
- Implement similarity scoring

## Must Follow

- `docs/03_ai/llm_strategy.md`

## Output

- Reliable normalization module

---

# 🧩 Phase 6: Orchestration (Prefect)

## Tasks

- Define Prefect flow
- Define task boundaries
- Implement retries

## Output

- End-to-end automated flow

---

# 🧩 Phase 7: Reliability Layer

## Tasks

- Implement retry strategy
- Implement error classification
- Implement fallback logic

## Must Follow

- `docs/02_execution/retry_strategy.md`

---

# 🧩 Phase 8: Validation & QA

## Tasks

- JSON schema validation
- End-to-end test cases
- Failure scenario tests

## Required Tests

- success case
- fallback case
- review case
- API failure case

---

# 🧪 Deliverable Requirements

Each phase must produce:

- working code
- test cases
- logs
- schema-compliant output

---

# 🧠 Task Execution Rule (IMPORTANT)

Each task must be:

- small (1 responsibility)
- testable
- reversible

---

# 🔁 Iteration Strategy

- Implement minimal → validate → extend
- Never implement everything at once

---

# 🚫 Anti-Patterns

- Big-bang implementation
- Skipping schema validation
- Ignoring confidence thresholds
- Mixing responsibilities

---

# 🔚 Final Goal

A system that:

- correctly identifies ≥90%
- never silently fails
- isolates uncertainty into review