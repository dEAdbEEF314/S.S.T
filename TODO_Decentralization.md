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

### 3. Server C: Core & Storage Node (Orchestrator)
- **Role**: Hosts the Prefect Server (state management, UI, task queue) and SeaweedFS (S3-compatible storage).
- **Requirement**: Must have a reachable IP/VPN accessible by both Server A and Server B.
- **Action**: Constantly running. Manages task state and storage.

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
