# Issue #7 — Detail-page fetch for company + salary enrichment

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in detail-page fetch phase to `TesterHomeSource` so `company` and `salary_raw` are populated from each topic's detail page, while leaving the default crawl path (listing-only) untouched.

**Architecture:** Detail fetching is **off by default** and gated by `cfg.detail.enabled` plus a CLI flag `--with-detail`. The implementation does **two** changes to `TesterHomeSource`:

1. **Refactor first (behavior-preserving for tested paths):** extract the existing listing fetch into a private `_fetch_classified(url)` helper that does cache-or-fetch → `classify()` → blob/cache write *only when classify is OK*. This is a small behavior change for the untested 200-with-block-markers case (the previous code wrote the blob and `url_cache` row before classifying, which would have poisoned the 24h URL cache); existing tests don't exercise that path so the refactor is observably safe.

2. **Layer detail-fetch on top:** for each listing item, sleep `delay_ms`, call `_fetch_classified(detail_url)`, and merge company/salary from the parsed detail HTML into the `Job`. A detail block tripping `classify()` converts the crawl to a [[PartialHarvest]] (see `CONTEXT.md`); a per-job network exception degrades that one job to listing-only.

Three domain decisions are codified in docs and the implementation must respect them:

- **`canonical_id` is latest-wins** ([docs/adr/0003-canonical-id-is-latest-wins-not-run-stable.md](../../adr/0003-canonical-id-is-latest-wins-not-run-stable.md)). Detail enrichment updates `canonical_id` but **must not** recompute `id` — for TesterHome `id = sha1("testerhome:" + internal_id)` is invariant under company changes.
- **PartialHarvest covers detail-fetch blocks too** ([CONTEXT.md](../../../CONTEXT.md), PartialHarvest entry). A block on a detail page must NOT write a blob, must NOT write to `url_cache`, and must convert the run to PartialHarvest.
- **`data_quality` is deferred** ([docs/adr/0001-cross-source-dedup-via-canonical-id.md](../../adr/0001-cross-source-dedup-via-canonical-id.md), amended). No schema/model field added in this plan.

**Tech Stack:** Python 3.12, httpx + selectolax (already in use), respx for HTTP mocking in tests, pydantic v2 frozen models, pytest. Tests via `uv run pytest`.

