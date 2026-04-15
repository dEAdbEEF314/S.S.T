# Processing Pipeline

## Standard Flow

1. Fetch Steam metadata
2. Extract embedded audio metadata (incl. cover art)
3. Cross-format validation (if multiple formats exist, compare album-wide metadata)
4. Search MusicBrainz (Primary external DB)
5. Filter & Score candidates
6. Decide source (Existing Validated > MusicBrainz > Steam)
7. Fallback to AcoustID (Last resort only)
8. Normalize metadata using LLM (Strict formatting only, NO GUESSING)
9. Convert format
10. Write tags
11. Store output

---

## Fast Track

- Skip MusicBrainz/AcoustID if cross-format validation of existing metadata yields high confidence.

---

## Failure Handling

- Missing data / Low confidence → review (STRICT: Do not guess or hallucinate missing tags)
- Errors → retry or fail
