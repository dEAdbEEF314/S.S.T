---
name: sst-tuner
description: Automates the S.S.T (Steam Soundtrack Tagger) metadata tuning loop. Use this skill when you need to perform iterative log analysis, code/prompt refinement, and validation test runs to achieve high-precision metadata archival.
---

# S.S.T Tuner

This skill automates the rigorous tuning loop required to refine the metadata identification and archival logic of the S.S.T system.

## Primary Workflow

When using this skill, you must follow the [tuning_workflow.md](references/tuning_workflow.md) guide.

### Key Responsibilities

1.  **State Management**: Use the `./sst --reset-db` command (or manual file deletion) and clear output folders before every tuning iteration to ensure fresh results.
2.  **Log Auditing**: Review the uniquely named logs in `logs/` to understand why specific albums were sent to `REVIEW`.
3.  **Prompt Refinement**: Edit `scout/src/scout/llm.py` to adjust the deduction criteria or add exception rules for legitimate metadata patterns (e.g., official track numbering).
4.  **Logic Hardening**: Update `scout/src/scout/processor.py` or `scout/src/scout/builder.py` to fix physical crashes or improve the deterministic scoring gates.

## Commands

- **Reset and Run (50 items)**:
  `rm -f data/sst_local_state.db && rm -rf output/archive/* output/review/* && ./sst -n 50`
- **Tail Unique Log**:
  `ls -t logs/SST_log_*.log | head -n 1 | xargs tail -f`
- **Check Review Breakdown**:
  `./sst --logs | grep "review"`