**Issue link:** [snowshine0216/job-market-agent#7](https://github.com/snowshine0216/job-market-agent/issues/7)

**Related:** depends on no prior work. Plan for issue #8 (URL freshness) builds on this one.

---

## File Structure

- Modify: [src/jma/sources/base.py](../../../src/jma/sources/base.py)
  - Extend `DetailConfig` with new fields: `enabled: bool`, `company_selectors: tuple[str, ...]`, `company_label_patterns: tuple[str, ...]`, `salary_selectors: tuple[str, ...]`, `salary_label_patterns: tuple[str, ...]`. All have safe defaults so existing YAML continues to load.

- Modify: [config/sources/testerhome.yaml](../../../config/sources/testerhome.yaml)
  - Populate the new `detail.*` fields with TesterHome-appropriate values.

- Modify: [src/jma/sources/testerhome.py](../../../src/jma/sources/testerhome.py)
  - Add a frozen `_ClassifiedFetch` dataclass and a private async method `_fetch_classified(url)`. Refactor the existing listing loop to use it (Task 5, behavior-preserving for tested paths).
  - Add pure helpers `_parse_detail(body, cfg)` and `_enrich_from_detail(job, detail, source_name)`. Iterate child block-elements during label scan (Task 3).
  - Add `_enrich_page(page_jobs)` that runs detail enrichment with sleep-before-fetch, narrow exception handling, and classify-aware halt (Task 6).
  - Integrate the per-page detail-enrichment loop in `TesterHomeSource.crawl`, pre-truncating to `max_jobs` before enrichment.

- Modify: [src/jma/cli.py](../../../src/jma/cli.py)
  - Add `--with-detail / --no-detail` Typer option. Override `cfg.detail.enabled` via `model_copy` before constructing the source.

- Create: `tests/fixtures/sources/testerhome/detail_basic.html`
  - Realistic detail-page fixture with labels in separate `<p>` tags.

- Create: `tests/fixtures/sources/testerhome/detail_minified.html`
  - Same content as `detail_basic.html`, but with no whitespace between `</p>` and `<p>` — locks down child-element iteration robustness against renderer minification.

- Create: `tests/fixtures/sources/testerhome/detail_blocked.html`
  - HTTP 200 body containing a content-block marker — used in Task 7 to verify classify-on-detail behavior.

- Create: `tests/sources/test_testerhome_detail.py`
  - Unit tests for `_parse_detail`, `_enrich_from_detail`, and the don't-downgrade salary rule.

- Create: `tests/sources/test_testerhome_with_detail.py`
  - Integration tests using respx to mock both listing and detail (success, disabled, 404 fallback, block-on-detail → PartialHarvest).

- Create: `tests/cli/test_crawl.py` (if missing)
  - CLI surface test for `--with-detail`.

---

## Tasks

### Task 1: Extend `DetailConfig` and YAML with new fields (additive, default-safe)

**Files:**
- Modify: `src/jma/sources/base.py`
- Modify: `config/sources/testerhome.yaml`

- [ ] **Step 1: Write a failing test for the new defaults**

Create `tests/sources/test_detail_config_defaults.py`:

```python
from jma.sources.base import DetailConfig


def test_detail_config_defaults_to_disabled_and_empty() -> None:
    cfg = DetailConfig(body_selector=".topic-detail .markdown-body")
    assert cfg.enabled is False
    assert cfg.company_selectors == ()
    assert cfg.company_label_patterns == ()
    assert cfg.salary_selectors == ()
    assert cfg.salary_label_patterns == ()
```

- [ ] **Step 2: Run the test to confirm it fails**

Run: `uv run pytest tests/sources/test_detail_config_defaults.py -v`

Expected: FAIL with a pydantic `ValidationError` or `AttributeError` because the fields don't exist yet.

- [ ] **Step 3: Add the fields to `DetailConfig` in `src/jma/sources/base.py`**

Replace the current class body of `DetailConfig` (lines 22–25) with:

```python
class DetailConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    body_selector: str
    enabled: bool = False
    company_selectors: tuple[str, ...] = ()
    company_label_patterns: tuple[str, ...] = ()
    salary_selectors: tuple[str, ...] = ()
    salary_label_patterns: tuple[str, ...] = ()
```

- [ ] **Step 4: Confirm the test now passes**

Run: `uv run pytest tests/sources/test_detail_config_defaults.py -v`

Expected: PASS.

- [ ] **Step 5: Populate `config/sources/testerhome.yaml` with realistic TesterHome values**

Replace the `detail:` block in `config/sources/testerhome.yaml` (lines 9–10) with:

```yaml
detail:
  body_selector: ".topic-detail .markdown-body"
  enabled: false                  # opt-in: flip via --with-detail CLI flag
  company_selectors:
    - ".topic-detail .markdown-body"   # root for the child-element scan (Task 3)
  company_label_patterns:
    - "公司[:：]\\s*(?P<value>[^\\n<]+)"
    - "公司名称[:：]\\s*(?P<value>[^\\n<]+)"
    - "招聘公司[:：]\\s*(?P<value>[^\\n<]+)"
  salary_selectors:
    - ".topic-detail .markdown-body"
  salary_label_patterns:
    - "薪资[:：]\\s*(?P<value>[^\\n<]+)"
    - "薪资范围[:：]\\s*(?P<value>[^\\n<]+)"
    - "工资[:：]\\s*(?P<value>[^\\n<]+)"
```

- [ ] **Step 6: Run the source-config loader smoke test**

Run: `uv run pytest tests/sources -v`

Expected: all existing source tests still PASS. The new defaults test PASSES. Existing YAML loads without error.

- [ ] **Step 7: Commit**

```bash
git add src/jma/sources/base.py config/sources/testerhome.yaml tests/sources/test_detail_config_defaults.py
git commit -m "feat(sources): extend DetailConfig with enabled + selector/label fields (#7)"
```

---

### Task 2: Add detail-page HTML fixtures (basic + minified + blocked)

**Files:**
- Create: `tests/fixtures/sources/testerhome/detail_basic.html`
- Create: `tests/fixtures/sources/testerhome/detail_minified.html`
- Create: `tests/fixtures/sources/testerhome/detail_blocked.html`

- [ ] **Step 1: Verify the fixture directory exists (it already holds listing fixtures)**

Run: `ls tests/fixtures/sources/testerhome/`

Expected: shows existing `listing_ok.html`, `listing_empty.html`.

- [ ] **Step 2: Create `detail_basic.html`**

Content (labels in separate `<p>` tags, whitespace between):

```html
<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>测试招聘</title></head>
<body>
  <article class="topic-detail">
    <div class="markdown-body">
      <p>岗位职责：负责测试平台建设。</p>
      <p>公司：上海冰鲸科技有限公司</p>
      <p>薪资：30k-50k·14薪</p>
      <p>城市：上海</p>
    </div>
  </article>
</body>
</html>
```

- [ ] **Step 3: Create `detail_minified.html`**

Same data, but with **no whitespace** between sibling tags — simulates a renderer that minifies output. The child-element iteration in `_extract_first_label_value` (Task 3) must still extract correctly because each `<p>`'s `.text()` is bounded by its element, regardless of inter-tag whitespace:

```html
<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>测试招聘</title></head><body><article class="topic-detail"><div class="markdown-body"><p>岗位职责：负责测试平台建设。</p><p>公司：上海冰鲸科技有限公司</p><p>薪资：30k-50k·14薪</p><p>城市：上海</p></div></article></body></html>
```

- [ ] **Step 4: Create `detail_blocked.html`**

A 200 response body that contains a soft-block marker — used by the Task 7 integration test verifying classify-on-detail PartialHarvest. Pick a marker that we'll also add to `cfg.content_block_markers` (or, more cleanly, configure the test to use an overridden cfg with a known marker, since `testerhome.yaml` currently ships `content_block_markers: []`).

```html
<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>请稍后再试</title></head>
<body>
  <div class="anti-bot-interstitial">
    系统繁忙，请稍后再试。
  </div>
</body>
</html>
```

- [ ] **Step 5: Commit the fixtures (no test yet)**

```bash
git add tests/fixtures/sources/testerhome/detail_basic.html \
        tests/fixtures/sources/testerhome/detail_minified.html \
        tests/fixtures/sources/testerhome/detail_blocked.html
git commit -m "test(sources): add TesterHome detail-page fixtures (basic, minified, blocked) (#7)"
```

---

### Task 3: TDD `_parse_detail(body, cfg) -> dict[str, str]` with child-element iteration

**Files:**
- Create: `tests/sources/test_testerhome_detail.py`
- Modify: `src/jma/sources/testerhome.py`

The parser walks **child block-elements** of the configured selector node (not the full body's `text()`). This avoids the silent over-match failure mode when HTML lacks whitespace between paragraphs. Two regression fixtures (basic + minified) lock down the invariant.

- [ ] **Step 1: Write the failing parser tests**

Create `tests/sources/test_testerhome_detail.py`:

```python
from pathlib import Path

from jma.sources.base import load_source_config
from jma.sources.testerhome import _parse_detail

REPO = Path(__file__).resolve().parents[2]
_CFG_PATH = REPO / "config/sources/testerhome.yaml"
_FIX_BASIC = REPO / "tests/fixtures/sources/testerhome/detail_basic.html"
_FIX_MIN = REPO / "tests/fixtures/sources/testerhome/detail_minified.html"


def _cfg_with_detail_enabled():
    cfg = load_source_config(_CFG_PATH)
    return cfg.model_copy(update={"detail": cfg.detail.model_copy(update={"enabled": True})})


def test_parse_detail_extracts_company_and_salary_from_basic_fixture() -> None:
    body = _FIX_BASIC.read_text(encoding="utf-8")
    cfg = _cfg_with_detail_enabled()
    out = _parse_detail(body, cfg)
    assert out["company"] == "上海冰鲸科技有限公司"
    assert out["salary_raw"] == "30k-50k·14薪"


def test_parse_detail_extracts_correctly_from_minified_fixture() -> None:
    """Renderer minification (no whitespace between </p> and <p>) must not
    cause label scan to span paragraphs. Child-element iteration is the
    invariant under test here."""
    body = _FIX_MIN.read_text(encoding="utf-8")
    cfg = _cfg_with_detail_enabled()
    out = _parse_detail(body, cfg)
    assert out["company"] == "上海冰鲸科技有限公司"
    assert out["salary_raw"] == "30k-50k·14薪"


def test_parse_detail_returns_empty_strings_when_no_match() -> None:
    body = "<html><body><div class='markdown-body'><p>nothing useful</p></div></body></html>"
    cfg = _cfg_with_detail_enabled()
    out = _parse_detail(body, cfg)
    assert out == {"company": "", "salary_raw": ""}


def test_parse_detail_no_op_when_disabled() -> None:
    body = _FIX_BASIC.read_text(encoding="utf-8")
    cfg = load_source_config(_CFG_PATH)  # detail.enabled = False from YAML
    out = _parse_detail(body, cfg)
    assert out == {"company": "", "salary_raw": ""}
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `uv run pytest tests/sources/test_testerhome_detail.py -v`

Expected: FAIL — `_parse_detail` is not exported from `jma.sources.testerhome`.

- [ ] **Step 3: Add `_parse_detail` and `_extract_first_label_value` to `src/jma/sources/testerhome.py`**

Append to the "pure helpers" section (after `_filter_keywords`):

```python
# Block-level child elements scanned when extracting labeled values.
# Each child's text() is bounded by the element, which prevents label
# scans from spanning paragraphs (robust against renderer minification).
_BLOCK_CHILD_CSS = "p, li, dt, dd, blockquote, h1, h2, h3, h4, h5, h6"


def _parse_detail(body: str, cfg: SourceConfig) -> dict[str, str]:
    """Extract {company, salary_raw} from a TesterHome topic detail page.

    Honours cfg.detail.enabled. Returns empty strings for fields that
    don't match any configured selector + label-pattern combination.
    Pure: HTML parsing only, no I/O.
    """
    if not cfg.detail.enabled:
        return {"company": "", "salary_raw": ""}
    tree = HTMLParser(body)
    return {
        "company": _extract_first_label_value(
            tree, cfg.detail.company_selectors, cfg.detail.company_label_patterns
        ),
        "salary_raw": _extract_first_label_value(
            tree, cfg.detail.salary_selectors, cfg.detail.salary_label_patterns
        ),
    }


def _extract_first_label_value(
    tree: HTMLParser, selectors: tuple[str, ...], patterns: tuple[str, ...]
) -> str:
    """For each selector, walk block-element children and run each regex
    against each child's text. Return the first non-empty named group
    `value`, stripped. Empty string on no match.

    Per-child scanning ensures the regex value cannot span across
    sibling elements even if the HTML has no inter-tag whitespace.
    """
    compiled = tuple(re.compile(p) for p in patterns)
    for selector in selectors:
        root = tree.css_first(selector)
        if root is None:
            continue
        children = list(root.css(_BLOCK_CHILD_CSS)) or [root]
        for child in children:
            text = (child.text() or "").strip()
            if not text:
                continue
            for pat in compiled:
                m = pat.search(text)
                if m:
                    value = (m.groupdict().get("value") or "").strip()
                    if value:
                        return value
    return ""
```

- [ ] **Step 4: Run the parser tests to confirm they pass**

Run: `uv run pytest tests/sources/test_testerhome_detail.py -v`

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/jma/sources/testerhome.py tests/sources/test_testerhome_detail.py
git commit -m "feat(sources): _parse_detail iterates block-element children for label scan (#7)"
```

---

### Task 4: TDD `_enrich_from_detail(job, detail, source_name) -> Job` (no id recomputation; don't-downgrade salary)

**Files:**
- Modify: `tests/sources/test_testerhome_detail.py`
- Modify: `src/jma/sources/testerhome.py`

Two behavioural rules locked down here, both flowing from grilling outcomes:

1. **`id` is NOT recomputed** — `job_id(source, internal_id, ...)` returns `sha1("source:internal_id")` whenever `internal_id` is set, so the value is invariant under company changes. ADR-0003 makes this explicit. The previous plan's id-recomputation was vacuous code.
2. **Detail salary wins ONLY when it parses cleanly** — never replace a `parsed=True` listing salary with a `parsed=False` detail salary (e.g. `面议`). [[SalaryDisclosure]] aggregations in Phase 4 drop unparseable rows entirely, so a downgrade would silently delete the row from future stats.

- [ ] **Step 1: Append the failing enrichment tests**

Append to `tests/sources/test_testerhome_detail.py`:

```python
from datetime import UTC, datetime

from jma.domain.dedup import canonical_id, job_id
from jma.domain.models import Experience, Job, Location, Salary, WorkMode
from jma.domain.normalize import parse_salary
from jma.sources.testerhome import _enrich_from_detail


def _make_listing_job() -> Job:
    return Job(
        id=job_id(source="testerhome", internal_id="42", title="测试开发",
                  company=None, city="Shanghai"),
        canonical_id=canonical_id(title="测试开发", company=None, city="Shanghai"),
        source="testerhome",
        source_internal_id="42",
        title="测试开发",
        title_raw="【上海】测试开发",
        company=None,
        location=Location(country="CN", city="Shanghai", work_mode=WorkMode.UNKNOWN),
        salary=Salary(raw=""),
        experience=Experience(raw=""),
        fetched_at=datetime.now(UTC),
        url="https://testerhome.com/topics/42",
        raw_payload_ref="testerhome/abc.html.gz",
    )


def test_enrich_fills_company_and_salary_and_recomputes_canonical_id_only() -> None:
    job = _make_listing_job()
    detail = {"company": "上海冰鲸科技有限公司", "salary_raw": "30k-50k·14薪"}
    enriched = _enrich_from_detail(job, detail, source_name="testerhome")

    assert enriched.company == "上海冰鲸科技有限公司"
    assert enriched.salary == parse_salary("30k-50k·14薪")
    # canonical_id changes (per ADR-0003, latest-wins).
    assert enriched.canonical_id == canonical_id(
        title="测试开发", company="上海冰鲸科技有限公司", city="Shanghai")
    # id is UNCHANGED — job_id is sha1("testerhome:42") regardless of company.
    assert enriched.id == job.id


def test_enrich_no_op_when_detail_empty() -> None:
    job = _make_listing_job()
    enriched = _enrich_from_detail(job, {"company": "", "salary_raw": ""}, source_name="testerhome")
    assert enriched.company is None
    assert enriched.salary == job.salary
    assert enriched.id == job.id
    assert enriched.canonical_id == job.canonical_id


def test_enrich_preserves_listing_salary_when_detail_salary_blank() -> None:
    job = _make_listing_job().model_copy(update={"salary": parse_salary("20k-30k")})
    enriched = _enrich_from_detail(job, {"company": "X公司", "salary_raw": ""},
                                    source_name="testerhome")
    assert enriched.salary == parse_salary("20k-30k")  # not clobbered
    assert enriched.company == "X公司"


def test_enrich_does_not_degrade_parseable_listing_salary_to_unparseable() -> None:
    """Detail wins only when it parses cleanly. If detail salary is e.g.
    '面议' (unparseable) and listing salary is parseable, listing wins."""
    listing_salary = parse_salary("30k-50k")
    assert listing_salary.parsed is True
    job = _make_listing_job().model_copy(update={"salary": listing_salary})

    enriched = _enrich_from_detail(
        job,
        {"company": "Y公司", "salary_raw": "面议"},
        source_name="testerhome",
    )
    assert enriched.salary == listing_salary  # listing preserved
    assert enriched.company == "Y公司"


def test_enrich_uses_detail_salary_when_listing_was_unparseable() -> None:
    """Symmetric case: if listing was unparseable (or absent) and detail
    is unparseable too, accept detail (no information loss, and detail
    raw text may be more informative)."""
    job = _make_listing_job()  # salary.raw="" → parsed=False
    enriched = _enrich_from_detail(
        job,
        {"company": "Z公司", "salary_raw": "面议"},
        source_name="testerhome",
    )
    assert enriched.salary == parse_salary("面议")
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `uv run pytest tests/sources/test_testerhome_detail.py -v`

Expected: 5 new failures — `_enrich_from_detail` not exported.

- [ ] **Step 3: Add `_enrich_from_detail` to `src/jma/sources/testerhome.py`**

Append after `_extract_first_label_value`:

```python
def _enrich_from_detail(job: Job, detail: dict[str, str], source_name: str) -> Job:
    """Return a new Job with company + salary filled from detail.

    Recomputes canonical_id (ADR-0003: latest-wins). Does NOT recompute
    `id` — for sources with an internal_id (TesterHome's /topics/NNN),
    job_id ignores company entirely, so recomputation is dead code that
    masks intent.

    Empty detail values do NOT clobber pre-existing listing data.
    Detail salary wins ONLY when it parses cleanly — never replace a
    parsed=True listing salary with a parsed=False detail salary
    (preserves [[SalaryDisclosure]] parseable status for Phase 4
    aggregations).
    """
    new_company = detail.get("company") or job.company
    new_salary = job.salary
    raw = (detail.get("salary_raw") or "").strip()
    if raw:
        candidate = parse_salary(raw)
        # Detail wins unless it would degrade parseable → unparseable.
        if candidate.parsed or not job.salary.parsed:
            new_salary = candidate
    new_canonical = canonical_id(
        title=job.title, company=new_company, city=job.location.city
    )
    return job.model_copy(update={
        "canonical_id": new_canonical,
        "company": new_company,
        "salary": new_salary,
    })
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `uv run pytest tests/sources/test_testerhome_detail.py -v`

Expected: 9 passed (4 from Task 3 + 5 from this task).

- [ ] **Step 5: Commit**

```bash
git add src/jma/sources/testerhome.py tests/sources/test_testerhome_detail.py
git commit -m "feat(sources): _enrich_from_detail merges detail with don't-downgrade rule (#7)"
```

---

### Task 5: Refactor existing listing fetch into `_fetch_classified` helper (behavior-preserving for tested paths)

**Files:**
- Modify: `src/jma/sources/testerhome.py`

This task extracts the cache-or-fetch → classify → blob/cache plumbing currently inline in the listing loop into a private method. The refactor introduces one **intentional behavior change** that no existing test exercises: a 200 response that classifies as BLOCKED (soft-block marker in body) will no longer write the blob or invoke `on_fetch`. The previous code wrote both before classifying, poisoning the URL cache for 24h. Existing listing tests don't cover this path, so the refactor is observably safe; Task 7 adds an integration test that locks down the new behavior for the detail path.

- [ ] **Step 1: Confirm the existing listing tests pass on `main` before refactoring**

Run: `uv run pytest tests/sources/test_testerhome.py -v`

Expected: all pass. Capture the baseline before touching the code.

- [ ] **Step 2: Add the `_ClassifiedFetch` dataclass and `_fetch_classified` method**

In `src/jma/sources/testerhome.py`:

Add to the imports at the top:

```python
from dataclasses import dataclass

from jma.domain.models import BlockStatus
```

Add the dataclass near the top of the file (after the module-level regexes, before `TesterHomeSource`):

```python
@dataclass(frozen=True)
class _ClassifiedFetch:
    status_code: int
    headers: dict[str, str]
    body: str
    blob_ref: str | None  # None when cache hit was blocked OR classify is non-OK
    block: BlockStatus
```

Add `_fetch_classified` as a method on `TesterHomeSource` (after `__init__`, before `crawl`):

```python
    async def _fetch_classified(self, url: str) -> _ClassifiedFetch:
        """Cache-or-fetch → classify → blob/cache write IFF classify OK.

        Used by both listing-page and detail-page fetches. Never writes
        a blob or calls on_fetch when classify returns non-OK — this
        keeps the URL cache from being poisoned by anti-bot responses
        for the next 24h.
        """
        hit = await self._cache_get(url) if self._cache_get else None
        if hit and hit.status_code == 200 and hit.blob_ref:
            body_text = blobs.read(root=self._root, ref=hit.blob_ref)
            block = classify(
                status_code=200, headers={}, body_text=body_text, cfg=self._cfg
            )
            return _ClassifiedFetch(
                status_code=200, headers={}, body=body_text,
                blob_ref=hit.blob_ref, block=block,
            )

        fetched = await self._http.fetch(url)
        block = classify(
            status_code=fetched.status_code,
            headers=fetched.headers,
            body_text=fetched.body,
            cfg=self._cfg,
        )

        blob_ref: str | None = None
        if block.kind is SourceStatus.OK and fetched.status_code == 200:
            blob_ref = blobs.write(
                root=self._root, source=self.name, url=url, body=fetched.body,
            )
            if self._on_fetch is not None:
                await self._on_fetch(url, fetched.status_code, blob_ref)
        elif self._on_fetch is not None and fetched.status_code != 200:
            # Non-200 (404, 5xx, etc.) still gets a url_cache entry so
            # future runs can see "we tried this URL". 200+block is the
            # case we deliberately skip — see docstring.
            await self._on_fetch(url, fetched.status_code, None)

        return _ClassifiedFetch(
            status_code=fetched.status_code,
            headers=fetched.headers,
            body=fetched.body,
            blob_ref=blob_ref,
            block=block,
        )
```

Add the `classify` import to the top of the file if not already present:

```python
from jma.domain.blockage import classify
```

(It is already imported — see line 13.)

- [ ] **Step 3: Replace the inline listing fetch with a call to `_fetch_classified`**

In `TesterHomeSource.crawl`, replace the block at lines 81–125 (the L1-cache-or-fetch + classify section) with:

```python
            page = await self._fetch_classified(url)
            status_code = page.status_code
            blob_ref = page.blob_ref
            block = page.block
            body_text = page.body

            if block.kind is not SourceStatus.OK:
                if collected:
                    return SourceResult(
                        source=self.name,
                        status=SourceStatus.OK,
                        jobs=tuple(collected),
                        reason=f"partial: stopped at page {n} ({block.kind.value}: {block.reason})",
                        pages_fetched=pages_fetched,
                    )
                return SourceResult(
                    source=self.name,
                    status=block.kind,
                    jobs=(),
                    reason=block.reason,
                    pages_fetched=pages_fetched,
                )
```

The local variables `status_code`, `headers`, `body_text` were used downstream; only `body_text` is still needed (for `_parse_listing`). Drop the now-unused locals.

- [ ] **Step 4: Run the listing test suite to verify refactor is behavior-preserving**

Run: `uv run pytest tests/sources/test_testerhome.py -v`

Expected: all existing tests still PASS.

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest -v`

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/jma/sources/testerhome.py
git commit -m "refactor(sources): extract _fetch_classified for shared fetch+classify+blob plumbing (#7)"
```

---

### Task 6: Wire detail-fetch loop into `TesterHomeSource.crawl`

**Files:**
- Modify: `src/jma/sources/testerhome.py`

The detail loop is a small composition of decisions from grilling:

- Pre-truncate `page_jobs` to `max_jobs - len(collected)` before enrichment — saves N HTTP calls when `max_jobs` is small (Q5).
- Sleep `delay_ms` **before** each detail fetch, not after — consistent inter-request rate; the listing-loop's existing tail sleep handles the last-detail → next-listing transition (Q6).
- Catch only `httpx.HTTPError` (covers `ConnectError`, `TimeoutException`, `ReadTimeout`, `RemoteProtocolError`); debug-log the swallow. Anything else (disk write, DB write) propagates and stops the run via `pipeline.crawl`'s outer handler (Q4).
- `classify()` runs on every detail response. Non-OK detail classification halts further enrichment for the remainder of the listing loop and converts the run to PartialHarvest (Q2). Jobs already collected on prior pages are preserved.

- [ ] **Step 1: Add a module-level logger to `src/jma/sources/testerhome.py`**

Near the top of the file, after the imports:

```python
import logging

_log = logging.getLogger(__name__)
```

- [ ] **Step 2: Add the `_enrich_page` method to `TesterHomeSource`**

After `_fetch_classified`, add:

```python
    async def _enrich_page(
        self, page_jobs: list[Job]
    ) -> tuple[list[Job], str | None]:
        """Run detail-fetch enrichment for one page's jobs.

        Returns (enriched_jobs, halt_reason). When halt_reason is set
        (e.g. a detail page tripped classify()), the caller must treat
        the entire crawl as a PartialHarvest and not fetch further
        listing pages.

        Errors are isolated per-job: a network failure on one detail
        keeps that job at listing-only quality and continues. A classify
        non-OK on any detail halts the rest of this page AND the rest
        of the crawl.
        """
        if not self._cfg.detail.enabled:
            return page_jobs, None

        import httpx

        enriched: list[Job] = []
        halt: str | None = None
        for job in page_jobs:
            if halt is not None:
                enriched.append(job)  # keep as listing-only
                continue

            await self._sleep(self._cfg.rate.delay_ms / 1000.0)

            try:
                page = await self._fetch_classified(job.url)
            except httpx.HTTPError as exc:
                _log.debug("detail fetch network error for %s: %s", job.url, exc)
                enriched.append(job)
                continue

            if page.block.kind is not SourceStatus.OK:
                halt = f"detail block: {page.block.kind.value}: {page.block.reason}"
                enriched.append(job)
                continue

            if page.status_code != 200:
                # Non-200 with classify=OK (e.g. 404 with empty/short body
                # not matching block markers). Keep listing-only.
                enriched.append(job)
                continue

            detail = _parse_detail(page.body, self._cfg)
            enriched.append(_enrich_from_detail(job, detail, source_name=self.name))

        return enriched, halt
```

Move the `import httpx` inside the method or to the top of the file — both are fine; keeping it at the top is more conventional. (Note: `httpx` may not currently be imported in `testerhome.py`. Confirm with `grep "^import httpx" src/jma/sources/testerhome.py` and add it if missing.)

- [ ] **Step 3: Integrate `_enrich_page` into the listing loop with `max_jobs` pre-truncation**

In `TesterHomeSource.crawl`, find the block after region+keyword filtering:

```python
            page_jobs = _filter_region(page_jobs, region)
            page_jobs = _filter_keywords(page_jobs, keywords)
            collected.extend(page_jobs)
```

Replace with:

```python
            page_jobs = _filter_region(page_jobs, region)
            page_jobs = _filter_keywords(page_jobs, keywords)

            # Pre-truncate before detail-enrichment to avoid wasting
            # HTTP calls on jobs we'll discard for max_jobs.
            remaining = max_jobs - len(collected)
            if remaining < len(page_jobs):
                page_jobs = page_jobs[:remaining]

            page_jobs, detail_halt = await self._enrich_page(page_jobs)
            collected.extend(page_jobs)

            if detail_halt is not None:
                return SourceResult(
                    source=self.name,
                    status=SourceStatus.OK,
                    jobs=tuple(collected),
                    reason=f"partial: stopped at page {n} ({detail_halt})",
                    pages_fetched=pages_fetched,
                )
```

- [ ] **Step 4: Run the existing source tests to confirm no regressions on the default (`enabled=false`) path**

Run: `uv run pytest tests/sources -v`

Expected: all existing tests PASS. `_enrich_page` is a no-op when `cfg.detail.enabled` is false, and `max_jobs` pre-truncation is a tightening that doesn't affect tests where `max_jobs` exceeds page size.

- [ ] **Step 5: Commit**

```bash
git add src/jma/sources/testerhome.py
git commit -m "feat(sources): wire detail-page fetch loop into TesterHomeSource.crawl (#7)"
```

---

### Task 7: Integration test — respx-mocked listing + detail end-to-end

**Files:**
- Create: `tests/sources/test_testerhome_with_detail.py`

Four scenarios:
1. Detail enabled, all detail fetches succeed → company + salary populated.
2. Detail disabled → no detail HTTP calls, listing-only behavior unchanged.
3. Detail enabled, detail 404 → fall back to listing-only for that job, crawl still succeeds.
4. Detail enabled, detail returns 200 with block marker → PartialHarvest, no blob written for the blocked URL, no `url_cache` row claiming success for it.

- [ ] **Step 1: Write the integration tests**

Create `tests/sources/test_testerhome_with_detail.py`:

```python
from pathlib import Path

import httpx
import pytest
import respx

from jma.domain.models import SourceStatus
from jma.sources.base import load_source_config
from jma.sources.http import AsyncHttpClient
from jma.sources.testerhome import TesterHomeSource

REPO = Path(__file__).resolve().parents[2]
_CFG_PATH = REPO / "config/sources/testerhome.yaml"
_FIX_DETAIL = REPO / "tests/fixtures/sources/testerhome/detail_basic.html"
_FIX_BLOCKED = REPO / "tests/fixtures/sources/testerhome/detail_blocked.html"

_LISTING_HTML = """
<html><body>
<div class="topics">
  <div class="topic">
    <div class="title"><a href="/topics/42">【上海】测试开发</a></div>
    <span class="time" title="2026-05-22T10:00:00+08:00">2d</span>
  </div>
</div>
</body></html>
"""


def _cfg_detail_on():
    base = load_source_config(_CFG_PATH)
    return base.model_copy(update={"detail": base.detail.model_copy(update={"enabled": True})})


def _cfg_detail_on_with_block_marker():
    base = _cfg_detail_on()
    return base.model_copy(update={
        "content_block_markers": ("系统繁忙，请稍后再试",),
    })


async def _noop_sleep(_s: float) -> None:
    return None


def _make_source(cfg, tmp_path: Path, ac: httpx.AsyncClient) -> TesterHomeSource:
    http = AsyncHttpClient(ac, rate=cfg.rate, sleep=_noop_sleep)
    return TesterHomeSource(cfg=cfg, http=http, data_root=tmp_path, sleep=_noop_sleep)


@respx.mock
@pytest.mark.asyncio
async def test_crawl_with_detail_enabled_populates_company_and_salary(tmp_path: Path) -> None:
    cfg = _cfg_detail_on()
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=_LISTING_HTML)
    )
    respx.get("https://testerhome.com/topics/42").mock(
        return_value=httpx.Response(200, text=_FIX_DETAIL.read_text(encoding="utf-8"))
    )

    async with httpx.AsyncClient() as ac:
        src = _make_source(cfg, tmp_path, ac)
        result = await src.crawl(
            region="Shanghai", keywords=("测试",), max_pages=1, max_jobs=10,
        )

    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.company == "上海冰鲸科技有限公司"
    assert job.salary.raw == "30k-50k·14薪"
    assert job.salary.parsed is True
    assert job.salary.min == 30000
    assert job.salary.max == 50000


@respx.mock
@pytest.mark.asyncio
async def test_crawl_with_detail_disabled_skips_detail_fetch(tmp_path: Path) -> None:
    cfg = load_source_config(_CFG_PATH)  # detail.enabled = False from YAML
    assert cfg.detail.enabled is False

    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=_LISTING_HTML)
    )
    detail_route = respx.get("https://testerhome.com/topics/42").mock(
        return_value=httpx.Response(200, text="should not be called")
    )

    async with httpx.AsyncClient() as ac:
        src = _make_source(cfg, tmp_path, ac)
        result = await src.crawl(
            region="Shanghai", keywords=("测试",), max_pages=1, max_jobs=10,
        )

    assert detail_route.call_count == 0
    assert len(result.jobs) == 1
    assert result.jobs[0].company is None


@respx.mock
@pytest.mark.asyncio
async def test_crawl_with_detail_falls_back_on_detail_404(tmp_path: Path) -> None:
    cfg = _cfg_detail_on()

    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=_LISTING_HTML)
    )
    respx.get("https://testerhome.com/topics/42").mock(
        return_value=httpx.Response(404, text="not found")
    )

    async with httpx.AsyncClient() as ac:
        src = _make_source(cfg, tmp_path, ac)
        result = await src.crawl(
            region="Shanghai", keywords=("测试",), max_pages=1, max_jobs=10,
        )

    # Crawl still succeeds with listing-only data.
    assert result.status == SourceStatus.OK
    assert len(result.jobs) == 1
    assert result.jobs[0].company is None


@respx.mock
@pytest.mark.asyncio
async def test_crawl_with_detail_block_converts_to_partial_harvest(tmp_path: Path) -> None:
    """A 200 detail response containing a content_block_marker must:
      - convert the run to PartialHarvest (reason starts 'partial:'),
      - NOT write a blob for the blocked URL,
      - NOT write a successful url_cache row for the blocked URL.
    """
    cfg = _cfg_detail_on_with_block_marker()

    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=_LISTING_HTML)
    )
    respx.get("https://testerhome.com/topics/42").mock(
        return_value=httpx.Response(200, text=_FIX_BLOCKED.read_text(encoding="utf-8"))
    )

    async with httpx.AsyncClient() as ac:
        src = _make_source(cfg, tmp_path, ac)
        result = await src.crawl(
            region="Shanghai", keywords=("测试",), max_pages=2, max_jobs=10,
        )

    assert result.status == SourceStatus.OK  # partial == status OK + 'partial:' reason
    assert result.reason.startswith("partial:")
    assert "detail block" in result.reason
    # Listing data preserved.
    assert len(result.jobs) == 1
    assert result.jobs[0].company is None
    # No raw blob was written for /topics/42 (detail was blocked).
    raw_dir = tmp_path / "raw" / "testerhome"
    detail_blob_count = sum(1 for _ in raw_dir.rglob("*.html.gz")) if raw_dir.exists() else 0
    # Only the listing page should have a blob.
    assert detail_blob_count == 1
```

- [ ] **Step 2: Run the integration tests**

Run: `uv run pytest tests/sources/test_testerhome_with_detail.py -v`

Expected: 4 passed.

- [ ] **Step 3: Run the entire `tests/sources` directory**

Run: `uv run pytest tests/sources -v`

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add tests/sources/test_testerhome_with_detail.py
git commit -m "test(sources): end-to-end detail-fetch integration tests incl. PartialHarvest on block (#7)"
```

---

### Task 8: Add `--with-detail` CLI flag

**Files:**
- Modify: `src/jma/cli.py`
- Modify or create: `tests/cli/test_crawl.py`

- [ ] **Step 1: Write a failing CLI test**

Create or extend `tests/cli/test_crawl.py`:

```python
from typer.testing import CliRunner

from jma.cli import app


def test_crawl_help_lists_with_detail_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["crawl", "--help"])
    assert result.exit_code == 0
    assert "--with-detail" in result.stdout
```

- [ ] **Step 2: Run the test to confirm it fails**

Run: `uv run pytest tests/cli/test_crawl.py -v`

Expected: FAIL — flag not in help output.

- [ ] **Step 3: Add the flag and wire it through the factory**

In `src/jma/cli.py`:

Change `_factory_for` (around line 36) from:

```python
def _factory_for(source_name: str, data_root: Path):
    cfg = load_source_config(_CFG_DIR / f"{source_name}.yaml")

    def _make(ac: httpx.AsyncClient, on_fetch, cache_get) -> JobSource:
```

to:

```python
def _factory_for(source_name: str, data_root: Path, with_detail: bool):
    cfg = load_source_config(_CFG_DIR / f"{source_name}.yaml")
    if with_detail:
        cfg = cfg.model_copy(update={
            "detail": cfg.detail.model_copy(update={"enabled": True})
        })

    def _make(ac: httpx.AsyncClient, on_fetch, cache_get) -> JobSource:
```

Add a new Typer option in `crawl()` after `no_cache` (around line 86):

```python
    with_detail: bool = typer.Option(
        False, "--with-detail/--no-detail",
        help="Fetch each job's detail page to populate company/salary "
             "(slower; adds N HTTP calls per page).",
    ),
```

Update the factory call inside `_run_all` (around line 102) from:

```python
                source_factory=_factory_for(s_name, data_root),
```

to:

```python
                source_factory=_factory_for(s_name, data_root, with_detail=with_detail),
```

- [ ] **Step 4: Run the CLI test to confirm it passes**

Run: `uv run pytest tests/cli/test_crawl.py -v`

Expected: PASS.

- [ ] **Step 5: Smoke-check the help output manually**

Run: `uv run jma crawl --help`

Expected: `--with-detail / --no-detail` is shown in the option list.

- [ ] **Step 6: Commit**

```bash
git add src/jma/cli.py tests/cli/test_crawl.py
git commit -m "feat(cli): --with-detail flag enables detail-page fetch (#7)"
```

---

### Task 9: Final regression sweep

**Files:** none (verification only).

- [ ] **Step 1: Full test suite**

Run: `uv run pytest`

Expected: all green; `live` marker excluded by default.

- [ ] **Step 2: Lint**

Run: `uv run ruff check . && uv run ruff format --check .`

Expected: no errors. If a step introduced minor style issues, amend the relevant commit.

- [ ] **Step 3: Manual blob/cache check** (only if you have a TesterHome data dir handy and want to validate end-to-end with the real site)

Run: `uv run jma crawl --region Hangzhou --keywords "测试" --max-pages 1 --max-jobs 3 --with-detail -v`

Expected: summary line shows `jobs=3`; spot-check the SQLite DB:

```bash
sqlite3 data/jobs.db "SELECT company, salary_raw FROM jobs ORDER BY fetched_at DESC LIMIT 3;"
```

Expected: most rows now have non-NULL company and non-empty salary_raw. (If the real site blocks or pages are empty, that's an unrelated runtime issue — note it but don't gate the PR on it.)

---

## Self-Review Notes

- **Spec coverage** (from issue body):
  - "Add `detail.body_selector` to YAML" → already present; extended with new selector+pattern fields in Task 1.
  - "Add an optional detail-fetch phase" → Task 6 (`_enrich_page` gated on `cfg.detail.enabled`).
  - "Update `_item_to_job()` (or new `_enrich_from_detail`)" → Task 4 chose the second option to keep `_item_to_job` minimal.
  - "Rate-limit detail fetches per `cfg.rate`" → Task 6 sleeps `delay_ms` **before** each detail fetch.

- **URL cache reuse** → Task 5's `_fetch_classified` calls `self._cache_get` first, then writes a blob + invokes `self._on_fetch` only when classify is OK. Subsequent runs within 24h skip the detail fetch when the previous response was OK; blocked responses do NOT populate the cache.

- **Failure isolation** → Task 6's `_enrich_page` catches `httpx.HTTPError` only (per-job network errors). Disk/DB errors propagate to `pipeline.crawl`'s outer exception handler. Classify-non-OK on a detail page is NOT an exception — it's a normal control-flow signal that halts further enrichment and converts the run to PartialHarvest.

- **canonical_id semantics** → `_enrich_from_detail` recomputes `canonical_id` only. `id` is invariant because `job_id` ignores company when `internal_id` is set (true for TesterHome). ADR-0003 documents the "latest wins" semantics.

- **`max_jobs` respected before detail HTTP** → Task 6 pre-truncates `page_jobs` to `max_jobs - len(collected)` before calling `_enrich_page`. Detail fetches happen only for jobs that will actually be collected.

- **Salary precedence** → Detail wins **only when it parses cleanly**. Listing's parseable salary is never downgraded to unparseable by a later detail value (Task 4, `test_enrich_does_not_degrade_parseable_listing_salary_to_unparseable`).

- **Backwards compat** → `detail.enabled` defaults to false; existing YAMLs load unchanged; default CLI invocation is unchanged. No data migration required.

- **Refactor safety** → Task 5 refactors the listing fetch path. All existing listing tests pass before and after the refactor (Steps 1 and 4). The intentional behavior change (no blob/cache write on 200+block) is unreached by existing tests; Task 7 adds the first test that locks it down (for the detail path; the same code now governs both paths).

- **No placeholder steps.** Every code step is complete enough to apply directly.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-23-issue-7-detail-page-fetch.md`. Three companion docs are required reading before execution:

- [docs/adr/0001-cross-source-dedup-via-canonical-id.md](../../adr/0001-cross-source-dedup-via-canonical-id.md) — `data_quality` deferral.
- [docs/adr/0003-canonical-id-is-latest-wins-not-run-stable.md](../../adr/0003-canonical-id-is-latest-wins-not-run-stable.md) — canonical_id stability rule.
- [CONTEXT.md](../../../CONTEXT.md) — PartialHarvest covers detail-fetch blocks.
