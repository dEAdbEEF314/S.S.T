# Retry Strategy

## Formula

delay = base_delay * (factor ^ n)

---

## Example

- 2s → 4s → 8s

---

## Targets

- VGMdb
- MusicBrainz
- AcoustID

---

## Rules

- Retry only on transient errors
- Log all retries
- Stop after max attempts
