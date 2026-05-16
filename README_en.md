# S.S.T (Steam Soundtrack Tagger)

S.S.T is a high-precision, standalone CLI tool that automatically identifies, enriches, and tags soundtracks purchased on Steam. It consolidates metadata from the Steam API, MusicBrainz, and local embedded tags using LLM-assisted "Factual Metadata Organization."

## 🚀 System Architecture: Standalone Edge Processing

S.S.T is a **Local-only Edge Processor**. All heavy lifting—including audio conversion, LLM consolidation, and tagging—is performed locally on the machine where the Steam library resides (e.g., WSL2/Windows). This minimizes network I/O and ensures maximum privacy and control.

### Core Pipeline
1.  **Scan**: Scans the Steam library and checks the local SQLite database for processed albums.
2.  **Enrich (3-Layer API Architecture)**: 
    - Layer 1 (Official Store API): Fetches localized album titles, official genres, and release dates.
    - Layer 2 (Local PICS Bridge): Extracts highly accurate tracklists directly from Steam's internal DB via a SteamCMD bridge.
    - Layer 3 (MusicBrainz / Embedded): Retrieves music DB candidates and existing local tags.
3.  **Consolidate (Separation of Powers)**: 
    - The LLM (Judiciary) infers the best track titles based on the user-defined `METADATA_SOURCE_PRIORITY` (Legislative). 
    - Finally, the System (Executive) strictly censors the output to ensure absolute physical cleanliness (e.g., stripping leading track numbers for DJ gear compatibility).
4.  **Process**: Converts audio (Lossless -> AIFF, Lossy -> MP3) and writes strict ID3v2.3 tags.
5.  **Package**: Bundles audio files and full processing logs (e.g., `BASIS_for_CLASSIFICATION.md`) into a ZIP archive in `output/`.

## ✨ Key Features (Act-18 Update)

-   **Adaptive LLM Router**: Dynamically adjusts the target model and context size (8K/16K/32K) based on the track count, enabling safe and massive parallel processing without VRAM overflow.
-   **Separation of Powers Logic**: While the LLM infers the most accurate title, the system rigidly enforces a "No Dirty Tags" rule. Even official titles like `01. Title` are forcefully cleaned to ensure optimal visibility on DJ equipment.
-   **Deterministic Fast-Track**: Completely bypasses the LLM inference if the data sources perfectly align, drastically reducing processing time and costs.
-   **Local State Management**: Uses a local SQLite database to track every processed album, preventing redundant API calls.

## 🛠️ Tech Stack

-   **Language**: Python 3.12+
-   **Package Manager**: [uv](https://github.com/astral-sh/uv) (Mandatory)
-   **AI**: Docker + `llama-server` (OpenAI-compatible API recommended for 16GB VRAM environments)
-   **Audio**: FFmpeg, Mutagen
-   **Database**: SQLite

## 🏗️ Getting Started

### 1. Prerequisites
-   **LLM Inference Environment**: Refer to `Models/LLM_setup.sh` to set up the environment using Docker and `llama-server`.
-   **Local PICS Bridge**: Start the local bridge to access Steam's internal DB:
    ```bash
    docker run --name sst-pics-bridge -d -p 8080:8000 --restart unless-stopped steamcmd/api:latest
    ```
-   Ensure `.env` is configured (see `.env.example`, paying close attention to `METADATA_SOURCE_PRIORITY`).
-   Install dependencies using `uv`:
    ```bash
    cd scout && uv sync
    ```

### 2. Run Processor
```bash
# Execute using uv run
uv run scout/src/scout/main.py --limit 10

# Or use the wrapper script
./sst --limit 10
```

## ⚠️ Integrity & Review Rules

-   **Failure Isolation**: Any album missing mandatory tags, failing the LLM confidence check, or triggering the system's forceful cleaning logic is automatically routed to `output/review/`.
-   **Full Transparency**: The exact reason for a review is stated in the `BASIS_for_CLASSIFICATION.md` file (under "System Decision Reason"), preventing human confusion.
-   **Finalization**: Once metadata is corrected manually (e.g., using MP3tag), run `./sst --finalize` to update the local database.

## 📄 License
TBD
