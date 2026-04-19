# LLM Strategy

## Primary Role

- Formatting and normalization ONLY (e.g., standardizing language, removing "- OST" suffixes, correcting casing).
- **CRITICAL: LLM MUST NOT GUESS or invent missing metadata (artists, years, titles). If data is missing, the LLM must flag it for `review/`.**

---

## Dual Provider

- Primary
- Secondary

---

## Comparison

- similarity ≥ 0.8 → accept
- confidence ≥ 0.65 → accept
- < 0.6 → review

---

## Failure Handling

- One fails → fallback to other (penalty)
- Both fail → rule-based fallback
- Missing required data → route to review (No hallucination allowed)

---

## Targets

- Title normalization
- Artist normalization
- Album normalization

---

## Context Utilization

- **Directory Names**: LLM should use the `parent_dir` field as a secondary source of truth. Folder names like "CD1", "Disc 2", or "Bonus" provide high-confidence context for disc numbering and track categorization when embedded tags are missing.

---

## Rate Limiting & Quota Management

To prevent API errors and service bans (especially for providers like Gemini), the system implements a multi-tier rate limiting strategy:

- **RPM (Requests Per Minute)**: Local in-memory throttling per worker.
- **TPM (Tokens Per Minute)**: Local token estimation (1 token ≈ 4 characters) and throttling.
- **RPD (Requests Per Day)**: Global usage tracking using shared storage (S3).
- **Retry Mechanism**: Exponential backoff specifically for 429 status codes.
