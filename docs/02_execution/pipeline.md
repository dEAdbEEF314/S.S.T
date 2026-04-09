# Processing Pipeline

## Standard Flow

1. Fetch Steam metadata
2. Search VGMdb
3. Filter candidates
4. Score candidates
5. Decide source
6. Fallback to MusicBrainz if needed
7. Optional AcoustID verification
8. Normalize metadata using LLM
9. Convert format
10. Write tags
11. Store output

---

## Fast Track

- Skip AcoustID if score is high

---

## Failure Handling

- Low confidence → review
- Errors → retry or fail
