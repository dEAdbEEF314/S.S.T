# Environment Variables Guide (.env.example)

This guide explains the configuration items required to run the S.S.T (Steam Soundtrack Tagger) system as a standalone CLI tool.

## 1. Steam Configuration
- `STEAM_LIBRARY_PATH`: The local path to your Steam library (e.g., `/mnt/e/SteamLibrary`). Must contain the `steamapps/common` directory.
- `STEAM_LANGUAGE`: Preferred language for metadata fetching (e.g., `japanese`, `english`).

## 2. Local Processing Settings
- `SST_WORKING_DIR`: Temporary directory for audio conversion and tagging. High-speed storage (NVMe/SSD) is recommended.
- `SST_DB_PATH`: Path to the SQLite database (`sst_local_state.db`) used for tracking processed albums and skipping redundant runs.

## 3. Metadata Source Priority
- `METADATA_SOURCE_PRIORITY`: A comma-separated list defining the order of truth.
    - `MBZ`: MusicBrainz (High precision for tracklists).
    - `STEAM`: Steam Store API (Authoritative for Developer/Publisher).
    - `EMBEDDED`: Existing tags in audio files.
    - *Default*: `MBZ,STEAM,EMBEDDED`

## 4. AI / LLM (OpenAI-compatible)
Used for "Factual Metadata Organization" (normalization and conflict resolution).
- `LLM_API_KEY`: API key for the provider (Gemini, OpenAI, etc.).
- `LLM_BASE_URL`: API endpoint. Supports any OpenAI-compatible provider.
- `LLM_MODEL`: The model name (e.g., `gemini-1.5-pro`).
- **Rate Limits**:
    - `LLM_LIMIT_RPM`: Requests Per Minute.
    - `LLM_LIMIT_TPM`: Tokens Per Minute.
    - `LLM_LIMIT_RPD`: Requests Per Day.

## 5. External API Details
- `MUSICBRAINZ_USER_AGENT`: Required by MusicBrainz API terms. Format: `AppName/Version (ContactURL)`.

---

## Important Notes
- **Security**: The `.env` file contains sensitive API keys. **NEVER commit it to Git.**
- **Template**: Copy `.env.example` to `.env` to start your configuration.
