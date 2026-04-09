# LLM Strategy

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

---

## Targets

- Title normalization
- Artist normalization
- Album normalization
