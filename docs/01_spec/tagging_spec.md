# Tagging Specification (ID3v2.3)

**STATUS: REPLACED BY [TAGGING_RULE.md](../TAGGING_RULE.md)**

Please refer to the root `TAGGING_RULE.md` for the authoritative tagging logic. This file remains for historical reference of the mapping table.

## Core Fields (Mapping)

| ID3 Tag | Name | Source & Policy |
| :--- | :--- | :--- |
| **TIT2** | Title | Original Track Title (MusicBrainz & filename). |
| **TPE1** | Artist | Composer/Performer names. |
| **TALB** | Album | 'name' from Steam .acf file. |
| **TPE2** | Album Artist | `[Developer] | [Publisher]` from Steam. |
| **TCON** | Genre | `STEAM VGM, [Original Game Genre]`. |
| **TIT1** | Grouping | `[Series or Game Title] | Steam`. |
| **COMM** | Comment | `[Game Title] | [Steam Tags] | [AppID] | [URL]`. |
| **TCOM** | Composer | Individual/Unit names. |
| **TDRC** | Year | Release Year (YYYY). |
| **TRCK** | Track Number | `n` format. |
| **TPOS** | Disc Number | `n/total` format. |
| **TLAN** | Language | ISO 639-2 code. |

---

## Implementation Details
- **Encoding**: UTF-8.
- **Artwork**: 500x500 PNG with black padding.
- **Formats**: AIFF (Lossless) or MP3 320k (Lossy).
