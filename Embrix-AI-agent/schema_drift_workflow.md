# Workflow: Automatic Schema Drift Check & Sync

**Target agent:** Gemini 3.6 Flash / Gemini 3.1 Pro, running inside Antigravity IDE
**Target project:** Embrix
**Depends on:** `nl2sql_validation_plan.md` (Phases 1, 2, and 4 must exist before this workflow can be wired in)

---

## Why not "check on every connection"

Before implementing: if Embrix uses a connection pool (standard with FastAPI + SQLAlchemy/asyncpg/psycopg), a single incoming user request can open/reuse a pooled connection many times per minute. Running full schema introspection on every connection event would:

- Add latency to every request for a check that's almost always a no-op (schema rarely changes second-to-second).
- Hit `information_schema` repeatedly under load, which is unnecessary DB load.

Instead, this workflow checks drift at three specific moments — startup, on a schedule, and reactively on validation failures — which covers the same goal ("agent always has an up-to-date schema") at a fraction of the cost. If your actual use case is closer to "a long-running desktop/CLI agent that opens a fresh connection per session, infrequently" (rather than a pooled web service), the startup + reactive triggers alone are sufficient and you can skip the scheduled one.

---

## Trigger 1: Startup Check (pool/session initialization)

**When:** Once, when the DB connection pool is first created — i.e., in Embrix's FastAPI startup event / lifespan handler, not per-request.

### Steps

1. In the FastAPI app's startup hook (`@app.on_event("startup")` or the `lifespan` context manager — check which pattern Embrix already uses and match it), call:
   ```python
   from embrix.schema_store.drift_sync import check_drift

   async def on_startup():
       drift_detected = await check_drift()
       if drift_detected:
           log.info("Schema drift detected at startup — snapshot resynced.")
   ```
2. This should block startup until the check completes (it's cheap — metadata-only query) so the very first NL-to-SQL request after a restart is guaranteed to use a current schema.
3. If `check_drift()` fails (DB unreachable, permissions issue), log the error clearly but do not crash app startup — fall back to the last-known `schema_snapshot.json` and log a visible warning that it may be stale.

**Done when:** Restart the service after manually altering a table; confirm the startup log shows drift detected and the snapshot updated before any request is served.

---

## Trigger 2: Scheduled Background Check

**When:** Every N hours while the service is running. Skip this trigger entirely if Embrix is a short-lived/CLI-style agent rather than a long-running server.

### Steps

1. Use whatever job scheduler is already in the Embrix stack. If none exists, add `APScheduler` (lightweight, in-process, no extra infra):
   ```python
   from apscheduler.schedulers.asyncio import AsyncIOScheduler

   scheduler = AsyncIOScheduler()
   scheduler.add_job(check_drift, "interval", hours=1)
   scheduler.start()
   ```
2. Pick the interval based on how often this specific DB actually changes — hourly is a reasonable default during active development; stretch to daily once the schema stabilizes. Don't hardcode this; make it a config value (`SCHEMA_DRIFT_CHECK_INTERVAL_HOURS`) so it can be tuned without a code change.
3. Log every scheduled check's result at debug level (even "no drift found") so there's a record the job is actually running, not just silent.

**Done when:** Leave the service running across the interval boundary with no manual schema change; confirm a debug log entry appears showing "checked, no drift" at the expected time.

---

## Trigger 3: Reactive Check (validation-failure driven)

**When:** The Query Auditor (from `nl2sql_validation_plan.md` Phase 3) logs 2+ EXPLAIN validation failures referencing the same table/column within a short window (e.g. 5 minutes). This is the fastest way to catch drift — faster than any fixed schedule — because it's driven by an actual symptom.

### Steps

1. In the Query Auditor's failure-logging path, track failures in a short-lived counter (in-memory dict or Redis if Embrix already has it) keyed by `(table_name, error_type)`.
2. When a key crosses the threshold (2 failures in 5 minutes), immediately call `check_drift()` out-of-band (don't block the current request on it — fire it as a background task, but do let the *current* retry loop know a check is in flight so it doesn't retry against a stale snapshot).
3. If drift is confirmed for that table, update the snapshot, then let the Query Auditor's existing retry loop (already capped at 2 attempts) pick up the corrected schema on its next attempt.
4. Surface a one-line status to the user in this case specifically (not for the startup/scheduled triggers, which should stay silent unless something's wrong): e.g. "Schema for `orders` was just updated — retrying your query with the new structure." This is the one moment where drift is directly affecting the user's current request, so it's worth surfacing.

**Done when:** Manually rename a column while the service is running, ask a query that references the old name twice in a row, and confirm: (a) drift is detected within the reactive window, (b) the snapshot updates without a restart, (c) the user sees the one-line status message, (d) the corrected query succeeds.

---

## Putting it together — decision flow

```
Service starts
   → Trigger 1 fires → snapshot guaranteed fresh at boot
   ↓
Service runs
   → Trigger 2 fires every N hours → catches slow/quiet drift
   → Trigger 3 fires on repeated validation failures → catches drift the moment it bites a real query
```

All three triggers call the same underlying `check_drift()` function from Phase 4 of the validation plan — this workflow only adds the calling logic and timing, not new drift-detection logic. Do not duplicate the diffing logic here; if `check_drift()` doesn't exist yet, build it in `nl2sql_validation_plan.md` Phase 4 first.
