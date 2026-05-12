# S.S.T Test Environment Specification

This document defines the standard test environment for validating S.S.T's standalone CLI logic and API integrations.

## 1. Core Stack
- **OS**: WSL2 (Ubuntu 22.04+)
- **Runtime**: Python 3.12+ managed by `uv`.
- **Media Engine**: FFmpeg (must be available in WSL `PATH`).
- **Database**: SQLite 3.

## 2. Infrastructure (Local Docker)
For the "Ultimate Data Mode", a local PICS bridge must be active:
- **Container**: `steamcmd/api:latest`
- **Exposed Port**: `8080` (mapped to internal `8000`).
- **Endpoint**: `http://localhost:8080/v1/info/{AppID}`

## 3. Data Sources (Validation Targets)
Tests should be run against these representative AppIDs:
1.  **1027880** (A Dance of Fire and Ice OST): Modern PICS tracklist + Direct MBZ links.
2.  **1113510** (Hellsinker): Deep directory structure + Legacy/Manual Review case.
3.  **1167720** (Artifact Adventure): Mixed quality formats (AIFF/MP3) for deduplication testing.

## 4. Environment Variables (.env)
A valid test environment MUST have:
- `STEAM_WEB_API_KEY`: Active key for `IStoreBrowseService`.
- `STEAM_PICS_BRIDGE_URL`: Set to `http://localhost:8080/v1/info/`.
- `LLM_BACKEND`: `GEMINI`, `OLLAMA` (Legacy), or `OPENAI_COMPATIBLE` (Recommended for local Docker llama-server).

## 5. Verification Checklist
- [ ] Automatic ZIP extraction on Windows (via native `tar.exe`).
- [ ] Correct ID3v2.3 tagging for MP3.
- [ ] Clean temporary buffer removal.
- [ ] PICS data persistence in SQLite `steam_store_data`.
