
This document defines all keys that can be specified in `config.yaml`.
Items whose environment variable is marked as `ENV` can be overwritten from the environment variable.

Settings are categorized by component as **common (core)** / **worker specific** / **scout specific**.

---

## Common settings (core)

### llm

```yaml
llm:
  provider: ollama            # ollama, google-genai, openai
  model: qwen2.5-coder:14b
  api_key: ENV # ENV: LLM_API_KEY (optional for local LLM)
  base_url: http://localhost:11434  # ENV: OLLAMA_BASE_URL
  temperature: 0.1
```

### storage

```yaml
storage:
  provider: s3_compatible
  endpoint_url: <placeholder>  # ENV: S3_ENDPOINT_URL (required)
  bucket: sst                                  # ENV: S3_BUCKET
  prefixes:
    ingest: ingest/
    archive: archive/
    review: review/
    processed: processed/
```

### mode

```yaml
mode:
  dry_run: false
```

---

## Worker specific settings

### steam

```yaml
steam:
  api_url: https://store.steampowered.com/api/appdetails
```

Notes:
- Can be replaced with mock server URL during testing

### musicbrainz

```yaml
musicbrainz:
  app_name: sst
  app_version: "0.1"
  contact_url: https://example.invalid
```

Notes:
- User-Agent setting is required according to MusicBrainz API Terms of Use
- Recommended to change `contact_url` to the actual contact URL of your project

### acoustid

```yaml
acoustid:
  api_url: https://api.acoustid.org/v2/lookup
  api_key: ENV # ENV: ACOUSTID_API_KEY (required)
  skip_acoustid_threshold: 0.9 # Skip AcoustID verification if MusicBrainz score is greater than or equal to this value
  score_gap: 0.05
  partial_verify_tracks: 3
  partial_match_threshold: 0.8
  full_fallback_min_match_ratio: 0.4
```

### search

```yaml
search:
  languages:
    - ja
    - en
    - original
  strategy: merge
```

### album_match

```yaml
album_match:
  track_count_tolerance: 1
  date_tolerance_days: 30
```

### retry

```yaml
retry:
  max_attempts: 3
  base_delay_sec: 5
  backoff_strategy: exponential
  base_backoff_factor: 2
  acoustid_max_attempts: 3
  musicbrainz_max_attempts: 2
```

### format

```yaml
format:
  lossless_target: aiff
  max_sample_rate: 48000
  max_bit_depth: 24
```

Notes:
- max_sample_rate / max_bit_depth are used as upper limit values ​​during conversion
- If the source is less than this, keep it as is, only if it exceeds, downsample/reduce bit depth
- If the sound source is only in `.ogg` format (without lossless), it will be converted to `.mp3` with an upper limit of `CBR-320kbps-48kHz` to maintain quality.

### vgmdb_client

```yaml
vgmdb_client:
  enabled: true
  retry_max_attempts: 3 # Number of retries when VGMdb query fails
  retry_backoff_strategy: exponential # backoff strategy: exponential | linear
  retry_backoff_delays_sec: # Number of seconds to wait for each retry step (ignored for exponential backoff)
    - 2
    - 4
    - 8
  fallback_on_failure: true # Continue with MusicBrainz+Steam if all three times fail?
  confidence_accept_threshold: 0.75 # Accept VGMdb above this value
  confidence_mb_fallback_threshold: 0.70 # Fallback to MusicBrainz below this value
  confidence_review_threshold: 0.55 # If both sources are less than this value, separate to review
  title_similarity_threshold: 0.80 # Threshold for title matching judgment
  track_count_tolerance: 1 # Track count difference tolerance (±1)
  date_tolerance_days: 30 # Date difference tolerance (days)
```

