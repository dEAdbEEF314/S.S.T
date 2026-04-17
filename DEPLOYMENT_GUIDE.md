# S.S.T Decentralized Deployment Guide

This document describes how to deploy the S.S.T (Soundtrack Sorting Tool) components in a decentralized architecture for production testing.

## 1. Architecture Overview

- **Server C (Central)**: Hosts the Core (Prefect Server), UI, and S3-compatible storage (e.g., SeaweedFS).
- **Server B (Worker)**: Scales horizontally to process identification and tagging tasks.
- **Server A (Scout)**: Runs at the edge (where the music files are) to scan and upload data.

## 2. Prerequisites

- Docker and Docker Compose installed on all servers.
- Network connectivity between nodes (Ports 4200 for Prefect, 8333 for S3, 8000 for UI).
- S3-compatible storage (SeaweedFS, MinIO, or AWS S3).

---

## 3. Server C: Central Management (Core & UI)

### Step 1: Configure Environment
Copy `.env.core.example` to `.env.core` and update the credentials.
```bash
cp .env.core.example .env.core
nano .env.core
```

### Step 2: Launch Services
Use `docker-compose.core.yml` to start the central services.
```bash
docker-compose -f docker-compose.core.yml up -d
```

### Step 3: Setup Storage
Ensure the bucket defined in `S3_BUCKET_NAME` (default: `sst-data`) exists in your S3 storage.

---

## 4. Server B: Processing Units (Worker)

### Step 1: Configure Environment
Copy `.env.worker.example` to `.env.worker`. 
**Crucial**: Update `S3_ENDPOINT_URL` and `PREFECT_API_URL` to point to **Server C's IP**.
```bash
cp .env.worker.example .env.worker
nano .env.worker
```

### Step 2: Launch Worker
Start the worker container.
```bash
docker-compose -f docker-compose.worker.yml up -d
```
The worker will automatically connect to the Prefect Server on Server C and wait for tasks.

---

## 5. Server A: Data Source (Scout)

### Step 1: Configure Environment
Copy `.env.scout.example` to `.env.scout`.
**Crucial**: 
- Set `STEAM_LIBRARY_PATH` to your actual Steam library.
- Update `S3_ENDPOINT_URL` and `PREFECT_API_URL` to point to **Server C's IP**.
```bash
cp .env.scout.example .env.scout
nano .env.scout
```

### Step 2: Run Scout
Scout can be run as a one-off container or scheduled.
```bash
docker-compose -f docker-compose.scout.yml run --rm scout uv run -m scout.main
```

---

## 6. Verification

1. **Prefect UI**: Access `http://<SERVER_C_IP>:4200` to see the flow status and active workers.
2. **S3 Storage**: Check your S3 bucket for uploaded files in the `ingest/` prefix.
3. **S.S.T UI**: Access `http://<SERVER_C_IP>:8000` to browse processed albums in `archive` or `review`.
