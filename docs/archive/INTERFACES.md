# INTERFACES

## Data Types

### Track
- path: str
- duration: float | None

### AlbumCandidate
- mbid: str
- vgmdb_id: str | None
- title: str
- artist: str | None
- track_count: int | None
- release_date: str | None
- score: float

### ScoredCandidate
- candidate: AlbumCandidate
- final_score: float

---

## Functions

### generate_fingerprint

generate_fingerprint(audio_path: str) -> tuple[int, str]

- Returns (duration, Chromaprint fingerprint)

---

### identify_track

identify_track(duration: int, fingerprint: str, api_key: str, api_url: str) -> dict | None

- Calls AcoustID API
- Returns best match result dict or None

---

### search_vgmdb

search_vgmdb(titles: list[str], limit: int = 5) -> list[AlbumCandidate]

- Queries VGMdb (hufman/vgmdb proxy) with multiple title variants
- Deduplicates by VGMdb album id

---

### verify_with_musicbrainz

verify_with_musicbrainz(titles: list[str], limit: int = 5) -> list[AlbumCandidate]

- Secondary verification/fallback path when VGMdb confidence is insufficient
- Deduplicates by MBID

---

### score_candidates

score_candidates(candidates: list[AlbumCandidate], local_track_count: int, steam_release_date: str | None) -> list[AlbumCandidate]

---

### select_best_candidate

select_best_candidate(scored: list[ScoredCandidate]) -> AlbumCandidate | None

---

### partial_acoustid_verify

partial_acoustid_verify(files: list[str], candidate_title: str, partial_tracks: int, threshold: float) -> float

- Prefect task
- Returns match ratio (0.0 - 1.0)

---

### write_tags

write_tags(file_path: str, metadata: dict) -> None

- metadata keys: TIT2(title), TPE1(artist), TALB(album), TPE2(album_artist), TCON(genre), TCOM(composer), TDRC(date), TRCK(track), TXXX, etc. (See DATA_CONTRACTS.md for details)

---

## Rules

- All functions must be pure (no side effects except write_tags)
- All outputs must be JSON serializable
