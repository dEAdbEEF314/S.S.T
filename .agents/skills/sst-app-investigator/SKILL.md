---
name: sst-app-investigator
description: Investigate evaluation status and reasoning for a specific Steam AppID in the S.S.T (Steam Soundtrack Tagger) project.
---

# S.S.T App Evaluation Investigator Skill

This skill provides the procedures and tools to investigate why a specific Steam AppID was evaluated with a certain status (e.g., `review`, `archive`, `skip`) and to trace the underlying reasoning path (including raw LLM outputs and system heuristics).

## 🛠️ Automated Investigation Tool

You can use the automated script in `Maintenance/investigate_app.py` to check the DB record and ZIP log bundle at once.

### Usage
Run the following command in the workspace root:
```bash
uv run python Maintenance/investigate_app.py <AppID>
```

### Example Output
```text
============================================================
AppID: 4304640 | Album Name: Blaze of Storm Soundtrack
Current DB Status: REVIEW
Validation Message: [Quality too low (40%)]
Confidence Score: 100% | Integrity Quality: 40%
System Reason: SYSTEM: STEAM-TRUSTにより確信度を100%に引き上げました (24トラックとの構造的一致)
============================================================
Found ZIP Package: output/review/4304640_Blaze_of_Storm_Soundtrack.zip

--- Raw LLM Phase 1 Response (Before System Heuristics) ---
Raw Confidence: 60%
Raw Quality: 40%
Raw Reason: STEAMのトラックリストとLOCALのファイル名に共通の曲名は見られるが、LOCAL側で同一曲の重複（例: cyber diving 1, 13）や順序の不一致が顕著であり、構造的な一致が認められないため。
Semantic Label: 不整合あり
============================================================
```

## 🔍 Manual Investigation Procedure

If you need to perform manual checks, follow these steps:

### Step 1: Query the SQLite Database
Query `processed_albums` in `data/sst_local_state.db` to check the current evaluation status, computed confidence score, and integrity quality:
```sql
SELECT status, album_name, metadata_json FROM processed_albums WHERE app_id = <AppID>;
```
Key parameters to observe in `metadata_json`:
* `status`: Final outcome (`archive` / `review`).
* `confidence_score` & `integrity_quality`: System grading metrics.
* `message`: Shows which validators triggered (e.g., `[Quality too low (40%)]`).
* `confidence_reason`: Reason recorded in DB. Note that system heuristics (like `STEAM-TRUST`) might have overwritten the original LLM reasoning here.

### Step 2: Unpack the ZIP Package Logs
Find the output ZIP file corresponding to the AppID under `output/review/` or `output/archive/`.
Extract `json/llm_log.json` to inspect the raw LLM responses.

* **Raw Phase 1 Response**:
  Look at `logs[0].response` inside `llm_log.json`. This contains the raw JSON output from the LLM *before* system heuristics adjusted the values.
  Key fields in raw response:
  * `identity_confidence`: Raw score given by LLM.
  * `integrity_quality`: Raw quality evaluation score.
  * `confidence_reason`: The actual raw textual reasoning explaining the discrepancies or alignment issues found.

### Step 3: Map to Code Logic
* Check `src/sst/validator.py` (`ResultValidator.validate`) to understand which rules (such as duplicates, track number 0, or quality threshold) converted the metrics into the final `review` status.
* Check `src/sst/llm.py` (`consolidate_virtual_albums`) for any active `SYSTEM-LEVEL HEURISTICS` (e.g., `STEAM-TRUST`) that might have overridden the raw LLM scores.
