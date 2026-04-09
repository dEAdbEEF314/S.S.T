# Tagging Specification (ID3v2.3)

## Core Fields

- TIT2: Title (LLM normalized)
- TPE1: Artist
- TALB: Album
- TPE2: Album Artist
- TCON: Genre (Soundtrack / Video Game Music)
- TCOM: Composer
- TDRC: Year
- TRCK: Track number (n/total)

---

## Priority

- VGMdb > MusicBrainz > Steam

---

## Artwork (APIC)

- Size: 500x500
- Maintain aspect ratio
- Black padding if necessary

---

## Custom Fields (TXXX)

- MusicBrainzAlbumID
- VGMdbID
- CatalogNumber
- SteamAppID

---

## Rules

- Never write empty tags
- Normalize encoding (UTF-8)
- Ensure compatibility with ID3v2.3
