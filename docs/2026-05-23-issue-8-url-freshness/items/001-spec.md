# 001 — URL freshness durable signal

Plan mode: spec phase is pre-completed (the user authored the plan inline, and
ADR 0003 records the design decisions). This file is a thin index pointing at
the actual artifacts.

## Goal

Make stale TesterHome job URLs detectable in the DB without ever erasing prior
evidence. Add `url_status: UrlStatus(StrEnum)` and `url_last_checked_at: datetime | None`
to `Job` + `jobs`, populate them from the Issue #7 detail-fetch path, surface
`gone_urls=N` in the `jma crawl` summary when detail ran.

## Authoritative sources

- Plan: `items/001-plan.md` (verbatim copy of user input)
- Design rationale: `docs/adr/0003-url-freshness-as-durable-signal.md`
- Issue: [snowshine0216/job-market-agent#8](https://github.com/snowshine0216/job-market-agent/issues/8)
