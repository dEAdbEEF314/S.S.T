# SST Project – Recruitment, Systems and Tools (Final Complete)

## Overview

This document defines the infrastructure, execution model, and required tools
for the SST (Steam Soundtrack Tagger) system.

SST is a distributed, containerized, Prefect-orchestrated pipeline designed to:
- Process Steam soundtrack files
- Identify tracks using acoustic fingerprinting
- Enrich metadata using VGMdb (Primary), MusicBrainz (Secondary), and AcoustID
- Enable human-assisted correction when needed

---

## Execution Model

All code is developed locally but executed inside Docker containers.

- Development: VS Code (local machine)
- Source of truth: GitHub repository
- Execution: Docker containers (Worker / Core / Scout)
- Deployment: git pull + docker compose up -d --build

Critical rules:

- No code runs directly on host OS
- All execution must be reproducible via Docker
- Config changes must NOT require image rebuilds
- Behavior must be controlled via config.yaml

---

## System Architecture

### Components

| Component        | Role |
|-----------------|------|
| SST-Core-VM     | Prefect Server / orchestration |
| SST-Worker-CT   | Audio processing / tagging |
| SST-Scout-VM    | Steam metadata ingestion |
| SeaweedFS S3    | Object storage / artifacts |
| M2 Mac          | LLM inference (Ollama / external LLM service) |

---

### High-Level Flow

1. Scout fetches Steam metadata
2. Core schedules jobs via Prefect
3. Worker processes audio:
   - Fingerprinting (fpcalc / AcoustID)
  - VGMdb primary lookup
  - MusicBrainz secondary verification/fallback
   - Metadata merging
   - Tag writing
4. Results:
   - Stored in SeaweedFS (S3-compatible)
   - OR sent to review queue

---

## Container Design

### Worker Container

Responsibilities:

- Audio decoding (ffmpeg)
- Fingerprinting (fpcalc / chromaprint)
- AcoustID API calls
- VGMdb primary queries
- MusicBrainz secondary verification/fallback queries
- Metadata normalization
- Tag writing (mutagen)

Mount path:

/mnt/work_area

Characteristics:

- Stateless (except local cache)
- Horizontally scalable
- Safe to terminate anytime

---

### Core Container

Responsibilities:

- Prefect Server
- Flow orchestration
- Job scheduling
- State tracking

Exposes:

http://<core-host>:4200

API:

/api

---

### Scout Container

Responsibilities:

- Steam library scanning (ACF manifest parsing)
- Soundtrack app discovery
- Audio file upload to SeaweedFS (ingest/)
- Metadata extraction:
  - AppID
  - Title
  - Release date
- Preprocessing for album matching

---

### SeaweedFS (S3-compatible Object Storage)

Responsibilities:

- Store input ingest objects
- Store archived outputs
- Store logs and artifacts
- Store processed temporary data
- Store review queue data

Example structure:

buckets:
  └─ sst/
     ├─ ingest/
     ├─ archive/
     ├─ review/
     └─ processed/

---

## Directory Layout (Repository)

SST_Project/
├─ worker/
│  ├─ Dockerfile
│  ├─ docker-compose.yml
│  ├─ docker-compose.dev.yml
│  ├─ config.yaml
│  ├─ requirements.txt
│  └─ src/
│     ├─ acoustid/
│     ├─ acoustid_api/
│     ├─ fingerprint/
│     ├─ musicbrainz/
│     ├─ scoring/
│     ├─ steam/
│     ├─ tagging/
│     ├─ pipeline/
│     └─ models/
│
├─ core/
│  ├─ docker-compose.yml
│  └─ prefect/
│     ├─ setup-work-pool.ps1
│     ├─ deploy-worker-flow.ps1
│     └─ run-worker-deployment.ps1
│
├─ scout/
│  ├─ Dockerfile
│  ├─ docker-compose.yml
│  ├─ docker-compose.dev.yml
│  ├─ config.yaml
│  ├─ .env.example
│  ├─ requirements.txt
│  ├─ src/
│  │  ├─ main.py
│  │  ├─ library_scanner.py
│  │  ├─ acf_parser.py
│  │  ├─ uploader.py
│  │  └─ models.py
│  └─ test/
│
├─ docs/
│  ├─ AGENT_PROMPT.md
│  ├─ ARCHITECTURE.md
│  ├─ CODING_RULES.md
│  ├─ CONFIG_SPEC.md
│  ├─ DATA_CONTRACTS.md
│  ├─ DATA_FLOW.md
│  ├─ ERROR_HANDLING.md
│  ├─ INFRASTRUCTURE.md
│  ├─ INTERFACES.md
│  ├─ IO_SPEC.md
│  ├─ PREFECT_FLOW.md
│  ├─ PROJECT_STRUCTURE.md
│  ├─ REPOSITORY_STRUCTURE.md
│  ├─ SST_Project_Architecture.md
│  ├─ SST_Project_Detailed_Specifications.md
│  ├─ SST_Project_Recruitment_Systems_and_Tools.md
│  ├─ STATE_MACHINE.md
│  ├─ SUCCESS_CRITERIA.md
│  ├─ TASKS.md
│  └─ TEST_PLAN.md
│
├─ examples/
│  ├─ minimal_pipeline.py
│  ├─ .env.example
│  └─ config.example.yaml
│
└─ work_area/

