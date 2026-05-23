# Cheaper 5xx Retries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HTTP 5xx retries in `AsyncHttpClient.fetch` cheaper (default 1 retry) while keeping 429 retries unchanged (default 3 retries with exponential backoff).

**Architecture:** Add a new frozen-pydantic field `max_retries_5xx: int = 1` to `RateConfig`. In `AsyncHttpClient.fetch`, split the retry-budget branch by status code: 429 keeps `rate.max_retries`; status >= 500 uses `rate.max_retries_5xx`. The backoff curve (`backoff_base_s ** attempts`) stays identical — only the budget changes per class. Default of `1` preserves every existing `config/sources/*.yaml` (no YAML edits required).

**Tech Stack:** Python 3.12, pydantic v2 (frozen models), httpx + respx for HTTP tests, pytest-asyncio (`auto` mode), uv for env/test/lint.

**Rationale for the asymmetry (lock this in code review):**
- **429** = "back off, server is rate-limiting you" → exponential retry with several attempts is correct; the budget gives the server time to recover.
- **5xx** on a single resource path = overwhelmingly "this resource is permanently broken server-side"; adjacent URLs return 200 throughout. One quick retry catches the rare true transient; more is wasted wall-clock (the motivating bug burned ~14s on `/topics/43915`).

**Out of scope:** `Retry-After` honoring on 429; per-source retry overrides; circuit-breaker / quarantine; any change outside `src/jma/sources/` + `tests/sources/`.

---

## File Structure

- **Modify** `src/jma/sources/base.py` — add `max_retries_5xx: int = 1` to `RateConfig`.
- **Modify** `src/jma/sources/http.py` — split retry budget by status class inside `AsyncHttpClient.fetch`.
- **Modify** `tests/sources/test_http.py` — add two new tests covering the new 5xx-cheap path and explicit `max_retries_5xx` override; existing tests stay green untouched.

---

## Task 1: Add `max_retries_5xx` field to `RateConfig`

