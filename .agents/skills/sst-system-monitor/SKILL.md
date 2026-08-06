---
name: sst-system-monitor
description: Monitor an active S.S.T run and Ollama backend for progress, stalls, and I/O or LLM failures without starting the batch.
---

# S.S.T System Monitor

Use this skill only after a batch or selected AppID run has already been started. Starting and completing the run belongs to `sst-batch-test`.

## Monitor

Observe the active S.S.T process and its structured logs, then inspect the Ollama service and model activity using the host’s available process and journal tools. Track:

- last log event and elapsed time;
- AppID and track identifiers on failure lines;
- LLM request/response or token progress;
- file copy, conversion, mount, permission, and package-write errors;
- whether the process is making progress or has stopped at one AppID/track.

Use `sst --tail` when available for the project’s live log view. Do not expose raw paths, usernames, hostnames, process IDs, credentials, or full private logs in public reports.

## Stall diagnosis

Call a run stalled only when the process has no meaningful log or token progress for a sustained interval and the backend state supports that conclusion. Distinguish an active long LLM request from an I/O hang, a dead backend, and a completed process whose output has not yet been inspected.

When the run ends, hand results to `sst-batch-inspector` or `sst-post-batch-investigator`; do not duplicate their Archive/Review classification.
