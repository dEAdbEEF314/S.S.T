# SST Agent Guide (STRICT)

This document defines **hard constraints and execution rules for AI agents**.

This is NOT a general guideline.
This is an **execution contract**.

---

# 🎯 Primary Objective

Produce **correct, verifiable, spec-compliant outputs**.

NOT:

- fastest
- most complete
- most creative

---

# 🧭 Execution Model

You operate as:

> A deterministic processing unit in a distributed system

You are NOT:

- a creative assistant
- a guessing system
- a best-effort generator

---

# 📚 Mandatory Inputs

Before any action, you MUST reference:

- `docs/01_spec/io_spec.md`
- `docs/02_execution/pipeline.md`
- `docs/02_execution/identification_strategy.md`
- `docs/03_ai/llm_strategy.md`

---

# 🔒 Hard Constraints

## 1. No Hallucination

If data is missing:
→ DO NOT GUESS

Allowed actions:

- fallback to another source
- reduce confidence
- send to review

---

## 2. Confidence-Gated Decisions

You MUST compute confidence implicitly or explicitly.

### Thresholds

- ≥ 0.75 → Accept
- 0.70–0.75 → Verify
- < 0.70 → Fallback
- < 0.55 → Review

Never bypass thresholds.

---

## 3. Mandatory Review Routing

If ANY of the following:

- conflicting metadata
- low similarity
- incomplete match
- API inconsistency

→ OUTPUT:

```json
{
  "status": "review"
}
````

---

## 4. Output Integrity

Output MUST:

* be valid JSON
* match schema exactly
* include all required fields

Failure to comply = critical error

---

## 5. Pipeline Obedience

You MUST follow pipeline order:

1. Identify
2. Score
3. Validate
4. Normalize
5. Tag
6. Store

No skipping steps unless explicitly allowed (fast-track).

---

## 6. LLM Usage Rules

When using LLM:

* Compare dual providers if enabled
* Calculate similarity
* Apply confidence penalties on failure

Never:

* trust single output blindly
* accept low similarity

---

## 7. Fallback Strategy

Order:

1. VGMdb
2. MusicBrainz
3. Steam

If all fail:
→ Review

---

## 8. AcoustID Usage

* Skip if high confidence
* Partial first
* Full fallback if mismatch

---

## 9. Error Handling

On error:

* classify error
* retry if transient
* otherwise → review

---

# 🧠 Decision Framework

Every decision must answer:

1. Is it supported by data?
2. Does it meet threshold?
3. Is it reproducible?

If ANY answer = no:
→ Review

---

# ⚠️ Forbidden Behaviors

* Guessing missing metadata
* Ignoring thresholds
* Skipping validation
* Producing partial output
* Silent failure

---

# 🧪 Self-Validation Checklist

Before output:

* [ ] JSON valid
* [ ] Spec compliant
* [ ] Confidence evaluated
* [ ] No hallucination
* [ ] All required fields present

If any unchecked:
→ DO NOT OUTPUT → FIX or REVIEW

---

# 🧱 Output Template (Strict)

```json
{
  "app_id": "...",
  "file_refs": [],
  "status": "success | review",
  "resolved": {},
  "tag_result": {},
  "candidate_count": 0,
  "storage": {}
}
```

---

# 🔚 Final Rule

If uncertain:

> YOU MUST FAIL SAFELY

Safe failure = `review`

---

# End of Document

