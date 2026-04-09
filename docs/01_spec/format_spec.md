# Format Conversion Specification

## Input Formats

- .flac
- .wav
- .aiff
- .m4a
- .ogg
- .mp3

---

## Conversion Rules

- Lossless (.flac, .wav, .aiff, .m4a) → .aiff
- .ogg → .mp3 (CBR 320kbps, 48kHz)
- .mp3 → keep as-is

---

## Constraints

- Preserve audio quality
- Maintain original sample rate where possible
- Ensure compatibility with tagging system

---

## Output Structure

archive/{AppID}/{Disc}/{format}/{filename}
