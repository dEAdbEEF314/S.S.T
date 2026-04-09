# Identification Strategy

## Source Priority

1. Manual
2. VGMdb
3. MusicBrainz
4. Steam

---

## Candidate Conditions

- format = Digital Media
- track_count ±1
- date ±30 days
- title similarity ≥ 0.80

---

## Scoring

- title_similarity
- track_count_match
- release_date_match
- format_match

---

## Decision

- ≥ 0.75 → accept
- 0.70–0.75 → verify with MB
- < 0.70 → fallback to MB
- < 0.55 → review
