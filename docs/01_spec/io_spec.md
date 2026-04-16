# I/O Specification

## Scout Output & Ingest Storage

### Directory Structure (S3: ingest/)
```
ingest/{AppID}/
├ appmanifest_{AppID}.acf   <-- NEW: Copy of the original manifest
├ [Track Files].flac
└ [Track Files].mp3
```

---

## Worker Output & Final Storage

### Directory Structure (S3: archive/ or review/)
```
{archive|review}/{AppID}/
├ metadata.json            <-- NEW: Source of truth for UI and manual review
├ appmanifest_{AppID}.acf   <-- NEW: Preserved manifest
└ {Disc}/
    └ {filename}.{ext}
```

### Metadata JSON Schema (metadata.json)
This file contains the complete record of the processing attempt.
```json
{
  "app_id": 123456,
  "album_name": "Example Album",
  "status": "success | review",
  "scanned_at": "2026-01-01T00:00:00Z",
  "processed_at": "2026-01-01T00:05:00Z",
  "steam_info": {
    "developer": "...",
    "publisher": "...",
    "url": "..."
  },
  "external_info": {
    "source": "musicbrainz",
    "mbid": "...",
    "vgmdb_url": "..."
  },
  "tracks": [
    {
      "file_path": "1/01. Title.aiff",
      "original_filename": "01_original.flac",
      "title": "Title",
      "artist": "Artist",
      "confidence": 0.95
    }
  ]
}
```

---

## Duplicate Prevention Rule
Scout MUST check for the existence of `{archive|review}/{AppID}/metadata.json` before uploading to `ingest/`. 
If found, the album is skipped unless the `--force` flag is used.
