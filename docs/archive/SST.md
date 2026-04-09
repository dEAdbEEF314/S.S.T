# SST integration specification

Last updated: 2026-04-07

## 1. Purpose

SST (Steam Soundtrack Tagger) is a distributed processing system that automatically identifies soundtrack sound sources purchased on Steam, completes metadata, tags them, and saves them.

This project focuses on the following:

- Applies to Steam purchased soundtracks only.
- Prefer accuracy over speed
- Reliably separate failure cases into reviews
- Achieve high automation rates with less manual intervention

## 2. Scope

### 2.1 Target

- Soundtrack from Steam Library
- Bring local audio sources into SeaweedFS and identify, tag, and store them with Workers

### 2.2 Non-targeted

- Non-Steam sourced audio sources
- Real-time distribution processing
- Decisions based only on a single data source

## 3. Overall architecture

SST has a distributed configuration orchestrated by Prefect.

- Scout VM: Steam library scanning, ACF parsing, uploading to ingest
- Core VM: Prefect flow execution, state management, retry control
- Worker Container: Sound source processing, AcoustID, MusicBrainz/VGMdb completion, tag writing
- LLM Node: OpenAI API compatible interface for title normalization and auxiliary inference
- SeaweedFS (S3 compatible): ingest/archive/review/processed storage

### 3.1 Storage structure

```text
sst/
├─ ingest/
├─ archive/
├─ review/
└─ processed/
```

## 4. End-to-end processing

### 4.1 Scout ingest

Scout does the following:

1. Scan `steamapps/appmanifest_*.acf`
2. Soundtrack judgment (keywords and minimum number of sound sources)
3. Collect and normalize for each sound source extension
4. Place manifest/acf/scout_result and sound source to `ingest/{AppID}/`

Placement rules:

- Basic: `ingest/{AppID}/{Disk No.}/{ext}/{filename}`
- Complement `Disc 1` if there is no disk hierarchy
- Redundant hierarchies that overlap with extension names such as `FLAC/` are removed by normalization.

### 4.2 Worker pipeline

The Worker processing flow is below.

1. Get Steam metadata (title, release_date)
2. VGMdb search (via hufman/vgmdb, ja/en/romaji)
3. VGMdb candidate filter (Digital Media, number of songs allowed ±1, date allowed 30 days)
4. VGMdb confidence score calculation
5. If `vgmdb_score >= 0.75`, adopt VGMdb candidate
6. `0.70 <= vgmdb_score < 0.75` will be verified and re-evaluated by MusicBrainz
7. `vgmdb_score < 0.70` is MusicBrainz search (ja/en/original integration)
8. If both sources are low trust (`< 0.55`), separate into review
9. Skip AcoustID if you have a high score (Fast-track)
10. If the score is low, use partial AcoustID (first N songs)
11. Full song AcoustID fallback when partial mismatch occurs
12. Format conversion + LLM title normalization
13. ID3v2.3 writing
14. Save to archive or review

## 5. State transition

Standard condition:

- `INGESTED`
- `IDENTIFIED`
- `FINGERPRINTED`
- `ENRICHED`
- `TAGGED`
- `STORED`
- `FAILED`

Transitions:

- Standard: `INGESTED -> IDENTIFIED -> FINGERPRINTED -> ENRICHED -> TAGGED -> STORED`
- Fast-track: `INGESTED -> IDENTIFIED -> ENRICHED -> TAGGED -> STORED`
- Failure: `ANY -> FAILED` (ultimately sent to review)

## 6. Identification Strategy

### 6.1 Source Priority

1. Manual verification
2. VGMdb
3. MusicBrainz
4. Steam

### 6.2 Candidate extraction conditions

- `format = Digital Media`
- Song number difference: `track_count_tolerance = ±1`
- Daily difference: `date_tolerance_days = 30`
- Title similarity: `title_similarity >= 0.80`

### 6.3 Scoring and Judgment

Score elements:

- title_similarity
- track_count_match
- release_date_match
- format_match
- vgmdb_bonus (if applicable)

judgement:

- `vgmdb_score >= 0.75` uses VGMdb
- Check with MusicBrainz for `0.70 <= vgmdb_score < 0.75`
- Fallback to MusicBrainz for `vgmdb_score < 0.70`
- If both sources are `< 0.55`, separate into review
- Skip AcoustID for `final_score >= skip_acoustid_threshold` of the hiring candidate
- Otherwise partial AcoustID, fallback to full AcoustID if the partial match rate is less than the threshold

## 7. Tagging specification (ID3v2.3)

Main mapping:

- `TIT2`: LLM-normalized title
- `TPE1`: VGMdb performers > MB artist_credit
- `TALB`: VGMdb name > MB title > Steam title
- `TPE2`: album artist (Various Artists if necessary)
- `TCON`: Soundtrack / Video Game Music
- `TCOM`: Composer
- `TDRC`: year
- `TRCK`: `n/total`
- `APIC`: 500x500, maintain aspect, black padding

