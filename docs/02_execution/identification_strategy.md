# Identification & Tie-breaking Strategy (Act-11)

SST uses a multi-layered evidence approach to resolve metadata conflicts. This document explains how the system ranks candidates and weights information.

## 1. Information Evidence Weights

When consolidating metadata, the system assigns weights to different sources:

| Weight Level | Source Type | Description |
| :--- | :--- | :--- |
| **LOCKED** | Steam API | Fixed values like AppID, Store URL, and Developer. Non-negotiable. |
| **STRONG** | Cross-validated Tags | Metadata that matches perfectly across multiple file formats (e.g. MP3 and FLAC). |
| **BASE** | MusicBrainz | Official database candidates. Provides the logical tracklist structure. |
| **WEAK** | Raw Headers / Filenames | Metadata extracted from single files or inferred from filenames. Used only when others fail. |

## 2. MusicBrainz Scoring (Rules a-f)

The system filters and ranks MusicBrainz (MBZ) candidates before presenting them to the LLM. The score is calculated as follows:

- **a. Album Title Match (+40)**: The MBZ release title matches the Steam soundtrack name.
- **b. Format = "Digital Media" (+50)**: High priority for digital releases.
- **c. Context: No "Bandcamp" (+20)**: Avoids Bandcamp-specific tagging styles.
- **d. Track Count Alignment (+40 or +20)**:
    - Exact match with local physical files: +40.
    - Off by ±2 tracks: +20.
- **e. Soundtrack Release Date (+40 or +20)**:
    - Year matches Steam soundtrack release date: +40.
    - Year within ±1: +20.
- **f. Parent Game Release Date (+30 or +10)**:
    - Year matches the parent game release date: +30.
    - Year within ±1: +10.

**Status Penalty**: "Bootleg" releases receive a -100 penalty.

## 3. Consolidation Workflow

1.  **Ranking**: The Python pre-processor ranks MBZ candidates based on the rules above.
2.  **Slimming**: Only the top 3-5 candidates (MBIDs and titles) are sent to the LLM.
3.  **Cross-Reference**: The LLM compares the selected MBZ candidate against "Strong Evidence" (local tags).
4.  **Confidence Calculation**:
    - **100**: Strong Evidence and Top MBZ Candidate match perfectly.
    - **80-90**: Minor title variations (e.g. suffix "Remix") or date discrepancies resolved.
    - **< 80**: Severe mismatches in track counts, artists, or missing data. (Triggers `review/` routing).

## 4. Audio Quality Enforcement

SST prioritizes audio bitstream integrity. The following rules are applied during the transformation phase:

1.  **Native Buffering**: To eliminate I/O jitter from Windows mounts (/mnt/d), files are copied to the WSL2 native filesystem before conversion.
2.  **Zero-Tolerance for Corruption**: Any FFmpeg warning (e.g., `invalid rice order`, `decode_frame() failed`) detected during native conversion will **force the album status to REVIEW**, regardless of metadata accuracy.
3.  **Critical Failure**: If conversion fails entirely, the album is marked as `[CRITICAL: Audio Source Error]`, and the user is advised to re-download the source via Steam.

---

## 5. Result Routing Summary

| Final Status | Criteria |
| :--- | :--- |
| **ARCHIVE** | Confidence >= 80, Metadata complete, **No Audio Warnings**. |
| **REVIEW** | Confidence < 80 OR Metadata missing OR **Audio Warnings detected**. |
| **ERROR** | Physical conversion failure OR unrecoverable API error. |
