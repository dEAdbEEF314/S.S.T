# Architecture

## Components

- Scout VM
- Core VM (Prefect)
- Worker Containers
- LLM Node
- SeaweedFS (S3 compatible)

---

## Flow

Scout → ingest → Worker → archive/review

---

## Description

### Scout VM
- Scans Steam library
- Parses ACF files
- Collects soundtrack files
- Uploads to ingest storage

### Core VM
- Runs Prefect orchestration
- Handles state management
- Controls retries and scheduling

### Worker Containers
- Stateless processing units
- Perform identification, tagging, conversion

### LLM Node
- OpenAI-compatible API
- Handles title normalization and validation

### Storage (SeaweedFS)
- S3-compatible object storage
- Stores ingest, archive, review, processed
