# SST Codebase Audit Report (Against SST.md)

**Date**: 2026-04-27
**Status**: Action Required

This document identifies contradictions between the current implementation and the "Single Source of Truth" (`docs/SST.md`).

## 1. Identified Contradictions (IMPLEMENTATION VS SPEC)

### 1.1 Scoring Gate Inconsistency
- **Spec (SST.md 2.2)**: Ranks 80-90% MUST be `REVIEW`. Only >= 95% is `ARCHIVE`.
- **Code (`processor.py`)**: Currently uses `conf_score < 80` to trigger review.
- **Action**: Change threshold to `conf_score < 95`.

### 1.2 "Dirty Tags" (Number-in-Title) Guard
- **Spec (SST.md 2.2)**: Dirty tags MUST force `REVIEW`.
- **Code (`processor.py`)**: No explicit programmatic check for numbers in titles during the final validation loop.
- **Action**: Implement regex check in validation loop: if title starts with `\d+ - ` or similar, force `REVIEW`.

### 1.3 Audio Warning Enforcement
- **Spec (SST.md 3.1)**: Any FFmpeg warning MUST force `REVIEW`.
- **Code (`processor.py`)**: Implementation is partial/unstable due to indentation issues in the last update.
- **Action**: Ensure `any_audio_warnings` strictly sets `status = "review"`.

---

## 2. Missing Definitions (NEED REFINEMENT IN SST.md)

### 2.1 Parent Game Fallback
- **Issue**: How to populate `COMM` (Comment) when `parent_app_id` is missing?
- **Proposal**: If no parent exists, use Soundtrack's own AppID/Name.

### 2.2 Date Conflict Resolution
- **Issue**: If Steam (Locked) and MBZ (Base) dates differ significantly.
- **Proposal**: Steam date is `LOCKED`, but allow LLM to flag for `REVIEW` if the gap is > 2 years.

---

## 3. Immediate Implementation Tasks (Act-13 Final)
1. Fix confidence threshold (95% rule).
2. Implement "Dirty Tag" detection in validation loop.
3. Stabilize audio warning status logic.
4. Update `SST.md` with missing fallback definitions.
