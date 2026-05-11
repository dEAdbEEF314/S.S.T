# S.S.T Tuning Workflow

This reference documents the iterative process for tuning the S.S.T (Steam Soundtrack Tagger) system to achieve "Zero-Hallucination" metadata archival.

## The Tuning Loop

1.  **Preparation (State Reset)**:
    -   Delete the local state database: `rm -f data/sst_local_state.db`
    -   Clear previous output artifacts: `rm -rf output/archive/* output/review/*`
2.  **Execution (Test Run)**:
    -   Execute a representative test run (typically 40-50 albums): `./sst -n 50`
3.  **Analysis (Log Audit)**:
    -   Analyze the uniquely generated debug log: `logs/SST_log_YYYYMMDDhhmmss.log`
    -   Filter for albums that ended up in `REVIEW` status.
    -   Identify the root cause for each `REVIEW` assignment (e.g., Score < 95%, Dirty Tags, Track count mismatch).
4.  **Refinement (Code/Prompt Patching)**:
    -   If the logic was too harsh: Adjust deduction rules in `scout/src/scout/llm.py` or the physical gates in `scout/src/scout/processor.py`.
    -   If the logic was too loose ("忖度"): Tighten prompt constraints or double-gate validation logic.
    -   If a technical error occurred: Patch the specific bug (e.g., `NoneType` guards).
5.  **Validation (Repeat)**:
    -   Return to Step 1 and verify that the changes improved the outcome.

## Common Log Patterns to Audit

| Pattern | Meaning | Action |
| :--- | :--- | :--- |
| `[AppID] --- [LLM RESPONSE START]` | Full reasoning trace | Compare the reasoning to the final score/ratio. |
| `archive_vs_review_ratio` | LLM's internal uncertainty | If low, check if it's due to minor acceptable diffs. |
| `Dirty Tags xN` | Physical gate triggered | Check if these are legitimate numerical titles. |
| `Track#0 xN` | Missing track metadata | Verify if the local file or MBZ is lacking data. |
| `HTTP 200 / Failure` | Malformed JSON | Check chunk sizes and `num_predict` limits. |
