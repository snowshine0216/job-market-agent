# Cheaper 5xx Retries — Master Spec

## Goal

Make per-page HTTP 5xx retries in `AsyncHttpClient` (`src/jma/sources/http.py`) cheaper.

## Problem (observed)

When `jma crawl --with-detail` hits a topic page that returns HTTP 500 (e.g. `https://testerhome.com/topics/43915`), `AsyncHttpClient.fetch` retries 4 times with exponential backoff `backoff_base_s ** attempts` = 2, 4, 8 seconds — ~14s of wall-clock time wasted on a single dead detail page. The user's run measured `elapsed=15.5s` for only 3 jobs, almost all of it spent retrying one terminal 500.

A 5xx on a single topic page is overwhelmingly "this resource is permanently broken on the server" rather than "transient, retry me" — TesterHome was returning 200 for everything else throughout. The aggressive retry budget belongs to 429 (rate-limit recovery), not 5xx.

## In scope

| # | Item | Brief |
|---|------|-------|
| 001 | cheaper-5xx-retries | Add a separate, smaller retry budget for 5xx. Keep 429's existing budget intact. |

## Out of scope

- Honoring `Retry-After` on 429 (current code uses `backoff_base_s ** attempts`, ignores header) — flagged as future work, separate fix.
- Per-source retry policy overrides — single project-wide knob is sufficient.
- Circuit-breaker / quarantine for repeatedly-failing URLs — beyond the scope of this fix.

## Constraints

- Backwards compatibility: existing `config/sources/*.yaml` files MUST continue to parse without modification. New retry knob defaults to a sensible value (1 retry for 5xx).
- 429 retry budget MUST remain at current value (`max_retries=3`) — this fix is asymmetric (5xx cheap, 429 unchanged).
- TDD: failing test BEFORE implementation. Tests must be fast (no real backoff sleep — use `_noop_sleep`).
- Domain rules unchanged: `domain/` stays pure; this is an effects-layer change in `sources/`.
