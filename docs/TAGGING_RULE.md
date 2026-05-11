# SST Audio Selection and Metadata Tagging Rules

This document defines the authoritative logic for audio file selection, tier classification, and metadata tagging for the Steam Soundtrack Tagger (SST).

## 1. File Selection & Tier Logic

SST groups audio files found in a Steam soundtrack directory by their logical tracks and adopts the highest quality version available.

### 1.1 Quality Tiers
- **Lossless (Tier 1)**: FLAC, WAV, AIFF, ALAC.
- **Lossy High (Tier 2)**: OGG, AAC, M4A.
- **MP3 (Tier 3)**: Standard MP3 files.

### 1.2 Deduplication Logic
The system collapse duplicates by stripping common quality suffixes (e.g., `(AIFF)`, `[FLAC]`, `(MP3)`) from filename stems. If multiple formats exist for the same track, the format with the highest tier is chosen.

## 2. Metadata Identification Logic

### 2.1 3-Tier API Consolidation
The system uses three structured data sources before resorting to LLM reasoning:
1. **Tier 1 (Official Store API)**: Basic localized info (Name, Genre).
2. **Tier 2 (PICS Bridge)**: Structured Tracklists and Credits directly from Steam's database.
3. **Tier 3 (Steam Web API)**: User-defined popular tags.

### 2.2 MusicBrainz Candidate Ranking
MBZ candidates are scored based on physical evidence:
- **AppID Match (+500)**: Direct Steam AppID link in `url-rels`.
- **SteamDB Match (+500)**: Direct SteamDB link for the AppID in `url-rels`.
- **Parent AppID Match (+300)**: Link to the parent game AppID in `url-rels`.
- **Structural Alignment (+50)**: Exact track count match.
- **Tracklist Fingerprint (+200)**: Average title similarity > 80%.

### 2.3 Deterministic Fast-Track
If a **Direct Link** is found and the **Track Count** matches perfectly across MBZ, Steam PICS, and Local files, the system promotes the album to `ARCHIVE` automatically, bypassing the LLM.

## 3. ID3v2.3 Tagging Standards

To ensure maximum compatibility with hardware (e.g., DJ gear) and Windows, the following standards are enforced.

### 3.1 Field Mapping & Formats
| ID3 Frame | Field | Format / Rule |
| :--- | :--- | :--- |
| **TIT2** | Title | Consolidated track title. No "Unknown". |
| **TPE1** | Artist | Main composers/performers from MBZ or Steam. |
| **TALB** | Album | Official Steam album title (Locked). |
| **TPE2** | Album Artist | `[Developer], [Publisher]`. |
| **TCON** | Genre | Prefixed: `STEAM VGM, [All Genres]`. |
| **TPUB** | Label | Official PICS Label or MBZ Label. |
| **TYER** | Year | Release Year (YYYY). *Note: MP3 uses TYER for v2.3.* |
| **TRCK** | Track Number | Single integer (e.g., `1`, `16`). |
| **TPOS** | Disc Number | `n/N` format (e.g., `1/1`). |
| **TIT1** | Grouping | `[Game Name], Steam`. |
| **COMM** | Comment | `[Game Name], [Tags], [AppID], [Store URL]`. |
| **TLAN** | Language | ISO 639-2 code (e.g., `jpn`). |

### 3.2 Technical Requirements
- **Strict ID3v2.3**: MP3 files are force-saved in v2.3 format.
- **Comment Pruning**: Tags in the `COMM` field are automatically removed from the end if the total length exceeds ~2000 characters to prevent ID3v2.3 limit violations.

## 4. Routing & Validation (Archive vs. Review)

### 4.1 Archive (Success)
Albums reach `archive/` only if:
- LLM confidence score is **100** (or Fast-Tracked).
- Integrity Quality is **95 or higher**.
- No "Dirty Tags" (track numbers mixed into titles) exist.

### 4.2 Review (Manual Check)
Albums are moved to `review/` if:
- Any doubt in identity (Score < 100) or quality (Quality < 95).
- Audio failures or FFmpeg warnings are detected.
- User review is manually requested by the LLM.
