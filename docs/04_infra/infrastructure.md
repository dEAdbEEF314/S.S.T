# Infrastructure

## Storage Structure

```

sst/
├ ingest/
├ archive/
├ review/
└ processed/

```

---

## Components

- Docker
- Prefect
- SeaweedFS

---

## Design Principles

- Stateless workers
- Idempotent processing
- Horizontal scalability

---

## Logging

Required fields:

- job_id
- track_id
- step
- result
- error

---

## Execution

- Container-based
- Orchestrated by Prefect
