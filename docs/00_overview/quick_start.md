# Quick Start

## Requirements

- Python 3.11+
- Docker
- Prefect 3.x
- uv (dependency manager)

---

## Setup

1. Install `uv` if not already present.
2. Clone the repository.
3. Setup virtual environment and install dependencies:
   ```bash
   uv sync
   ```
4. Configure environment variables (`.env`).
5. Prepare `config.yaml`.

---

## Execution Flow

1. Run Scout
2. Upload soundtrack files to ingest
3. Trigger Prefect flow
4. Worker processes files
5. Check results in archive/review

---

## Notes

- Ensure Docker is running
- Ensure Prefect API is accessible
- Ensure storage endpoint is reachable
