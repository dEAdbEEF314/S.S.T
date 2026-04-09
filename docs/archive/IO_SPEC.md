# IO Specification

---

## Scout Output (`scout_result.json`)

Metadata that Scout writes to SeaweedFS's `ingest/{AppID}/scout_result.json`.
The presence of this file is also used as a "processed" criterion.

```json
{
  "app_id": 123456,
  "name": "Example Game Soundtrack",
  "install_dir": "Example Game Soundtrack",
  "storage_location": "music",
  "track_count": 15,
  "files_by_ext": {
    "flac": {
      "count": 15,
      "keys": [
        "ingest/123456/Disc 1/flac/01 - Track One.flac",
        "ingest/123456/Disc 1/flac/02 - Track Two.flac"
      ]
    },
    "mp3": {
      "count": 15,
      "keys": [
        "ingest/123456/Disc 1/mp3/01 - Track One.mp3",
        "ingest/123456/mp3/02 - Track Two.mp3"
      ]
    }
  },
  "acf_key": "ingest/123456/manifest.acf",
  "uploaded_at": "2026-04-03T00:00:00+00:00",
  "dry_run": false
}
```

### S3 key configuration rules

Scout arranges audio files according to the following rules:

1. **Basic structure**: `ingest/{AppID}/{Disk No.}/{extension}/{filename}`
   - `{Disk No.}` is `Disc 1`, `Disc 2`, etc.
   - If the sound source file is not in a specific disk directory (flat structure), `Disc 1` is completed by default.
   - If the original directory structure started with `Disc`, `CD`, `Volume`, etc., that structure is preserved.
   - This prevents directories with the same name from being duplicated for each extension, such as in multi-disc soundtracks.
2. **Path normalization**:
   - If the directory name included in the relative path from `install_path` matches the name of the current extension (e.g. `flac`, `mp3`) (ignoring case), that directory is considered redundant and removed.
   - Example: `install_path/track.flac` -> `ingest/123/Disc 1/flac/track.flac` (Disc 1 completion)
   - Example: `install_path/FLAC/track.flac` -> `ingest/123/Disc 1/flac/track.flac` (normalization + Disc 1 completion)
   - Example: `install_path/Disc 1/FLAC/track.flac` -> `ingest/123/Disc 1/flac/track.flac` (normalization + structure preserved)

Field description:

| Field | Type | Description |
|-----------|------|------|
| `app_id` | int | Steam AppID |
| `name` | str | App name obtained from ACF |
| `install_dir` | str | `installdir` value of ACF |
| `storage_location` | str | `"music"` or `"common"` |
| `track_count` | int | Total number of tracks for all extensions |
| `files_by_ext` | dict | Number of files by extension and S3 key list |
| `acf_key` | str | S3 key for ACF file |
| `uploaded_at` | str | Upload date and time (ISO 8601) |
| `dry_run` | bool | Whether it was run in dry-run mode |

---

## Worker Input

The Worker receives files under `ingest/{AppID}/` of SeaweedFS for processing.

```json
{
  "app_id": 123456,
  "files": [
    "ingest/123456/flac/01 - Track One.flac"
  ]
}
```

---

## Worker Output

```json
{
  "app_id": 123456,
  "file_refs": [
    "archive/123456/Disc 1/aiff/Disc_1 - 1 - Example Track Title.aiff"
  ],
  "status": "success",
  "resolved": {
    "resolved": true,
    "source": "vgmdb",
    "album": "Example Album",
    "artist": "Example Artist",
    "composer": "Example Composer",
    "mbid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "vgmdb_id": "123456",
    "vgmdb_album_url": "https://vgmdb.net/album/123456",
    "catalog_number": "ABCD-1234",
    "discid": "...",
    "title": "Example Track Title",
    "resolution": "vgmdb_enriched",
    "vgmdb_score": 0.82,
    "musicbrainz_score": 0.68,
    "partial_ratio": 0.85
  },
  "tag_result": {
    "updated": 1,
    "dry_run": false
  },
  "candidate_count": 5,
  "storage": {
    "bucket": "sst",
    "key": "archive/app_123456_20260101T000000Z.json"
  }
}
```

status values: "success" | "review"

resolved additional fields:
- vgmdb_score: float (0.0-1.0)
- musicbrainz_score: float (0.0-1.0)

---

## Internal

```json
{
  "state": "PROCESSING",
  "node": "worker"
}
```

---

# END

