# Job Market + Personal Fit Analyzer — Plan

> Greenfield CLI that, given a region and keywords, crawls job postings,
> produces a market-overview report, and (when a user profile is supplied)
> produces a personalised fit report with match percentages and skill gaps.
>
> Date: 2026-05-21 · Status: pre-implementation, plan locked

---

## 1. Investigation trail

Each decision was resolved one branch at a time. The table below records the
question, why it mattered, the options considered, and the choice made — so we
do not relitigate later.

| # | Branch | Why it matters | Options weighed | Decision |
|---|---|---|---|---|
| 1 | Stack | Gates scraping libs, LLM SDK, packaging | Python 3.12 + uv · Node ESM · Go | **Python 3.12 + uv** |
| 2 | v1 sources | Determines crawl mechanism, blockage budget, realism of "comprehensive view" | Lean (2 readable + 1 aggregator) · Aggressive (5+ boards) · Search-engine only | **Lean: Bing-aggregator (SerpAPI) via pluggable `JobSource`. TesterHome retired in Phase 2 (volume too low for AI-eng market stats); Randstad deferred.** |
| 3 | Fetch stack | Binary size, container needs, graceful degradation on blockage | httpx-first + Playwright fallback · Playwright everywhere · httpx-only | **httpx + selectolax default; Playwright opt-in via per-source flag** |
| 4 | Search API | Cost/quota, China-language coverage | Bing · Brave · SerpAPI · Pluggable+Bing | **SerpAPI (Bing engine; native Bing v7 retired 2025-08-11)** |
| 5 | Pipeline | "Don't spam the LLM" constraint — token cost, latency, scalability | 3-stage rules+LLM · One mega-call · Map-reduce LLM · Pure deterministic | **3-stage: rules-first extraction → deterministic pandas aggregation → ONE narrative LLM call** |
| 6 | Storage | Re-run idempotency, crash recovery, trend analysis | SQLite + raw blobs · JSON-only · DuckDB · In-memory | **SQLite (`data/jobs.db`) + gzipped raw blobs (`data/raw/`); 24h URL-hash cache** |
| 7 | Blockage detection | Hard v1 requirement: detect & continue, never fail | Structured `SourceResult` hybrid · Status-only · Active probe | **`SourceResult { status, jobs, reason, pages_fetched }`; hybrid HTTP+content+empty detection** |
| 8 | Crawl limits | Politeness, LLM cost, run time | Bounded+polite+dedup · Unbounded · Bounded no-dedup | **`--max-jobs 300`, per-source `max_pages 5`, `concurrency 4`, `delay_ms 800`, exp-backoff on 429, dedup by `sha1(title+company+city)`** |
| 9 | LLM provider | Cost, Chinese quality, ergonomics | DashScope (qwen) · OpenAI · DeepSeek · LiteLLM-pluggable | **DeepSeek-chat for both stages** (single OpenAI-compatible client) |
| 10 | Skills extraction | Drives both top-skills stats and fit-match precision | Hybrid LLM+YAML · Free-form · Strict controlled vocab | **LLM extracts free-form → canonicalize via `data/skills.yaml`; both forms stored; unmapped logged** |
| 11 | Profile sufficiency | Avoid LLM spend on empty profiles; clear UX for "need more" | Two-tier (deterministic min → LLM enrich) · Pure LLM · Strict structured | **Tier 1: must have role + years + ≥3 skills. Tier 2: LLM returns persona with `confidence_score`; <0.6 → stop & ask** |
| 12 | Fit scoring | Match % at scale without spamming LLM | Deterministic-all + LLM-top-N · LLM-per-job · Deterministic-only | **Weighted score on ALL jobs (skills .50 / exp .20 / salary .15 / loc .10 / seniority .05); one LLM call refines top-30** |
| 13 | CLI | Re-runnability, scriptability | Subcommands+`run` · Single command · REPL | **Typer subcommands: `crawl`, `report market`, `report fit`, `sources status`, `run`** |
| 14 | Region/keyword input | Multi-language search recall | Free text + alias map · ISO-structured · Free-text-only | **Free text + bundled `data/region_aliases.yaml` for multilingual expansion** |
| 15 | Output | Render targets, deps weight | Markdown + JSON sidecar · Rich+md · HTML+SVG | **Markdown primary + `data.json` sidecar; lang derived from region, `--lang` overrides** |
| 16 | Trend | "Trend" requested but only snapshot data exists | Freshness histogram + cross-run delta · Snapshot-only · LLM-extrapolated | **Posting-age histogram always; cross-run deltas when prior runs of same `(region, keywords)` exist** |
| 17 | Resume formats | Adoption vs deps | md+txt+pdf · md+txt only · +docx | **`.md` / `.txt` / `.pdf` via `pypdf`; image-PDF fails loudly** |

