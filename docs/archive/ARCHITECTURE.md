# SST Architecture

---

## 1. System Overview

SST is a **distributed, orchestrated, multi-node pipeline system**.

It is designed to run across multiple machines and containers, coordinated by Prefect.

---

## 2. Physical Infrastructure

### Nodes

* SST-Scout-VM (Ubuntu Desktop + Docker)
* SST-Core-VM (Ubuntu Server + Docker)
* SST-Worker-CT (Container, USB-SSD mounted)
* M2 MacBook Air (AI / LLM support)

> [!NOTE]
> **About the Scout VM environment**
> Scout VM maintains an Ubuntu Desktop (GUI) environment for manual intervention such as debugging AI agents, running in Headed mode to avoid bot protection, and resolving CAPTCHAs, in addition to resolution via API.

---

## 3. System Architecture

```text
[Scout VM]
   ↓
[Prefect Flow (Core VM)]
   ↓
[Worker Containers]
   ↓
[SeaweedFS S3 Storage]
```

---

## 4. Roles

### Scout VM

* Web metadata resolution (API & CDDB)
* VGMdb proxy (`hufman/vgmdb` Docker container)
* Browser automation for authentication (Playwright Headed Mode)
* Fallback browser automation (browser-use)
* Manual review / Captcha solving

---

### Core VM

* Prefect orchestration
* Flow control
* State tracking

---

### Worker Containers

* Audio processing
* AcoustID matching
* Tag writing

---

### LLM Node (M2 Mac or others)

* Multi-backend LLM inference via API
* Communication method: **OpenAI API compatible format** as standard (using Python `openai` library)
* Default: Ollama (local inference)
*Selectable: Gemini API, OpenAI API
* Role: Metadata inconsistency resolution, search result scoring, complex HTML parsing

---

## 5. Orchestration (Prefect)

Prefect manages:

* Task execution order
* Retry logic
* State transitions
* Observability

---

## 6. Data Flow

1. Scout collects metadata
2. Core schedules flow
3. Workers process tasks
4. Results stored in SeaweedFS

---

## 7. Storage

SeaweedFS (S3-compatible)

```text
buckets/
 └─ sst/
     ├─ ingest/
     ├─ archive/
     ├─ review/
     └─ processed/
```

---

## 8. Parallelism

* Prefect task-level parallel execution
* Multiple workers per task

---

## 9. Design Principles

* Orchestration-first
* Node separation
* Fault tolerance
* Reproducibility

---

# END
