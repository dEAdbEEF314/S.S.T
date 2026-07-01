---
name: sst-system-monitor
description: Monitor the S.S.T system execution and Ollama backend simultaneously to diagnose hangs, slow processing, or LLM thinking-loop issues.
---

# S.S.T System Monitor

When the S.S.T process appears to be frozen or hanging at the `[LLM PROMPT END]` stage, it is often due to the LLM backend (e.g., Ollama) taking a long time to process large contexts or generating excessive "thinking" text. 
Use this skill to run a concurrent monitoring trace.

## 🛠️ 3-Tier Monitoring Setup (Diagnostics Execution Steps)

To properly monitor the system and ensure you don't miss any context, launch these three processes concurrently in the background (using `WaitMsBeforeAsync` to stream their outputs to your context):

1. **The Main S.S.T Process**:
   Ensure `data/sst.lock` is removed first, then start your batch or test.
   ```bash
   rm -f data/sst.lock && uv run ./sst --limit <LIMIT> --fingerprint-all --dev --y
   ```
   *Provides high-level progress and overall task management.*

2. **S.S.T App Logs (Frontend)**:
   Start this immediately after the main process to capture verbose application logs.
   ```bash
   uv run ./sst --tail
   ```
   *Reveals if the LLM is outputting `--- [LLM THINKING START] ---` and how long it takes before returning the actual JSON response.*

3. **Ollama Server Logs (Backend)**:
   Start this to monitor the native backend behavior.
   ```bash
   journalctl -u ollama.service -f
   ```
   *Watch for `n_tokens` sizes and `n_decoded` progress to see if the LLM is actively generating text, loading KV caches, or stuck.*

## 🔍 How to Analyze

- If `journalctl` shows a steady output of `n_decoded` metrics, the LLM is **not hung**, it is actively generating tokens.
- If `sst --tail` shows an `[LLM THINKING START]` block that takes a long time, the model is likely bypassing the `NO PREAMBLE` rule and producing excessive verbose thoughts.
- Before killing the process, evaluate the token generation speed and allow the model some time to finish. If it truly gets stuck in an infinite generation loop, stop the processes and consider switching the `LLM_MODEL` in `.env`.