---

## 2. Architecture at a glance

```
                       ┌──────────────────────────┐
   region, keywords ──►│      jma crawl           │
   (+ profile.yaml)    │                          │
                       │  TesterHome  Randstad    │
                       │       Bing-aggregator    │
                       │  (httpx | Playwright)    │
                       │  ── SourceResult per ─►  │
                       └────────────┬─────────────┘
                                    │ persists
                                    ▼
                       ┌──────────────────────────┐
                       │   SQLite + raw/*.gz      │  ◄── 24h URL cache
                       └────────────┬─────────────┘
                                    │
                                    ▼
                       ┌──────────────────────────┐
                       │   Stage 1: extract       │  parallel, bounded
                       │   • rules → cheap fields │  (concurrency 4)
                       │   • DeepSeek → skills,   │
                       │     seniority, work-mode │
                       └────────────┬─────────────┘
                                    ▼
                       ┌──────────────────────────┐
                       │ Stage 2: aggregate (py)  │  deterministic
                       │   stats, histograms,     │  pandas
                       │   TF-IDF role clusters   │
                       └─────┬──────────────┬─────┘
                             │              │
                             ▼              ▼
                  market.md (narrative)   fit.md (top-30 refined)
                  ── ONE LLM call ──      ── ONE LLM call ──
```

I/O is concentrated in `sources/`, `llm/`, `storage/`, `profile/`, `report/`.
`domain/` is pure — every function is deterministic, no network, no mutation.

---

## 3. Module layout

```
job-market-agent/
├── pyproject.toml
├── PLAN.md                              ← this file
├── data/
│   ├── skills.yaml                      # synonym → canonical (~300 entries)
│   ├── region_aliases.yaml              # city → multilingual variants
│   ├── sources/
│   │   └── bing.yaml
│   └── jobs.db                          # gitignored
├── src/jma/
│   ├── cli.py                           # typer wiring only
│   ├── domain/                          # PURE; no I/O
│   │   ├── models.py
│   │   ├── normalize.py                 # salary / exp / location parsers
│   │   ├── dedup.py
│   │   ├── stats.py
│   │   ├── skills.py
│   │   └── scoring.py
│   ├── sources/
│   │   ├── base.py                      # JobSource protocol + SourceResult
│   │   ├── http.py                      # httpx + hybrid blockage classifier
│   │   └── bing.py                     # Phase 2: SerpAPI-backed aggregator
│   ├── llm/
│   │   ├── client.py                    # DeepSeek (OpenAI-compatible), retries, disk cache
│   │   ├── extract.py                   # per-job structured fields
│   │   ├── narrate.py                   # market narrative (1 call)
│   │   ├── persona.py                   # tier-2 user picture
│   │   └── fit.py                       # top-N refinement
│   ├── storage/{db,cache,runs}.py
│   ├── pipeline/{crawl,extract,market,fit}.py
│   ├── profile/ingest.py
│   └── report/
│       ├── view.py                                          # Phase 2: jma view
│       ├── render.py                                        # Phase 4+
│       └── templates/{view.html.j2, market_en.j2, market_zh.j2, fit_en.j2, fit_zh.j2}
└── tests/                                # mirrors src/jma
    ├── domain/                           # pure, no mocks
    ├── sources/                          # fixture HTML, respx for HTTP
    └── llm/                              # FakeLLM returning canned JSON
```

---

## 4. Phased build with real-case justification

