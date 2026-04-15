# Identification Strategy

## Source Priority

1. Manual
2. Existing Metadata (Cross-format validated)
3. MusicBrainz
4. Steam
5. AcoustID (Last resort fallback)

---

## Cross-Format Validation

- If multiple formats (e.g., FLAC, MP3) exist for the same album, extract album-wide metadata and cover art from each.
- Compare the extracted metadata across formats.
- If they match perfectly, treat the existing metadata as highly reliable and elevate priority.

---

## MusicBrainz Search Rules (Tie-breaking)

If multiple releases match with the same high score (e.g., Score 100), evaluate in the following order:
1. **Format**: Digital Media preferred.
2. **Exclude Source**: Exclude releases containing "Bandcamp" string if alternatives exist.
3. **Track Count**: Closest match to the actual count of audio files.
4. **Release Date**: Closest match to the Steam release or current date.

---

## Candidate Conditions

- format = Digital Media
- track_count ±1
- title similarity ≥ 0.80

---

## Scoring

- metadata_match_score (cross-format consistency)
- title_similarity
- track_count_match
- release_date_match

---

## Decision & Strict No-Guessing Rule

- ≥ 0.75 → accept
- 0.70–0.75 → verify
- < 0.70 → review
- **CRITICAL**: If required metadata is missing and cannot be definitively sourced, the system MUST route the file to `review/`. **Guessing or inventing metadata is strictly prohibited project-wide.**
