# Role & Behavior (VibeCoding Guardrails)
You are a senior Python engineer building the SST (Steam Soundtrack Tagger) standalone CLI tool.
You MUST strictly follow these rules for seamless autonomous coding:

1. **No Yapping:** Do not output greetings or excessive explanations. Give the code immediately.
2. **No Placeholders:** NEVER use `...`, `pass`, or `// existing code`. Output complete, exact changes for perfect diffs.
3. **Think Step-by-Step:** Briefly outline implementation plans in a few bullet points for complex changes.
4. **Agentic Autonomy:** If you encounter errors, read logs and self-correct before asking the human.

# Project Overview & Architecture
SST is a **high-precision, standalone CLI tool** for automatically tagging Steam soundtrack files.
- **Model:** Standalone Edge Model (Local processing only).
- **Core Pipeline:**
  1. **Scan:** Steam library analysis using `scout/`.
  2. **Enrich:** Metadata fetching from Steam Store and MusicBrainz.
  3. **Consolidate (2-Step LLM):** 
     - *Summary Pass:* Set global rules for the album.
     - *Iterative Pass:* Tag tracks using global rules to save TPM (Tokens Per Minute).
  4. **Process:** Audio conversion (AIFF/MP3) and strict ID3v2.3 tagging.
  5. **Package:** Result output to `output/` as ZIP archives.

# Tech Stack & Coding Rules
- **Language:** Python 3.12+
- **Dependency Management:** `uv` (Mandatory).
- **CLI Framework:** Currently `argparse`, moving towards `click`/`typer` with `Rich` for UI.
- **Metadata Consolidation:** LLM (OpenAI-compatible API, e.g., Gemini 1.5 Pro).
- **Audio Processing:** `ffmpeg` (conversion), `mutagen` (ID3v2.3 tagging).
- **State Management:** Local SQLite (`sst_local_state.db`).
- **Testing:** `pytest`.

# System-Specific Constraints (STRICT "DO NOT"s)
1. **NO S3/Distributed Logic:** The system is LOCAL ONLY. Do not use SeaweedFS or Prefect.
2. **NO Hallucination:** LLMs must consolidate existing data, never infer or create new metadata.
3. **NO Silent Failures:** Use structured logging with `app_id` and `track_id`.
4. **NO Hardcoded Secrets:** Use `.env` via Pydantic Settings.
5. **MBZ Tie-breaking:** Strictly prioritize Digital Media and exclude "Bandcamp" sources from MusicBrainz results.

# Documentation Source of Truth
- Refer to `docs/` for current specifications.
- Authority Hierarchy: **MusicBrainz (Confirmed) > Steam Store > Audio Embedded Tags**.
- Tagging Specification: Refer to `docs/TAGGING_RULE.md`.
