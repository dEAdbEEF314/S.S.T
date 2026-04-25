# Processing Success & Routing Criteria (Act-11)

This document defines the automated conditions for routing soundtrack processing results to the `archive/` (approved) or `review/` (manual check) directories.

## 1. Archive Conditions (Automatic Approval)

An album is automatically moved to `archive/` only when all of the following metadata integrity checks pass:

1.  **High Confidence Score**: The LLM confidence score for the consolidation must be **80 or higher** (out of 100).
2.  **Completeness**: 
    - Every track must have a non-empty `TIT2` (Title).
    - Every track must have a valid `TRCK` (Track Number) that is a positive integer.
3.  **Forbidden Values**:
    - No metadata field (Title, Artist, Album, etc.) may contain the string "Unknown".
    - Track numbers cannot be "0".
4.  **Formatting**:
    - Genre starts with `STEAM VGM, `.
    - Disc numbers follow the `n/N` format.
5.  **Technical Success**: File conversion, image processing (500x500 PNG), and ID3v2.3 tagging completed without exceptions.

## 2. Review Conditions (Manual Intervention)

An album is moved to `review/` if any of the following triggers occur:

1.  **Low Confidence**: 
    - LLM confidence score is **below 80**.
    - The reason for uncertainty is stored in `llm_log.json` under `confidence_reason`.
2.  **Metadata Gaps**:
    - Any mandatory field is missing or resulted in "Unknown".
    - Track number is determined to be "0".
3.  **Schema Mismatch**: The LLM output failed to parse as valid JSON or does not match the required track mapping.
4.  **Hardware/API Failure**: API timeouts or local processing errors (FFmpeg, etc.).

## 3. Post-Processing Audit

Users can perform a batch audit of the `archive/` directory using the `audit_archives.py` utility to ensure no "False Positives" (e.g. hallucinated titles) escaped the automatic filters.
