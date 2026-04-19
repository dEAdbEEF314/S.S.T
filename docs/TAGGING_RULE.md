# S.S.T Audio Selection and Metadata Tagging Rules

This document outlines the theoretical foundation and concrete logic for how the Steam Soundtrack Tagger (S.S.T) selects the optimal audio file for each track and how it consolidates metadata from multiple sources to achieve highly accurate tagging. This approach relies on "Local-only (Edge Processing)" to eliminate network overhead.

## 1. Core Philosophy

1.  **Separation of Concerns:** The process of selecting which audio file to keep (File Adoption) is completely separated from the process of gathering tags (Metadata Collection).
2.  **No Data Left Behind:** Even if an audio file (e.g., a low-quality MP3) is discarded in favor of a higher-quality file (e.g., a FLAC), its embedded metadata is still extracted and used as a valuable information source.
3.  **LLM as an Organizer, Not a Creator:** The LLM is used strictly for data consolidation and conflict resolution based on provided factual sources. It is explicitly forbidden from inferring or fabricating metadata.
4.  **Duration-based Matching for WAV:** WAV files, which lack reliable metadata, are identified by matching their exact playback duration against authoritative external databases (MusicBrainz).
5.  **Safe Fallback (Review Mode):** If the LLM cannot confidently resolve conflicts or lacks sufficient information, the album is safely moved to `review/` for human intervention, bundling all raw sources and LLM logs to assist the user.
6.  **Minimize External Access:** Once an album is archived, its metadata is cached locally. Processed albums are strictly skipped unless forced.

---

## 2. File Adoption Logic (Audio Selection)

When a soundtrack contains multiple audio formats (e.g., FLAC and MP3 versions of the same album), S.S.T must adopt exactly ONE optimal file per logical track.

### 2.1. Priority Hierarchy
For each logical track, the system evaluates all available files and selects the best one according to the following strict priority:

1.  **Lossless (Highest Priority)**
    *   **Source:** FLAC, WAV, ALAC, etc.
    *   **Action:** Convert to **AIFF**.
    *   **Limits:** Maximum 24-bit depth, Maximum 48kHz sample rate.
2.  **High-Quality Lossy (Medium Priority)**
    *   **Source:** AAC, OGG, M4A (if not ALAC).
    *   **Action:** Convert to **MP3**.
    *   **Limits:** Constant Bitrate (CBR) 320kbps, Maximum 48kHz sample rate.
3.  **Standard Lossy (Lowest Priority)**
    *   **Source:** MP3.
    *   **Action:** Adopt as-is (**Passthrough**). Re-encoding MP3 to MP3 only inflates file size without quality gain and is strictly avoided.

### 2.2. Discarding Redundancy
Once the optimal file is selected, all other format variants for that specific track are discarded.

---

## 3. Metadata Collection & Exception Handling

### 3.1. Source Aggregation
1.  **Format-Specific Tag Sets:** Extracted from *every* audio file before discarding.
2.  **Steam API Data:** App details fetched directly from the Steam Store.
3.  **MusicBrainz Data:** Fetched using the Steam Album Title (`.acf` name).
    *   *Tie-breaking Rules:* If multiple top-score candidates exist, prioritize:
        a. Format = Digital Media
        b. Exclude "Bandcamp"
        c. Track count closest to actual files
        d. Release Date closest to Steam
4.  **Filename & Path Parsing:** Crucial for tracks lacking internal tags. Extremely complex directory structures must be accounted for during parsing.
    *   *Note:* AcoustID is explicitly deprioritized/removed due to its extremely low hit rate for Steam VGM.

### 3.2. The WAV Exception (Duration Matching)
If the highest priority file is a WAV:
1.  Calculate its exact playback duration.
2.  Match the duration against the MusicBrainz tracklist.
3.  If a match is found, elevate the MusicBrainz source for that track to "High Confidence" before passing to the LLM.

---

## 4. LLM-Based Consolidation (Organizing the Truth)

Raw data is passed to the LLM for final consolidation.

### 4.1. The LLM Prompt Directives
*   **Absolute Prohibition on Hallucination:** Do not invent metadata.
*   **Language Priority (TLAN):** If multiple languages exist, select based on: User Configured Language -> English -> Original Language.
*   **Conflict Resolution:** Rely strictly on the provided factual sources to fix formatting or encoding errors.

### 4.2. Target Metadata Mapping Specification
The LLM must map the consolidated truth to the following ID3v2/Standard tags:

*   **TIT2 (Title):** Original Track Title from MusicBrainz & Filename (adopt most detailed specific to the track).
*   **TPE1 (Artist):** Composer name from original metadata, Steam, or MusicBrainz.
*   **TALB (Album):** The exact `name` string from the `.acf` file.
*   **TPE2 (Album Artist):** Format as `[Developer] | [Publisher]`.
*   **TCON (Genre):** Format as `STEAM VGM, [Original Game Genre]`. (Mandatory inclusion of "STEAM VGM" for robust filtering).
*   **TIT1 (Grouping):** Format as `[Series or Game Title] | Steam`.
*   **COMM (Comment):** Format as `[Game Title] | [Original Game Steam Tags] | [Original Game AppID] | [URL]`.
*   **TCOM (Composer):** Individual/Unit names from Steam & MusicBrainz.
*   **TDRC (Year):** Release Year (YYYY).
*   **TXXX (MusicBrainzAlbumID):** ID if matched.
*   **TRCK (Track Number):** Mandatory.
*   **TPOS (Disc Number):** Mandatory. Format as `Disc/Total` (e.g., `1/1` if only one disc).
*   **TLAN (Language):** Based on the language priority rule.

### 4.3. Track-Specific Artwork
Artwork is evaluated and embedded on a *per-track* basis, not globally per-album, to respect soundtracks that feature unique art for different tracks.
*   **Artwork Spec:** PNG, 500x500 dimensions. Pad non-square images with a black background.

---

## 5. Workflow Execution & State Management

1.  **State Caching:** Metadata for albums marked as `archive/` is cached in a local database indexed by Steam `app_id`.
2.  **Skip Logic:** Albums that have already been processed (exist in `archive/` or `review/`) are strictly skipped to prevent redundant external API calls, unless a specific `--force` flag is used.
3.  **Review Workflow (Human Fallback):** If the LLM cannot confidently determine the metadata, the album is routed to `review/`.
    *   The user downloads a bundled ZIP containing: The adopted audio files, the `.acf` file, a JSON of all collected raw metadata sources, and the full LLM interaction logs.
    *   The user utilizes external tools (Mp3tag, VGMdb) to manually tag the files using the provided context.
