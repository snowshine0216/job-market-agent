# Run = one CLI invocation, recorded via a `run_jobs` join table

A [[Run]] is one `jma crawl` execution — every invocation is a new Run
regardless of inputs. The trend-delta feature (Phase 6) needs each
invocation to leave a permanent, queryable record of what it observed,
which forces a many-to-many relationship between Runs and
[[JobObservation]]s rather than a single FK on `jobs`.

`runs.id` is a UUID4. The `jobs` table has no `run_id` column; instead
a `run_jobs(run_id, job_id)` join table records membership. `INSERT OR
REPLACE` on `jobs` keeps "latest wins" semantics for the JobObservation
fields, while `INSERT OR IGNORE` on `run_jobs` preserves historical
membership.

## Considered options

- **`run_id` FK column on `jobs`** (the original spec shape). Rejected: `INSERT OR REPLACE` rebinds the column to the latest Run on every re-insert, destroying the historical "what did Run X see" answer Phase 6 depends on.
- **`runs.id = sha1(region|keywords|started_at.iso)[:16]`** (also original spec). Rejected: the hash is pretending to be deterministic when it isn't — `started_at` changes every invocation, so the hash is doing no dedup work. UUID4 communicates intent honestly.
- **Run = `(region, normalised_keywords)` plus date bucket.** Rejected: collapses legitimate same-day re-runs (e.g., morning was blocked, afternoon worked) into one row, losing the signal.
- **Append-only JobObservations across Runs** (each crawl writes new rows even if `id` repeats). Rejected: balloons row count, forces `MAX(fetched_at)` defensiveness in every aggregation. The join-table normalisation is cleaner.

## Consequences

- Phase 6 cross-run delta queries become a single LEFT JOIN against `run_jobs` — no `JSON_EXTRACT` or string parsing needed.
- "Most recent observation" for a JobObservation is still `jobs` (latest wins). "Set of observations a Run produced" is `run_jobs`. Read access patterns split cleanly between the two tables.
- `run_jobs` grows monotonically. Schema should index `(job_id)` as well as the natural `(run_id, job_id)` PK so "show me every Run that has seen Job X" stays cheap.
