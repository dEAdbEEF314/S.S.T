
# Contributing Guide (Human & AI)

This project is designed for **AI-assisted implementation**.

All contributors (human or AI agents) MUST follow this document.

---

# 🧭 Core Principles

1. **Accuracy over speed**
2. **No silent failure**
3. **Deterministic behavior**
4. **Spec-first implementation**
5. **Low-confidence → review (never guess)**

---

# 📚 Source of Truth

The following priority MUST be respected:

1. `docs/01_spec/*` (strict contract)
2. `docs/02_execution/*` (behavior rules)
3. `docs/03_ai/*` (AI decision rules)
4. `docs/00_overview/*` (context only)

If conflicts exist:
→ **Spec overrides everything**

---

# 🚫 Strict Prohibitions

## ❌ No Hallucination
- Never invent metadata
- Never assume missing fields
- Never “fill gaps” with guesses

## ❌ No Silent Fallback
- Every fallback must be logged
- Every degradation must be explicit

## ❌ No Spec Violation
- Do not change I/O formats
- Do not alter required fields
- Do not skip required steps

## ❌ No Hidden State
- Workers must remain stateless
- No implicit caching unless defined

---

# ✅ Required Behaviors

## Deterministic Processing
- Same input → same output
- No randomness unless explicitly allowed

## Explicit Failure Handling
- All failures must produce:
  - error log
  - status = "review" or "failed"

## Logging (Mandatory)
Each step MUST log:

- job_id
- track_id
- step
- result
- error (if any)

---

# 🔁 Retry Rules

- Only retry transient errors
- Use exponential backoff
- Respect retry limits from config

Never:
- Retry infinite times
- Retry deterministic failures

---

# 🧠 AI-Specific Rules

AI agents MUST:

- Follow `docs/03_ai/agent_prompt.md`
- Use dual-provider validation when enabled
- Respect confidence thresholds

### Decision Rules

| Condition | Action |
|----------|--------|
| High confidence | Accept |
| Medium confidence | Accept with warning |
| Low confidence | Send to review |

---

# 📦 Output Contract

All outputs MUST follow:

👉 `docs/01_spec/io_spec.md`

Requirements:

- Valid JSON
- All required fields present
- Paths must be valid
- No partial structures

---

# 🧪 Testing Requirements

Before merging:

- Validate JSON schema
- Test at least:
  - success case
  - fallback case
  - failure case

---

# 🧩 Code Style

- Language: Python 3.11+
- Stateless functions preferred
- Pure functions where possible
- Side effects must be explicit

---

# 🔀 Branch / Commit Rules

## Commit Message Format

```

[type] short description

Examples:
feat: add vgmdb client
fix: handle acoustid timeout
refactor: split pipeline step

```

## Rules

- One logical change per commit
- No mixed concerns
- Must be reproducible

---

# 🧱 Pull Request Rules

PR must include:

- What was implemented
- Which spec it follows
- Test results

---

# ⚠️ Failure Routing

If ANY of the following occurs:

- Confidence < threshold
- Data mismatch
- API inconsistency
- Tagging uncertainty

→ MUST route to:

```

status = "review"

```

---

# 🧠 Mental Model

Think like this:

> "If I am not sure, I am wrong."

---

# 🚀 Final Rule

Correctness is more important than:

- speed
- cost
- completeness

---

# End of Document
