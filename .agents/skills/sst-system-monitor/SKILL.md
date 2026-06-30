---
name: sst-system-monitor
description: Monitor the S.S.T system execution and Ollama backend simultaneously to diagnose hangs, slow processing, or LLM thinking-loop issues.
---

# S.S.T System Monitor

When the S.S.T process appears to be frozen or hanging at the `[LLM PROMPT END]` stage, it is often due to the LLM backend (e.g., Ollama) taking a long time to process large contexts or generating excessive "thinking" text. 
Use this skill to run a concurrent monitoring trace.

## 🛠️ Diagnostics Execution Steps

To properly monitor the system, run the following commands concurrently in the background:

1. **Monitor Ollama Logs (Backend)**:
   ```bash
   journalctl -u ollama.service -f
   ```
   *Watch for `n_tokens` sizes and `n_decoded` progress to see if the LLM is actively generating text or stuck.*

2. **Run the S.S.T Task**:
   Ensure `data/sst.lock` is removed if a previous instance was killed forcefully, then run the test:
   ```bash
   rm -f data/sst.lock && uv run ./sst --limit 1 --fingerprint-all --dev --y
   ```

3. **Monitor S.S.T Logs (Frontend)**:
   Wait 1-2 seconds after starting the task, then run:
   ```bash
   uv run ./sst --tail
   ```
   *This log will reveal if the LLM is outputting `--- [LLM THINKING START] ---` and taking a long time before the actual JSON response.*

## 🔍 How to Analyze

- If `journalctl` shows a steady output of `n_decoded` metrics, the LLM is **not hung**, it is actively generating tokens.
- If `sst --tail` shows an `[LLM THINKING START]` block that takes a long time, the model is likely bypassing the `NO PREAMBLE` rule and producing excessive verbose thoughts.
- Before killing the process, evaluate the token generation speed and allow the model some time to finish. If it truly gets stuck in an infinite generation loop, stop the processes and consider switching the `LLM_MODEL` in `.env`.
