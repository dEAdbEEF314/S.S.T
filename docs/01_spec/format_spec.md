# Format Conversion Specification

## Conversion Matrix

| Input Format | Target Format | Bitrate / Quality Settings |
| :--- | :--- | :--- |
| **Lossless** (.flac, .wav, .aiff, .m4a-alac) | **.aiff** | 48kHz Max, 24bit Max |
| **MP3** (.mp3) | **.mp3** | Passthrough (Keep as-is) |
| **Other Lossy** (.ogg, .m4a-aac, etc.) | **.mp3** | CBR 320kbps, 48kHz Max |

---

## Exclusive Selection Policy (Single File Output)

To ensure the highest quality library and avoid duplicates, the system MUST only output **ONE file per track** following this priority:

1. **AIFF (from Lossless)**: Highest priority. If any lossless source exists for a track, convert to AIFF and ignore other formats.
2. **MP3 (Original)**: Second priority. If no lossless source exists but an MP3 exists, use the original MP3.
3. **MP3 (Converted)**: Last resort. If only other lossy formats (e.g., OGG) exist, convert to 320kbps MP3.

---

## Audio Constraints

- **Sample Rate**: Hard limit of **48,000 Hz**. Downsample if the source is higher (e.g., 96kHz -> 48kHz).
- **Bit Depth**: Hard limit of **24-bit** for AIFF.
- **MP3 Encoding**: Must use **CBR (Constant Bit Rate)** at **320kbps** for conversions.

---

## Output Structure

`archive/{AppID}/{Disc}/{filename}.{ext}`  
*(Where {ext} is either 'aiff' or 'mp3')*

---

## Implementation Rules

- Process only the "Best Quality" candidate for each unique track.
- Delete or ignore lower-quality redundant files before the tagging stage.
