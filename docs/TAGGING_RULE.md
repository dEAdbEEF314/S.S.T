# SST Audio Selection and Metadata Tagging Rules

This document defines the authoritative logic for audio file selection, tier classification, and metadata tagging for the Steam Soundtrack Tagger (SST).

## 1. File Selection & Tier Logic

SST groups audio files found in a Steam soundtrack directory by their logical tracks and adopts the highest quality version available.

### 1.1 Quality Tiers
- **Lossless (Tier 1)**: FLAC, WAV, AIFF, ALAC.
- **Lossy High (Tier 2)**: OGG, AAC, M4A.
- **MP3 (Tier 3)**: Standard MP3 files.

If multiple formats exist for the same track, the format with the highest tier is chosen for conversion/tagging.

## 2. Metadata Identification Logic

### 2.1 Hybrid Consolidation (Act-11)
The system uses a hybrid approach combining deterministic programmatic logic and LLM-based reasoning.

1.  **Programmatic Pre-processing**:
    - **Local Cross-Validation**: If tags in different formats (e.g., MP3 and FLAC) match perfectly, they are marked as "Strong Evidence."
    - **MusicBrainz Scoring**: Candidates are ranked by title similarity, digital media status, and track count alignment.
2.  **LLM Consolidation**:
    - An entire album is processed in a single LLM request (All-in-One).
    - The LLM resolves conflicts between Steam, MusicBrainz, and Local Tags based on evidence weights.

### 2.2 MusicBrainz Candidate Ranking (Rules a-f)
MBZ candidates are scored based on:
- **a. Title Match**: Album title matches Steam name (+40).
- **b. Format**: "Digital Media" preferred (+50).
- **c. Context**: No "Bandcamp" in title (+20).
- **d. Track Count**: Exact match with local files (+40).
- **e. Date**: Matches Steam release date (+40).
- **f. Parent Date**: Matches parent game release date (+30).

## 3. ID3v2.3 Tagging Standards

To ensure compatibility across Windows and various media players, the following strict formats are enforced.

### 3.1 Field Mapping & Formats
| ID3 Frame | Field | Format / Rule |
| :--- | :--- | :--- |
| **TIT2** | Title | Consolidated track title. No "Unknown". |
| **TPE1** | Artist | Main composers or performers. |
| **TALB** | Album | Official Steam album title. |
| **TPE2** | Album Artist | `[Developer] | [Publisher]`. |
| **TCON** | Genre | Prefixed: `STEAM VGM, [Genre]`. |
| **TDRC** | Year | Release Year (YYYY). |
| **TRCK** | Track Number | Single integer (e.g., `1`, `16`). No `n/N`. |
| **TPOS** | Disc Number | `n/N` format (e.g., `1/1`). Forced to `1/1` for single-disc. |
| **TIT1** | Grouping | `[Game Name] | Steam`. |
| **COMM** | Comment | `[Game Title] | [Tags] | [AppID] | [Store URL]`. |
| **TLAN** | Language | ISO 639-2 code (e.g., `jpn`, `eng`). |

### 3.2 Technical Requirements
- **Encoding**: UTF-16 with BOM (encoding=1) for all text frames.
- **Artwork**: Exactly 500x500 PNG. Square images are force-resized; non-square images are padded with black.

## 4. Routing & Validation (Archive vs. Review)

### 4.1 Archive (Success)
Albums reach `archive/` only if:
- LLM confidence score is **80 or higher**.
- No fields contain "Unknown".
- Track numbers are not "0".

### 4.2 Review (Manual Check)
Albums are moved to `review/` if:
- LLM confidence is low (< 80).
- Mandatory metadata is missing.
- Severe conflicts between local files and MusicBrainz are found.
