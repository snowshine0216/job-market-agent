# PR review verdict — Item 001 (URL freshness)

Verdict: PASS-WITH-NITS
Date: 2026-05-23
PR: https://github.com/snowshine0216/job-market-agent/pull/15
Reviewer: /code-review subagent (Sonnet 4.6)

---

## High-confidence findings

### Critical
- (none)

### Important
- (none)

### Minor

**M1 — `import sqlite3` inside `_apply_jobs_migrations` body** (`src/jma/storage/db.py:115`)
  The import is deferred inside the function. Currently harmless: `aiosqlite.OperationalError is sqlite3.OperationalError` (verified — they are the same class object, not a wrapper). But the placement is non-idiomatic; if a future aiosqlite release ever introduces its own exception hierarchy, the catch would silently stop catching. Prefer a module-level import, and log the failing statement before re-raising for easier diagnosis. Low urgency — no actual risk today.

**M2 — cache-hit `checked_at` is "now", not the cache's `fetched_at`** (`src/jma/sources/testerhome.py:182`)
  When `_fetch_classified` returns a cache hit (status_code=200), `_enrich_page` calls `datetime.now(UTC)` for `checked_at`. The actual fetch could have been up to 24h ago (cache TTL). The `CacheHit` struct carries `fetched_at` but `_ClassifiedFetch` does not surface it, so threading the timestamp through would require a `_ClassifiedFetch` field change. The effect: a URL that was truly fetched 20h ago gets `url_last_checked_at` stamped as "just now". Consequence is minor staleness in the reported `url_last_checked_at`, not a data-loss or correctness issue. Pre-existing cache plumbing; defer to a follow-up issue.

**M3 — `_apply_url_freshness` lives in `sources/testerhome.py` rather than `domain/`**
  The helper is pure (same inputs always yield same outputs, no I/O, no globals). The project's global CLAUDE.md states "Pure functions in `domain/`; effects live at the edges." However, the plan and ADR 0003 explicitly placed it in `testerhome.py` as a private module helper (`_apply_url_freshness`), motivated by the fact that it maps HTTP status codes — which are inherently a source-layer concept. Tests import it directly with `from jma.sources.testerhome import _apply_url_freshness`. The placement is defensible and intentional, but it is a conscious deviation from the stated convention. The ADR should note the exception explicitly; currently it only calls the helper "pure and stateless" without addressing the convention tension.

**M4 — `_apply_jobs_migrations` always commits even when all ALTERs are no-ops**
  On a freshly-created DB (where _DDL has already created the columns), every ALTER raises `OperationalError: duplicate column name`, gets swallowed, and then `conn.commit()` is called on a connection that saw no successful writes. This is harmless (committing an empty transaction is a no-op in SQLite), but it is conceptually impure. The /ship review noted this as a P2 adversarial point. If desired, track whether any ALTER succeeded and commit conditionally, or simply accept the harmlessness and document it.

---

## Specific questions from the review scope

### 1. 404/410 branch order in `_enrich_page` — is it correct?

**Yes, the re-ordering is correct and necessary.**

`blockage.classify()` maps any `status_code != 200` that isn't 429, 401, 403, or 5xx to `BlockStatus(kind=SourceStatus.ERROR)` (lines 44–45 of `domain/blockage.py`). This means `classify(404, ...)` returns `kind=ERROR`. The old code ran the `block.kind is not SourceStatus.OK` check before any status_code inspection; a 404 on a detail page would have triggered `halt = "detail block: error: ..."`, treating a routine "post deleted" outcome as a crawl-halting anti-bot block. Moving the `if page.status_code in (404, 410)` check BEFORE the `block.kind` check correctly short-circuits the false positive. The comment in the code explains this reasoning. Confirmed correct.

### 2. SQLite NULL semantics for the CASE clause

**Correct. NULL falls through to ELSE.**

In SQLite, `NULL IN ('live','gone')` evaluates to NULL (not FALSE). In a `CASE WHEN <condition> THEN ... ELSE ... END`, a NULL condition takes the ELSE branch. Verified empirically:

```python
conn.execute("SELECT CASE WHEN NULL IN ('live','gone') THEN 'overwrite' ELSE val END FROM t WHERE id=1").fetchone()
# → ('old',)  -- ELSE branch taken, prior value preserved
```

