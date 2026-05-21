# Job Market + Personal Fit Analyzer — Design Spec

**Date:** 2026-05-21
**Status:** Draft, pending user review
**Project:** `job-market-agent` (greenfield)
**Owner:** Harry

---

## 1. Purpose

A generalized CLI tool that, given a **region** and **keywords**, crawls job postings from multiple boards, normalizes them, and produces:

1. A **market report** (default) — salary distribution, popular roles, skill frequency, geo/seniority split, posting-volume trend. Usable with no LLM key.
2. A **personal fit report** (opt-in, when a complete user profile is supplied) — top matching jobs, skill gaps, per-posting match score, narrative summary.

Designed to be **usable by anyone**, not hard-coded to one user, region, or industry. Sources must **degrade gracefully** when individual boards block scraping.

---

## 2. Goals / Non-goals

**Goals (v1):**
- CLI tool, single-user, local.
- Required inputs: `--region`, `--keywords`. Optional: `--profile` (YAML, optionally seeded from resume).
- Pluggable source adapters; blocked sources do not fail the run.
- LLM-cost bounded even with hundreds of postings (map-reduce + retrieve-then-rerank).
- Reports in markdown and HTML (HTML embeds Plotly charts).

**Non-goals (v1):**
- Web UI or hosted service.
- Real-time monitoring or alerts.
- Recommending against specific employers.
- Multi-language UI (CLI is English; Chinese and English JD text are both supported in parsing).
- Applying to jobs or auto-tailoring resumes.

---

## 3. Architecture

```
CLI (typer)
  → Orchestrator
      → Source adapters [zhaopin, liepin, testerhome, randstad, search-fallback]
           (concurrent · per-source rate-limited · block-detecting)
        ↓ RawPosting[]
      → Normalizer (pure)            — salary parse, skill extract, dedup by hash
        ↓ NormalizedPosting[]  → SQLite cache
      → Statistical Analyzer (pandas, NO LLM)
        ↓ MarketStats
      → Market Report Renderer (markdown + HTML with embedded Plotly)
      → if --profile:
          → Profile Validator (completeness gate)
          → Resume Parser (LLM, one-shot, cached)
          → Candidate Retriever (embeddings + keyword overlap → top-K)
          → Batched Match Analyzer (LLM map-reduce, chunks of 10)
          → Fit Report Renderer
```

