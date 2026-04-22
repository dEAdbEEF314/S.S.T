# S.S.T Document List & Implementation Alignment Report

This document provides an overview of the existing documentation in the workspace and evaluates its alignment with the current codebase.

## 📊 Document Inventory

### 1. Core & High-Level Docs
| File | Language | Status | Purpose |
| :--- | :--- | :--- | :--- |
| `README.md` | EN | **Authoritative** | Primary source of truth for the current Standalone Edge Model. |
| `docs/00_overview/architecture.md` | EN/JP | **Outdated** | Describes the legacy/initial distributed (Prefect) design. |
| `docs/IMPLEMENTATION_PLAN.md` | EN | **In Progress** | Roadmap (Phase 5 complete, Phase 6 skipped/redefined). |
| `AGENT_GUIDE.md` | EN/JP | **Authoritative** | Workflow guidelines for AI agents. |

### 2. Technical Specifications
| File | Language | Status | Purpose |
| :--- | :--- | :--- | :--- |
| `docs/01_spec/tagging_spec.md` | EN/JP | **Valid** | Rules for ID3 tags and artwork processing. |
| `docs/01_spec/format_spec.md` | EN | **Valid** | Audio conversion constraints (AIFF/MP3). |
| `docs/03_ai/llm_strategy.md` | EN/JP | **Authoritative** | Metadata consolidation logic using LLMs. |
| `docs/schemas/*.json` | JSON | **Valid** | Data contracts (partially used in standalone mode). |

### 3. Execution & Pipeline
| File | Language | Status | Purpose |
| :--- | :--- | :--- | :--- |
| `docs/02_execution/pipeline.md` | EN/JP | **Outdated** | Describes the multi-stage S3-ingest flow. |
| `docs/02_execution/state_machine.md`| EN | **Partial** | High-level states apply, but orchestration differs. |

---

## 🔍 Key Discrepancies (Code vs. Docs)

### 1. Centralized vs. Distributed
- **Doc says**: A distributed system where `Scout` scans, `Core` (Prefect) orchestrates, and `Worker` processes.
- **Code does**: A standalone application (`scout/main.py`) that performs scanning, LLM consolidation, conversion, and tagging in a single local pipeline.
- **Impact**: `core/` directory is currently empty. The "Worker" logic is integrated into `scout/src/scout/processor.py`.

### 2. Data Flow
- **Doc says**: Local -> S3 (Ingest) -> Worker -> S3 (Archive).
- **Code does**: Local Scan -> Local Process (LLM/FFmpeg) -> S3 Upload & Local ZIP.
- **Impact**: S3 (SeaweedFS) is now used for archival and UI display rather than as an intermediary processing buffer.

### 3. Implementation Roadmap
- **Status**: According to `IMPLEMENTATION_PLAN.md`, the project is at Phase 5 (LLM Integration). Phase 6 (Orchestration/Prefect) was bypassed in favor of the standalone model to optimize local execution.

---

## 💡 Recommendations

1.  **Update Architecture Docs**: Revise `docs/00_overview/architecture.md` to reflect the Standalone Edge Model.
2.  **Synchronize Pipeline Docs**: Update `docs/02_execution/pipeline.md` to match the current synchronous local flow.
3.  **Core Directory**: Either populate `core/` with shared utilities or remove/rename it if the standalone model remains the permanent choice.
4.  **Tagging Consistency**: Ensure `scout/tagger.py` continues to strictly follow `tagging_spec.md` as new features (like Parent Game metadata) are added.
