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

### 2.1 Steam API Data (LOCKED - 3-Tier Architecture)
To maximize data depth while ensuring reliability, the system uses a 3-tier API fetch strategy (Zero Scraping):
- **Tier 1 (Official Store API)**: Retrieves localized Album Title, Genres, and Release Date.
- **Tier 2 (Self-hosted PICS Bridge)**: Retrieves structured Tracklists, multi-language Credits, and Label information directly from Steam's internal PICS database.
- **Tier 3 (Steam Web API)**: Retrieves high-fidelity User Tags (popular tags) using an official API key.

The following fields from these APIs are absolute truths:
- **Album Title**: `steam_meta.name`
- **Artist (Album-level)**: `steam_meta.developer`, `steam_meta.publisher`
- **Release Year**: Extracted via 4-digit regex from `steam_meta.release_date`.
- **Steam IDs**: `app_id`, `parent_app_id`
- **Comment Metadata**: Must reference the **Parent Game** details including its popular tags.

### 2.2 Hybrid Scoring & Decision System
To ensure absolute reliability, the system employs a three-stage evaluation process:

#### Stage 1: Python Mathematical Sieve (Calculated in `mbz.py`)
Python calculates a deterministic score for each MusicBrainz candidate based on physical evidence:
- **AppID Match (+500)**: Direct Steam AppID link in `url-rels`.
- **SteamDB Match (+500)**: Direct SteamDB link for the AppID in `url-rels`.
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

#### Stage 3: Deterministic Fast-Track (LLM Bypass)
The system automatically promotes an album to `ARCHIVE` without an LLM query if:
1. A **Direct Link** (Steam or SteamDB) is found in MusicBrainz.
2. The **Track Count** matches perfectly across MBZ, PICS, and Local files.

### 2.3 Gate-based Scoring System
LLM confidence scores must adhere to a strict threshold:
- **Rank S (100%)**: Perfect match between Steam, MBZ, and Local Tags. -> **ARCHIVE**
- **Rank A (95%)**: High consistency, no "Dirty Tags". -> **ARCHIVE**
- **Rank B (80-90%)**: Any minor discrepancy, track count mismatch, or "Dirty Tags". -> **REVIEW**
- **Rank C (< 80%)**: Conflict or insufficient evidence. -> **REVIEW**

---

## 3. Audio & Packaging Integrity
### 3.1 Native Buffering Strategy
To prevent I/O jitter and ensure clean output:
1.  **Buffer**: Copy raw source files to a dedicated WSL2 buffer (`/tmp/sst-work/buffer_*`) outside the output tree.
2.  **Transform**: Execute FFmpeg locally. **MP3 files are strictly forced to ID3v2.3** for hardware compatibility.
3.  **Validate**: Any FFmpeg warning/error triggers **Forced REVIEW**.

### 3.2 Deployment & Extraction
Soundtracks are first packaged as ZIPs for safe transfer, then automatically extracted on the Windows host using native `tar.exe` called from WSL. This preserves file integrity across filesystems.

---

## 4. LLM Operational Contract (Zero-Hallucination)
- **Thinking Language**: Japanese (JA) ONLY.
- **No Inference**: LLMs are forbidden from guessing titles or artists from internal filenames (e.g., `bgm_01.wav`).
- **Semantic Labeling**: For Review items, the LLM must provide a human-readable label explaining the specific anomaly (e.g., "BGM/SFX Mixing", "Dirty Tags detected").
- **Stateless Chunks**: When processing large albums in chunks, the `Global Identity` decided in Phase 1 must be strictly injected as an absolute constraint into Phase 2.

---

## 5. Tagging Format Standard
- **Separators**: Use `, ` (Comma + Space) for multi-value fields.
- **Language Tag (TLAN)**: Use ISO 639-2 (e.g., `jpn`).
- **Field Mapping**:
    - `TPE1` (Artist): MusicBrainz Credit (Best) or Developer (Fallback).
    - `TPE2` (Album Artist): Developer, Publisher.
    - `TALB` (Album): Steam Album Name (Locked).
    - `TPUB` (Label): Official PICS Label or MBZ Label. Fallback to Publisher.
    - `COMM` (Comment): [Parent Name], [Popular Tags], [AppID], [Store URL].
      - *Note*: Tags are automatically pruned from the end to stay within the 2000-character limit for ID3v2.3.

---

## 6. System Execution Modes
- **Default Mode**: `LOG_LEVEL=INFO`. Standard append logs.
- **Debug Mode (`--dev`)**: Forces `LOG_LEVEL=DEBUG`. Generates unique timestamped logs (`SST_DEBUG_*.log`). Retains temporary work files on error.
- **Critical Commands**: `--delete-db` and `--finalize` require a mandatory **3-step confirmation**.

---

## 7. Configuration (`.env`)
Required variables for the "Ultimate Data Mode":
- `STEAM_WEB_API_KEY`: For official tag retrieval.
- `STEAM_LOGIN_SECURE`: For `userdata.json` personalized scan.
- `STEAM_PICS_BRIDGE_URL`: Points to the local Docker PICS bridge.
