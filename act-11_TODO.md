# act-11 TODO: High-Efficiency Hybrid Logic

Objective: Fully optimize for high-limit models (Gemma 4 31B / Gemini 3.1 Flash Lite) by batching LLM requests and implementing strict programmatic gating.

## 1. LLM All-in-One Consolidation (Priority: Critical)
- [ ] **Refactor `llm.py`**: Remove track-by-track loops. Implement single-pass prompts that handle an entire album.
- [ ] **Update JSON Schema**: Extend schema to accept/return an array of all tracks in one go.
- [ ] **Implement Self-Evaluation**: Add `confidence_score` (0-100) and `confidence_reason` to the LLM response schema.

## 2. Pre-LLM Logic & Context Slimming
- [ ] **Local Cross-Validation**: Merge identical tags from multiple formats (e.g., MP3 & FLAC) into a single "Source B (Strong Evidence)" entry.
- [ ] **MBZ Candidate Scoring**: Implement the `a-f` scoring rules (Title, Format, No-Bandcamp, Track Count, Date matching) to filter MBZ results down to the best 1-3 candidates.
- [ ] **Deterministic Lock**: Directly apply Steam metadata (Dev, Pub, Year, URL) in `processor.py`, removing them from the LLM prompt.

## 3. Strict Routing & Validation
- [ ] **Confidence-Based Routing**: Automatically route to `review/` if `confidence_score < 80`.
- [ ] **Zero-Tolerance for Unknowns**: Post-LLM validation to route to `review/` if any mandatory field contains "Unknown" or "0".
- [ ] **Track Anchor Matching**: Use track numbers as primary keys for matching files to MusicBrainz entries during pre-processing.

## 4. Documentation & Maintenance
- [ ] Update `identification_strategy.md` to reflect the weighted source logic (A: Weak, B: Strong, C: Base Candidates).
- [ ] Verify `metadata.json` schema updates.
