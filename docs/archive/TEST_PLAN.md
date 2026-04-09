# TEST_PLAN

---

## 1. Worker Unit Tests

Run pytest on `worker/test/`. Each file verifies:

### test_flow_resolution.py
- `select_best_candidate` correctly selects the maximum value of `final_score`
- `select_best_candidate` returns `None` with empty list
- `_to_scored_candidates` correctly adds similar bonuses based on fallback_title
- `refine_candidates_with_fallback_title` adds new candidates and rescores
- `refine_candidates_with_fallback_title` retains existing candidates on search error

### test_config_and_scoring.py
- `load_config` now correctly loads retry / acoustid / storage settings from config.yaml
- `score_candidates` prioritizes candidates by track count & proximity of release date

### test_fallback_confidence.py
- `full_acoustid_fallback` returns `no_files` reason without file
- Includes match_ratio when `full_acoustid_fallback` is resolved=True

### test_storage_prefixes.py
- Does `put_json_for_prefix_name` PUT to the correct key with processed prefix (MOCK)?

### test_tagging_convert.py
- ffmpeg is called for FLAC → AIFF conversion
- Select bit depth 16 → `pcm_s16be` codec for WAV → AIFF conversion
- 96kHz/32bit source is converted to max_sample_rate=48000/max_bit_depth=24

### test_tagging_id3.py
- TRCK tag with track_number/total_tracks is written to the MP3 file

---

## 2. Scout Unit Tests

Run pytest on `scout/test/`.

### test_acf_parser.py
- Parse ACF and return dict
- Get `appid`, `name`, `StateFlags`, `installdir` correctly
- `is_installed` determines based on StateFlags

### test_library_scanner.py
- `_is_soundtrack_name` detects keywords such as OST/Soundtrack
- `_find_audio_files` only returns sound files and excludes non-sound sources
- `_find_audio_files` recursively retrieves subdirectories
- `_find_audio_files` returns a sorted list
- return empty list with empty directory

### test_uploader.py
- No S3 operations occur during dry-run
- dry-run returns `UploadResult`
- ACF keys are in `ingest/{app_id}/manifest.acf` format
- Sound source file key is in `ingest/{app_id}/Disc 1/{ext}/` format
- scout_result.json key becomes `ingest/{app_id}/scout_result.json`

---

## 3. E2E / Integration Test Scenarios

Perform manual or automatic verification in the following three scenarios:

| Scenario | Contents |
|--------|------|
| known correct | Known album where VGMdb candidate is accepted with high reliability (`vgmdb_score >= 0.75`) |
| ambiguous | Albums where MusicBrainz matching occurs on `0.70 <= vgmdb_score < 0.75` |
| failure | Cases where AcoustID match rate is low and sent to review/ |

---

## 4. E2E acceptance criteria

- At least 90% of tracks are correctly identified (according to SUCCESS_CRITERIA.md)
- Sorting to review/ is done correctly for failure/low reliability cases.
- structured log includes job_id, track_id, step, result, error
