# DATA CONTRACTS

> [!IMPORTANT]
> **Source of Truth**
> This document defines a common schema (Source of Truth) for metadata and file I/O in SST pipelines.

---

## 1. Tagging Specification & Metadata Mapping

When writing ID3v2.3 tags, the following mapping specifications are standard.

| ID3v2.3 Frame | Content | Source (in order of priority) |
| ------------- | ---- | ------------------- |
| `TIT2` | Track name | LLM inference results (VGMdb > MB > Steam-based) |
| `TPE1` | Artist | VGMdb (`performers`) > MB (`artist_credit`) |
| `TALB` | Album name | VGMdb (`name`) > MB (`title`) > Steam (`title`) |
| `TPE2` | Album artist | Compliant with `TPE1`, `Various Artists` etc. when multiple artists |
| `TCON` | Genre | `"Soundtrack", "Video Game Music"` |
| `TCOM` | Composer | VGMdb (`composers`) |
| `TDRC` | Release year | VGMdb > MB > Parsing from Steam response |
| `TRCK` | Track number | Local file order or parsing result (`1/15` etc.) |
| `APIC` | Artwork | VGMdb (`picture_full`) > Steam (`header_image`) |

### TXXX (User Defined Text)
- `MusicBrainzAlbumID`: MBID
- `VGMdbID`: VGMdb Algorithm ID
- `CatalogNumber`: VGMdb Catalogue Number
- `SteamAppID`: Steam App ID

### Artwork Specification
- Format: PNG (preferred) or JPEG
- Size inference: resize to 500x500
- Maintain aspect: If it is not square, adjust to 1:1 with black background (Padding)

### Resolution Decision Contract (VGMdb Primary)
- VGMdb adoption lower bound: `vgmdb_score >= 0.75`
- MB collation zone: `0.70 <= vgmdb_score < 0.75`
- MB fallback: `vgmdb_score < 0.70`
- review separation: `vgmdb_score < 0.55` and `musicbrainz_score < 0.55`
- Title match judgment: `title_similarity >= 0.80`
- Tolerance for number of songs: `track_count_tolerance = ±1`
- Date tolerance: `date_tolerance_days = 30`

---

## 2. Worker I/O Schemas

### Input (from Scout)

```json
{
  "app_id": 123456,
  "files": [
    "/mnt/work_area/123456/Disc 1/flac/01.flac"
  ]
}
```

### Output (to Archive/Review)

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

- `status`: `"success"` | `"review"`
- `resolved.source`: `"vgmdb"` | `"musicbrainz"` | `"steam"` | `"manual"`
- `resolved.title`: Track title normalized by LLM
- `resolved.resolution`: Solution path (`"vgmdb_enriched"`, `"partial_acoustid"`, `"full_acoustid"`, `"fallback"`)
- `resolved.vgmdb_score`: VGMdb confidence score (0.0-1.0)
- `resolved.musicbrainz_score`: MusicBrainz Reliability Score (0.0-1.0)
