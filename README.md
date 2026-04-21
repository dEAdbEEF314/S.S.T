# S.S.T (Steam Soundtrack Tagger)

S.S.T is a high-precision, local-first edge processing system that automatically identifies, enriches, and tags soundtracks purchased on Steam. It consolidates metadata from the Steam API, MusicBrainz, and local embedded tags using LLM-assisted "Factual Metadata Organization."

## 🚀 System Architecture: Standalone Edge Processing

S.S.T has transitioned from a distributed architecture to a **Standalone Edge Model**. All heavy lifting—including audio conversion, LLM consolidation, and tagging—is performed locally on the machine where the Steam library resides (e.g., WSL2/Windows). This minimizes network I/O and maximizes privacy and control.

### Core Pipeline
1.  **Scan**: Steam library scan with local caching (`scout_cache.json`).
2.  **Enrich**: Fetches metadata from Steam API (including Parent Game info) and MusicBrainz.
3.  **Consolidate**: Iterative LLM Chat Session (1 track at a time) to normalize metadata without hallucinations.
4.  **Process**: Converts audio (Lossless -> AIFF, Lossy -> MP3) and writes strict ID3v2 tags.
5.  **Archive**: Uploads results to SeaweedFS (S3) and creates a local ZIP package in `output/`.

## ✨ Key Features (Act-10 Update)

-   **Iterative LLM Chat**: Processes large albums reliably by handling tracks one-by-one with a sliding window context (Smart TPM management).
-   **Parent Game Integration**: Automatically fetches tags and genres from the main game if soundtrack data is sparse.
-   **Strict Metadata Fallback**: Ensures "Truth" by prioritizing Steam/MBZ data and tracking metadata origins in the `source` field.
-   **Automatic ZIP Packaging**: Saves processed albums as ready-to-use ZIP files in `output/archive/` or `output/review/`.
-   **Comprehensive Logging**: Bundle includes `llm_log.json` (full chat history), `mbz_log.json` (raw API responses), and `raw_metadata.json`.
-   **Web UI Dashboard**: Browse processed albums, inspect detailed metadata, and review LLM interaction logs.

## 🛠️ Tech Stack

-   **Language**: Python 3.12+
-   **Package Manager**: [uv](https://github.com/astral-sh/uv) (Mandatory)
-   **Storage**: [SeaweedFS](https://github.com/seaweedfs/seaweedfs) (S3 + Filer API)
-   **AI**: OpenAI-compatible LLM APIs (Gemini, etc.)
-   **Audio**: FFmpeg, Mutagen
-   **Frontend**: React (Vite), Tailwind CSS, FastAPI (Backend proxy)
-   **Environment**: Docker Compose (for UI and Storage)

## 🏗️ Getting Started

### 1. Prerequisites
-   Ensure `.env` is configured (see `.env.example`).
-   Install dependencies using uv:
    ```bash
    cd scout && uv sync
    ```

### 2. Launch Infrastructure (Storage & UI)
```bash
docker compose up -d
```

### 3. Run Processor
```bash
# Run from the root directory using the scout venv
PYTHONPATH=scout/src ./scout/.venv/bin/python -m scout.main --limit 10
```

## ⚠️ Integrity & Review Rules

-   **Failure Isolation**: Any album missing mandatory tags (`Title` or `Track Number`) is automatically routed to `review/`.
-   **Zero Hallucination**: LLM prompts are strictly designed to prevent inference. Missing data remains "Unknown" for manual review.
-   **Timezone Support**: Timestamps respect the `TZ` environment variable for local logging accuracy.

## 📄 License
TBD