Per the user's instruction: **job-search must work end-to-end before anything
else.** TDD red-green-refactor each step. Each phase below carries one concrete
real-world case that justifies the design.

### Phase 0 — Foundation · ½ day

Bootstrap: `uv init`, `ruff`, `pytest`, `pydantic`. Land `domain/models.py`
with `Job`, `Profile`, `SourceResult`, `MarketReport`, `FitReport` dataclasses
+ unit tests.

**Real case — the `Job` schema must survive heterogeneity.**
A single TesterHome post might say "20-40K·15薪 / 杭州余杭 / 3+yr / Python+LangChain";
a Bing-snippet "AI 工程师 - 杭州 - 阿里巴巴 - 15-30K"; a Randstad listing might
have salary `"Competitive"` and no posted-at date. The model must accept all
three without raising:

```python
Job(
    id="sha1:...", source="testerhome",
    title="AI Agent 工程师", title_raw="【急招】AI Agent 工程师",
    company="某AI创业公司",
    location=Location(country="CN", city="Hangzhou", district="余杭",
                      work_mode=WorkMode.UNKNOWN),
    salary=Salary(min=20000, max=40000, currency="CNY",
                  period=SalaryPeriod.MONTHLY, months_per_year=15,
                  raw="20-40K·15薪", parsed=True),
    experience=Experience(min_years=3, max_years=None, raw="3年以上"),
    skills_raw=["Python", "LangChain"], skills_canonical=[],
    seniority=Seniority.UNKNOWN, posted_at=None,
    fetched_at=datetime.utcnow(), raw_payload_ref="raw/testerhome/abc.html.gz",
)
```

`salary.parsed=False` with non-null `raw` is the contract for "面议".
Every downstream stat must tolerate it.

---

### Phase 1 — Job search works · 2–3 days

This is the user-stated priority. Phase exits when `jma crawl --region Hangzhou
--keywords "AI agent"` writes ≥1 `Job` row to SQLite from a real TesterHome
fetch, with `SourceResult.status == ok`.

**Steps**:

1. `domain/normalize.py` — pure parsers for salary, experience, location.
2. `sources/base.py` — `JobSource` protocol + `SourceResult` dataclass.
3. `sources/http.py` — `httpx.AsyncClient` wrapper with hybrid blockage detection.
4. `sources/testerhome.py` — first concrete source.
5. `storage/db.py` + `storage/cache.py` — SQLite schema + URL-hash cache.
6. `pipeline/crawl.py` — single-source orchestration.
7. `cli.py jma crawl` — first vertical slice ships.

**Real case 1.A — salary parser test corpus (drives `normalize.py`).**
Before writing the parser, collect this table from real Hangzhou postings and
turn it into a parametrised pytest:

| Raw string | min | max | currency | period | months/yr | parsed |
|---|---|---|---|---|---|---|
| `20-40K·15薪` | 20000 | 40000 | CNY | monthly | 15 | true |
| `25-50K·14薪` | 25000 | 50000 | CNY | monthly | 14 | true |
| `15-30K` | 15000 | 30000 | CNY | monthly | 12 | true |
| `年薪 40-80万` | 33333 | 66666 | CNY | monthly | 12 | true |
| `400元/天` | — | — | CNY | daily | — | true (period=daily) |
| `面议` | null | null | CNY | unknown | — | false |
| `Competitive` | null | null | null | unknown | — | false |
| `$120K–$160K` | 10000 | 13333 | USD | monthly | 12 | true |

The annual-→-monthly conversion (`年薪 40-80万 → 33333-66666 ¥/mo`) is what
makes the median-salary histogram comparable across postings — that's the
justification for parsing complexity instead of storing raw strings.

**Real case 1.B — blockage classifier (drives `sources/http.py`).**
Three failure modes we have to distinguish:

```
GET https://www.zhaopin.com/...     → 200 OK
  body contains "<title>验证</title>" + slider-captcha script
  → status: blocked, reason: "soft-block: captcha challenge"

GET https://www.testerhome.com/jobs → 200 OK, 47 .topic items parsed
  → status: ok

GET https://www.randstad.cn/jobs/?q=AI&l=Hangzhou → 200 OK
  body parses cleanly but 0 .job-card elements
  → status: empty, reason: "0 jobs parsed from known-good selector"

GET https://api.bing.microsoft.com/... → 429 + Retry-After: 30
  → status: rate_limited, reason: "429; retrying after 30s"

GET https://www.liepin.com/...      → 403 Forbidden
  → status: blocked, reason: "HTTP 403"
```

