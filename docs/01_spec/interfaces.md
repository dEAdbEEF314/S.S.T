# External Interfaces Specification

## Purpose

Define REQUIRED behavior and OPTIONAL implementation details for external services.

---

# MusicBrainz Interface

## Endpoint (Reference)

- https://musicbrainz.org/ws/2/

## Required Capabilities

- Search releases by title
- Filter by artist / date when possible
- Retrieve:
  - release title
  - artist_credit
  - track count
  - release date

## Query Requirements

- Must include:
  - query string (title)
  - fmt=json

Example:

/ws/2/release/?query=release:NAME&fmt=json

## Constraints

- Must include User-Agent
- Must respect rate limiting (~1 req/sec recommended)
- Must implement retry

## Normalized Output (Required)

```json
{
  "title": "...",
  "artist": "...",
  "track_count": 10,
  "release_date": "YYYY-MM-DD"
}
````

---

# VGMdb Interface

## Implementation Strategy

* Preferred: use hufman/vgmdb wrapper
* Alternative: HTTP scraping (if compliant)

## Required Capabilities

* Search album by title (ja/en/romaji)
* Retrieve:

  * album title
  * track count
  * release date
  * catalog number
  * performers

## Constraints

* Must handle:

  * 403 / 429
  * timeouts
* Must implement retry (3 attempts minimum)

## Normalized Output

```json
{
  "title": "...",
  "track_count": 10,
  "release_date": "YYYY-MM-DD",
  "catalog_number": "...",
  "performers": []
}
```

---

# Steam Metadata Interface

## Required Fields

* title
* release_date

---

# Common Rules

All interfaces MUST:

* Return normalized data
* Handle partial failures
* Be retryable
* Never throw unhandled exceptions

---

# Design Rule

This layer MUST isolate:

* API differences
* data inconsistencies
* rate limits

From the core pipeline.