Notes:
- `retry_max_attempts`: If the inquiry to VGMdb fails (HTTP 5xx/timeout/connection failure/403/429/response structure corruption), retry this number of times.
- When `retry_backoff_strategy: exponential` is specified, `retry_backoff_delays_sec` is ignored and calculated using `base_delay_sec * (base_backoff_factor ^ attempt)`.
- If `fallback_on_failure: true`, proceed to the IDENTIFIED step even after all three failures and continue with MusicBrainz+Steam only (review separation is determined by reliability)
- For `fallback_on_failure: false`, transition to FAILED state after all three failures
- `confidence_accept_threshold`: VGMdb primary adoption threshold (0.75)
- `confidence_mb_fallback_threshold`: Fallback boundary to MB (0.70)
- `confidence_review_threshold`: Review separation boundary when both sources are unreliable (0.55)

### llm_validation

```yaml
llm_validation:
  enabled: true # Enable LLM validation?
  dual_provider_compare: true # Compare two providers before hiring each time
  similarity_threshold_consensus: 0.8 # String similarity threshold (0.0-1.0) to determine that the outputs of two companies match
  confidence_threshold_auto_adopt: 0.65 # When there is a discrepancy between two companies, if the confidence level is above this level, it will be automatically adopted, if it is below this level, it will be separated into review.
  confidence_threshold_review: 0.6 # review separation threshold (separation below)
  apply_to_fields: # Tags to which LLM validation applies
    - title
    - artists
    - album
```

Notes:
- For `enabled: false`, LLM validation step is skipped and MusicBrainz/VGMdb results are used as is.
- Every time `dual_provider_compare: true` throw the same prompt at two companies (Primary + Secondary) and compare
- `similarity_threshold_consensus`: Normalized score based on editdistance. 0.8 = Match within 20%
- `confidence_threshold_auto_adopt`: For gray zone judgment. If it is less than 0.65, it is subject to review.
- LLM verification targets can be restricted with `apply_to_fields` (if omitted, the above 3 fields)

---

## Scout specific settings

### vgmdb

```yaml
vgmdb:
  enabled: true
  cddb_url: http://vgmdb.net:80/cddb/ja.utf8
  proxy_url: http://localhost:9801                 # ENV: VGMDB_PROXY_URL
  user_cookie: ENV # ENV: VGMDB_USER_COOKIE (Automatic update by Playwright recommended)
  rate_limit_sec: 2
  lang_priority:
    - ja
    - en
    - romaji
  notification_webhook: ENV # ENV: VGMDB_WEBHOOK_URL (Discord/Slack, etc., notification destination when cookie expires)
  auth_local_port: 8080 # Port number of browser launch endpoint for local authentication
```

### paths

```yaml
paths:
  input: /mnt/work_area
```

### scan

```yaml
scan:
  audio_extensions:
    - .flac
    - .mp3
    - .ogg
    - .wav
    - .m4a
    - .aiff
  soundtrack_keywords:
    - "OST"
    - "Soundtrack"
    - "Sound Track"
    - "Original Sound"
    - "Music Pack"
    - "Digital Soundtrack"
    - "Original Score"
  min_audio_files: 1
```

Notes:
- `audio_extensions`: Extension list of sound source files to be scanned
- `soundtrack_keywords`: Keyword that is determined as a soundtrack if it is included in the `name` field of ACF
- `min_audio_files`: Minimum number of files to be recognized as a soundtrack
- These values ​​have priority over the default constants in the code (see ``Configuration Priority'' below).

---

## Setting priority

Each setting value is resolved in the following priority order (the top has the highest priority).

### General

```
CLI arguments > Environment variables (.env) > config.yaml > Default values ​​in code
```

### scan section specific

```
config.yaml > default constants in code
```

`AUDIO_EXTENSIONS` / `SOUNDTRACK_KEYWORDS` within `library_scanner.py` are kept as default values ​​for fallback, but
If a value is specified in the `scan` section of `config.yaml`, the value in the configuration file takes precedence.

### bucket settings

If the `S3_BUCKET` environment variable is empty or unset, it automatically uses `sst` as the default value.

