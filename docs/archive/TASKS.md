# SST Tasks

---

## Phase 0: Infrastructure

Goal:
- Run a minimal Prefect flow on current Docker environment and confirm SeaweedFS connectivity.

Tasks:
- Setup Prefect server and verify API health.
- Configure SeaweedFS S3 endpoint and credentials.
- Confirm bucket and prefixes:
	- bucket: sst
	- prefixes: ingest/, archive/, review/, processed/
- Setup Docker nodes (core/scout/worker) with shared network reachability.

Acceptance Criteria:
- Prefect API is reachable from worker container.
- Worker can execute S3 ListBuckets/PutObject/GetObject.
- A test object is written and read successfully under processed/.

---

## Phase 1: Scout

Goal:
- Collect Steam metadata required for album candidate narrowing.

Tasks:
- Implement Steam metadata fetch (AppID, localized title, release date).
- Implement browser-use integration only where API data is insufficient.
- Normalize localized/original titles for downstream search.
- Output JSON contract consumable by core flow.

Acceptance Criteria:
- Given app_id, scout returns deterministic metadata JSON.
- Missing fields are explicitly marked and logged.

---

## Phase 2: Core

Goal:
- Orchestrate full pipeline as Prefect flow with deterministic retries and state transitions.

Tasks:
- Define flow entry parameters:
	- app_id: int
	- files: list[str]
- Implement task graph:
	- fetch_steam_metadata
	- search_vgmdb
	- verify_with_musicbrainz
	- score_candidates
	- partial_acoustid_verify
	- full_acoustid_fallback
	- write_tags
	- persist_results
- Configure retry policy via config:
	- retry.max_attempts
	- retry.base_delay_sec
- Enforce rule: partial verification failure must escalate to full AcoustID.

Acceptance Criteria:
- Flow runs can be triggered manually and from deployment.
- Failure/retry behavior matches docs/ERROR_HANDLING.md and docs/STATE_MACHINE.md.
- Flow-level output JSON is produced for success and review cases.

---

## Phase 3: Worker

Goal:
- Implement worker modules and local execution path for one album end-to-end.

Tasks:
- Implement modules:
	- acoustid/
	- fingerprint/
	- musicbrainz/
	- scoring/
	- tagging/
	- pipeline/
	- models/
- Implement fpcalc wrapper and duration extraction.
- Implement candidate scoring and threshold decision.
- Implement tagging with ID3v2.3.
- Implement SeaweedFS persistence:
	- input references from ingest/
	- output to archive/
	- review artifacts to review/
	- transient data to processed/
- **[Added] Worker output field implementation for vgmdb_id / discid**:
- Add `vgmdb_id` (str | None) and `discid` (str | None) to the resolved dict.
- VGMdb primary search results are prioritized and MusicBrainz is used for verification/fallback.
- Match the Worker Output output contract in DATA_CONTRACTS.md.
- **[Added] Utilization of search / album_match settings**:
- Control language variants when searching VGMdb based on `search.languages`.
- Reflect `album_match.track_count_tolerance` in the track number comparison of scoring/album.py.
- Reflect `album_match.date_tolerance_days` to `_date_score` of scoring/album.py (currently hardcoded 30 days).
- Add SearchConfig / AlbumMatchConfig to WorkerConfig and read from config.yaml.
- **[Added] `identify_track` signature correction in INTERFACES.md**:
- Add `api_key: str`, `api_url: str` to the current `identify_track(duration, fingerprint)` to match the implementation.
- Update the Functions section of `docs/INTERFACES.md`.
- **[Added] Added retry settings to `write_tags_task`**:
- Add `retries=1` with the `@task` decorator or `with_options`.
- Output `WARNING` log when `write_tags` skips non-MP3 files (silent ignore prohibited).
- Consistent with the Tag Write Failure clause of `docs/ERROR_HANDLING.md`.

Acceptance Criteria:
- One 31-track album completes with tags updated and output JSON written.
- Partial verification failure correctly triggers full fallback.
- Ambiguous/failure runs are persisted to review/.

---

## Phase 4: Integration

Goal:
- Validate production-like behavior for quality, observability, and operability.

Tasks:
- Implement pytest suite for unit and integration tests.
- Execute E2E test set:
	- 1 known correct album
	- 1 ambiguous album
	- 1 failure album
- Validate structured logging fields:
	- job_id, track_id, step, result, error
- Validate retry/backoff and final review routing.
- Add deployment runbook for local operations.

Acceptance Criteria:
- Success criteria in docs/SUCCESS_CRITERIA.md are met.
- Test reports and run artifacts are reproducible.
- Operational runbook allows rerun without manual hidden steps.

---

## Current Priority (MVP)

- Implement Phase 3 first for single-album E2E with manual app_id input.
- Keep Scout optional for MVP; use direct metadata input when needed.
- Complete Phase 2 minimal Prefect orchestration once worker path is stable.

---

# END