Design principles (carried over from user's global `CLAUDE.md`):

- Pure functions for all normalization, statistics, and scoring.
- I/O (crawling, LLM calls, file writes, DB) confined to thin adapter layers.
- Immutable data (`@dataclass(frozen=True)`); transforms return new values.
- Small focused modules, single-purpose files.

---

## 4. Tech stack

- **Language:** Python 3.11+.
- **CLI:** `typer`.
- **Crawling:** `httpx` for plain HTTP, `playwright` (headless Chromium with stealth) for JS-heavy boards.
- **Concurrency:** `asyncio` with per-source `aiolimiter` rate limits.
- **Data:** `pandas` for aggregation, `pydantic` for typed config and profile schema.
- **Storage:** SQLite (via `sqlite3` stdlib) for normalized postings + embedding cache; JSON files for raw HTML snapshots (debug aid).
- **Templating:** `jinja2` for markdown and HTML reports.
- **Charts:** `plotly` (HTML embed, no server).
- **LLM:** provider abstraction with adapters for DashScope, OpenAI, Anthropic. Default: DashScope (`qwen-plus`).
- **Testing:** `pytest`, `pytest-asyncio`, recorded HTTP fixtures (`pytest-recording` / VCR), golden files for prompts.

### Rationale (vs Node.js)
Python wins on (1) Playwright maturity for anti-bot scenarios, (2) pandas for statistics, (3) richer LLM SDKs. User's preferred FP discipline (`.mjs` style) is preserved through pure functions, frozen dataclasses, and isolated I/O — same principles, different syntax.

---

## 5. Source adapters

### 5.1 Adapter contract

```python
class SourceAdapter(Protocol):
    name: str
    requires_login: bool
    js_required: bool
    rate_limit_rps: float

    async def search(
        self, q: SearchQuery, ctx: CrawlContext
    ) -> SearchResult: ...

@dataclass(frozen=True)
class SearchQuery:
    region: str
    keywords: tuple[str, ...]
    max_pages: int

@dataclass(frozen=True)
class SearchResult:
    postings: tuple[RawPosting, ...]
    status: Literal["ok", "blocked", "partial", "error"]
    blocked_reason: str | None
    pages_fetched: int

@dataclass(frozen=True)
class RawPosting:
    source: str
    source_id: str
    fetched_at: datetime
    url: str
    raw_html: str          # or extracted block when full page is huge
    extracted: dict        # source-shape dict before normalization
```

### 5.2 Block detection signals

Any one of the following marks a source `blocked` (or `partial` if some pages succeeded before blocking):

- HTTP `403` / `429`.
- Redirect to a known login URL pattern.
- Page DOM contains captcha / verification markers (per-source matcher).
- Page title or body matches a configured "blocked" regex.
- Result count below a floor when the query should have many.
- Per-request timeout exceeded.

**On block:** record `blocked_reason`, log warning, continue with other sources. The orchestrator never raises on a single-source failure unless **all** sources fail (then exit code 3).

### 5.3 v1 source list

| Source       | Adapter type | Notes                                                                   |
|--------------|--------------|-------------------------------------------------------------------------|
| `testerhome` | `httpx`      | Scrape-friendly community board — Phase 0 reference adapter.            |
| `zhaopin`    | Playwright   | Likely needs stealth; Phase 1.                                          |
| `liepin`     | Playwright   | Likely needs stealth; Phase 1.                                          |
| `randstad`   | `httpx`      | Corporate site, generally friendlier.                                   |
| `search`     | `httpx`      | DuckDuckGo HTML fallback — query like `"AI Agent" jobs Hangzhou site:*`. Mines JD-bearing search result pages. |

51job, Boss直聘 and LinkedIn deferred to Phase 5 (heavy anti-bot / auth-walled).

---

## 6. Normalization

```python
@dataclass(frozen=True)
class NormalizedPosting:
    id: str                     # sha256(company|title|location|salary_signature)[:16]
    title: str
    company: str
    location: str
    salary: SalaryRange | None  # parsed; None if "面议" or unparseable
    seniority: Seniority | None
    skills: tuple[str, ...]     # extracted; ordered by first appearance
    jd_text: str                # cleaned plain text
    posted_at: date | None
    url: str
    source: str
```

- **Salary parser:** golden-fixture-driven. Handles `"15-30K"`, `"15-30K·14薪"`, `"$120k"`, `"120k-180k base"`, `"面议"` → `None`. Output normalized to `monthly_min_cny`, `monthly_max_cny`, optional `annual_multiplier` (e.g. `14`).
- **Skill extractor:** v1 keyword dictionary loaded from `data/skills.yaml` (Python, Java, AWS, Kubernetes, LangChain, etc.). Case-insensitive; whole-word match. v2 may swap to LLM-per-posting with cache.
- **Dedup:** by `id` hash. If two postings collide, keep the one with longer JD.

---

## 7. Hundreds-of-jobs strategy

User-flagged requirement: do not dump all jobs into one LLM call.

### 7.1 Layer 1 — no LLM for statistics

All stats computed via pandas/regex:

- Salary distribution: histogram with configurable buckets (default 5K CNY).
- Top roles: clustered by normalized title token signature.
- Skill frequency: from extracted skills list.
- Geo split: by `location`.
- Seniority split: parsed from title keywords.
- Posting volume: weekly counts when `posted_at` is available.

The market report is **fully usable at this layer** without an LLM key.

### 7.2 Layer 2 — map-reduce for narrative section

When LLM is enabled:

- **Map:** chunk normalized postings into groups of 20. Per-chunk prompt extracts `{role_archetypes, common_requirements, surprising_signals}` as JSON.
- **Reduce:** one final call merges chunk JSONs into the narrative section (`market_trends`, `notable_employers`, `emerging_skills`).
- **Total calls:** `ceil(N/20) + 1`. 100 postings = 6 calls.

### 7.3 Layer 3 — retrieve-then-rerank for fit

- **Embed once:** each normalized posting → embedding (cached by `id`).
- **Retrieve:** profile → query embedding; hybrid score = `α · cosine(query_emb, posting_emb) + (1-α) · jaccard(profile.skills, posting.skills)`. Default `α = 0.6`. Top-K candidates (default 50).
- **Rerank with LLM:** batches of 10, structured output:
  ```json
  {"posting_id": "...", "match_score": 0..100, "matched_skills": [...],
   "missing_skills": [...], "fit_rationale": "..."}
  ```
- **Summarize:** one final call produces `overall_fit_narrative`, `skill_gap_summary`, `recommended_next_steps`.
- **Total calls:** `ceil(K/10) + 1`. K=50 = 6 calls.

### 7.4 Cost guardrails

- Per-run budget USD in config (default `1.0`).
- Batching helper tracks running cost; aborts mid-run if budget exceeded and emits a partial report with what was processed.
- Report footer always shows: sources used (with status), LLM calls made, estimated cost.

---

## 8. Profile completeness gate

### 8.1 Schema

```python
class Profile(BaseModel):
    # required for `jma fit`
    years_experience: int
    current_or_target_roles: list[str] = Field(min_length=1)
    skills: list[str] = Field(min_length=3)

    # optional, quality-boosting
    current_salary: SalaryRange | None = None
    seniority: Seniority | None = None
    industry_preferences: list[str] = []
    location_preference: str | None = None
    resume_text: str | None = None
```

### 8.2 Behavior

- `jma fit` calls `validate(profile)` **before** any crawling or LLM call.
- If required fields missing → print exactly which fields are missing, suggest `jma profile init --resume <path>`, exit code 2.
- If `resume_text` is provided and other fields are sparse → one LLM call extracts them into the profile, then re-validates. Result is written back to the YAML file (with a `# auto-extracted` comment) so future runs skip the LLM call.

---

## 9. CLI surface

```
jma market   --region "Hangzhou" --keywords "AI Agent,LLM" \
             [--sources s1,s2] [--limit 200] [--no-cache] [--output report.html]

jma fit      --region ... --keywords ... --profile profile.yaml \
             [--top-k 50] [--output fit.html]

jma profile  init [--resume resume.pdf]      # interactive; writes profile.yaml
jma profile  validate profile.yaml

jma sources  list                            # show registered sources + last status
jma cache    clear
jma config   show
```

**Exit codes:** `0` ok · `1` runtime error · `2` profile incomplete · `3` all sources blocked.

---

## 10. Configuration

`~/.jma/config.yaml`:

```yaml
llm:
  provider: dashscope          # or openai | anthropic
  model: qwen-plus
  api_key_env: DASHSCOPE_API_KEY
  embedding_model: text-embedding-v2
  per_run_budget_usd: 1.0

sources:
  zhaopin:    { enabled: true,  rate_limit_rps: 0.3 }
  liepin:     { enabled: true,  rate_limit_rps: 0.3 }
  testerhome: { enabled: true,  rate_limit_rps: 1.0 }
  randstad:   { enabled: true,  rate_limit_rps: 1.0 }
  search:     { enabled: true,  engine: duckduckgo }

crawl:
  max_pages_per_source: 5
  timeout_s: 30
  user_agent_pool: [ "Mozilla/5.0 ...", ... ]

cache:
  ttl_hours: 24
  dir: ~/.jma/cache
```

---

## 11. Module layout

```
job-market-agent/
├── pyproject.toml
├── src/jma/
│   ├── cli.py                 # typer entrypoint
│   ├── orchestrator.py
│   ├── sources/
│   │   ├── base.py            # SourceAdapter Protocol, dataclasses
│   │   ├── registry.py
│   │   ├── testerhome.py
│   │   ├── zhaopin.py
│   │   ├── liepin.py
│   │   ├── randstad.py
│   │   └── search.py
│   ├── normalize/
│   │   ├── posting.py
│   │   ├── salary.py
│   │   ├── skills.py
│   │   └── dedup.py
│   ├── analyze/
│   │   ├── market.py          # pandas aggregations
│   │   ├── retrieve.py        # embeddings + keyword hybrid
│   │   └── fit.py             # LLM map-reduce match
│   ├── profile/
│   │   ├── schema.py
│   │   ├── validator.py
│   │   └── resume_parser.py
│   ├── llm/
│   │   ├── client.py          # provider abstraction
│   │   ├── batching.py        # chunked map-reduce + cost ceiling
│   │   └── prompts/           # versioned .txt files
│   ├── render/
│   │   ├── market_report.py
│   │   ├── fit_report.py
│   │   └── templates/         # jinja2 .md.j2 + .html.j2
│   ├── storage/
│   │   ├── cache.py           # raw HTML cache
│   │   └── db.py              # sqlite for normalized postings + embeddings
│   └── config.py
├── data/
│   └── skills.yaml            # keyword dictionary for skill extractor
└── tests/
    ├── unit/                  # pure-function tests, fast
    ├── adapters/              # recorded-fixture tests per source
    ├── integration/           # end-to-end with fixture sources
    └── llm/                   # prompt regression goldens
```

Module size guideline: ≤ 200 lines per file; pure-function modules preferred over classes.

---

## 12. Build phases

User-emphasized priority: **prove job search works first**, then layer on intelligence.

### Phase 0 — Skeleton + one known-good source
- `pyproject.toml`, typer CLI scaffold, config loader.
- `testerhome` adapter (scrape-friendly).
- Normalizer (salary, skills v1), SQLite cache, dedup.
- `jma market --region Hangzhou --keywords "AI Agent"` returns normalized rows and prints a summary table.
- **No LLM yet.**
- Tests: adapter with recorded fixtures, normalizer/dedup unit tests.
- **Exit criterion:** running the command produces real data from `testerhome`.

### Phase 1 — Source resilience
- Playwright adapter for one harder source (whichever of `zhaopin`/`liepin` responds best to stealth).
- Block-detection signals + per-source status reporting.
- DuckDuckGo search-fallback adapter.
- 3+ sources concurrent, per-source rate-limited.
- **Exit criterion:** a blocked source still produces a partial report with clear status.

### Phase 2 — Market report (no LLM)
- Pandas stats: salary buckets, top skills, role types, geo, top companies, weekly volume.
- Jinja markdown + HTML templates with embedded Plotly charts.
- **Exit criterion:** fully usable report without an LLM key.

### Phase 3 — LLM batched narrative
- LLM provider abstraction + DashScope adapter.
- Map-reduce chunker → narrative section.
- Per-run budget guard.
- **Exit criterion:** narrative section appears in report; cost matches estimate within 20%.

### Phase 4 — Profile + fit
- Profile schema, validator, resume parser.
- Embedding cache, retrieve-then-rerank.
- Fit report renderer.
- **Exit criterion:** complete profile produces a fit report; incomplete profile exits with the missing-field list.

### Phase 5 — Polish
- Additional sources (Indeed / LinkedIn via search; 51job; Boss直聘 if feasible).
- Swap skill-extraction dictionary → LLM-per-posting with cache if dictionary quality plateaus.
- Better dedup heuristics (cross-source same-job collapse).
- Internationalization of region parsing.

---

## 13. Testing strategy

- **Pure unit:** normalizer (salary, skills), dedup, profile validator, stats aggregations, batching cost-ceiling logic. Fast, no I/O, no mocks.
- **Adapter:** recorded HTTP/Playwright fixtures replayed in CI. Live smoke tests gated behind `JMA_LIVE=1` for manual runs.
- **Integration:** end-to-end with fixture sources → assert report sections render and contain expected anchors.
- **LLM:** prompt regression on golden inputs; batching helper has a hard cost-ceiling assertion (test fails if a prompt change pushes cost above bound).
- **No mocking of SQLite** — use real tmp directories.

TDD discipline per user's global `CLAUDE.md`: write failing test first, minimum code to pass, refactor green.

---

## 14. Risks

| # | Risk | Mitigation |
|---|------|------------|
| 1 | Sources block scraping | Multi-source + graceful degradation + search fallback. Documented as known limitation. |
| 2 | Salary string variety (`"15-30K·14薪"`, `"面议"`, `"$120k+equity"`) | Golden-fixture-driven incremental coverage; unparseable → `None`, reported separately. |
| 3 | Skill-extraction quality (dictionary misses) | Start with curated dict; swap to LLM extraction (cached) in Phase 5 if needed. |
| 4 | LLM cost overrun | Per-run budget + mid-run abort with partial report. Cost surfaced in report footer. |
| 5 | Generalization beyond CN market | v1 is CN-heavy; Phase 5 adds international boards via search fallback. |
| 6 | Anti-bot countermeasures evolve | Adapter fixtures get stale; CI live-smoke job (weekly) flags regressions. |

---

## 15. Open questions deferred to "user picture" pass

These are the questions the user asked to defer; they belong to the profile-design pass, not the market-pipeline design:

- Exact profile YAML schema beyond required fields.
- Resume parser prompt details (CV layouts, internationalization).
- How to weight `current_salary` and `seniority` in the fit score.
- Whether to surface "stretch" vs "safe" job tiers in the fit report.

---

## 16. Acceptance criteria for v1 (Phases 0–4 shipped)

- `jma market --region X --keywords Y` runs end-to-end against ≥3 sources, produces a markdown + HTML report, degrades gracefully when any source is blocked.
- `jma fit --region X --keywords Y --profile p.yaml` produces a fit report when the profile is complete; exits 2 with a clear missing-field message when incomplete.
- 100 postings ≤ 10 LLM calls for the market narrative; 50 fit candidates ≤ 6 LLM calls for fit analysis.
- All pure-function modules covered by unit tests; each source adapter has at least one recorded-fixture test.
- LLM cost is bounded by config and never silently exceeded.
