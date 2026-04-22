# LLM Strategy: Factual Metadata Organization

SST uses Large Language Models (LLMs) to consolidate and normalize metadata gathered from fragmented sources.

## 1. Core Principles

- **Zero Hallucination**: No inference allowed. Use "Unknown" for missing data.
- **Iterative Consolidation**: Processed track-by-track for scalability.
- **Summary-First Pass (Proposed)**: Before the iterative loop, send a global tracklist summary to the LLM to establish consistency for Artists and Disc counts.
- **Conflict Reporting**: If high-conflict metadata is detected, the LLM must summarize the conflicting information (URLs, mismatched fields) and route the album to the `review/` queue for the user.

## 2. Implementation: Multi-Model Compatibility

SST is designed to be model-agnostic. While Gemini 1.5 Pro is the recommended model due to its context window, any provider supporting the **OpenAI Chat Completions API** can be used, including:
- Google Gemini (via OpenAI proxy/compatibility layer)
- OpenAI GPT-4o
- DeepSeek / Groq / Local LLMs (if they expose an OpenAI-compatible endpoint)

## 3. Conflict Resolution & Review

When the LLM encounters a conflict it cannot resolve with high confidence:
1.  It generates a `conflict_report.json`.
2.  The report includes specific details: "MBZ Title: A vs. Steam Title: B", "Mismatched Artist URLs", etc.
3.  The album is moved to `review/` with this report attached, assisting the user's manual correction.

## 4. Priority & Weighting

Users can configure the weighting of metadata sources in the configuration:
`METADATA_SOURCE_PRIORITY=MBZ,STEAM,EMBEDDED` (Default)

The system treats matches differently based on their origin:
- **Confirmed**: Matches based on specific Digital Media formats and non-Bandcamp sources.
- **Weak**: Matches based on track count or date proximity only.
