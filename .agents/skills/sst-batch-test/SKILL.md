---
name: sst-batch-test
description: Run and verify a 100-item S.S.T batch test, leaving live process monitoring to sst-system-monitor.
---

# S.S.T Batch Test

Use this skill to execute one 100-item batch and verify completion. Monitoring is a separate concern owned by `sst-system-monitor`.

## Procedure

1. Confirm the repository root, selected environment, and an intentionally sanitized output destination.
2. Start the supported S.S.T batch command with a limit of 100 using the project’s current CLI entry point.
3. Record the command, start time, process identifier, and exit result in local ignored notes only. Do not publish environment-specific values.
4. Wait for the command to finish, then verify the expected SQLite and output artifacts exist.
5. Run the canonical post-batch report:

```bash
uv run python .agents/skills/sst-post-batch-investigator/scripts/generate_post_batch_report.py
```

6. Use `sst-app-investigator` for any AppID that needs evidence-level analysis.

Do not classify individual outcomes from shell output alone. Do not weaken the validator or reinterpret format variants as final duplicates to improve the Archive rate.

## Monitoring handoff

If the process is still running, use `sst-system-monitor` for `sst --tail`, Ollama activity, token progress, and hang diagnosis. That skill does not start or own the batch command.
