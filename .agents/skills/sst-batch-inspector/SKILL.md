---
name: sst-batch-inspector
description: Analyze and inspect processing results of a batch tagger execution in S.S.T (Steam Soundtrack Tagger) project, including detailed statistics and detection of unnatural outcomes.
---

# S.S.T Batch Process Inspector Skill

This skill provides automated scripts and manual procedures to query, categorize, and inspect the overall results of a batch soundtrack tagging run. It helps detect:
1. Aggregate statistics (Archive vs. Review ratios).
2. Grouped root causes of `REVIEW` status (e.g. Duplicates, Track#0, Audio errors).
3. Unnatural `ARCHIVE` outcomes (e.g. massive title deviations with MusicBrainz matching).
4. Unnatural `REVIEW` outcomes (e.g. LLM has 100% confidence but system validator overrode it due to physical checks).

---

## 🛠️ Automated Investigation Tool

You can run the aggregate analysis script included in this skill to get a complete breakdown of the processing database.

### Usage
Run the following command at the workspace root:
```bash
uv run python .agents/skills/sst-batch-inspector/scripts/analyze_batch_results.py
```

### Script Output Details
*   **Status Distribution**: Gives count and percentages of overall success (Archive) vs. manual review needed.
*   **Archive Reason Patterns**: Shows the dominant decision paths (e.g., `Success [Steam Trust]`).
*   **Review Reason Patterns**: Groups all issues by category (e.g., Duplicates counts, Track#0 counts).
*   **Unnatural Archive scan**: Reports any albums where the selected MusicBrainz (MBZ) release title similarity to the Steam album title is below 40%.
*   **Unnatural Review scan**: Lists any AppIDs where the LLM returned `confidence_score == 100` but the final outcome was downgraded to `REVIEW` by the validator, showing the corresponding physical trigger.

---

## 🔍 Manual SQL Investigation Queries

For direct database inspections, query `data/sst_local_state.db` using the following references.

### 1. View Total Statistics
```sql
SELECT status, COUNT(*), ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM processed_albums), 2) || '%' AS ratio
FROM processed_albums
GROUP BY status;
```

### 2. Identify High-Confidence Overrides (Unnatural Review)
Find albums where the system evaluated identity confidence at 100% but validator downgraded it to `REVIEW`:
```sql
SELECT app_id, album_name, 
       json_extract(metadata_json, '$.message') as validator_msg,
       json_extract(metadata_json, '$.confidence_reason') as reasoning
FROM processed_albums
WHERE status = 'review' 
  AND json_extract(metadata_json, '$.confidence_score') >= 100;
```

### 3. Extract Tracks Mapped to MusicBrainz Releases
To check if files are being tagged with wrong MBZ releases:
```sql
SELECT app_id, album_name, metadata_json
FROM processed_albums
WHERE status = 'archive' 
  AND metadata_json LIKE '%"source":%"MusicBrainz"%';
```
*(Parse the returned metadata JSON's `tracks[].tags.album` against `album_name` using Levenshtein distance).*
