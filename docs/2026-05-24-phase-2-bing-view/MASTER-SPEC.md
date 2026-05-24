# MASTER-SPEC — Phase 2: Bing Aggregator + `jma view` + TesterHome Retirement

Mode: **spec** (single-task)
Date: 2026-05-24
Source spec: [docs/superpowers/specs/2026-05-23-phase-2-bing-aggregator-and-view-design.md](../../superpowers/specs/2026-05-23-phase-2-bing-aggregator-and-view-design.md) — copied verbatim to [items/001-spec.md](items/001-spec.md).

## IN scope

| # | Item | Why |
|---|------|-----|
| 001 | Phase 2 — Bing aggregator (SerpAPI), `jma view` static HTML, TesterHome retirement, per-Run `raw_payload_ref`, ADR-0005, doc/diagram refresh | This is the entire user-provided spec; spec mode has exactly one IN row by definition. |

The user-provided spec is internally cohesive — retirement + new source + view command + schema column + ADR + doc refresh form one ship, scoped around the acceptance demo in §8 (`jma crawl … && jma view --open`). Splitting it into sub-items would require backlog-mode decomposition that contradicts spec mode (one IN row, no per-item dependency scan).

## OUT scope

None. Spec mode does not classify OUT items at the run level. Items explicitly listed under "Out of scope (deferred)" in the source spec (§1) — Randstad, Playwright, LLM extraction, `sources status`, view filtering, direct BOSS, live SerpAPI in CI, Phase 2.1 detail-fetch — are deferred *within* the spec's narrative, not at the MASTER-SPEC layer. They will not be planned or implemented in this run; the plan phase must respect those exclusions verbatim.

## Acceptance criteria (from source spec §8)

```
$ export SERPAPI_KEY=...
$ uv run jma crawl --region Hangzhou --keywords "AI agent"
run_id        : <hex>
sources:
  bing       : ok    pages=5  jobs=180   elapsed=8.4s
written       : 180 observations to data/jobs.db

$ uv run jma view --open
wrote data/view.html (run <hex-prefix>, 180 observations)
# → browser opens, table sorts on click
```

## Verification surface

Non-web Python CLI. Post-ship verifier: **`/verify`** (not `/qa`). Entry-point smoke = invoking `uv run jma view --help` and `uv run jma crawl --help` to confirm CLI surface, plus the demo crawl-then-view flow above (live SerpAPI call requires `SERPAPI_KEY`; opt-in only). Unit tests (`uv run pytest`) cover everything verifiable without the network.
