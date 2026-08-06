---
name: sst-post-batch-investigator
description: Inspect S.S.T batch outcomes against the current Steam-slot and physical-file contracts, classify Archive/Review causes, and generate an auditable HTML report.
---

# S.S.T Post-Batch Investigator

Use this skill after `./sst --limit N` or a selected AppID rerun. Explain each Archive/Review result using persisted metadata and logs. Do not improve Archive rate by weakening validation: Steam remains the structural source of truth, and physical integrity failures remain Review conditions.

## Run the report

From the repository root:

```bash
uv run python .agents/skills/sst-post-batch-investigator/scripts/generate_post_batch_report.py
```

The script reads the latest `processed_albums` row for each AppID from `data/sst_local_state.db`, scans `logs/*.log`, and writes `report/batch_analysis_report.html`. This is a diagnostic artifact; use the per-AppID ZIP audit bundle for definitive evidence.

## Current processing contract

Evaluate results in this order:

1. **Steam structure**: `steam_info.store_tracklist` defines expected `(disc, track)` slots. PICS/Steam structure outranks MusicBrainz and local filenames. Text tracklists are lower-confidence and must remain visible in audit data.
2. **Physical candidates**: every audio file is an independent `file_id` record. AIFF/WAV/FLAC and MP3 variants of one song are candidates for one Steam slot, not automatically duplicate songs.
3. **Slot adoption**: `build_slot_variant_index()` groups candidates by aligned Steam slot; `adopt_best_file_per_slot()` chooses one highest-priority format. The final `tracks` list must contain at most one record per adopted slot.
4. **Tag validation**: `ResultValidator.validate()` checks duplicate `(disc_number, track_number)` keys, zero/unknown tracks, dirty titles, duplicate titles, audio failures, and confidence gates. High LLM scores do not override physical failures.
5. **Audit evidence**: use `metadata.json`, `llm_log.json`, `AUDIT_REPORT.html`, the SQLite row, and timestamp-matched logs together. Never infer a root cause from the final status message alone.

## Required batch checks

For every AppID, record:

- latest DB status, message, confidence fields, strategy, and processed timestamp;
- expected Steam slot count and final processed track count;
- output format counts and physical file count when a debug directory or package is available;
- duplicate `(disc, track)` keys and duplicate `slot_key` values;
- missing or unexpected Steam slots;
- `source == "Fallback"`, `title_source == "LOCAL"`, `Unknown` titles, and track number `0`;
- format variants per slot and whether adoption reduced them to one final record;
- audio failures/warnings and matching I/O errors in logs;
- LLM slot assignments, unassigned files, duplicate assignments, and title/number mismatches against Steam.

## Classify findings

### Archive integrity concerns

An Archive is suspicious when it has a final track count different from the Steam slot count, duplicate `(disc, track)` or `slot_key` values, missing/extra slots, `Fallback`, `LOCAL` titles, track `0`, `Unknown` titles, an output-count mismatch, or a final format below the highest available candidate tier. HTML entities and malformed artist/album fields are additional metadata concerns.

Distinguish a real duplicate song from uncollapsed format variants. Multiple input formats are expected; two final records for one Steam slot are not.

### Review causes

Use the actual validator message and evidence:

- **Structural**: `Duplicates`, `Track#0`, `Unknown Title`, `Dirty Tags`, `Duplicate Titles`, missing/extra slots, or unresolved Steam structure.
- **Physical I/O**: `CRITICAL: Audio Source Error`, copy/conversion failures, inaccessible mounts, permission errors, or matching log exceptions.
- **Audio warning**: non-fatal encoding or quality warning.
- **Confidence/LLM**: confidence or archive/review ratio gates when physical structure is clean. Do not call this a hardcoded `conf < 100` early-exit bug unless current code and logs prove it.
- **LLM alignment**: unassigned files, one file assigned to multiple slots, unrelated titles in one slot, or a title/number mismatch against Steam. Confidence does not make a contradictory mapping correct.
- **Mixed**: use when multiple independent causes are present and list each one.

## AppID deep investigation

1. Query the latest SQLite row and preserve status/message/confidence values.
2. Locate the matching `output/archive` or `output/review` ZIP and inspect `json/metadata.json` and `json/llm_log.json`.
3. Compare Steam slots, LLM `alignment_res.slots`, final `tracks`, `slot_key`, and physical files.
4. Count final duplicate keys and compare them with the validator message.
5. Inspect timestamp-matched logs around `FILE_RECORDS_BUILT`, duplicate-resolution messages, `VALIDATION_DONE`, and package save events.
6. State whether the cause is specification/data quality, LLM alignment, or implementation. Keep these categories separate.

For format variants, verify this transition:

```text
physical input files -> track_groups -> slot_variant_index -> adopted_files -> processed_tracks_meta
```

The invariant is one adopted physical file per Steam slot. A format variant must not create a final `Duplicates` finding merely because it existed in the input.

## Recommendations

Recommendations must follow observed evidence. Prefer a synthetic regression fixture, an owning-boundary fix for key/slot identity, rejection or Review of contradictory LLM mappings, structured collection-count diagnostics, or retry handling for proven I/O failures. Do not recommend globally lowering confidence thresholds, weakening duplicate validation, auto-renumbering ambiguous tracks, or replacing Steam structure with local filenames without a reproduced case and focused test.

## Privacy and evidence rules

Reports and public fixtures must not expose real paths, usernames, hostnames, process IDs, timestamps, credentials, caches, databases, audio, artwork, or raw private logs. Use sanitized synthetic fixtures for tests. Keep raw local evidence in ignored workspace output and summarize only fields needed for the conclusion.
