# TODO act-8: Local-only Architecture Migration & LLM Implementation

This branch focuses on transitioning the S.S.T system to a "Local-only (Edge Processing)" architecture and implementing the definitive LLM metadata consolidation logic as defined in `TAGGING_RULE.md`.

## 1. Core Architecture Refactoring
- [ ] **Retire Distributed Pipeline**: Deprecate the `ingest/` prefix in S3 and remove the Prefect flow dependency for the primary processing path.
- [ ] **Merge Worker into Local Service**: Integrate `AudioTagger`, `MusicBrainzIdentifier`, and metadata extraction logic directly into the Scout (local processor).
- [ ] **Local State Management**:
    - [ ] Implement a SQLite database to track processed `app_id`s, cached metadata, and local file hashes.
    - [ ] Ensure processed albums are skipped unless `--force` is used.

## 2. Audio Processing & Adoption Logic
- [ ] **Multi-Format Metadata Extraction**:
    - [ ] Implement a scanner that extracts tags from *every* audio file variant before any conversion.
    - [ ] Calculate exact playback duration (float seconds) for all files, especially WAV.
- [ ] **Strict Adoption Hierarchy**:
    - [ ] Lossless (FLAC/WAV/ALAC) -> Convert to AIFF (24bit/48kHz).
    - [ ] High-quality Lossy (AAC/OGG) -> Convert to MP3 (CBR 320k/48kHz).
    - [ ] MP3 -> Passthrough (No re-encoding).
- [ ] **Per-Track Artwork**: Update logic to extract and embed artwork on a per-track basis.

## 3. LLM Metadata Consolidation ("The Organizer")
- [ ] **Prompt Engineering**:
    - [ ] Create a system prompt for the LLM as a "Factual Metadata Organizer".
    - [ ] Include strict instructions: No hallucination, follow language priority (User > EN > Native).
- [ ] **Context Assembly**:
    - [ ] Pass Format-Specific Tag Sets, Steam API data, and MusicBrainz data to the LLM.
    - [ ] For WAV files, pass MusicBrainz matches based on duration comparison.
- [ ] **Conflict Resolution**: Implement logic for the LLM to pick the most detailed and consistent strings across sources.

## 4. Review & Archival Workflow
- [ ] **Final Packaging**:
    - [ ] Standardize the upload to `archive/` with `metadata.json` and `.acf`.
    - [ ] Store LLM interaction logs (prompts/responses) alongside the metadata.
- [ ] **Enhanced Review Bundle**:
    - [ ] If confidence is low, create a bundle ZIP containing: adopted audio, `.acf`, raw metadata sources JSON, and LLM logs.
    - [ ] Upload bundle to `review/`.

## 5. UI & Integration
- [ ] **Backend Update**: Adjust UI backend to read from the new SQLite cache for faster dashboard rendering.
- [ ] **Log Viewer**: Ensure the UI can display the LLM consolidation logs from S3.
