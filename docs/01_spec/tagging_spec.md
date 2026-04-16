# Tagging Specification (ID3v2.3)

## Core Fields (Mapping)

| ID3 Tag | Name | Source & Policy |
| :--- | :--- | :--- |
| **TIT2** | Title | Original Track Title (MusicBrainz & filename). Track-specific. |
| **TPE1** | Artist | Composer name (Original Metadata & Steam & MusicBrainz). Track-specific. |
| **TALB** | Album | 'name' from Steam .acf file. |
| **TPE2** | Album Artist | `[Developer] | [Publisher]` from Steam. |
| **TCON** | Genre | `STEAM, VGM, [Original Game Genre]`. (Search-friendly). |
| **TIT1** | Grouping | `[Series or Game Title] | Steam`. |
| **COMM** | Comment | `[Game Title] | [Original Game Steam Tags] | [Original Game AppID] | [URL]` from Steam. |
| **TCOM** | Composer | Individual/Unit names (Steam & MusicBrainz). Track-specific. |
| **TDRC** | Year | Release Year (YYYY). |
| **TRCK** | Track Number | `n/total` format. |
| **TPOS** | Disc Number | `n/total` format (always included, e.g., 1/1). |
| **TLAN** | Language | Priority: `Configured Language -> English -> Original`. |

---

## Priority

1. Existing Metadata (Validated via cross-format check)
2. MusicBrainz (Tie-broken via spec)
3. Steam Metadata (.acf & Store API info)

---

## Artwork (APIC)

- **Track-Specific**: Artwork can vary by track. The tagger must preserve track-specific art if it exists.
- **Output Format**: PNG
- **Dimensions**: 500x500
- **Aspect Ratio Policy**: Maintain aspect ratio. Pad non-square images with a **Black background**.

---

## Custom Fields (TXXX)

- **MusicBrainzAlbumID**: (TXXX:MusicBrainz Album Id)
- **SteamAppID**: (TXXX:Steam App Id)
- **VGMdbURL**: (Optional: ONLY if found via MusicBrainz URL relationship)

---

## Rules

- **NO GUESSING**: If a field is unknown and cannot be found in trusted sources, leave it blank or route to `review/`.
- Never write empty tags.
- Normalize encoding to UTF-8.
- Ensure strict compatibility with ID3v2.3 for broad player support.
