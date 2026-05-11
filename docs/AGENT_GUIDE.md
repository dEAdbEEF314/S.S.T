# SST Agent Guide (STRICT)

This document defines **hard constraints and execution rules for AI agents**.

This is NOT a general guideline.
This is an **execution contract**.

---

# 🎯 Primary Objective

Produce **correct, verifiable, spec-compliant outputs** that adhere to the **"Absolute Trust"** policy.

---

# 🧭 Execution Model

You operate as:
> A deterministic processing unit in a standalone CLI system.

You are NOT a creative assistant or a guessing system.

---

# 📚 Mandatory Inputs

Before any action, you MUST reference:
- `docs/SST.md` (Core Architecture & Decision logic)
- `docs/TAGGING_RULE.md` (Audio & Metadata standards)
- `docs/DEPLOYMENT_GUIDE_jp.md` (Environment setup)

---

# 🔒 Hard Constraints

## 1. No Hallucination
If data is missing: **DO NOT GUESS**.
- Fallback to another official source (PICS, Web API).
- Reduce confidence.
- Mandatory route to `REVIEW`.

## 2. Confidence-Gated Decisions (Absolute Trust)
You MUST adhere to the gate-based scoring system:
- **ARCHIVE**: Identity Confidence == 100 AND Integrity Quality >= 95.
- **REVIEW**: Any score lower than above, or any presence of "Dirty Tags" (numbers mixed in titles) that don't match the source spec.

## 3. Mandatory Review Workflow
1.  **System Action**: Move uncertain items to `review/` as extracted folders.
2.  **User Action**: Correct metadata manually using tools like **MP3tag**.
3.  **Finalization**: Use `./sst --finalize` to ingest corrected tags back into the database.

## 4. Pipeline & Safety
- **3-Step Confirmation**: Mandatory for `--delete-db` and `--finalize`.
- **Fast-Track**: Bypass LLM ONLY if a direct MBZ link exists and track counts align perfectly across all sources.
- **Buffer Separation**: All temporary processing must occur in `/tmp/sst-work/buffer_*` to prevent workspace pollution.

## 5. Tagging Enforcement
- **ID3v2.3**: Mandatory for MP3 files. Use `TYER` for years.
- **Separators**: Always use comma + space (`, `).
- **Pruning**: Automatically prune `COMM` tags from the end if they exceed ~2000 characters.

## 6. Environment Management
- **You MUST use `uv`** for all Python-related tasks.
- Always use `uv run` for executing the system to ensure environment consistency.

---

# 🧠 Decision Framework

Every decision must answer:
1. Is it supported by **Official Steam PICS** or **MusicBrainz**?
2. Does it meet the **100/95 threshold**?
3. Is it reproducible?

If ANY answer is no → **REVIEW**.

---

# 🧪 Self-Validation Checklist
* [ ] JSON valid & schema compliant.
* [ ] ID3v2.3 compatibility checked.
* [ ] No hallucination (Source-backed only).
* [ ] All 3-tier API data considered.

If any unchecked → **FIX or REVIEW**.

---

# End of Document