---

## Environment Configuration

### .env (Secrets ONLY)

ACOUSTID_API_KEY=xxx
S3_ENDPOINT_URL=http://swfs-s3:8333
S3_ACCESS_KEY=xxx
S3_SECRET_KEY=xxx
S3_BUCKET=sst
PREFECT_API_URL=http://core:4200/api

Rules:

- Never commit .env
- Inject via Docker or environment

---

### config.yaml (Behavior control)

acoustid:
  skip_acoustid_threshold: 0.9
  score_gap: 0.05
  partial_verify_tracks: 3
  partial_match_threshold: 0.8

search:
  languages:
    - ja
    - en
    - original
  strategy: merge

album_match:
  track_count_tolerance: 1
  date_tolerance_days: 30

retry:
  max_attempts: 3
  base_delay_sec: 5

---

## Docker Strategy

### Principles

- Config changes must NOT trigger rebuild
- Use bind mounts for:
  - config.yaml
  - work_area
- Separate dev/prod compose files

---

### Dev

docker-compose.dev.yml

- Fast iteration
- Local volume mounts
- Debug logging enabled

---

### Production

docker-compose.yml

- Stable execution
- Minimal logging
- Restart policies enabled

---

## Networking

### Internal

- Worker → Core (Prefect API)
- Worker → SeaweedFS S3 endpoint
- Scout → Steam API

---

### Core Endpoint

http://core:4200/api

Health:

/api/health

---

## Required Tools

### Core Stack

- Python 3.11+
- Docker / Docker Compose
- Prefect 3.x
- ffmpeg
- chromaprint (fpcalc)

---

### Python Libraries

- prefect
- httpx
- pydantic
- mutagen
- pyacoustid
- musicbrainzngs
- boto3
- PyYAML
- vdf (Scout)
- python-dotenv (Scout)

---

### Development Tools

- VS Code
- GitHub Copilot
- AI coding agents (optional)

---

## Fingerprinting Requirements

fpcalc must exist inside container.

Check:

fpcalc -version

---

## Failure Handling

Must handle:

- VGMdb failure/low confidence (`vgmdb_score < 0.70`) → fallback to MusicBrainz
- VGMdb and MusicBrainz both low confidence (`< 0.55`) → send to review queue
- Fingerprint fails → retry
- Low confidence → full scan
- API timeout → retry with backoff
- Final failure → send to review queue

---

## Caching Strategy

- Cache successful matches
- Reuse if confidence > 0.95
- Cache data stored under processed/
- Manual corrections override cache

---

## Review System

Stored in SeaweedFS:

review/
 ├─ job_id/
 │   ├─ metadata.yaml
 │   └─ diff.md

Contains:

- Candidate comparisons
- Editable corrections

---

## Logging

Each job must log:

- job_id
- track_id
- processing step
- result
- error

Logs must be:

- Structured (JSON preferred)
- Stored in SeaweedFS (archive/ or processed/ policy)

---

## Scaling Strategy

- Workers are horizontally scalable
- Prefect distributes jobs
- No shared state dependency

---

## AI Agent Compatibility

This project is explicitly designed for AI-assisted development.

Guarantees:

- No hidden assumptions
- All configs externalized
- Deterministic execution paths
- Clear separation of roles

AI agents must be able to:

- Implement features without guessing environment
- Run flows without manual intervention
- Extend pipeline safely

---

## LLM Integration

M2 Mac acts as an LLM inference node via API.

- API communication: OpenAI API compatible format as standard
- Default: Ollama (local inference)
- Can be configured to seamlessly switch with external LLM services (OpenAI, Gemini, etc.)
- Used for metadata enrichment and automatic determination of ambiguous cases

---

## Development Workflow

1. Edit locally (VS Code)
2. Commit to GitHub
3. Pull on server
4. docker compose up -d --build

---

## Future Extensions

- Web-based review UI
- Shared metadata database
- Distributed worker auto-scaling
- OSS contribution model

---

## Summary

SST is a distributed audio identification system combining:

- Acoustic fingerprinting (AcoustID)
- Metadata intelligence (VGMdb + MusicBrainz + Steam)
- Human-in-the-loop validation
- Container-based scalable execution

It is designed for both human developers and AI agents.

---