The classifier is a pure function `(response, source_config) → BlockStatus`,
unit-tested against captured fixtures of all five — no live network in tests.

**Real case 1.C — TesterHome parser (drives `sources/testerhome.py`).**
Listing URL: `https://testerhome.com/jobs?page=1`. Real DOM shape:

```html
<div class="topics">
  <div class="topic">
    <div class="title">
      <a href="/topics/41234">【杭州·余杭】AI Agent 后端工程师 25-50K·14薪</a>
    </div>
    <div class="info">
      <span class="user">@nodejh</span>
      <span class="time" title="2026-05-18 14:22">3天前</span>
    </div>
  </div>
  …
</div>
```

Selectors stored in `data/sources/testerhome.yaml`:

```yaml
name: testerhome
base_url: https://testerhome.com
listing_url: "{base_url}/jobs?page={page}"
selectors:
  list_item: ".topics .topic"
  title:     ".title a"
  href:      ".title a@href"
  posted_at: ".time@title"
detail:
  selector_body: ".topic-detail .markdown-body"
requires_browser: false
content_block_markers: []      # TesterHome rarely blocks
```

This source ships first because the listing page already carries title +
salary in the title text — so even before stage-1 extraction we have crawlable,
demo-able stats. That's the justification for "lean MVP, one good source first".

---

### Phase 2 — Bing aggregator (SerpAPI), `jma view`, TesterHome retirement · 2 days

Three-part Phase 2:

a. **Retire TesterHome.** Volume too low — as a QA/testing community, "AI agent"
   searches surface mostly test-automation roles; the AI-eng sample is too small
   for meaningful market stats. Delete the source, YAML, tests, live test, and
   phase-1 diagram. Wipe the existing `data/jobs.db` and `data/raw/testerhome/`
   manually (documented; not scripted).
b. **Add the Bing-aggregator via SerpAPI (snippet-only).** Single source class,
   multi-site query template, **no detail-fetch in this phase**. Snippet mapped
   into structured columns (`title`, `posted_at`, `salary`, `experience`);
   raw snippet text stored in `description_text` as Phase 3's LLM-extraction
   input. `source = "bing:<host>"` where `<host>` is the matched `target_sites`
   entry (collapses subdomains; ADR-0005).
c. **Add `jma view`** — a CLI command that renders one self-contained static
   HTML page listing every observation in the latest finished run. Sortable
   client-side via inline ~30-line JS. No web server.

**Real case 2.A — Bing aggregator query construction.** For `--region Hangzhou
--keywords "AI agent"`, after alias expansion:

```
("AI agent") (Hangzhou OR 杭州 OR 杭州市)
  (site:zhipin.com OR site:lagou.com OR site:liepin.com OR site:51job.com OR site:zhaopin.com)
  (招聘 OR hiring OR JD) -inurl:resume
```

One SerpAPI call returns up to 50 organic results. `max_pages=N` maps 1:1 to
N SerpAPI calls (`start = (page - 1) * 50`). The CLI's `--max-pages 5` default
costs 5 SerpAPI queries per crawl, ~20 crawls/month on the free tier.

### Phase 2.1 — Detail-fetch enrichment for Bing — deferred

**Trigger to re-open:** a live SerpAPI sample where at least one target board's
detail pages return useful 200s (i.e. evidence that the anti-bot is *not* uniform
across the target set). **Cost when revived:** extra HTTP budget per crawl, an
`--with-detail`-style flag, the detail outcome matrix from the original spec
draft, and a follow-up ADR-0005 clause on no-halt-on-detail-block. The column
footprint (`url_status`, `url_last_checked_at`, `data_quality=0.9` reserved) is
already in place.

---

### Phase 3 — Extraction (LLM enters) · 1–2 days

