# S.S.T Error Logs & Debugging History

This file documents significant errors encountered during development and testing, along with their root causes and solutions.

## [2026-04-17] Prefect 3.x API Change - Deployment Error
**Phase:** 10-Album Production Test (Core Execution)
**Error:** `prefect.exceptions.PrefectImportError: 'prefect.deployments:Deployment' has been removed.`
**Context:** During the `run_production_test.py` execution, the Core container attempted to import `Deployment` from `prefect.deployments` to register the main flow.
**Root Cause:** The `prefect` package installed via `uv` was version 3.x (latest). In Prefect 3.x, the old `Deployment.build_from_flow()` API has been completely removed in favor of `flow.deploy()` or `flow.serve()`.
**Solution:** 
- Removed the obsolete import `from prefect.deployments import Deployment`.
- Updated the `deploy()` function in `core/src/core/main.py` to use `sst_main_flow.deploy(name="sst-decentralized-deployment", work_pool_name="sst-worker-pool", image="sst-core:latest", build=False, push=False)`.

## [2026-04-17] NameError in Worker Prefect Task
**Phase:** 10-Album Production Test (Worker Execution)
**Error:** `NameError: name 'SteamMetadata' is not defined`
**Context:** The `process_single_album_task` mapped task failed on all items when attempting to initialize a `SteamMetadata` object for the `WorkerInput`.
**Root Cause:** During the refactoring of the worker code to expose the `@task` directly to Prefect, the import statement for `.models` was truncated and missed the `SteamMetadata` class.
**Solution:** 
- Re-added `SteamMetadata` to the `from .models import ...` statement in `worker/src/worker/main.py`.

## [2026-04-17] 10-Album Production Test Success
**Phase:** Full Production Pipeline Test
**Result:** `Success: 9, Review: 0` (Out of 10 limit, 1 was skipped/cached).
**Notes:** After resolving the `PrefectImportError` and the `SteamMetadata` `NameError`, the pipeline successfully processed a large batch of new soundtracks in parallel. The separation of Scout, Worker, and Core components functioned perfectly under load.

## [2026-04-18] Prefect 3.x Migration - .serve() Specification
**Error:** `TypeError: Flow.serve() got an unexpected keyword argument 'work_pool_name'`
**Root Cause:** In Prefect 3.x, `.serve()` directly hosts the flow and does not support `work_pool_name`.
**Solution:** Removed `work_pool_name` from the `.serve()` call in `core/src/core/main.py`.

## [2026-04-18] Starlette/FastAPI TemplateResponse Compatibility
**Error:** `TypeError: unhashable type: 'dict'` when accessing UI.
**Root Cause:** Newer versions of Starlette require the `request` object as the first positional argument or a keyword argument in `TemplateResponse`.
**Solution:** Updated `ui/src/ui/main.py` to use keyword arguments: `templates.TemplateResponse(request=request, name="index.html")`.

## [2026-04-18] Steam API 429 Rate Limiting
**Error:** HTTP 429 Too Many Requests during bulk scanning.
**Root Cause:** Rapid sequential requests to Steam Store API for metadata.
**Solution:**
- Implemented exponential backoff in `scout.scanner.SteamScanner` (1m, 3m, 5m, 10m).
- Added local caching (`scout_cache.json`) to minimize redundant API calls.