**Files:**
- Modify: `/Users/snow/Documents/Repository/job-market-agent/src/jma/sources/base.py:33-37`
- Test: (no new test file — covered indirectly by Task 2/3 + pydantic's own validation)

- [ ] **Step 1: Write a failing test asserting the new default**

Add this test to `/Users/snow/Documents/Repository/job-market-agent/tests/sources/test_http.py` (append at end of file):

```python
def test_rate_config_default_max_retries_5xx() -> None:
    """Default 5xx retry budget is 1; default 429 budget stays at 3."""
    rate = RateConfig()
    assert rate.max_retries_5xx == 1
    assert rate.max_retries == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/sources/test_http.py::test_rate_config_default_max_retries_5xx -v`
Expected: FAIL with `AttributeError: 'RateConfig' object has no attribute 'max_retries_5xx'` (or pydantic equivalent).

- [ ] **Step 3: Add the field to `RateConfig`**

Edit `/Users/snow/Documents/Repository/job-market-agent/src/jma/sources/base.py`. Replace:

```python
class RateConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    delay_ms: int = 800
    max_retries: int = 3
    backoff_base_s: int = 2
```

with:

```python
class RateConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    delay_ms: int = 800
    max_retries: int = 3
    backoff_base_s: int = 2
    max_retries_5xx: int = 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/sources/test_http.py::test_rate_config_default_max_retries_5xx -v`
Expected: PASS.

- [ ] **Step 5: Confirm no existing test regressed**

Run: `uv run pytest tests/sources/ -v`
Expected: All sources tests pass (the existing `test_fetch_5xx_exhausts_retries` still passes because `http.py` hasn't been touched yet — it still uses `max_retries`).

- [ ] **Step 6: Commit**

```bash
git add src/jma/sources/base.py tests/sources/test_http.py
git commit -m "feat(sources): add max_retries_5xx field to RateConfig (default 1)"
```

---

## Task 2: Update the existing 5xx exhaustion test to reflect the new default behavior

**Files:**
- Modify: `/Users/snow/Documents/Repository/job-market-agent/tests/sources/test_http.py:68-80`

**Why:** The existing `test_fetch_5xx_exhausts_retries` test currently asserts `attempts == 4` (initial + 3 retries) under `max_retries=3`. After Task 3 lands, 5xx will use `max_retries_5xx=1` by default, so the same `RateConfig(max_retries=3, ...)` will produce `attempts == 2`. We update the test FIRST (red), then Task 3 makes it green.

- [ ] **Step 1: Edit the existing 5xx test to reflect the new contract**

In `/Users/snow/Documents/Repository/job-market-agent/tests/sources/test_http.py`, replace the entire `test_fetch_5xx_exhausts_retries` function (currently lines 68-80):

```python
@respx.mock
@pytest.mark.asyncio
async def test_fetch_5xx_exhausts_retries(fake_sleep, sleeps) -> None:
    """5xx uses the (cheaper) max_retries_5xx budget, not max_retries."""
    route = respx.get("https://example.com/x")
    route.side_effect = [httpx.Response(503, text="")] * 4
    async with httpx.AsyncClient() as ac:
        client = AsyncHttpClient(
            ac,
            rate=RateConfig(max_retries=3, backoff_base_s=2),  # default max_retries_5xx=1
            sleep=fake_sleep,
        )
        result = await client.fetch("https://example.com/x")
    assert result.status_code == 503
    # Default max_retries_5xx=1 → initial attempt + 1 retry = 2 attempts.
    assert result.attempts == 2
    assert sleeps == [2]  # one backoff: 2^1
```

- [ ] **Step 2: Run the test to verify it fails (red)**

Run: `uv run pytest tests/sources/test_http.py::test_fetch_5xx_exhausts_retries -v`
Expected: FAIL — current `http.py` still uses `max_retries=3` for 5xx, so `attempts == 4` and `sleeps == [2, 4, 8]`.

- [ ] **Step 3: Do NOT commit yet**

Leave the test red. Task 3 will make it green by editing `http.py`.

---

## Task 3: Split retry budget by status class in `AsyncHttpClient.fetch`

**Files:**
- Modify: `/Users/snow/Documents/Repository/job-market-agent/src/jma/sources/http.py:43-56`

- [ ] **Step 1: Implement the budget split**

Edit `/Users/snow/Documents/Repository/job-market-agent/src/jma/sources/http.py`. Replace the entire `fetch` method (currently lines 43-56):

```python
    async def fetch(self, url: str) -> FetchResult:
        attempts = 0
        while True:
            attempts += 1
            resp = await self._client.get(url)
            status = resp.status_code
            if status == 429:
                budget = self._rate.max_retries
            elif status >= 500:
                budget = self._rate.max_retries_5xx
            else:
                budget = 0  # no retry for 2xx/3xx/4xx (excluding 429)
            if budget == 0 or attempts > budget:
                return FetchResult(
                    status_code=status,
                    headers=dict(resp.headers),
                    body=resp.text,
                    attempts=attempts,
                )
            await self._sleep(self._rate.backoff_base_s**attempts)
```

Also update the module docstring at the top of the file (lines 1-8) to reflect the asymmetry. Replace:

```python
"""Async HTTP wrapper with retry/backoff (spec §6 + slice 1.6).

Retry policy:
- status 429 or >= 500 → retry up to max_retries with exponential backoff
  (backoff_base_s ** attempt_index, starting at 1).
- status 401/403/other non-200 → return immediately (no retry).
- network errors propagate as httpx exceptions; callers may catch.
"""
```

with:

```python
"""Async HTTP wrapper with retry/backoff (spec §6 + slice 1.6).

Retry policy:
- status 429 → retry up to `rate.max_retries` (default 3) with exponential
  backoff (`backoff_base_s ** attempt_index`, starting at 1).
- status >= 500 → retry up to `rate.max_retries_5xx` (default 1) with the
  same exponential backoff curve. Asymmetry is intentional: 429 means
  "back off, server is rate-limiting" (retry generously); 5xx on a single
  resource path is overwhelmingly a permanent server-side breakage
  (retry once for a true transient hiccup, then move on).
- status 401/403/other non-200 → return immediately (no retry).
- network errors propagate as httpx exceptions; callers may catch.
"""
```

- [ ] **Step 2: Run the Task-2 red test to verify it now passes**

Run: `uv run pytest tests/sources/test_http.py::test_fetch_5xx_exhausts_retries -v`
Expected: PASS — `attempts == 2`, `sleeps == [2]`.

- [ ] **Step 3: Run the full HTTP test file to verify no regressions**

Run: `uv run pytest tests/sources/test_http.py -v`
Expected: All four existing tests PASS (`test_fetch_200_first_try`, `test_fetch_403_returned_without_retry`, `test_fetch_429_then_200_with_backoff`, `test_fetch_5xx_exhausts_retries`) plus `test_rate_config_default_max_retries_5xx` from Task 1.

- [ ] **Step 4: Commit Task 2 + Task 3 together**

```bash
git add src/jma/sources/http.py tests/sources/test_http.py
git commit -m "feat(sources): use cheaper 5xx retry budget (max_retries_5xx, default 1)

5xx on a single resource path is overwhelmingly a permanent server-side
breakage rather than a transient hiccup. Use a separate, smaller retry
budget for 5xx (default 1) while leaving 429 unchanged (default 3) —
429 means 'back off, I'm rate-limiting you' and deserves the larger budget."
```

---

## Task 4: Add a test pinning the 429 path stays at 3 retries

**Files:**
- Modify: `/Users/snow/Documents/Repository/job-market-agent/tests/sources/test_http.py` (append)

**Why:** Lock in the asymmetry as a regression test. A future refactor that accidentally unifies the two budgets must trip a test.

- [ ] **Step 1: Write a failing test for 429 exhaustion under the new field**

Append to `/Users/snow/Documents/Repository/job-market-agent/tests/sources/test_http.py`:

```python
@respx.mock
@pytest.mark.asyncio
async def test_fetch_429_uses_max_retries_not_max_retries_5xx(fake_sleep, sleeps) -> None:
    """429 keeps the large max_retries budget even when max_retries_5xx is small."""
    route = respx.get("https://example.com/x")
    route.side_effect = [httpx.Response(429, text="")] * 4  # initial + 3 retries
    async with httpx.AsyncClient() as ac:
        client = AsyncHttpClient(
            ac,
            rate=RateConfig(max_retries=3, max_retries_5xx=1, backoff_base_s=2),
            sleep=fake_sleep,
        )
        result = await client.fetch("https://example.com/x")
    assert result.status_code == 429
    # 429 uses max_retries=3 → 4 total attempts, three backoffs.
    assert result.attempts == 4
    assert sleeps == [2, 4, 8]
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `uv run pytest tests/sources/test_http.py::test_fetch_429_uses_max_retries_not_max_retries_5xx -v`
Expected: PASS — this is a regression-pin test, the behavior is already correct after Task 3.

(If it FAILs, the budget split in Task 3 is wrong — fix `http.py` before continuing.)

- [ ] **Step 3: Commit**

```bash
git add tests/sources/test_http.py
git commit -m "test(sources): pin 429 retry budget stays at max_retries (regression guard)"
```

---

## Task 5: Add a test for an explicit `max_retries_5xx` override

**Files:**
- Modify: `/Users/snow/Documents/Repository/job-market-agent/tests/sources/test_http.py` (append)

**Why:** Acceptance criterion #3 says the field must be configurable. Pin that behavior with a test using `max_retries_5xx=2`.

- [ ] **Step 1: Write the test**

Append to `/Users/snow/Documents/Repository/job-market-agent/tests/sources/test_http.py`:

```python
@respx.mock
@pytest.mark.asyncio
async def test_fetch_5xx_respects_explicit_max_retries_5xx(fake_sleep, sleeps) -> None:
    """An explicit max_retries_5xx overrides the default of 1."""
    route = respx.get("https://example.com/x")
    route.side_effect = [httpx.Response(500, text="")] * 4
    async with httpx.AsyncClient() as ac:
        client = AsyncHttpClient(
            ac,
            rate=RateConfig(max_retries=3, max_retries_5xx=2, backoff_base_s=2),
            sleep=fake_sleep,
        )
        result = await client.fetch("https://example.com/x")
    assert result.status_code == 500
    # max_retries_5xx=2 → initial + 2 retries = 3 attempts.
    assert result.attempts == 3
    assert sleeps == [2, 4]  # 2^1, 2^2
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `uv run pytest tests/sources/test_http.py::test_fetch_5xx_respects_explicit_max_retries_5xx -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/sources/test_http.py
git commit -m "test(sources): pin explicit max_retries_5xx override behavior"
```

---

## Task 6: Final verification — full suite + lint

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest`
Expected: All tests PASS — original 160 tests plus the four new tests added in Tasks 1, 4, 5 and the rewritten test from Task 2.

- [ ] **Step 2: Run ruff lint**

Run: `uv run ruff check .`
Expected: `All checks passed!` (or no output with exit code 0).

- [ ] **Step 3: Run ruff format check (no changes expected)**

Run: `uv run ruff format --check .`
Expected: `X files already formatted` with exit code 0. If it reports unformatted files, run `uv run ruff format .` then `git add -u && git commit -m "style: ruff format"`.

- [ ] **Step 4: No commit needed if all green**

If steps 1-3 are all green, the feature is done. The plan's acceptance criteria (spec §Acceptance criteria 1-7) are all satisfied:

1. Single 500 URL consumes only 2 attempts (Task 2 test pins this).
2. 429 still uses `max_retries=3` (Task 4 test pins this).
3. `RateConfig.max_retries_5xx` exists with default `1` (Task 1 test pins this; no YAML changes required).
4. `FetchResult.attempts` count reflects new budget (all tests assert exact attempt counts).
5. Full suite green (Step 1 above).
6. Ruff clean (Steps 2-3 above).
7. No domain-layer changes — all edits live in `src/jma/sources/` and `tests/sources/`.
