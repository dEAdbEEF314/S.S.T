---
name: sst-batch-inspector
description: Summarize the latest S.S.T result row for every AppID and route structural auditing to the post-batch investigator.
---

# S.S.T Batch Inspector

Use this skill for a quick batch overview after processing. The detailed audit and HTML report are owned by `sst-post-batch-investigator`; do not duplicate its slot, validator, or Archive/Review classification logic here.

## Quick inspection

Run the canonical report generator from the repository root:

```bash
uv run python .agents/skills/sst-post-batch-investigator/scripts/generate_post_batch_report.py
```

The report reads the latest `processed_albums` row per AppID and writes `report/batch_analysis_report.html`. Treat that report and its canonical script as the only source for batch-level classification. Use `sst-app-investigator` for a single AppID deep dive.

## Batch questions

Summarize counts of Archive and Review results, then identify AppIDs that require deep investigation. Preserve the distinction between input format variants and final duplicate records. Steam `store_tracklist`, adopted physical files, and `ResultValidator.validate()` control the interpretation; confidence alone never proves integrity.

For detailed reasons, inspect the canonical report fields for Steam slot count, final track count, duplicate keys, missing/unexpected slots, `Fallback`, `LOCAL`, track `0`, audio errors, and LLM alignment evidence. Do not reintroduce the former `confidence >= 100` heuristic or an independent MBZ similarity classifier.

## Compatibility scripts

The scripts in `scripts/` are thin compatibility wrappers around the post-batch investigator. They exist for old command references and must not grow independent business logic.
