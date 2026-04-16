# Architecture

## Components

- **Scout Container**: Scans local Steam library and uploads to ingest.
- **Core Container (Prefect)**: Manages workflow, state, and retries.
- **Worker Containers**: Perform the actual identification, tagging, and conversion tasks.
- **LLM Node (Containerized API)**: Provides metadata normalization services.
- **Storage (SeaweedFS/S3)**: Independent S3-compatible storage service.

---

## Flow

Scout Container → ingest → Worker Container → archive/review

---

## Description

### Scout Container
- Scans Steam library (local filesystem access required)
- Parses ACF files
- Fetches enriched metadata (Developer, Publisher, Genre) from Steam Store API
- Collects soundtrack files
- Uploads to ingest storage

### Core Container
- Runs Prefect orchestration
- Handles state management
- Controls retries and scheduling
- Triggers Worker containers

### Worker Containers
- Stateless, independently scalable processing units
- Perform identification, tagging, conversion
- Run as ephemeral or persistent containers

### LLM Node
- OpenAI-compatible API (can be local container or external)
- Handles title normalization and validation

### Storage (SeaweedFS)
- S3-compatible object storage
- Stores ingest, archive, review, processed
