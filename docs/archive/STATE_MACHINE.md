# STATE MACHINE

## States

INGESTED
IDENTIFIED
FINGERPRINTED
ENRICHED
TAGGED
STORED
FAILED

---

## Transitions

- **Standard Path:**
  INGESTED → IDENTIFIED (Candidates Found / VGMdb Primary Search)
  IDENTIFIED → FINGERPRINTED (AcoustID Verification Started)
  FINGERPRINTED → ENRICHED (AcoustID Verified / Fallback Success)
  ENRICHED → TAGGED
  TAGGED → STORED

- **Fast-track Path:**
  INGESTED → IDENTIFIED (VGMdb confidence >= 0.75 or MB verified)
  IDENTIFIED → ENRICHED (AcoustID Skipped)
  ENRICHED → TAGGED
  TAGGED → STORED

- **Failure Path:**
  ANY → FAILED (both source confidences < 0.55 or unrecoverable error)

---

## Retry Rules

- FAILED can be retried up to N times via Prefect mechanics.
- Retry state resumes from last successful task based on task cache/flow status.
