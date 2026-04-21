# Test Environment Specification (Local-only Architecture)

## Overview
This document describes the environment and infrastructure used for testing the S.S.T (Steam Soundtrack Tagger) system. The system now operates in a "Local-only (Edge Processing)" mode, where audio processing, tagging, and LLM consolidation happen directly on the machine with access to the Steam library.

## Infrastructure Dependencies
The system relies on the following external services:

- **Storage (S3/SeaweedFS)**: `http://swfs-s3.outergods.lan`
  - Bucket: `sst-data`
  - Used for processed archives (`archive/`) and review queue (`review/`). The `ingest/` prefix is deprecated.
- **AI / LLM**: `https://generativelanguage.googleapis.com/v1beta/openai` (Gemini API).
  - Used for metadata consolidation and "The Organizer" logic.
  - Requires `LLM_API_KEY` in the `.env` file.

## Component Configuration
The system is consolidated into two primary interfaces:

### 1. Scout (Local Processor)
- **Role**: Scans Steam library, adopts optimal audio files, converts formats locally (WSL2), consolidates metadata via LLM, tags files, and uploads finalized results to S3.
- **Config**: `.env` (Consolidated)
- **Primary Execution**: `cd scout && uv run -m scout.main`

### 2. UI Dashboard (Docker)
- **Role**: Provides real-time monitoring of archived albums, metadata inspection, and ZIP downloads.
- **Config**: `.env` (Consolidated)
- **URL**: `http://localhost:8000`

---

## Local Production Testing Procedure

The production testing is performed directly in the workspace root.

### 1. Environment Preparation
All commands should be executed from the workspace root: `/home/sexyroot/AI_Base/WorkSpace/S.S.T/`

Ensure dependencies are up to date using `uv`:
```bash
# From workspace root
uv sync
```

### 2. Configuration
Ensure the `.env` file is present in the workspace root and contains all necessary credentials for S3 and LLM. 
The system will use `SST_WORKING_DIR` (e.g., `/home/sexyroot/sst-work`) to perform copy/conversion operations without touching the Steam library.

### 3. Execution
To process soundtracks and verify the tagging logic:

```bash
# Run the local processor
export $(grep -v '^#' .env | xargs)
cd scout
uv run -m scout.main --limit 5
```

### 4. Verification
- **Web UI**: Access `http://localhost:8000` and check the "Archive" tab.
- **S3 Filer**: Verify that `archive/{app_id}/` contains only one audio file per track (AIFF or MP3) and the `metadata.json`.
- **ZIP Download**: Download the ZIP from the UI and verify tags using external tools like Mp3tag.
