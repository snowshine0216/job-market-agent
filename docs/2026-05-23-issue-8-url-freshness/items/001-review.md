# Review verdict — Item 001 (URL freshness)

Verdict: PASS-WITH-NITS
Date: 2026-05-23
Source: `/ship` workflow steps 8 (pre-landing parallel review) + 9 (adversarial)
PR: https://github.com/snowshine0216/job-market-agent/pull/15

## Reviewers dispatched

- `pr-review-toolkit:code-reviewer` — Sonnet
- `pr-review-toolkit:silent-failure-hunter` — Sonnet
- `general-purpose` (adversarial role) — Sonnet

## P0 findings (must-fix-before-landing blockers)

**None in this branch.**

One finding was classified P0 by the silent-failure-hunter:

> `src/jma/sources/testerhome.py:162-164` — `httpx.HTTPError` on detail fetch logged at DEBUG, masks systematic connectivity failures.

Triage: this is a **pre-existing** line added by Issue #7 (PR #14), not introduced by this PR's diff. The branch's behavioural contract is preserved (the upsert's CASE clause keeps `url_status=LIVE` when a network error occurs on a previously-verified row). Reclassified to P1 follow-up. Noted in the PR body's review-notes section so the user can decide whether to bundle a log-level fix into this PR or defer it.

## P1 findings (noted, do not block)

1. **Cache-hit timestamp staleness** — `_fetch_classified`'s cache branch returns `status_code=200`, then `_enrich_page` stamps `url_last_checked_at = datetime.now(UTC)`. The actual fetch could have been up to 24h ago (cache TTL). Threading `hit.fetched_at` through `_ClassifiedFetch` would fix it cleanly. Pre-existing cache plumbing; defer to a follow-up.
2. **No DB `CHECK` constraint on `url_status`** — defense-in-depth. The upsert's CASE clause already guards the write path.
3. **DEBUG log level on detail-fetch network errors** — see triage above (pre-existing).
4. **`import sqlite3` inside `_apply_jobs_migrations`** — fragile if aiosqlite ever wraps the exception. Move to module-level + log the failing statement before re-raise.

## P2 / adversarial notes (RISKS verdict)

- Concurrent `open_db` on the same DB file: idempotent thanks to duplicate-column swallow. Theoretical race, no breakage observed.
- `datetime.now(UTC)` called per-job rather than once per page: timestamps within a single batch differ by milliseconds. Harmless.
- `_apply_jobs_migrations` always commits even when both ALTERs are no-ops. Code-clarity issue.
- CLI `gone_urls=N` counts in-memory jobs from the current run, not DB-wide state. Documented in the test docstrings.

## Strengths

- Pure helper with idempotent transient branch (`_apply_url_freshness`). 9 dedicated unit tests cover every status-code class.
- Conditional upsert's CASE clause is fail-safe (NULL `excluded.url_status` falls through to `ELSE jobs.url_status`, preserving signal).
- End-to-end pipeline test confirms the durable-signal invariant through full crawl + storage round-trip.
- Migration is idempotent; tested on both pre-migration and already-migrated DBs.
- CONTEXT.md glossary section uses canonical [[JobObservation]] glossary terms and links the ADR.
- All commits follow the project's conventional-commit style.

## Verdict rationale

Three reviewers ran. Zero true P0 findings (the silent-failure-hunter's P0 was a pre-existing line). All P1s are pre-existing, low-impact, or defense-in-depth nice-to-haves. The adversarial reviewer's RISKS verdict explicitly notes "the conditional upsert logic is sound, migration idempotency is correct, and the freshness signal cannot be erased by a transient re-insert."

Verdict: **PASS-WITH-NITS**. Cleared for the autodev fix loop's exit contract.
