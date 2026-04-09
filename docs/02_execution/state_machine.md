# State Machine

## States

- INGESTED
- IDENTIFIED
- FINGERPRINTED
- ENRICHED
- TAGGED
- STORED
- FAILED

---

## Transitions

Standard:
INGESTED → IDENTIFIED → FINGERPRINTED → ENRICHED → TAGGED → STORED

Fast-track:
INGESTED → IDENTIFIED → ENRICHED → TAGGED → STORED

Failure:
ANY → FAILED → review

---

## Rules

- No silent failures
- All transitions logged
