# TODO: Decentralization Architecture Migration

## Overview
This document outlines the required steps to migrate the current `docker-compose` based S.S.T (Steam Soundtrack Tagger) system into a fully decentralized architecture running across multiple bare-metal servers.

## Node Responsibilities & Placement

### 1. Server A: Scout Node (Data Ingestion)
- **Role**: Scans the local Steam library, extracts metadata, and uploads audio files to S3.
- **Requirement**: Must have local access to the Steam `steamapps` directory.
- **Action**: Runs as a cron job or manual trigger. Upon successful S3 upload, it sends a webhook or API call to the Core Node to trigger the Prefect workflow.

### 2. Server B: Worker Node (Processing Engine)
- **Role**: Handles heavy processing tasks (FFmpeg audio conversion, MusicBrainz metadata fetching, ID3 tagging, artwork padding) and uploads results to S3.
- **Requirement**: High CPU and network bandwidth. Can be scaled horizontally across multiple servers.
- **Action**: Runs continuously as a `prefect worker` (polling the Core Node's work pool for tasks). Does *not* require access to the Steam library.

### 3. Server C: Core, Storage & UI Node (Management)
- **Role**: Hosts the Prefect Server (state management, task queue), SeaweedFS (S3-compatible storage), and the S.S.T Web UI (`ui` container).
- **Requirement**: Must have a reachable IP/VPN accessible by Server A, Server B, and end-users (for Web UI access).
- **Action**: Constantly running. Manages task state, storage, and serves the user interface.

## Required Implementation Steps

- [ ] **Step 1: Separate Worker Execution**
  - Change the `CMD` in `worker/Dockerfile` from running a local test to starting a Prefect worker: `uv run prefect worker start --pool "sst-worker-pool"`.
  - Remove direct logic import (`from worker.main import WorkerService`) from the Core container.
- [ ] **Step 2: Create Prefect Deployments**
  - Update `core/src/core/main.py` to deploy `process_single_album_task` to the `sst-worker-pool` instead of running it locally.
- [ ] **Step 3: Implement Scout Trigger**
  - Update `scout/src/scout/main.py` to send an HTTP POST request to the Prefect Server (Server C) after uploading files to S3, initiating the `sst_main_flow` with the generated JSON payload.
- [ ] **Step 4: Environment Variable Segregation**
  - Define separate `.env.example` templates for each node type, ensuring `PREFECT_API_URL` and `S3_ENDPOINT_URL` point to Server C's address.
- [ ] **Step 5: UI Deployment Configuration**
  - Ensure the `ui` container is deployed on Server C alongside the S3 storage.
  - Configure the UI's `.env` to point to the local or internal S3 endpoint for fast ZIP generation, and expose port 8000 securely.
