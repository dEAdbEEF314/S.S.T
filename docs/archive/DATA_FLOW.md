# DATA FLOW

## Overview

SST processes Steam-purchased soundtrack files through a multi-phase identification pipeline.

---

## Pipeline States

Soundtracks passing through this system will transition through the following statuses:
1. `INGESTED` (Start point: uploaded to SeaweedFS)
2. `IDENTIFIED` (Candidate extraction from web metadata and VGMdb information addition completed)
3. `FINGERPRINTED` (AcoustID verification completed, *If the score is high, you can skip using Fast-track)
4. `ENRICHED` (Final metadata normalization completed by LLM)
5. `TAGGED` (ID3 tag added)
6. `STORED` (Success: Saved to final storage completed) or `FAILED` (Failed: Waiting for manual review)

---

## Pipeline

### 0. SCOUT INGEST (pipeline starting point)

As a starting point for your system, Scout scans your local Steam library and efficiently pulls audio files and metadata into SeaweedFS.

- **Source**: Steam Library (`STEAM_LIBRARY_PATH`)
- **Process**:
  1. Scan `steamapps/appmanifest_*.acf`
  2. Determine whether the ACF `name` field contains a soundtrack keyword
  3. Search the installation directory in the order of `steamapps/music/` → `steamapps/common/`
  4. Processed check: Check the existence of `ingest/{AppID}/scout_result.json` on SeaweedFS (can be skipped with `--force`)
  5. Sound source collection: Collect and classify all files matching the target extension (`.flac`, `.mp3`, `.wav`, etc.)
  6. Normalization/correction: Removal of redundant folders (`FLAC/`, etc.) and auto-completion of missing `Disc 1` hierarchy
  7. Upload: Copy audio source, ACF, and statistical metadata (`scout_result.json`)

- **Asset placement on SeaweedFS**:
  ```text
  ingest/{AppID}/manifest.acf
  ingest/{AppID}/scout_result.json
  ingest/{AppID}/{Disk No.}/{ext}/{filename}
  ```
  - **Structuring rule**: Prioritize the disk hierarchy ({Disk No.}) such as `Disc 1` and place the extension directory under it. If there is no internal hierarchy, `Disc 1` is completed by default.
  - **Path Normalization**: If the original folder name exactly matches the current extension name, remove that hierarchy to avoid duplication.

- **Output**:
  - `scout_result.json`: Detailed metadata such as AppID, number of tracks, S3 key list by extension, upload date and time, etc.

---

### 1. INPUT (WORKER)

- **Source**: Various extension files under `ingest/{AppID}/` of SeaweedFS (all are downloaded in advance to the local `/mnt/work_area/{AppID}/` via S3 compatible API when starting Worker execution)
- **Metadata**: Steam AppID


2. STEAM METADATA FETCH

- Input: AppID
- Output:
  - title (localized)
    - release_date

---

3. VGMdb PRIMARY SEARCH

- Input:
  - title (ja/en/original)
- Process:
  - Run album search for `hufman/vgmdb` proxy
  - Integrated multilingual (ja/en/romaji) suggestions
  - Deduplicate by candidate_id

- Output:
  - VGMdb candidate albums

---

3.5 MUSICBRAINZ SECONDARY VERIFICATION

- Condition: If `vgmdb_score < 0.75`
- Process:
  - `0.70 <= vgmdb_score < 0.75`: Use MB for verification
  - `vgmdb_score < 0.70`: Use MB as fallback resolution source
  - Re-score candidates after MBID deduplication
- Output:
  - VGMdb/MB integration candidate albums

---

4. CANDIDATE FILTERING

Conditions:
- format = Digital Media
- track_count ≈ local file count (±1)
- release_date ≈ Steam release date (±30 days)
- title_similarity >= 0.80
- **If the VGMdb track list can be obtained, is the order and structure similar to the local file?**

---

5. SCORING

Each candidate receives a score:

score =
  title_similarity +
  track_count_match +
  release_date_match +
  format_match
  **+ vgmdb_bonus (if supported by VGMdb data)**

---

6. DECISION

- If `vgmdb_score >= 0.75`:
  → Adopt VGMdb as primary source
- If `0.70 <= vgmdb_score < 0.75`:
  → Perform MusicBrainz verification and re-judgment
- If `vgmdb_score < 0.70`:
  → Move to MusicBrainz fallback
- If both confidence `< 0.55`:
  → Separate into review
- Final candidate score ≥ `skip_acoustid_threshold` (e.g. 0.9):
  → **Fast-track**: Skip AcoustID verification and ACCEPT
- Otherwise:
  → Fallback to partial verify

---

7. PARTIAL ACOUSTID VERIFICATION

- Input: first 3 tracks
- Process:
  - fingerprint
  - match via AcoustID

- If match_ratio ≥ 0.8:
  → ACCEPT album
- Else:
  → Fallback to full AcoustID

---

8. FULL ACOUSTID (Fallback)

- Process all tracks
- Aggregate matches
- Determine album

---

9. FORMAT CONVERSION & LLM TITLE RESOLUTION (NEW)

- **Format Conversion**: 
  - Lossless (`.flac`, `.wav`, `.aiff`, `.m4a`): Convert to `.aiff` and locally delete the original file.
  - OGG (`.ogg`): Convert `CBR-320kbps-48kHz` to `.mp3` and delete the original file locally.
  - Other (`.mp3`): Keep as is.
- **LLM Resolution**:
  - Unified to **OpenAI API compatible method** using Python's `openai` library etc.
  - Based on the multiple candidates obtained (including language-specific information from VGMdb) and the original file name, one optimal title name is determined.

---

10. TAGGING

- Write ID3v2.3 tags (to `.mp3` & `.aiff`)
- Mapping specifications:
  - `TIT2`: Optimal track name for LLM determination
  - `TPE1`, `TALB`, `TPE2`, `TCON`, `TIT1`, `COMM`, `TCOM`, `TDRC`, `TRCK` are assigned according to the definition
  - `APIC`: Artwork (500x500 PNG, Aspect Ratio: Black background padding)
  - `TXXX`: `MusicBrainzAlbumID`, `VGMdbID`, `VGMdbDiscID`

---

11. STORAGE

- **archive/**: Files that have been processed and tagged (success) are renamed to `Disc_{Disc No.} - {Track_Number} - {Title}.{Extension}` and uploaded to SeaweedFS while maintaining the directory structure (`Disc {X}/{ext}/`). Also upload JSON. Once the upload is complete, local temporary files will be deleted immediately.
- **review/**: Save metadata JSON of resolution failure (review).
- **processed/**: Saves the pipeline execution metadata log for each pipeline run (formerly known as workspace).

---

## Notes

- Album-level and track-level logic MUST be separated
- All decisions must be deterministic and reproducible
