# UI Specification: S.S.T Engineer Dashboard

## Overview
A modern, engineer-centric dashboard for monitoring the Steam Soundtrack Tagger (S.S.T) pipeline. Built with React and shadcn/ui, it provides real-time visibility into the decentralized tagging process.

## Technology Stack
- **Frontend**: React 18 (Vite), TypeScript, Tailwind CSS, shadcn/ui.
- **Backend**: FastAPI (Python 3.12).
- **Icons**: Lucide React.
- **State Management**: TanStack Query (React Query) for data fetching and polling.

## Core Features

### 1. Dashboard (Home)
Visual overview of the system state.
- **Global Metrics**:
  - `Scanned`: Total albums found in Steam libraries (S3 `ingest/`).
  - `Processing`: Active albums being tagged (Prefect `Running`).
  - `Archive`: Successfully tagged albums (S3 `archive/`).
  - `Review`: Albums requiring human verification (S3 `review/`).
- **System Health**: Connection status for Prefect Server, S3 (SeaweedFS), and LLM (Open-WebUI).

### 2. Pipeline Monitor (`/pipeline`)
Real-time tracking of flow runs.
- **Data Table**: Lists flow runs for `SST-Production-Pipeline`.
- **Columns**: `App ID`, `Album Name`, `State` (Badge), `Start Time`, `Duration`.
- **State Badges**: 
  - `Scheduled`: Gray
  - `Running`: Blue (Animate)
  - `Completed`: Green
  - `Failed`: Red
  - `Cancelled`: Yellow

### 3. LLM Interaction Log (`/llm-logs`)
Developer-focused view of AI decision making.
- **Chat UI**: Displays the system prompt, user prompt, and model response.
- **Metadata**: Shows model name (e.g., `llama3.1`), token usage (if available), and timestamp.
- **Localized Support**: Full UTF-8 rendering for Japanese track titles and metadata verification.

### 4. Archive & Review Explorer
Browse and download processed files.
- **List View**: Card-based or table-based view of processed albums fetched from S3 `archive/` or `review/`.
- **Display Data**: Album Name, App ID, Developer, Publisher, Track Count, Total Size, Processed Date, VGMdb Link (if available).
- **Advanced Management**:
  - **Search & Filter**: Real-time filtering by Album Name or App ID.
  - **Bulk Deletion**: Select multiple albums via checkboxes and delete them from S3 with a confirmation dialog.
  - **Metadata Inspector**: Side panel to view the raw `metadata.json` (tracks, tags) without downloading.
  - **Workflow Actions**:
    - **Reprocess**: Move an album back to `ingest/` and re-trigger the Prefect pipeline.
    - **Approve (Review only)**: Move an album from `review/` to `archive/` manually.
- **Download**: Trigger a server-side ZIP generation of the album contents using the `/download/{status}/{app_id}` endpoint. Filename follows the `[AlbumName]_[Status].zip` convention.

## Design Principles
- **Theme**: Pure Dark Mode. Use `slate` or `zinc` color palettes for an "IDE-like" feel.
- **Typography**:
  - Main UI: Inter.
  - Album Metadata: Noto Sans JP (ensuring zero character corruption).
  - Code/JSON: JetBrains Mono.
- **Responsiveness**: Mobile-friendly navigation, but optimized for desktop monitoring.

## Internal API (Backend)
- `GET /api/stats`: Aggregated counts.
- `GET /api/pipeline`: Proxy to Prefect API `/flow_runs/filter`.
- `GET /api/llm-logs`: List interaction JSON files from S3.
- `GET /api/llm-logs/detail`: Detailed conversation data.
- `GET /api/albums?status={status}`: List albums with metadata and total size.
- `GET /api/albums/{status}/{app_id}/metadata`: Fetch raw metadata JSON.
- `POST /api/albums/bulk-delete`: Delete multiple albums.
- `POST /api/albums/reprocess`: Move back to ingest and re-trigger pipeline.
- `POST /api/albums/approve`: Move from review to archive.
- `GET /download/{status}/{app_id}`: Stream ZIP file for an album.
