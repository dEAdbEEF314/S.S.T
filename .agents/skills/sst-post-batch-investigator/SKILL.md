---
name: sst-post-batch-investigator
description: Analyze batch processing results in S.S.T, detect unnatural Archive/Review outcomes, examine root causes (e.g. LLM confidence thresholds, I/O errors, HTML encoding issues), propose concrete action plans to increase Archive rate while raising metadata quality, and generate dark-mode HTML reports.
---

# S.S.T Post-Batch Investigator Skill

This skill provides automated analysis procedures to inspect the execution outcomes of an S.S.T batch tagging run (`./sst --limit N`), identify unnatural classification edge-cases, and produce actionable recommendations alongside a rich dark-mode HTML report.

---

## 🛠️ Automated Investigation Script

Run the automated post-batch inspection script included in this skill:

```bash
uv run python .agents/skills/sst-post-batch-investigator/scripts/generate_post_batch_report.py
```

This will analyze `data/sst_local_state.db` and the logs under `logs/`, automatically generating a dark-mode HTML report at `report/batch_analysis_report.html`.

---

## 🔍 Analytical Methodology & Investigation Focus

When invoking this skill or analyzing post-batch results, evaluate three major areas:

### 1. Unnatural Archive Detection
Identify albums marked as `ARCHIVE` that possess quality flaws or incomplete metadata:
*   **HTML Entity Residue**: Titles containing `&amp;`, `&quot;`, `&#39;`, etc.
*   **Developer/Publisher Concatenation**: `AlbumArtist` containing duplicated company names (e.g. `CAPCOM CO., LTD., CAPCOM CO., LTD.`) or raw developer strings instead of composer names.
*   **Game Genre Pollution**: Genre tags containing store categories (e.g. `STEAM VGM, アクション, インディー`) rather than clean music genres.

### 2. Unnatural Review Detection
Examine albums downgraded to `REVIEW` despite high quality or matching evidence:
*   **Early Exit Gate (`conf < 100`)**: Check for cases where LLM identity confidence is 90%–98% but Phase 2 track mapping was bypassed due to hardcoded 100% threshold checks (resulting in `Unknown Review Reason` / empty messages).
*   **Storage I/O & Mount Failures**: Inspect `logs/*.log` for `[Errno 112] Host is down` or CIFS/SMB file copy exceptions that triggered `CRITICAL: Audio Source Error` despite 100% confidence.
*   **Minor Structural Penalties**: Identify cases downgraded due to `Track#0` or multi-disc duplicate track numbers.

### 3. Actionable Improvement Plan & Target Metric Projections
Formulate 5 core technical remedies to elevate metadata correctness and boost Archive rates in subsequent runs:
1.  **Relax Early Exit & Dynamic Confidence Thresholds**: Transition from `conf < 100` hard exit to `conf >= 85` transition and `Conf >= 90% & Qual >= 85%` Archive approval.
2.  **Exponential Backoff I/O Retries**: Add 3-stage retries on `shutil.copy2` and network storage access.
3.  **Automatic HTML Unescaping**: Enforce `html.unescape()` across all string builder pipelines.
4.  **Intelligent AlbumArtist/Genre Normalization**: Deduplicate company names and sanitize store categories into clean music genres.
5.  **Track#0 / Prefix Sanitization**: Auto-renumber 0-indexed tracks and strip `01 - ` title prefixes.
