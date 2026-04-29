# S.S.T (Steam Soundtrack Tagger) - The Definitive Specification

This is the **Single Source of Truth** for the S.S.T project. Any past documentation is deprecated. This document defines the ironclad rules for the system's behavior, metadata integrity, and processing pipeline.

---

## 1. Core Principle: "Archive once, trust forever"
- **Primary Audience**: Japanese speakers.
- **Goal**: High-precision, zero-maintenance audio archiving.
- **Policy**: If there is *any* doubt about metadata accuracy or audio integrity, the item MUST be sent to `REVIEW`. A status of `ARCHIVE` must represent 100% reliability.

---

## 2. Metadata Sovereignty (The "LOCKED TRUTH")
Specific information is considered "Deterministic" and cannot be modified by LLMs or heuristics.

### 2.1 Steam API Data (LOCKED)
The following fields from the Steam Store API are absolute truths:
- **Album Title**: `steam_meta.name`
- **Artist (Album-level)**: `steam_meta.developer` + `steam_meta.publisher`
- **Release Year**: `steam_meta.release_date[:4]`
- **Steam IDs**: `app_id`, `parent_app_id`
- **Comment/Grouping Metadata**: Must reference the **Parent Game** details. If `parent_app_id` is missing, fallback to using the soundtrack's own AppID and Name.

### 2.2 Hybrid Scoring System
To ensure absolute reliability, the system employs a two-stage evaluation process:

#### Stage 1: Python Mathematical Sieve (Calculated in `mbz.py`)
Python calculates a deterministic score for each MusicBrainz candidate based on physical evidence:
- **AppID Match (+500)**: Direct Steam AppID link in `url-rels`.
- **Parent AppID Match (+300)**: Link to the parent game AppID in `url-rels`.
- **Bandcamp Bonus (+100)**: Official Bandcamp link in `url-rels`.
- **Title Similarity (0 to +100)**: Highest `SequenceMatcher` score against Steam Name or Local Tags.
- **Structural Alignment (+50)**: Exact track count match. (Subtracts 10 per track discrepancy).
- **Tracklist Fingerprint (+200)**: Awarded if the average similarity of track titles exceeds 80%.

#### Stage 2: LLM Semantic Audit (Calculated in `llm.py`)
The LLM acts as the final arbiter on a pre-sorted shortlist (Top 3-5 candidates):
- **Translation Matching**: Resolves linguistic differences (e.g., "Battle" vs "戦闘").
- **Tag Hygiene**: Identifies "Dirty Tags" or other subtle anomalies.
- **Final Judgment**: Assigns the final rank (S, A, B, or C).

### 2.3 Gate-based Scoring System
LLM confidence scores must adhere to a strict threshold:
- **Rank S (100%)**: Perfect match between Steam, MBZ, and Local Tags. -> **ARCHIVE**
- **Rank A (95%)**: High consistency, no "Dirty Tags". -> **ARCHIVE**
- **Rank B (80-90%)**: Any minor discrepancy, track count mismatch, or "Dirty Tags". -> **REVIEW**
- **Rank C (< 80%)**: Conflict or insufficient evidence. -> **REVIEW**

### 2.3 Steam API Access Optimization
- **Targeted Fetching**: The system MUST utilize the Steam API Key and `@data/userdata.json` to identify relevant AppIDs (Wishlists, Library, etc.).
- **Minimal Footprint**: Brute-force scanning of the Store API is strictly forbidden. Use user app lists to target and fetch metadata for confirmed soundtracks or parent games with the absolute minimum number of API requests required.

---

## 3. Audio & Packaging Integrity
### 3.1 Native Buffering Strategy
To prevent I/O jitter errors from Windows mounts (`/mnt/d`):
1.  **Gather**: Copy raw source files to WSL2 native filesystem (`/tmp/sst-work`).
2.  **Transform**: Execute FFmpeg on local files (Strict ID3v2.3, AIFF/MP3 320k).
3.  **Validate**: Any FFmpeg warning/error triggers **Forced REVIEW**.

### 3.2 Atomic Move
ZIP files must be generated in the WSL2 native filesystem and moved to the Windows mount ONLY when the compression is 100% complete and verified.

---

## 4. LLM Operational Contract (Zero-Hallucination)
- **Thinking Language**: Japanese (JA) ONLY.
- **No Inference**: LLMs are forbidden from guessing titles or artists from internal filenames (e.g., `bgm_01.wav`).
- **Semantic Labeling**: For Review items, the LLM must provide a human-readable label explaining the specific anomaly (e.g., "BGM/SFX Mixing", "Dirty Tags detected").
- **Stateless Chunks**: When processing large albums in chunks, the `Global Identity` decided in Phase 1 must be strictly injected as an absolute constraint into Phase 2.

---

## 5. Tagging Format Standard
- **Separators**: Use `; ` (Semicolon + Space) for multi-value fields.
- **Language Tag (TLAN)**: Use ISO 639-2 (e.g., `jpn`).
- **Field Mapping**:
    - `TPE1` (Artist): MusicBrainz Credit (Best) or Developer (Fallback).
    - `TPE2` (Album Artist): Developer; Publisher.
    - `TALB` (Album): Steam Album Name (Locked).
    - `COMM` (Comment): Parent Game Name; AppID; Store URL.

---

## 6. System Execution Modes
- **`production`**: Silent terminal (Progress bars only). Logs to file. High-throughput (CPU-optimized).
- **`development`**: Detailed console logs. Error directories preserved for audit. Cache-bypass.
- **`LLM_FORCE_LOCAL`**: Bypasses API rate limits. Enforces 20-track chunking for VRAM efficiency.
