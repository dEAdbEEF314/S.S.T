# S.S.T (Steam Soundtrack Tagger) Project Instructions

## 🚨 Critical Safety & Communication Rules

1. **Read-Only Steam Library**: NEVER attempt to write, modify, delete, or move files within the Steam library directories. Access must be strictly **READ-ONLY**. All processing results must be written to the designated `SST_OUTPUT_DIR`.
2. **Japanese Communication Mandate**: Before starting any technical task or execution phase, you MUST provide a detailed explanation of the planned work in **Japanese**. This includes the rationale, affected files, and expected outcome.

## 🛠️ Engineering Standards

- **Tech Stack**: Python 3.12 (managed via `uv`), FFmpeg, SQLite3.
- **Architecture**: "Separation of Powers" (Legislation: .env, Judiciary: LLM, Executive: System Logic).
- **Environment**: Always use `uv run` for script execution. Ensure `PYTHONPATH` includes `src`.
- **Logic Priority**: Archive reliability is paramount. If metadata is ambiguous, route to `Review`.
- **Mandatory Change History Recording**: Whenever you make changes, modifications, new additions, or deletions to any code or files in this workspace (except for system cleanup performed before tests), you MUST append an entry to `CHANGE_HISTORY.md`. Each entry must include: "Date and time (YYYY/MM/DD hh:mm:ss), name of the modified file, and details of the changes (in Japanese)." Always append new entries to the end of the file to maintain chronological order.
- **Installed tools**: rg, fd, uv, ruff, jq, pytest are already installed. If there are any other tools you would like to install, please explain what they are to the user and ask if they would like to install them.

## 📂 Directory Layout

- `src/scout/`: Core application logic.
- `data/`: Local state DB and cache.
- `docs/`: Technical specifications and logic definitions.
- `Maintenance/`: Test scripts, reproduction scripts, and temporary test data. All manual verification and investigative scripts MUST be placed here.