`llm/client.py` (DeepSeek + on-disk response cache keyed by
`sha1(prompt) → response.json`), `llm/extract.py`, `domain/skills.py`,
`data/skills.yaml` seeded with ~300 entries, `pipeline/extract.py` running
bounded-concurrency extraction across uncached jobs.

**Real case 3.A — JD → structured JSON.**
Real JD body from a Hangzhou AI posting:

```
岗位职责：
1. 负责大模型推理引擎的优化（vLLM、TGI、LMDeploy），关注吞吐与显存
2. 基于 LangChain / LlamaIndex 构建 Agent 应用，对接 MCP 工具
3. 熟悉 K8s 集群编排，使用 Triton Inference Server 部署服务
任职要求：
- 3年以上后端开发经验，精通 Python，了解 Go 优先
- 熟悉至少一种向量库（Milvus / Qdrant / Faiss）
- 有 RAG 项目落地经验，蒸馏/微调经验加分
工作地点：杭州·余杭区 飞天园区
```

Stage 1 (rules — `domain/normalize.py`):
```json
{"location": {"city": "Hangzhou", "district": "余杭"},
 "experience": {"min_years": 3, "max_years": null}}
```

Stage 2 (one DeepSeek extraction call):
```json
{
  "skills_raw": ["vLLM", "TGI", "LMDeploy", "LangChain", "LlamaIndex",
                 "MCP", "K8s", "Triton Inference Server",
                 "Python", "Go", "Milvus", "Qdrant", "Faiss", "RAG"],
  "seniority": "mid",
  "work_mode": "onsite",
  "responsibilities_summary": "Optimise LLM inference engines, build Agent
                               apps on LangChain/LlamaIndex, deploy on K8s."
}
```

Stage 3 (`domain/skills.py` canonicalisation against `skills.yaml`):
```yaml
# excerpt of skills.yaml
Kubernetes:
  aliases: [k8s, K8s, kubernetes, KUBERNETES]
LLM Inference:
  aliases: [vLLM, TGI, LMDeploy, Triton Inference Server, llm 推理, 大模型推理]
LangChain:
  aliases: [LangChain, langchain, Lang Chain]
RAG:
  aliases: [RAG, rag, 检索增强生成]
MCP:
  aliases: [MCP, Model Context Protocol, mcp]
```

After canonicalisation:
```json
{"skills_canonical":
 ["LLM Inference", "LangChain", "LlamaIndex", "MCP", "Kubernetes",
  "LLM Inference",                              // dup, dedup'd
  "Python", "Go",
  "Vector Database",                            // Milvus|Qdrant|Faiss collapse here
  "Vector Database", "Vector Database",
  "RAG"]
 // → dedup → ["LLM Inference", "LangChain", "LlamaIndex", "MCP",
 //            "Kubernetes", "Python", "Go", "Vector Database", "RAG"]
}
```

`vLLM`, `TGI`, `LMDeploy`, `Triton Inference Server` all collapsing to
`LLM Inference` is what makes the market chart say "LLM Inference: 38%"
instead of four separate 9–15% bars. **Justification for canonicalisation**:
without it, the top-10 skills bar chart is dominated by synonym noise and the
fit-match underestimates overlap (a candidate listing `vLLM` would not match
a JD listing `Triton`).

**Real case 3.B — extraction cost ceiling.**
Per call: prompt ~1.2k tokens, response ~300 tokens. DeepSeek-chat at
~$0.27/M in, $1.10/M out ⇒ ≈ $0.0005 per job. 300 jobs ⇒ $0.15. With the
`sha1(prompt)` disk cache, re-running the same crawl is $0. This is what
makes parallel per-job extraction acceptable instead of "spamming".

---

### Phase 4 — Market report · 1–2 days

`domain/stats.py` aggregations, `llm/narrate.py` one-call narrative,
`report/render.py` + Jinja templates, `jma report market` ships.

**Real case 4.A — what a stats dump looks like, before LLM narration.**
For `("AI agent", Hangzhou)`, n=180 jobs (152 high-quality + 28 snippet-only):

