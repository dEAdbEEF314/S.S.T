# PREFECT FLOW

## Flow Name

sst-worker-pipeline

---

## Purpose

Enter Steam soundtrack files, search for candidates, verify, write tags, and save.
Execute observably and re-executably with Prefect.

---

## Flow Parameters

- app_id: int
- files: list[str]
- config_path: str
- dry_run: bool = false

Notes:
- The input contract has files as positive.
- Even if app_id cannot be obtained, it can be executed if files are available, but the drop in accuracy will be clearly indicated in the log.

---

## Task Graph

1. fetch_steam_metadata
2. search_vgmdb_task
3. verify_with_musicbrainz_task
4. score_candidates_task
5. partial_acoustid_verify
6. full_acoustid_fallback
7. write_tags_task
8. persist_results

---

## Task Responsibilities

### fetch_steam_metadata
- Input: app_id
- Output: title variants, release_date
- Retry: config.retry.max_attempts (default 3), exponential backoff
- Default task decorators: retries=3, retry_delay_seconds=5
- Overwrite the config value with with_options when running Flow

### search_vgmdb_task
- Input: title variants
- Behavior: Multilingual search using hufman/vgmdb (ja/en/romaji)
- Output: vgmdb candidate list
- Retry: vgmdb_client.retry_max_attempts (default 3), exponential backoff (2/4/8 sec)

### verify_with_musicbrainz_task
- Input: title variants
- Behavior:
- `0.70 <= vgmdb_score < 0.75` is used for verification
- `vgmdb_score < 0.70` is used for fallback resolution
- Output: secondary-verified candidate list
- Retry: config.retry.musicbrainz_max_attempts (default 2), exponential backoff

### score_candidates_task
- Input: candidates, local context
- Output: scored candidates, best candidate
- Note:
- `vgmdb_score >= 0.75` is adopted by VGMdb
- `0.70 <= vgmdb_score < 0.75` is selected after MB verification
- `vgmdb_score < 0.70` is MB fallback
- If confidence of both sources is `< 0.55`, review
- Fast-track if final score is `>= cfg.acoustid.skip_acoustid_threshold`

### partial_acoustid_verify
- Input: first N tracks, best candidate title, partial_tracks, threshold
- Output: match_ratio
- Rule: failure must escalate to full_acoustid_fallback

### full_acoustid_fallback
- Input: all tracks
- Output: resolved album or failure reason
- Note: Search MusicBrainz candidates again using the fallback title and readjust the final album/artist.

### write_tags_task
- Input: resolved metadata, files
- Output: tagging result summary

### persist_results
- Input: run artifacts
- Output: objects in SeaweedFS
- Paths:
	- ingest/ for source file reference manifests
	- archive/ for successful outputs
	- review/ for ambiguous or failed cases
	- processed/ for run metadata and temporary/cache-like artifacts

---

## State and Transition Rules

- Preferred path:
	INGESTED -> IDENTIFIED (VGMdb Primary) -> FINGERPRINTED -> ENRICHED -> TAGGED -> STORED
- Fast-track path:
	INGESTED -> IDENTIFIED (VGMdb>=0.75 or MB verified) -> ENRICHED (AcoustID Skip, score >= skip_acoustid_threshold) -> TAGGED -> STORED
- Failure path:
	Any state -> FAILED -> review/

---

## Retry and Error Policy

- Config keys:
	- retry.max_attempts
	- retry.base_delay_sec
	- retry.backoff_strategy (default: exponential)
	- retry.base_backoff_factor (default: 2)
	- retry.acoustid_max_attempts (default: 3)
	- retry.musicbrainz_max_attempts (default: 2)
	- vgmdb_client.retry_max_attempts (default: 3)
	- vgmdb_client.confidence_accept_threshold (default: 0.75)
	- vgmdb_client.confidence_mb_fallback_threshold (default: 0.70)
	- vgmdb_client.confidence_review_threshold (default: 0.55)
- Retry target:
	- network timeouts
	- transient API failures
- Fails even after Retry:
- Fallback if possible
- If not possible, send to review/
- Exponential Backoff:
- retry_delay_seconds generates a list of [base_delay_sec * factor^0, base_delay_sec * factor^1, ...]
- Applied with with_options of Prefect

---

## Concurrency Policy (MVP)

- Sequential execution in album units (first of all, reproducibility is given priority)
- Track-based parallelization will be expanded in the future
- Deployment concurrency_limit starts at 1 and increases after stabilizing

---

## Deployment Notes (MVP)

- Use Docker or Process work pool for self-hosted Prefect.
- Required runtime env:
	- PREFECT_API_URL
	- S3_ENDPOINT_URL
	- S3_ACCESS_KEY
	- S3_SECRET_KEY
	- S3_BUCKET
	- ACOUSTID_API_KEY
- Observe run states in Prefect UI and verify final artifacts in SeaweedFS.

Core operational scripts:
- core/prefect/setup-work-pool.ps1
- core/prefect/deploy-worker-flow.ps1
- core/prefect/run-worker-deployment.ps1

---

## Run Checklist

1. Prefect API reachable from worker.
2. SeaweedFS credentials valid (list/put/get success).
3. Trigger flow with app_id and files.
4. Confirm fallback behavior on partial verify failure.
5. Confirm archive/review outputs.

---

# END