So if `excluded.url_status` were somehow NULL (which cannot happen given the column is `NOT NULL DEFAULT 'unknown'` and `UrlStatus.UNKNOWN.value` is always serialised as `'unknown'`), the ELSE branch would still correctly preserve `jobs.url_status`. The upsert logic is fail-safe. Confirmed correct.

### 3. `_apply_jobs_migrations` — "duplicate column name" error robustness

**Robust on tested versions; minor theoretical risk on old SQLite.**

The error message `"duplicate column name: <col>"` has been stable since SQLite 3.x. Verified on SQLite 3.51.0 (current macOS): message is exactly `"duplicate column name: val"`, and `.lower()` comparison works correctly. The `aiosqlite.OperationalError` is the same object as `sqlite3.OperationalError` (confirmed: `aiosqlite.OperationalError is sqlite3.OperationalError == True`), so the catch is correct. The only theoretical fragility: if SQLite ever changed the error message wording (historically it has not), the catch would re-raise, breaking `open_db` for existing databases. No action needed now; monitoring the SQLite changelog is sufficient.

---

## Strengths

- **Durable-signal model is sound end-to-end.** The two-place rule ("preserve prior on transient" in both `_apply_url_freshness` and the SQL `CASE` clause) is explicitly documented in ADR 0003, and both places have independent test coverage that would catch a divergence.
- **Thorough test pyramid.** 9 unit tests for `_apply_url_freshness` cover every status-code class including edge cases (fresh job with transient 429 keeps UNKNOWN+NULL, idempotency on repeat definitive outcome). DB round-trip and upsert-preservation tests in `test_db_migration.py` are clear and targeted. The pipeline e2e test locks the full crawl+storage durable-signal invariant.
- **Migration is idempotent and tested on both old-schema and fresh DBs.** The test uses an accurate pre-migration DDL snapshot, not a synthetic minimal table.
- **`_apply_url_freshness` is genuinely pure.** Returns the job unchanged for transient codes — no timestamp is written, so `url_last_checked_at=None` correctly stays None on a fresh job that hits a 429. The docstring accurately describes all three branches.
- **CLI `gone_urls=N` omission logic is correct.** Checking `any(j.url_last_checked_at is not None ...)` properly distinguishes "detail ran but found none gone" (show `gone_urls=0`) from "listing-only crawl" (omit segment). Three dedicated tests pin this behaviour.
- **CONTEXT.md glossary section is accurate and uses canonical glossary terms.** Correctly explains `unknown` as covering both "never verified" and "every attempt so far was transient."
- **ADR 0003 is thorough.** Records six considered alternatives with rejection rationale, including the non-obvious choice to treat 5xx as transient (not gone).
- **Placeholder count matches column count.** 33 columns, 33 `?` placeholders, 32 `DO UPDATE SET` clauses (all non-PK columns). Counted and verified.
- **All 140 tests pass, ruff clean.** Zero regressions.

---

## Comparison to inline /ship review (`items/001-review.md`)

### Overlapping findings (confirmed by this review)
- M1 (`import sqlite3` inside function body) — /ship review flagged as P1.4. Confirmed.
- M2 (cache-hit `url_last_checked_at` staleness) — /ship review flagged as P1.1. Confirmed, pre-existing.
- No DB CHECK constraint on `url_status` — /ship review flagged as P1.2. Confirmed absent, still a defense-in-depth nit.
- `_apply_jobs_migrations` always commits on no-ops — /ship review flagged as P2 adversarial. Confirmed harmless.

### New findings (not surfaced by /ship review)
- **M3** — `_apply_url_freshness` placement in `sources/` vs `domain/` violates stated CLAUDE.md convention. The /ship review did not call this out. It is a minor nit given the ADR's explicit justification, but worth noting for future contributors encountering the "pure functions in domain/" rule.

### /ship findings reclassified after PR-level review
- None. All /ship P1 findings remain P1 at this level. The pre-existing P0 candidate (silent network failure log level from issue #7) is correctly classified as pre-existing and does not block this PR.

---

## Verdict rationale

The implementation is correct across all three specifically-requested verification points (404/410 ordering, SQLite NULL semantics, migration error-message robustness). The test suite is comprehensive: unit, integration, storage round-trip, and pipeline e2e. The ADR correctly documents the design decisions and deferrals. All four "Minor" findings are nits or pre-existing issues — none introduce correctness risk or data loss.

Verdict: **PASS-WITH-NITS**. No blocker was found that the inline /ship review missed. The one new finding (M3, helper placement vs convention) is a documentation-level nit, not a bug.