```
SALARY (monthly, CNY, normalised to ×14 months; 152 parseable)
  p25:  22,000        p50: 30,000        p75: 45,000        max: 80,000
  histogram (in 'K'):
    10-20  ▇▇▇         12
    20-30  ▇▇▇▇▇▇▇▇▇   38
    30-45  ▇▇▇▇▇▇▇▇▇▇▇ 54
    45-60  ▇▇▇▇▇       22
    60-80  ▇▇          14
    >80    ▇            5

TOP SKILLS (canonical; weight by data_quality)
  Python              ▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇   98%
  LangChain           ▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇                62%
  RAG                 ▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇                   51%
  Kubernetes          ▇▇▇▇▇▇▇▇▇▇▇▇▇▇                     44%
  LLM Inference       ▇▇▇▇▇▇▇▇▇▇▇▇                       38%
  Vector Database     ▇▇▇▇▇▇▇▇▇▇▇                        35%
  MCP                 ▇▇▇                                11%   ← rising
  Go                  ▇▇▇▇▇▇                             22%

ROLE CLUSTERS (TF-IDF + simple k=4 clustering on titles)
  • "Agent Backend Engineer"  (52 jobs, salary p50 28K)
  • "LLM Platform / Infra"    (41 jobs, salary p50 38K)
  • "RAG / Knowledge"         (37 jobs, salary p50 32K)
  • "Algorithm / Research"    (22 jobs, salary p50 45K)

POSTING AGE
  <7d   ▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇  45%
  7-30d ▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇       38%
  30-90 ▇▇▇▇▇                  12%
  >90d  ▇▇                      5%

DATA QUALITY
  high-quality (full JD parsed):   152  (84%)
  snippet-only (degraded weight):   28  (16%)
  blocked sources: zhaopin (soft-block), liepin (403)
```

