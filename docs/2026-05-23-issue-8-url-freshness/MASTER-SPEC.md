# MASTER-SPEC — Issue #8 URL freshness

Source input: `docs/superpowers/plans/2026-05-23-issue-8-url-freshness.md` (single
ready-to-execute plan). Mode inferred from input shape: numbered Tasks, file paths,
exact `git commit` commands, expected pytest output per step — **plan mode**.

Issue: [snowshine0216/job-market-agent#8](https://github.com/snowshine0216/job-market-agent/issues/8)
Companion ADR: `docs/adr/0003-url-freshness-as-durable-signal.md` (currently
untracked on `main`; committed as part of the design-artifact commit at Phase 1).

## IN scope (this run)

| id  | item                                                                 |
|-----|----------------------------------------------------------------------|
| 001 | Detect stale TesterHome job URLs via new `url_status`, `url_last_checked_at` columns; surface `gone_urls=N` in `jma crawl` summary; durable-signal semantic per ADR 0003. |

N=1. Single-task plan mode: full per-item loop runs once.

## OUT of scope (explicitly deferred — captured from plan's "Out of Scope" section)

- Standalone `jma reprobe` command — track as a follow-up issue.
- Lowering `data_quality` for stale URLs — explicitly rejected (ADR 0003).
- Expanding `UrlStatus` beyond `live` / `gone` / `unknown` — separate ADR if needed.
- Broader "merge by confidence" upsert policy for `company` / `salary` / etc. —
  separate design conversation; mentioned in PR description.
- Second timestamp `url_last_attempt_at` distinguishing "never tried" from
  "tried but never definitive" — additive ALTER later if needed.

## Dependencies and assumptions

- **Depends on Issue #7** (`_enrich_page` detail-fetch loop). Issue #7 is **merged**
  on `main` at commit `f307226` — verified via `git log --oneline -5`.
- TesterHome detail config (`config/sources/testerhome.yaml`) already exists.
- `Job` pydantic model is frozen; all updates go through `model_copy(update=...)`.
- `pytest-asyncio` `auto` mode is already configured.
- No network during unit tests; live marker stays excluded.

## Acceptance criteria (from issue #8)

- Stale URLs detectable in the DB — covered by `url_status='gone'` query.
- `jma crawl` output summarises how many stored URLs were found stale — covered by
  `gone_urls=N` segment in the OK summary line, scoped to the current Run.
- Re-probe respects existing rate-limit config — covered: the detail-fetch loop
  reuses `self._cfg.rate.delay_ms` (no new HTTP path; freshness is computed from
  Issue #7's existing detail-fetch outcomes).
