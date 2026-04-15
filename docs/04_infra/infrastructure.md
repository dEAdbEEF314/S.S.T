# Infrastructure

## Architecture: Multi-Container Strategy

The S.S.T system is designed as a set of **independent, decoupled Docker containers**. Each component must be able to run in isolation and communicate via network protocols (HTTP/S3/API).

## Storage Structure

```
sst/
├ ingest/
├ archive/
├ review/
└ processed/
```

---

## Components (Standalone Containers)

- **Docker / Docker Compose**: Standard orchestration for local/production environments.
- **Prefect**: Decoupled orchestration engine (Core).
- **SeaweedFS**: S3-compatible object storage (Storage).
- **SST Workers**: Scalable, stateless processing units.

---

## Design Principles

- **Independent Scaling**: Each container can be scaled horizontally depending on the load.
- **Isolation**: Failures in one container must not affect the health of others.
- **Stateless Workers**: Workers do not hold persistent local state.
- **Idempotent processing**: Rerunning a container on the same input produces the same output.

---

## Logging

Required fields for all containers:

- job_id
- track_id
- step
- result
- error

---

## Execution

- **Fully Container-based**
- Orchestrated by Prefect (or Docker Compose for simple setups)
- Managed via `uv` within containers for dependency consistency