TXXX:

- `MusicBrainzAlbumID`
- `VGMdbID`
- `CatalogNumber`
- `SteamAppID`

## 8. Sound source format conversion

- Lossless (`.flac`, `.wav`, `.aiff`, `.m4a`) -> `.aiff`
- For `.ogg` only -> `.mp3` of `CBR-320kbps-48kHz`
- Existing `.mp3` will be maintained

## 9. I/O Contract

### 9.1 Scout output (`scout_result.json`)

Main fields:

- `app_id`
- `name`
- `install_dir`
- `storage_location`
- `track_count`
- `files_by_ext`
- `acf_key`
- `uploaded_at`
- `dry_run`

### 9.2 Worker input

```json
{
  "app_id": 123456,
  "files": [
    "ingest/123456/Disc 1/flac/01 - Track One.flac"
  ]
}
```

### 9.3 Worker output

```json
{
  "app_id": 123456,
  "file_refs": [
    "archive/123456/Disc 1/aiff/Disc_1 - 1 - Example Track Title.aiff"
  ],
  "status": "success",
  "resolved": {
    "resolved": true,
    "source": "vgmdb",
    "album": "Example Album",
    "artist": "Example Artist",
    "composer": "Example Composer",
    "mbid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "vgmdb_id": "123456",
    "vgmdb_album_url": "https://vgmdb.net/album/123456",
    "catalog_number": "ABCD-1234",
    "discid": "...",
    "title": "Example Track Title",
    "resolution": "vgmdb_enriched",
    "partial_ratio": 0.85
  },
  "tag_result": {
    "updated": 1,
    "dry_run": false
  },
  "candidate_count": 5,
  "storage": {
    "bucket": "sst",
    "key": "archive/app_123456_20260101T000000Z.json"
  }
}
```

`status` is `success` or `review`.

## 10. Setting specifications

Setting resolution priority:

- `CLI arguments > environment variables > config.yaml > in-code defaults`

Main sections:

- `llm`: provider/model/api_key/base_url/temperature
- `storage`: endpoint/bucket/prefixes
- `mode`: dry_run
- `steam`: API URL
- `musicbrainz`: app_name/app_version/contact
- `acoustid`: api_key, skip/partial/fallback threshold
- `search`: Language strategy
- `album_match`: Number of songs/date allowed
- `retry`: Retry count and backoff
- `format`: Conversion upper limit
- `vgmdb` (Scout): proxy, cookie, language priority, rate limit
- `scan` (Scout): Target extension, judgment keyword, minimum number of files

## 11. Retry/Error Handling

Common principles:

- Silent failure prohibited
- Log all failures
- Retries are config driven

Representative rules:

- MusicBrainz: Exponential backoff with dedicated times
- AcoustID: Exponential backoff with dedicated number of times
- Temporary network error: retry
- `write_tags`: Issue WARNING and skip unsupported formats
- Unrecoverable/low reliability is saved to review

Backoff example:

- `delay_n = base_delay_sec * (base_backoff_factor ^ n)`

## 12. Operational requirements

- Python 3.11+
- Dependency management is uv
- Prefect 3.x
- Docker-based execution
- Stateless / Idempotent design
- Structured logs for all tasks

Minimum log items:

- `job_id`
- `track_id`
- `step`
- `result`
- `error`

## 13. Quality criteria

Criteria for successful execution:

- At least 90% of tracks are correctly identified
- Album matches correctly
- Tags are written without errors

## 14. Confirmed matters (formerly known unconfirmed matters)

### 14.1 mode.upload_audio_files

- **Default value**: `false` (disabled for continuous operation)
- **Usage scene**: Explicitly enabled only during initial import, reprocessing/debugging
- **Upload target**: Post-conversion deliverables only (format left in archive/review)
- **Storage amount**: false By default, unnecessary transfer of the original sound source is avoided. Specify true only when completion/correction is necessary.

### 14.2 Prefect PowerShell script execution requirements

- **Officially supported environment**: PowerShell 7.x
- **Policy**: Minimize the absorption of environmental differences on the script side. Prioritize prerequisite checks and step-by-step instructions in README
- **Minimum prerequisite checks recommended**:
  - Check PowerShell version
  - Check the existence of required commands (prefect, docker)
  - If the requirements are not met, the process will end immediately and you will be directed to the corresponding procedure in the README.
- **Prerequisites**: Docker, Prefect CLI, and uv have been installed.

### 14.3 Degradation specifications in case of VGMdb failure

#### 14.3.1 Failure determination conditions

The following cases are determined as VGMdb failure:

