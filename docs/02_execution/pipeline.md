# SST Pipeline (Standalone CLI)

The SST pipeline is a single-threaded, synchronous local process. It eliminates all network-based intermediate storage (S3) and distributed orchestration (Prefect) to provide a predictable and high-performance edge processing experience.

## Pipeline Steps

### 1. Discovery (Scanner)
- Scans the configured `STEAM_LIBRARY_PATH`.
- Parses `.acf` files to identify soundtrack manifests.
- Checks the local SQLite database to skip already processed `app_id`s.

### 2. Data Gathering (Enrichment)
- **Steam API**: Fetches detailed metadata (Developer, Publisher, Release Date, Tags, Genre). If the soundtrack is a DLC, it automatically follows the parent game relationship.
- **Local Audio Analysis**: Scans all subdirectories of the album.
    - Extracts embedded tags from all formats (FLAC, MP3, etc.).
    - Calculates audio duration for WAV matching.
- **MusicBrainz**: Performs a fuzzy search using the album title and track count.

### 3. Consolidation (LLM)
- Sends the gathered data to the LLM (e.g., Gemini 1.5 Pro).
- The LLM processes tracks **iteratively** (one-by-one) with a sliding window context to ensure consistency and stay within token limits.
- **Output**: A strict JSON object mapping track IDs to ID3v2.3 fields.

### 4. Transformation (Tagger)
- **Conversion**:
    - Lossless (FLAC/WAV) → **AIFF** (24-bit/48kHz).
    - High-quality Lossy (AAC/OGG) → **MP3** (320kbps).
    - Standard MP3 → **Passthrough** (No re-encoding).
- **Tagging**: Applies the consolidated metadata and embedded artwork (resized/padded to 500x500).

### 5. Packaging (Finalization)
- Creates a temporary working directory for the album.
- Bundles the processed audio files and the following logs:
    - `metadata.json`: The final consolidated data.
    - `llm_log.json`: The full chat history for transparency.
    - `raw_metadata.json`: All inputs provided to the LLM.
- Creates a ZIP archive in:
    - `output/archive/[AppID]_[Name].zip` (Success)
    - `output/review/[AppID]_[Name].zip` (Needs attention)
- Records the completion in the local SQLite database.

## Error Handling
- **Non-Fatal**: If a track lacks mandatory tags (Title/Track Number), the entire album is routed to `review/` rather than failing.
- **Fatal**: If the LLM fails to respond or produces invalid JSON, the album is skipped or marked as an error in the database for later retries.
