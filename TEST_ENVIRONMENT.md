# Test Environment Specification

## Overview
This document describes the environment and infrastructure used for testing the S.S.T (Steam Soundtrack Tagger) system. The environment is designed to simulate a distributed production setup using Docker and external services accessible via local domain names.

## Infrastructure Dependencies
The system relies on the following external services, managed via Nginx Proxy Manager (NPM) for port-less access:

- **Storage (S3/SeaweedFS)**: `http://swfs-s3.outergods.lan`
  - Bucket: `sst-data`
  - Used for raw file ingestion, processed archives (`archive/`), review queue (`review/`), and global rate limit tracking.
- **Orchestration (Prefect Server)**: `http://prefect.outergods.lan/api`
  - Manages the execution of Core and Worker flows.
  - Core and Worker run as "served" deployments within Docker containers.
- **AI / LLM**: `https://generativelanguage.googleapis.com/v1beta/openai` (Gemini) or local Ollama.
  - Used for track title and artist normalization.
  - Rate limits (RPM/TPM/RPD) are strictly enforced and tracked globally.

## Component Configuration
Testing is performed across multiple specialized nodes (containers), each with its own configuration file:

### 1. Scout Node (Local CLI or Container)
- **Role**: Scans local Steam library, uploads files to S3, and triggers the Prefect pipeline.
- **Config**: `.env.scout`
- **Primary Command**: `cd scout && uv run -m scout.main --limit 5`

### 2. Core Service (Docker)
- **Role**: Receives triggers from Scout and delegates processing tasks to available Workers via Prefect deployments.
- **Container**: `sst-core`
- **Config**: `.env.core`

### 3. Worker Node (Docker)
- **Role**: Downloads audio from S3, extracts metadata, performs LLM normalization, converts formats (AIFF/MP3), tags files, and uploads results.
- **Container**: `sst-worker`
- **Config**: `.env.worker`

### 4. UI Dashboard (Docker)
- **Role**: Provides real-time monitoring of the pipeline, metadata inspection, bulk deletion, and ZIP downloads.
- **URL**: `http://localhost:8000`
- **Config**: `.env.ui`

## Data Flow for Testing
1. **Ingest**: Scout scans `/mnt/d/SteamLibrary` -> Uploads to S3 `ingest/{appid}/`.
2. **Trigger**: Scout calls Prefect API -> Starts `SST-Production-Pipeline`.
3. **Delegation**: Core Flow calls `sst-worker-flow/sst-worker-deployment`.
4. **Processing**: Worker processes files according to `format_spec.md` -> Uploads to S3 `archive/` (success) or `review/` (manual check needed).
5. **Verification**: User monitors progress and downloads processed ZIPs via the Web UI.

## Environment Persistence
- **Rate Limits**: Daily LLM usage is tracked in `sst-data/system/llm_usage_YYYYMMDD.json`.
- **Cache**: Scout uses a local `scout_cache.json` to prevent redundant scanning (if configured).
