# SST (Steam Soundtrack Tagger)

This document defines the **core concept and navigation root** of SST.

---

## Overview

- ./00_overview/README.md
- ./00_overview/architecture.md
- ./00_overview/quick_start.md

---

## Specification

- I/O: ./01_spec/io_spec.md
- Tagging: ./01_spec/tagging_spec.md
- Format: ./01_spec/format_spec.md
- Config: ./01_spec/config_spec.md

---

## Execution

- Pipeline: ./02_execution/pipeline.md
- State Machine: ./02_execution/state_machine.md
- Identification: ./02_execution/identification_strategy.md
- Retry: ./02_execution/retry_strategy.md

---

## AI / LLM

- ./03_ai/llm_strategy.md
- ./03_ai/agent_prompt.md
- ./03_ai/success_criteria.md

---

## Infrastructure

- ./04_infra/infrastructure.md

---

## Notes

SST.md is the conceptual root.

All implementation MUST follow:
- spec (strict)
- execution rules (strict)
- AI validation rules (strict)

Ambiguity must be resolved toward **accuracy over speed**.