These tables are deterministic, reproducible from SQLite alone, and
template-rendered. The **single narrative LLM call** then receives `{stats,
top_20_sample_jds}` and produces 4–6 paragraphs of insight ("the market is
mid-heavy, RAG vs Agent split, MCP is a fresh signal worth tracking…").
Justification: the LLM's job is synthesis, not arithmetic — by the time it
runs, every number is already correct.

**Real case 4.B — narrative call shape.**
One call only, ~3k input tokens, ~1.2k output:

```python
prompt = render("narrate_market.j2", stats=stats, samples=sampled_jds,
                region="Hangzhou", keywords=["AI agent"], lang="zh")
narrative = llm.complete(prompt, model="deepseek-chat", max_tokens=1500)
```

Cost ≈ $0.002. Cached by `sha1(stats_digest + sample_ids + lang)`.

---

### Phase 5 — Profile + fit · 2 days

`profile/ingest.py`, two-tier sufficiency, `llm/persona.py`,
`domain/scoring.py`, `llm/fit.py`, `jma report fit` ships.

**Real case 5.A — Tier 1 (deterministic) rejection.**
User runs `jma report fit --resume one_line.txt`. Resume content:
`"I'm a backend engineer with 5 years of experience."`

Tier 1 parses to `{current_role: "backend engineer", years_experience: 5,
skills: []}`. Skills < 3 ⇒ stop. CLI exits with:

```
profile insufficient. need at least 3 of:
  - skills you actively use (e.g. Java, Spring, Python)
  - target role or job title
  - current salary range (optional but improves fit ranking)

drop these into profile.yaml or extend the resume and re-run.
```

Zero LLM tokens spent. Justification: the LLM cannot rescue a one-sentence
resume, and pretending otherwise wastes money and gives a hallucinated persona.

**Real case 5.B — Tier 2 (LLM persona) success.**
Real profile:

```yaml
# profile.yaml
current_role: "Senior Backend Engineer"
years_experience: 5
current_salary_cny_monthly: 25000
expected_salary_cny_monthly: 35000
location: "Hangzhou"
skills:
  - Java
  - Spring Boot
  - Python    # intermediate
  - MySQL
  - Redis
  - Kubernetes
  - Docker
target_roles: ["AI Engineer", "AI Platform Engineer"]
notes: "Built an internal RAG prototype with LlamaIndex last quarter."
```

Single DeepSeek call returns:

```json
{
  "persona": "Senior Java backend engineer pivoting into AI/agent platform work; production infra fluency + early RAG exposure",
  "strengths": ["Spring/Java ecosystem", "production K8s ops",
                "5y backend experience", "early RAG exposure (LlamaIndex)"],
  "gaps": ["LangChain (not LlamaIndex)", "vLLM/LLM inference",
           "vector DB ops at scale", "Python ML stack depth"],
  "salary_range_expectation": [30000, 45000],
  "target_roles_refined": ["AI Platform Engineer",
                           "Senior Backend Engineer (Agent)",
                           "LLM Infra Engineer"],
  "confidence_score": 0.82,
  "clarifications_needed": []
}
```

`confidence_score 0.82 ≥ 0.6` ⇒ proceed to scoring. Justification: this
persona is the single anchor the fit-scorer and fit-narrator both share — one
LLM call, reused everywhere downstream.

**Real case 5.C — deterministic scoring on one job.**
Job: *Alibaba — AI Platform Engineer · 30-50K·15薪 · Hangzhou · 3-5yr · Python, K8s, LangChain, vLLM, RAG, Go*

```
skill_overlap_jaccard = |{Python, K8s} ∩ user| / |union|
                      = 2 / 8 = 0.25                  # weight 0.50 → 0.125
exp_fit       = 5y inside [3,5] → 1.0                 # weight 0.20 → 0.200
salary_fit    = job_min 30K ≥ user_expected_min 35K?
              = 30K vs 35K → 0.65                     # weight 0.15 → 0.0975
location_fit  = same city                  → 1.0      # weight 0.10 → 0.100
seniority_fit = mid vs senior              → 0.7      # weight 0.05 → 0.035
                                                     ─────────────
overall match score                                   ≈ 0.5575 → 56%
skill_gap = {LangChain, vLLM, RAG, Go}
```

Done in pure Python, reproducible across runs. Same job will always score 56%
unless the YAML weights or skills canonicalisation change.

**Real case 5.D — top-N LLM refinement (one call).**
The top 30 scored jobs + the persona are fed to DeepSeek once:

```
You are advising the candidate above. Given the 30 jobs below (already
ranked by deterministic score), produce:
1. A ranked top-10 with one-sentence "why this fits / what's the risk".
2. A skill-gap synthesis paragraph: across these 30 jobs, which gaps
   appear most often, and in what learning order would closing them
   maximise match across the cohort?
3. Two concrete next-90-days actions.
```

Output excerpt (rendered into `fit.md`):

```markdown
## Top 10 matches

1. **Alibaba — AI Platform Engineer** · 30-50K · 56%
   Strong infra overlap (K8s, Python) + your RAG prototype is the wedge.
   Risk: LangChain (not LlamaIndex) is the team's choice — 1 weekend to bridge.

2. **NetEase — Senior Backend (Agent Tools)** · 28-45K · 54%
   Backend-first role with Agent tools as half the work — closest to current
   role. Risk: lower ceiling on LLM-infra growth.

… (8 more)

## Skill-gap synthesis

Across these 30 jobs, **LangChain** appears in 22/30 (73%), **vLLM/LLM
inference** in 14/30 (47%), and **production RAG ops** in 12/30 (40%). Your
LlamaIndex exposure narrows the LangChain gap to roughly a weekend of porting;
vLLM is the biggest single delta. Suggested order:
1. Port your RAG prototype from LlamaIndex to LangChain (1 weekend → unlocks
   17 of 22 LangChain-required roles)
2. vLLM serving lab on your existing K8s cluster (2 weeks → unlocks 11 jobs)
3. Vector DB ops: a Milvus+Qdrant comparison side-project (2 weeks → +6 jobs)

## Concrete actions (next 90 days)

…
```

Justification: the LLM is doing what only an LLM can do here — synthesise
patterns across 30 JDs and a persona. The deterministic scorer already did
the ranking and arithmetic, so the LLM cannot misrank or miscount.

---

### Phase 6 — Polish · 1 day

- `jma run` convenience wrapper (`crawl → market → fit if profile`)
- Cross-run delta section in market report
- README with worked example, sample reports

**Real case 6.A — cross-run delta.**
Two runs 3 weeks apart, both `("AI agent", Hangzhou)`:

| Metric | Run 1 (2026-04-30) | Run 2 (2026-05-21) | Δ |
|---|---|---|---|
| Active postings | 158 | 180 | +14% |
| Median salary | 28K×14 | 30K×14 | **+7%** |
| LangChain share | 58% | 62% | +4pp |
| **MCP share** | 0% | 11% | **new signal** |
| RAG share | 56% | 51% | -5pp |
| New roles | — | 47 | |
| Disappeared roles | — | 22 | |

Rendered in the report as:

```markdown
## Trend (vs run from 2026-04-30, 21 days ago)

Hiring intensity is up 14% by active-posting count; median offer has
moved 28K → 30K (×14 months). **MCP** is a new entrant — absent
3 weeks ago, now cited in 11% of postings — worth watching as a
fresh signal. RAG dipped 5 points, possibly absorbed into broader
"Agent" framing.
```

Justification: this only works because Phase 1 chose SQLite + run-tracking
over JSON-only or in-memory storage. The trend section is "free" once data
accumulates — no extra LLM cost, just a diff query.

---

## 5. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Randstad CN/HK locales differ in JS-rendering | Source YAML supports `variants` with per-host `requires_browser` flag (Phase 2) |
| Zhaopin/Liepin JD pages soft-block after Bing snippet leads us there | Snippet-only `Job` with `data_quality=0.4`, downweighted in stats, excluded from salary medians; share of snippet-only rows footnoted in report |
| SerpAPI rate-limit (100/mo free) | Tight default `max_pages 5`; 24h URL cache covers SerpAPI page URLs; `--no-cache` opt-out for force-refresh; document the $75/mo dev tier in README if hitting the wall |
| Bing `site:` operator behaviour per board | PLAN intent of cross-board breadth depends on SerpAPI's `site:` behaviour on each board — verify against fixture + opt-in live test before shipping |
| Snippet-only is the floor of Phase 2 data quality | If a future SerpAPI/Bing change degrades snippet content to title-only, Phase 2 silently drops to title+url+date rows. `tests/live/test_bing_live.py` asserts salary/experience/date richness as a tripwire |
| Salary parsing edge cases (`面议`, `Competitive`, USD/HKD mixed currency) | Parse-corpus-first TDD (case 1.A); `parsed=false` is a first-class state every aggregator handles |
| DeepSeek rate limits during extraction burst | `concurrency 4` cap; `sha1(prompt)` disk cache makes re-runs free; exp-backoff on 429 |
| Skills YAML drift / unmapped novel skills | `data/unmapped_skills.log` records every unmapped extraction; review monthly to grow vocab |
| LLM hallucinated stats (if pipeline were collapsed) | Architecturally prevented: aggregation is pure Python; LLM only narrates over pre-computed numbers |
| Resume image-PDF (scanned) | Fail loudly in Phase 5 ingest: "PDF appears image-based; convert to text/markdown" — no silent OCR |
| Multi-region generalisation (Berlin, Tokyo, Bengaluru) | `region_aliases.yaml` user-overridable; `JobSource` is pluggable so locale-specific boards can be added without core changes |

---

## 6. Open items (intentionally deferred)

- Web UI / hosted version — out of scope for v1.
- Docx resume — defer to v1.1 unless adoption demand.
- Live job-board partnerships / official APIs — none publicly available; revisit if one opens.
- Multi-region market comparison (`Hangzhou vs Shanghai vs Shenzhen`) — natural v1.1 once trend infrastructure exists.
- Randstad direct crawler, Playwright fallback (`sources/browser.py`), direct
  BOSS Zhipin crawler — **deferred to a later phase or v1.1 if justified.**
  Volume coverage solved by Bing across CN boards.
- **Phase 2.1 — detail-fetch enrichment for Bing.** See Phase 2.1 heading + ADR-0005.

---

*End of plan. Next step on approval: Phase 0 + Phase 1.1 — pyproject + uv init
+ `domain/models.py` + `domain/normalize.py` with failing salary-parse tests
(red), then green, then refactor.*