```
Environment variable S3_BUCKET > bucket in config.yaml > default value "sst"
```

---

## Scout CLI options

```
python main.py [OPTIONS]
```

| Options | Type | Description |
|-----------|------|------|
| `--steam-library PATH` | str | Steam library root path (overrides `STEAM_LIBRARY_PATH` environment variable) |
| `--app-id ID` | int | Process only the specified AppID |
| `--dry-run` | flag | Does not perform S3 operations, only logs what is uploaded |
| `--no-audio` | flag | Upload only ACF manifest and skip audio files |
| `--force` | flag | Skip unprocessed checks and reprocess already processed AppIDs |
| `--limit N` | int | Maximum number of new soundtracks to process (for testing/debugging) |
| `--log-level LEVEL` | str | Log level specification (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `--config FILE` | str | config.yaml path (default: `/app/config.yaml`) |
| `--output-json FILE` | str | Write execution summary JSON to specified file |

### --limit operation specifications

- Does not limit the scan (library detection) itself, only limits the number of upload processes**
- Extract and process the first N items from the target list after applying unprocessed filtering.
- When used with `--force`, process the first N items from all detected apps
- If omitted, all items will be processed (no limit)

### --force behavior specifications

- Skip outstanding check due to presence of `ingest/{AppID}/scout_result.json` on SeaweedFS
- Already uploaded files will be overwritten

---

## Log level specifications

Log level priority: `CLI (--log-level)` > `environment variable (LOG_LEVEL)` > Default (`INFO`)

| Level | Output content |
|--------|---------|
| `DEBUG` | List of all ACF files to be scanned, skip reason details, S3 key generation log, size of each file, extension classification results |
| `INFO` | Detected soundtrack list, processing start/completion, upload progress, number of skips, final summary |
| `WARNING` | ACF parsing failure, installation path not found, inconsistent settings |
| `ERROR` | S3 connection failure, upload error, fatal configuration error |

---

## SeaweedFS storage specifications

### API used

Scout accesses SeaweedFS via the **S3 Compatible API**.
Since the S3 API does not have the object concept of "directory", specifying the key with `put_object`
Intermediate paths (directory-visible prefixes) are automatically recognized.
**No explicit directory creation required**.

> When using SeaweedFS' Filer API, there are cases where it is necessary to explicitly create an empty directory.
> This time it is not applicable because it is via S3 API. Filer API support is for future consideration.

### Ingest directory structure

```text
{S3_BUCKET}/
  ingest/
    {AppID}/
      manifest.acf ← ACF manifest file
      scout_result.json ← Scan result metadata
      Disc 1/ ← Disk hierarchy (supplement if not available)
        flac/ ← Directory by extension
          01 - Track One.flac
          subdir/02 - Track Two.flac ← Subdirectory structure is maintained
        mp3/
          01 - Track One.mp3
      Disc 2/
        flac/
          01 - Bonus Track.flac
```

- **Basic structure**: `ingest/{AppID}/{Disk No.}/{extension}/{filename}`
- **Disc Hierarchy Completion**: If the source file is not in a specific disc directory, `Disc 1` is completed by default (for metadata consistency).
- **Subdirectory preservation**: Further subdirectory structures in the disk hierarchy are also preserved, such as `Disc 1/subdir/flac/file.flac`.
- **Extension directory placement**: Extension directories (`flac/`, `mp3/`, etc.) are always placed as the immediate parent directory of the file name.
- **Path normalization**: If the original folder name exactly matches the current extension name (e.g. `FLAC/01.flac`), redundant hierarchies (`FLAC/`) are removed.

### Unprocessed judgment

Determine whether processing has been completed based on the presence of `ingest/{AppID}/scout_result.json`.
Overwriting and reprocessing is possible with the `--force` flag.

### All format collection

If multiple format subdirectories exist (e.g. `flac/` and `mp3/`),
**Copy all files in all formats** (does not select only the highest priority format).
