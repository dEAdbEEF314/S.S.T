# ERROR HANDLING

## General Rules

- All errors must be logged
- No silent failures
  - Even when `write_tags` skips a file in an unsupported format (other than MP3), output logs at WARNING level.
- Retry must be controlled via config

---

## Cases

### AcoustID Timeout

- Retry: 3 times (configurable via retry.acoustid_max_attempts)
- Backoff: exponential (base_delay_sec * base_backoff_factor^n)
- Backoff strategy and coefficients can be changed in config

---

### MusicBrainz Failure

- Retry: 2 times (configurable via retry.musicbrainz_max_attempts)
- Backoff: exponential
- Used as secondary path when VGMdb confidence is insufficient
- If still failing and VGMdb confidence `< 0.55` → move to review

---

### VGMdb Failure

- Retry: 3 times (configurable via vgmdb_client.retry_max_attempts)
- Backoff: exponential (2s, 4s, 8s)
- Error classes:
  - HTTP 5xx / timeout / connection failure
  - HTTP 403 / 429
  - malformed response / required field missing
- If still failing:
  - fallback_on_failure=true: Continue on MusicBrainz + Steam
  - fallback_on_failure=false: FAILED -> review

---

### Fingerprint Failure

- Mark track as FAILED
- Skip album if >50% fail

---

### Tag Write Failure

- Supported formats: MP3 (ID3v2.3) and AIFF (ID3v2.3)
- Non-Supported formats: `write_tags` logs WARNING and skips it (silent ignore prohibited)
- Retry once
- If fail → move to review
- Add `retries=1` to `write_tags_task`

---

### Network Errors

- Always retry with exponential backoff

---

## Config Keys

- retry.max_attempts: Default number of retries
- retry.base_delay_sec: Base delay seconds
- retry.backoff_strategy: Backoff strategy (exponential)
- retry.base_backoff_factor: Backoff factor (default: 2)
- retry.acoustid_max_attempts: AcoustID dedicated retry count
- retry.musicbrainz_max_attempts: MusicBrainz exclusive retry count
- vgmdb_client.retry_max_attempts: VGMdb dedicated retry count
- vgmdb_client.confidence_accept_threshold: VGMdb adoption lower bound (0.75)
- vgmdb_client.confidence_mb_fallback_threshold: MB fallback bound (0.70)
- vgmdb_client.confidence_review_threshold: review separation boundary (0.55)

---

## Implementation Notes

- Set default retry value in Prefect task decorator
- Override config values ​​using with_options in Flow
- Pass the exponential backoff column in list format to retry_delay_seconds

---

## Logging Format

- job_id
- track_id
- step
- error
