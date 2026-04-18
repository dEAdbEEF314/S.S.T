# SST Pipeline Execution Strategy

## Overview
The SST pipeline follows a decentralized "Flow-of-Flows" architecture. This ensures that the orchestration logic (Core) is separated from the heavy-lifting processing logic (Worker), allowing for independent scaling and remote execution.

## Pipeline Flow

1.  **Phase 1: Scouting (Scout Node)**
    - Scans the local Steam library for soundtracks.
    - Uploads raw files and `.acf` manifests to S3 (`ingest/` bucket).
    - Triggers the Prefect **Main Flow** via a REST API POST request.

2.  **Phase 2: Orchestration (Core Node)**
    - Receives the scout result.
    - Iterates over the list of albums.
    - For each album, it calls `run_deployment("sst-worker-flow/sst-worker-deployment")`.
    - This creates a sub-flow run that is picked up by a Worker.

3.  **Phase 3: Processing (Worker Node)**
    - The Worker Flow Server picks up the assigned `sst-worker-flow`.
    - **Logic**:
        - Downloads files from S3 to temporary storage.
        - Identifies the album using MusicBrainz and embedded metadata.
        - **AI Interaction**: Calls the LLM for title normalization and metadata verification.
        - **Tagging**: Normalizes audio formats (if needed) and applies ID3/FLAC tags + Artwork.
        - **Upload**: Pushes the tagged files to `archive/` or `review/` and logs LLM interactions to `logs/llm/`.

## Reliability & Monitoring
- **Error Handling**: Failures in a Worker flow do not crash the Main Flow. The Dashboard displays individual album statuses.
- **Observability**: All interactions are logged to S3 and can be viewed via the S.S.T Dashboard UI.
- **Concurrency**: Multiple Workers can be deployed to process different albums in parallel.
