# act-12 TODO: Rich CLI and Mode-Based Behavior

Objective: Implement Phase 5 (CLI UX) and enforce system behaviors based on `ENV_MODE` and `LOG_LEVEL` to provide a professional user experience.

## 1. Environment & Logic Tuning (Priority: High)
- [ ] **Dynamic Error Cleanup**: Update `processor.py` to preserve the `temp_output` directory if `ENV_MODE=development` and an error occurs, for easier debugging.
- [ ] **Production Fail-safe**: Ensure that in `ENV_MODE=production`, the processor continues to the next album even if a critical error occurs in one (currently, some exceptions might bubble up).
- [ ] **Automated Log Rotation**: In `production` mode, redirect all detailed `INFO/DEBUG` logs to `logs/sst_run_YYYYMMDD.log` and keep the stdout clean.

## 2. Phase 5: Rich CLI Implementation (Priority: Critical)
- [ ] **Multi-Progress Bars**: Use the `rich` library to show:
    - Overall album scan/queue progress.
    - Per-album track conversion/tagging progress (synchronized with `MAX_ENCODING_TASKS`).
- [ ] **Summary Dashboard**: Display a beautiful result summary at the end of each run (Success, Review, Error counts).

## 3. Documentation & Handover
- [ ] Finalize `CLI_RECONSTRUCTION.md` with the new interactive flow.
- [ ] Update `HANDOVER_act-12.md` for team onboarding.
