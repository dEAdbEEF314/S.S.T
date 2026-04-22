# S.S.T (Steam Soundtrack Tagger)

S.S.T is a high-precision, standalone CLI tool that automatically identifies, enriches, and tags soundtracks purchased on Steam. It consolidates metadata from the Steam API, MusicBrainz, and local embedded tags using LLM-assisted "Factual Metadata Organization."

## 🚀 System Architecture: Standalone Edge Processing

S.S.T is a **Local-only Edge Processor**. All heavy lifting—including audio conversion, LLM consolidation, and tagging—is performed locally on the machine where the Steam library resides (e.g., WSL2/Windows). This minimizes network I/O and ensures maximum privacy and control.

### Core Pipeline
1.  **Scan**: Scans the Steam library and checks the local SQLite database for processed albums.
2.  **Enrich**: Fetches metadata from Steam API (including Parent Game integration) and MusicBrainz.
3.  **Consolidate (2-Step LLM)**: 
    - **Summary Pass**: Establishes global album rules (Artist, Genre, Discs) to ensure consistency.
    - **Iterative Pass**: Consolidates track-level metadata using global rules without exceeding TPM limits.
4.  **Process**: Converts audio (Lossless -> AIFF, Lossy -> MP3) and writes strict ID3v2.3 tags.
5.  **Package**: Bundles audio files and full processing logs into a ZIP archive in `output/`.

## ✨ Key Features (Act-10 Update)

-   **High-Precision CLI**: Built for power users. Provides detailed progress and terminal-based inspection.
-   **TPM-Optimized LLM**: Uses a global decision pass to maintain consistency while keeping per-track token usage low and linear.
-   **Smart Tie-breaking**: Strictly prioritizes Digital Media and non-Bandcamp sources from MusicBrainz to ensure "Gold Standard" metadata.
-   **Local State Management**: Uses a local SQLite database to track every processed album, preventing redundant API calls.
-   **Parent Game Integration**: Automatically fetches tags and genres from the main game if soundtrack metadata is sparse.
-   **Comprehensive Logging**: Every ZIP bundle includes `llm_log.json` (full chat history), `mbz_log.json` (raw API responses), and `metadata.json`.

## 🛠️ Tech Stack

-   **Language**: Python 3.12+
-   **Package Manager**: [uv](https://github.com/astral-sh/uv) (Mandatory)
-   **AI**: OpenAI-compatible LLM APIs (Gemini 1.5 Pro recommended)
-   **Audio**: FFmpeg, Mutagen
-   **Database**: SQLite (Local state tracking)

## 🏗️ Getting Started

### 1. Prerequisites
-   Ensure `.env` is configured (see `.env.example`).
-   Install dependencies using `uv`:
    ```bash
    cd scout && uv sync
    ```

### 2. Run Processor
```bash
# Run from the root directory using the scout venv
PYTHONPATH=scout/src ./scout/.venv/bin/python -m scout.main --limit 10
```

## ⚠️ Integrity & Review Rules

-   **Failure Isolation**: Any album missing mandatory tags (`Title` or `Track Number`) or having metadata conflicts is automatically routed to `output/review/`.
-   **Zero Hallucination**: LLM prompts are strictly designed to prevent inference. Missing data remains "Unknown" for manual review.
-   **Local Database**: Archived metadata is stored in `sst_local_state.db`. Any `app_id` present in this DB is skipped by default.

## 📄 License
TBD
