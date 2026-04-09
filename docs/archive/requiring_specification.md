# Requiring Specification

This document manages "items that have been implemented or are in actual operation, but are not finalized or described as specifications."
After making a decision, move to the corresponding design document and delete it from this document.

---

## List of unconfirmed items

### [Scout] mode.upload_audio_files

| Project | Content |
|------|------|
| Current situation | `mode.upload_audio_files: true` exists in `scout/config.yaml` and `scout/config.example.yaml` |
| Implementation | `upload_app()` of `uploader.py` receives as `upload_audio` parameter and controls audio source upload to S3 |
| CLI support | `--no-audio` flag now corresponds to `upload_audio=False` |
| Undetermined point | Is the process of reading `mode.upload_audio_files` from config and overwriting `upload_audio` implemented in `main.py`, or is CLI flag the only means of control? |
| Corresponding document candidates | Scout → mode section of `docs/CONFIG_SPEC.md` |
| Responsible action | Check `scout/src/main.py` and verify that `upload_audio_files` is read from config. If you have read it, add it to the mode section of CONFIG_SPEC |

---

### [Core] Prefect Production confirmation of operation script

| Project | Content |
|------|------|
| Current situation | The following PowerShell script exists in `core/prefect/`, but its actual operation has not been confirmed |
| Script list | `setup-work-pool.ps1` / `deploy-worker-flow.ps1` / `run-worker-deployment.ps1` |
| Undetermined points | Does each script match the current Prefect server settings, environment variables, and work pool name? |
| Scope of Impact | “Operational runbook” requirements for Phase 4 Integration testing |
| Responsible Actions | Execute the 3 scripts in sequence in the actual environment and check the operation. If an error occurs, modify the script and update the Run Checklist in PREFECT_FLOW.md |

---

## Determined items (moved)

(none)
