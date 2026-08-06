---
name: sst-app-investigator
description: Investigate one S.S.T AppID by reconciling SQLite state, Steam slots, LLM assignments, physical output, package metadata, and timestamp-matched logs.
---

# S.S.T App Investigator

Use this skill for one AppID. It is an evidence workflow, not a batch report generator and not a replacement for the post-batch audit.

## Evidence order

1. Read the latest `processed_albums` row for the AppID from `data/sst_local_state.db`.
2. Locate the matching Archive or Review ZIP under `output/` and inspect only its `json/metadata.json` and `json/llm_log.json` first.
3. Compare `steam_info.store_tracklist` with `alignment_res.slots`, final `tracks`, `slot_key`, and the physical files represented by each record.
4. Check `track_groups -> slot_variant_index -> adopted_files -> processed_tracks_meta`; format variants are candidates for one slot, not automatically duplicate songs.
5. Inspect logs around the processed timestamp and correlate `FILE_RECORDS_BUILT`, duplicate-resolution messages, `VALIDATION_DONE`, package save events, and I/O exceptions.

## Required findings

Report the AppID, latest status/message/confidence fields, strategy, processed timestamp, expected Steam slot count, final track count, output formats, duplicate `(disc, track)` keys, duplicate `slot_key` values, missing/unexpected slots, `Fallback`, `LOCAL`, `Unknown`, and track `0` counts.

Separate the cause into these categories:

- **Specification/data**: missing or contradictory Steam structure, malformed source metadata, or unavailable physical files.
- **LLM alignment**: unassigned files, multiple slots for one file, one slot receiving unrelated files, or a title/number contradiction with Steam.
- **Implementation**: a reproducible mismatch between an owning transformation boundary and its expected key/slot contract.
- **I/O**: copy, conversion, permission, mount, or package-write failures supported by matching logs.

Treat the final validator result and physical output as authoritative. A high LLM confidence value does not override duplicate slots, missing Steam slots, or audio failures. Do not recommend weakening validation, lowering thresholds globally, auto-renumbering ambiguity, or replacing Steam structure with local filenames.

## Privacy

Do not paste raw logs, real local paths, hostnames, usernames, credentials, caches, audio, artwork, or database contents into public reports. Summarize the minimum evidence and use synthetic sanitized fixtures for tests.
