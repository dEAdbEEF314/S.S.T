# I/O Specification

## Scout Output (scout_result.json)

```json
{
  "app_id": 123456,
  "name": "Example Game",
  "install_dir": "ExampleDir",
  "storage_location": "local",
  "track_count": 10,
  "files_by_ext": {
    "flac": 10
  },
  "acf_key": "123456",
  "uploaded_at": "2026-01-01T00:00:00Z",
  "dry_run": false
}
````

---

## Worker Input

```json
{
  "app_id": 123456,
  "files": [
    "ingest/123456/Disc 1/flac/01 - Track One.flac"
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

---

## Status Values

* success
* review

---

## Constraints

* Output must always be valid JSON
* All paths must be S3-compatible

````

