# 001 — Cheaper 5xx Retries

## Goal

Make per-page HTTP 5xx retries in `AsyncHttpClient` (`src/jma/sources/http.py`) cheaper.

## Acceptance criteria

1. A single URL returning HTTP 500 must NOT consume the full `max_retries=3` budget. The 5xx retry budget defaults to `1` (one quick retry, then return).
2. HTTP 429 retries are unchanged: still use `max_retries` (currently 3) with `backoff_base_s ** attempts` exponential backoff.
3. The 5xx retry budget is configurable via `RateConfig.max_retries_5xx` in `src/jma/sources/base.py`, with a default value that does NOT require updating existing `config/sources/*.yaml` files.
4. With `_noop_sleep` in tests, the new behavior is observable as a count of HTTP attempts in `FetchResult.attempts`: 5xx → `attempts <= max_retries_5xx + 1`, 429 → unchanged.
5. Full test suite remains green (`uv run pytest` → all 160 existing tests + new tests pass).
6. `ruff check` clean.
7. No domain-layer changes — fix lives entirely in `sources/`.

## Why the asymmetry (5xx cheap, 429 unchanged)

- **429** is "you're being rate-limited; back off and try again" — exponential retry with several attempts is appropriate; the budget allows the server to recover.
- **5xx** on a single resource path (e.g. `/topics/43915`) is overwhelmingly "this resource is permanently broken server-side" rather than "transient, retry me" — adjacent URLs return 200 throughout. A short budget (1 retry catches a true transient hiccup; more is just wasted wall-clock).

## Observed bug (motivating evidence)

```
2026-05-23 14:52:28  GET /topics/43915  HTTP/1.1 500
2026-05-23 14:52:30  GET /topics/43915  HTTP/1.1 500   (+2s)
2026-05-23 14:52:34  GET /topics/43915  HTTP/1.1 500   (+4s)
2026-05-23 14:52:42  GET /topics/43915  HTTP/1.1 500   (+8s)
elapsed=15.5s  jobs=3
```

~14s of the 15.5s total run was spent retrying one dead topic.

## Existing code (unchanged contract pinned for the planner)

- `src/jma/sources/http.py:43-56` — `AsyncHttpClient.fetch`: current logic is `should_retry = resp.status_code == 429 or resp.status_code >= 500` with uniform `max_retries`.
- `src/jma/sources/base.py:32-35` — `RateConfig`: pydantic frozen model, fields `delay_ms`, `max_retries`, `backoff_base_s`. Add `max_retries_5xx: int = 1` here.

## Out of scope

- Honoring `Retry-After` on 429.
- Per-source retry policy overrides.
- Circuit-breaker for repeatedly-failing URLs.