1. **HTTP Level**: 5xx / timeout / connection failure
2. **API Level**: 403 Forbidden / 429 Too Many Requests
3. **Data Quality**: Corrupt response structure/missing required fields

#### 14.3.2 Retry Strategy

- **Retry count**: 3 times
- **Retry Interval**: Exponential backoff
  - If the first attempt fails: wait 2 seconds → retry
  - Second time failure: wait 4 seconds → retry
  - 3rd time failure: wait 8 seconds → retry
- **Formula**: `delay = base_delay_sec * (base_backoff_factor ^ attempt_number)`

#### 14.3.3 Fallback Behavior

- **When all three times fail**: Degenerate VGMdb step
- **Continuation Strategy**: Continue processing only on MusicBrainz + Steam
- **Reliability judgment**:
  - `vgmdb_score >= 0.75`: adopt VGMdb
  - `0.70 <= vgmdb_score < 0.75`: Re-judgment based on MusicBrainz verification
  - `vgmdb_score < 0.70`: Fallback to MusicBrainz
  - Both sources `< 0.55`: Separated into review
- **Log**: Detailed record of all retry failure reasons (for recovery consideration)

#### 14.3.4 Configuration example

```yaml
vgmdb_client:
  enabled: true
  retry_max_attempts: 3
  retry_backoff_strategy: exponential
  retry_backoff_delays_sec:
    - 2
    - 4
    - 8
  fallback_on_failure: true # Proceed to IDENTIFIED even after all three failures
  confidence_accept_threshold: 0.75
  confidence_mb_fallback_threshold: 0.70
  confidence_review_threshold: 0.55
  title_similarity_threshold: 0.80
  track_count_tolerance: 1
  date_tolerance_days: 30
```

### 14.4 LLM integration details

#### 14.4.1 Basic policy

- **When LLM fails**: Processing continues. Fallback to non-LLM rules
- **Comparison strategy**: Compare two providers every time
- **Target tags**: Title, artist, album correction

#### 14.4.2 Two company comparison flow

1. **Throw to Primary + Secondary at the same time**
   - Use the same prompt template
   - Timeout management (independent of each company)

2. **Output comparison**
   - **String similarity score calculation** (editdistance + normalization)
   - Similarity ≥ 0.8 → Match judgment (automatic recruitment, reason recording)
   - Similarity < 0.8 → Go to mismatch flow

3. **Judgment in case of mismatch**
   - **Confidence score calculation** (multiple factors)
     - Inhibition rule inspection (empty characters, excessive symbols, etc.)
     - Context matching (degree of match with known database)
     - Dispersion of both company scores

   - **Reliability ≥ 0.65**: Automatic adoption (Warning recorded in log, reliability also recorded)
   - **0.6 ≤ Confidence < 0.65**: Gray zone (recruitment + special log)
   - **Reliability < 0.6**: Separated to review (subject to manual confirmation)

4. **LLM single-system failure support**
   - Primary failure → Determined only by Secondary (reliability -0.1 penalty)
   - Secondary failure → Judgment based only on Primary (reliability -0.05 penalty)

#### 14.4.3 Provider switching strategy

- **Prioritized Failover**:
  - If Primary (recommended: OpenAI / Gemini) fails -> Secondary (Ollama / alternative)
  - Secondary also fails → fallback to non-LLM rule
  - Retries follow provider settings

#### 14.4.4 Configuration example

```yaml
llm_validation:
  enabled: true
  dual_provider_compare: true
  similarity_threshold_consensus: 0.8
  confidence_threshold_auto_adopt: 0.65
  confidence_threshold_review: 0.6
  apply_to_fields:
    - title
    - artists
    - album

llm:
  provider: openai              # Primary
  model: gpt-4
  api_key: ENV
  base_url: https://api.openai.com/v1
  temperature: 0.1

llm_secondary:                   # Secondary
  provider: ollama
  model: qwen2.5-coder:14b
  api_key: ENV
  base_url: http://localhost:11434
  temperature: 0.1
```

#### 14.4.5 Priority of decision criteria

1. **Accuracy (mis tag minimization)**: Primary
2. **Cost (API usage fee minimization)**: Secondary
3. **Speed ​​(reduced processing time)**: Tertiary
4. **Operational ease (reduced maintenance burden)**: Quaternary

Cases judged to have low reliability are separated into reviews and manual re-evaluation is recommended.

## 15. Referenced document

- ARCHITECTURE.md
- SST_Project_Detailed_Specifications.md
- CONFIG_SPEC.md
- DATA_CONTRACTS.md
- IO_SPEC.md
- DATA_FLOW.md
- STATE_MACHINE.md
- PREFECT_FLOW.md
- ERROR_HANDLING.md
- INTERFACES.md
- CODING_RULES.md
- SUCCESS_CRITERIA.md
- requiring_specification.md
- TASKS.md
