# S.S.T (Steam Soundtrack Tagger) Project Instructions

## 🚨 Critical Safety & Communication Rules

1. **Read-Only Steam Library**: NEVER attempt to write, modify, delete, or move files within the Steam library directories. Access must be strictly **READ-ONLY**. All processing results must be written to the designated `SST_OUTPUT_DIR`.
2. **Japanese Communication Mandate**: Before starting any technical task or execution phase, you MUST provide a detailed explanation of the planned work in **Japanese**. This includes the rationale, affected files, and expected outcome.

## 🛠️ Engineering Standards

- **Tech Stack**: Python 3.12 (managed via `uv`), FFmpeg, SQLite3.
- **Architecture**: "Separation of Powers" (Legislation: .env, Judiciary: LLM, Executive: System Logic).
- **Environment**: Always use `uv run` for script execution. Ensure `PYTHONPATH` includes `src`.
- **Logic Priority**: Archive reliability is paramount. If metadata is ambiguous, route to `Review`.
- **Keep a record of changes**: If you add or modify any files, be sure to update CHANGE_HISTORY.md with the following information: “Date and time (YYYY/MM/DD hh:mm:ss), name of the modified file, and details of the changes (in Japanese).”
- **Installed tools**: rg, fd, uv, ruff, jq, pytest are already installed. If there are any other tools you would like to install, please explain what they are to the user and ask if they would like to install them.

## 📂 Directory Layout

- `src/scout/`: Core application logic.
- `output/`: Processing artifacts (Archives and Reviews).
- `data/`: Local state DB and cache.
- `docs/`: Technical specifications and logic definitions.
