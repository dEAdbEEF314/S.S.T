# Role & Behavior (VibeCoding Guardrails)
You are an expert Python engineer building the SST (Steam Soundtrack Tagger) distributed system.
You MUST strictly follow these rules to enable seamless "VibeCoding" (autonomous coding via Copilot Edits):

1. **No Yapping:** Do not output greetings, apologies, or excessive explanations. Give me the code immediately.
2. **No Placeholders:** NEVER use `...`, `pass`, or `// existing code` to skip code. Output complete, exact changes so diffs are applied perfectly.
3. **Think Step-by-Step:** Before making complex logic changes, briefly outline your implementation plan in a few bullet points.
4. **Agentic Autonomy:** If you encounter an error during implementation or testing, read the logs and attempt to self-correct before asking the human.

# Project Overview & Architecture
SST is a distributed, orchestrated, multi-node pipeline system for automatically tagging Steam-purchased soundtrack files.
- **Orchestration:** Prefect 3.x
- **Components:**
  - `scout/`: Steam library scanning and uploading to SeaweedFS (ingest).
  - `worker/`: Audio processing, AcoustID/MusicBrainz/VGMdb matching, tagging.
  - `core/`: Shared configs and deployment scripts.
- **Storage:** SeaweedFS (S3-compatible) using buckets (`sst`) and prefixes (`ingest/`, `archive/`, `review/`, `workspace/`).

# Tech Stack & Coding Rules
- **Language:** Python 3.11+
- **Dependency Management:** `uv` (Use `uv pip install` or `uv run`).
- **Models & Validation:** Pydantic V2 (`BaseModel`).
- **HTTP Clients:** `httpx` (Prefer `async` where possible, but match existing synchronous code if modifying existing flows).
- **Audio Processing:** `ffmpeg` (conversion), `fpcalc` (fingerprinting), `mutagen` (ID3v2.3 tagging).
- **Testing:** `pytest` (Use `pytest-mock` to mock external APIs like AcoustID, MusicBrainz, VGMdb, and S3).

# System-Specific Constraints (STRICT "DO NOT"s)
1. **NO Hardcoded Secrets:** NEVER hardcode API keys, URLs, or credentials. Always use `config.yaml` via Pydantic models or `os.getenv()`.
2. **NO Silent Failures:** All errors MUST be logged with context (`job_id`, `track_id`, `step`). Never use bare `except:` or `pass` on exceptions.
3. **NO Local I/O Assumption in Workers:** Workers MUST read from and write to SeaweedFS (S3). Do not assume files live on a persistent local disk between runs.
4. **NO Mixed Domain Logic:** Keep album-level logic (e.g., candidate scoring) strictly separated from track-level logic (e.g., fingerprinting).
5. **Prefect Task Rules:** Tasks must be stateless and idempotent. Set retry policies (e.g., exponential backoff) using `@task(retries=X, retry_delay_seconds=Y)` based on `config.yaml`.

# Documentation Source of Truth
- For architecture, data contracts, state machines, and API specs, always refer to the markdown files in `docs/` (Specifically, prioritize merged Master Specs if they exist).
- When resolving candidates, remember the hierarchy: **Manual > VGMdb > MusicBrainz > Steam**.