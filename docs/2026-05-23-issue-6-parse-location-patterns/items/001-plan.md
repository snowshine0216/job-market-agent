# Issue #6 — parse_location() coverage for non-bracket city patterns

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `parse_location()` so TesterHome titles that use Chinese parentheses (`（武汉）`), a `base 城市` prefix, or a bare city token at the start of the title yield a populated `location_city` instead of `None`. Workplace semantics only — see the [[Location]] entry in [CONTEXT.md](../../../CONTEXT.md) and the precedence rules in [ADR 0003](../../adr/0003-location-probe-precedence.md).

**Architecture:** Pure-domain change in [src/jma/domain/normalize.py](../../../src/jma/domain/normalize.py). The existing `【city·district】` path stays first; three new fallback probes are tried in order (`paren` → `base X` → bare scan), each delegating to a shared `_build_location()` helper. No source/storage/pipeline files are touched.

**Tech Stack:** Python 3.12, pydantic v2 frozen models, pytest, ruff. Tests via `uv run pytest`.

**Issue link:** [snowshine0216/job-market-agent#6](https://github.com/snowshine0216/job-market-agent/issues/6)

---

## Design decisions (resolved during grilling 2026-05-23)

These shape the regexes and helper code in the tasks below. Each was a live design choice, not a default — keep them in view while implementing.

1. **Probe precedence is fixed: bracket → paren → base-prefix → bare-scan.** First hit wins. See [ADR 0003](../../adr/0003-location-probe-precedence.md).
2. **Paren regex is restrictive — CJK-only content.** `（Remote）`/`(NYC)`/`(2025)` must not match. The pattern accepts only `city` or `city·district` shaped CJK strings.
3. **`base` keyword requires a non-letter boundary on the left.** `database`, `firebase`, `codebase` must not trigger the probe.
4. **Bare-scan returns the *leftmost* city by string position**, not dict-insertion order. Stable under any `_CITY_PINYIN` reordering.
5. **Unknown native city → no district pollution.** When a probe matches the shape but the city isn't in `_CITY_PINYIN`, return `Location(country="CN", city=None, district=None, work_mode=...)`. The old "stuff native form into district" trick is removed (in both the existing bracket path and the new probes).
6. **Workplace semantics only.** `Location.city` is the workplace, never company HQ. Company-name-as-city extraction is explicitly out of scope and noted as follow-up.

---

## File Structure

- Modify: [src/jma/domain/normalize.py](../../../src/jma/domain/normalize.py)
  - Add `_RE_PAREN`, `_RE_BASE_PREFIX` module-level regexes.
  - Add `_build_location(city_native, district, work_mode) -> Location` helper (no district fallback).
  - Add `_scan_bare_city(s) -> str | None` helper (leftmost-wins).
  - Refactor `parse_location()` to try bracket → paren → base-prefix → bare-scan in order.

- Modify: [tests/domain/test_normalize_location.py](../../../tests/domain/test_normalize_location.py)
  - Add tests for the four documented patterns from issue #6.
  - Add regression tests for the false-positive guards (English parens, `database`, leftmost-wins).
  - Add a test for unknown-city → `district=None` (locks the Q6 decision).

---

## Tasks

### Task 1: Failing tests — four documented patterns + guard tests

**Files:**
- Modify: `tests/domain/test_normalize_location.py`

- [ ] **Step 1: Append the new tests after the existing `test_no_brackets_no_city`**

Add the following functions. Note: there is **no** `test_company_name_city_substring_still_extracted` — that case asks bare-scan to act on a company-HQ string, which contradicts the workplace-only definition of `Location.city` (see [CONTEXT.md](../../../CONTEXT.md)). It's tracked separately as the follow-up at the end of this plan.

```python
# Four patterns from issue #6 ---------------------------------------------

def test_chinese_paren_city() -> None:
    loc = parse_location("招聘中高级测试工程师（武汉）")
    assert loc.city == "Wuhan"
    assert loc.country == "CN"
    assert loc.district is None


def test_chinese_paren_city_district() -> None:
    loc = parse_location("招聘高级开发（杭州·余杭）")
    assert loc.city == "Hangzhou"
    assert loc.district == "余杭"
    assert loc.country == "CN"


def test_base_prefix_city() -> None:
    loc = parse_location("APP测试工程师热招中！base 北京")
    assert loc.city == "Beijing"
    assert loc.country == "CN"


def test_bare_city_at_start() -> None:
    loc = parse_location("深圳招聘~AI独角兽急招测试")
    assert loc.city == "Shenzhen"
    assert loc.country == "CN"


# Guard tests — must NOT extract a city ----------------------------------

def test_english_paren_does_not_match() -> None:
    # ASCII parens around English content must not trip the paren probe.
    loc = parse_location("Senior Backend Engineer (Remote)")
    assert loc.city is None
    assert loc.district is None
    assert loc.country is None
    # work_mode is REMOTE via the existing English-remote token detection.
    assert loc.work_mode is WorkMode.REMOTE


def test_database_does_not_trigger_base_prefix() -> None:
    # "Database" contains "base" — the base-prefix probe must require a
    # non-letter boundary on the left.
    loc = parse_location("资深 Database 测试工程师")
    assert loc.city is None
    assert loc.district is None


def test_bare_scan_leftmost_city_wins() -> None:
    # Multiple known cities — leftmost in the string wins (not dict order).
    loc = parse_location("深圳/广州招聘 AI 工程师")
    assert loc.city == "Shenzhen"


def test_unknown_native_city_in_brackets_yields_none_district() -> None:
    # 厦门 is a real city but not yet in _CITY_PINYIN. The bracket shape
    # matches, but we must NOT stuff "厦门" into the district field.
    loc = parse_location("【厦门】Senior QA")
    assert loc.city is None
    assert loc.district is None
    assert loc.country == "CN"
```

- [ ] **Step 2: Run tests to confirm the right ones fail**

Run: `uv run pytest tests/domain/test_normalize_location.py -v`

Expected:
- The five pre-existing tests still PASS.
- `test_chinese_paren_city`, `test_chinese_paren_city_district`, `test_base_prefix_city`, `test_bare_city_at_start` FAIL (current code returns `None`).
- `test_english_paren_does_not_match` already PASSES (no paren probe exists yet, so nothing matches it incorrectly).
- `test_database_does_not_trigger_base_prefix` already PASSES (same reason).
- `test_bare_scan_leftmost_city_wins` FAILS (no bare-scan yet).
- `test_unknown_native_city_in_brackets_yields_none_district` FAILS — current code returns `district="厦门"`. This catches the Q6 decision.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/domain/test_normalize_location.py
git commit -m "test(domain): cover paren/base-prefix/bare-city location patterns (#6)"
```

---

### Task 2: Introduce `_build_location()` and fix unknown-city handling

**Files:**
- Modify: `src/jma/domain/normalize.py`

This task does two things in one commit because they're inseparable: the refactor extracts the helper, *and* the helper drops the "stuff unknown city into district" fallback. Running them separately would leave the bracket path subtly wrong between commits.

- [ ] **Step 1: Add the helper above `parse_location`**

Insert after the `_REMOTE_TOKENS_EN` constant (around line 141), before `def parse_location`:

```python
def _build_location(
    city_native: str,
    district: str | None,
    work_mode: WorkMode,
) -> Location:
    """Map a native-Chinese city string to a Location using _CITY_PINYIN.

    Unknown native cities yield city=None, district=None — we do NOT stuff
    the native form into `district`. See CONTEXT.md (Location) and
    docs/adr/0003-location-probe-precedence.md.
    """
    city_native = city_native.strip()
    if city_native == "":
        return Location(work_mode=work_mode)
    if city_native in _REMOTE_TOKENS_CN:
        return Location(work_mode=WorkMode.REMOTE)
    city = _CITY_PINYIN.get(city_native)
    if city is None:
        return Location(country="CN", city=None, district=None, work_mode=work_mode)
    return Location(country="CN", city=city, district=district, work_mode=work_mode)
```

- [ ] **Step 2: Replace the bracket-branch body in `parse_location` to delegate**

Replace the block currently spanning lines 158–170 (from `inside = m["inside"].strip()` through `return Location(country="CN", city=city, district=district, work_mode=work_mode)`) with:

```python
    inside = m["inside"].strip()
    parts = [p.strip() for p in inside.split("·") if p.strip()]
    city_native = parts[0] if parts else ""
    district = parts[1] if len(parts) > 1 else None
    return _build_location(city_native, district, work_mode)
```

- [ ] **Step 3: Run the location suite**

Run: `uv run pytest tests/domain/test_normalize_location.py -v`

Expected:
- The five **original** tests PASS (the bracket-known-city path is unchanged in behavior).
- `test_unknown_native_city_in_brackets_yields_none_district` NOW PASSES (the helper no longer pollutes `district`).
- The four pattern tests and `test_bare_scan_leftmost_city_wins` still FAIL.
- `test_english_paren_does_not_match` and `test_database_does_not_trigger_base_prefix` still PASS.

- [ ] **Step 4: Commit**

```bash
git add src/jma/domain/normalize.py
git commit -m "refactor(domain): extract _build_location, drop district fallback (#6)"
```

---

### Task 3: Add Chinese-paren probe (restrictive content class)

**Files:**
- Modify: `src/jma/domain/normalize.py`

- [ ] **Step 1: Add the paren regex next to `_RE_BRACKET`**

Replace the line:

```python
_RE_BRACKET = re.compile(r"【\s*(?P<inside>[^】]+?)\s*】")
```

with:

```python
_RE_BRACKET = re.compile(r"【\s*(?P<inside>[^】]+?)\s*】")
# After NFKC, full-width parens (（ ）) fold to ASCII ( ). Match only
# CJK-shaped content — "city" or "city·district" — to avoid mis-firing
# on English parens like "(Remote)" or "(NYC)". See ADR 0003.
_RE_PAREN = re.compile(r"[(]\s*(?P<inside>[一-鿿]{2,4}(?:·[一-鿿]{2,6})?)\s*[)]")
```

- [ ] **Step 2: Wire the paren probe into `parse_location` after the bracket miss**

Replace the block:

```python
    m = _RE_BRACKET.search(s)
    if not m:
        return Location(work_mode=work_mode)
```

with:

```python
    m = _RE_BRACKET.search(s)
    if m is None:
        m = _RE_PAREN.search(s)
    if m is None:
        return Location(work_mode=work_mode)
```

The downstream block (`inside = m["inside"].strip()` etc.) is unchanged — both regexes expose the same `inside` group.

- [ ] **Step 3: Run the new paren tests**

Run: `uv run pytest tests/domain/test_normalize_location.py -v`

Expected:
- `test_chinese_paren_city` and `test_chinese_paren_city_district` NOW PASS.
- `test_english_paren_does_not_match` STILL PASSES (restrictive content class rejects `Remote`).
- All bracket tests still PASS.
- `test_base_prefix_city`, `test_bare_city_at_start`, `test_bare_scan_leftmost_city_wins` still FAIL.

- [ ] **Step 4: Commit**

```bash
git add src/jma/domain/normalize.py
git commit -m "feat(domain): parse_location handles （city） and （city·district） parens (#6)"
```

---

### Task 4: Add `base X` prefix probe (with word-boundary guard)

**Files:**
- Modify: `src/jma/domain/normalize.py`

- [ ] **Step 1: Add the regex**

Immediately below `_RE_PAREN`, add:

```python
# "base 北京" / "BASE 上海" — 2-4 CJK chars after the keyword.
# Lookbehind rejects "database", "firebase", "codebase". The `\s+`
# requires at least one separator (matches real TesterHome usage and
# keeps "base" from gluing onto an unrelated CJK token).
_RE_BASE_PREFIX = re.compile(
    r"(?<![A-Za-z])base\s+(?P<city>[一-鿿]{2,4})",
    re.IGNORECASE,
)
```

- [ ] **Step 2: Try base-prefix after bracket and paren both miss**

Replace the trailing region of `parse_location` (everything from `m = _RE_BRACKET.search(s)` to the end of the function) with:

```python
    m = _RE_BRACKET.search(s)
    if m is None:
        m = _RE_PAREN.search(s)
    if m is not None:
        inside = m["inside"].strip()
        parts = [p.strip() for p in inside.split("·") if p.strip()]
        city_native = parts[0] if parts else ""
        district = parts[1] if len(parts) > 1 else None
        return _build_location(city_native, district, work_mode)

    m = _RE_BASE_PREFIX.search(s)
    if m is not None:
        return _build_location(m["city"], None, work_mode)

    return Location(work_mode=work_mode)
```

- [ ] **Step 3: Run the new base-prefix test**

Run: `uv run pytest tests/domain/test_normalize_location.py -v`

Expected:
- `test_base_prefix_city` NOW PASSES.
- `test_database_does_not_trigger_base_prefix` STILL PASSES.
- `test_bare_city_at_start` and `test_bare_scan_leftmost_city_wins` still FAIL.

- [ ] **Step 4: Commit**

```bash
git add src/jma/domain/normalize.py
git commit -m "feat(domain): parse_location handles 'base <city>' prefix (#6)"
```

---

### Task 5: Add bare-city scan (leftmost-wins)

**Files:**
- Modify: `src/jma/domain/normalize.py`

- [ ] **Step 1: Add `_scan_bare_city` immediately above `def parse_location`**

```python
def _scan_bare_city(s: str) -> str | None:
    """Return the native city whose first occurrence in `s` is leftmost.

    The tiebreak is *string position*, not dict-insertion order — stable
    under any `_CITY_PINYIN` reordering. See ADR 0003.

    Lowest-priority probe: only runs after bracket, paren, and
    base-prefix all miss.
    """
    best_native: str | None = None
    best_pos = len(s) + 1
    for native in _CITY_PINYIN:
        pos = s.find(native)
        if pos != -1 and pos < best_pos:
            best_pos = pos
            best_native = native
    return best_native
```

- [ ] **Step 2: Use it as the final probe in `parse_location`**

Replace the trailing block:

```python
    m = _RE_BASE_PREFIX.search(s)
    if m is not None:
        return _build_location(m["city"], None, work_mode)

    return Location(work_mode=work_mode)
```

with:

```python
    m = _RE_BASE_PREFIX.search(s)
    if m is not None:
        return _build_location(m["city"], None, work_mode)

    bare = _scan_bare_city(s)
    if bare is not None:
        return _build_location(bare, None, work_mode)

    return Location(work_mode=work_mode)
```

- [ ] **Step 3: Run the full file — all tests must pass**

Run: `uv run pytest tests/domain/test_normalize_location.py -v`

Expected: 12 passed (5 original + 4 pattern + 3 guard, all green).

- [ ] **Step 4: Run the whole domain suite to catch unintended fallout**

Run: `uv run pytest tests/domain -v`

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add src/jma/domain/normalize.py
git commit -m "feat(domain): parse_location bare-city fallback scan, leftmost wins (#6)"
```

---

### Task 6: Lint + final regression

**Files:** none (verification only).

- [ ] **Step 1: Lint**

Run: `uv run ruff check . && uv run ruff format --check .`

Expected: no errors.

- [ ] **Step 2: Full test suite**

Run: `uv run pytest`

Expected: all green (the `live` marker stays excluded by default per `pyproject.toml`).

- [ ] **Step 3: If lint or tests fail, fix and amend the last relevant commit** — do NOT commit lint fixes in a separate noise commit.

---

## Self-Review Notes

- **Spec coverage:** Issue #6 lists four missing patterns (`（city）`, `base city`, bare city at start, city inside company name). Tasks 3–5 implement the first three. The fourth is reframed as out-of-scope per the workplace-semantics decision in CONTEXT.md and tracked as a follow-up below.
- **Precedence guard:** `【…】` > `（…）` > `base X` > bare-scan, encoded as ordered `if` blocks in `parse_location`. Locked in [ADR 0003](../../adr/0003-location-probe-precedence.md).
- **False-positive guards have tests, not just comments:** `test_english_paren_does_not_match` covers the `(Remote)`/`(NYC)` family; `test_database_does_not_trigger_base_prefix` covers the `database`/`firebase` family; `test_bare_scan_leftmost_city_wins` locks the dict-order-independent tiebreak.
- **Unknown city does not pollute district:** the Q6 decision is enforced by `test_unknown_native_city_in_brackets_yields_none_district`. This is a behavior change from the previous code — the old bracket path stuffed `厦门` into `district`; the new one returns `district=None`.
- **No placeholder code paths.** Every step contains the full code or command needed.

---

## Follow-ups (out of scope for this PR)

1. **Expand `_CITY_PINYIN` vocabulary.** Current set covers 11 first-tier cities. TesterHome routinely posts from 厦门, 青岛, 合肥, 长沙, 天津, 郑州, 苏州 (already in), 无锡, 宁波, etc. Adding cities is a data-only change with no semantic implications (per ADR 0003), but choosing *which* cities and on *what evidence* deserves its own issue. Each addition flips `test_unknown_native_city_in_brackets_yields_none_district`-style cases from `city=None` to `city=<Pinyin>`.
2. **Company-city extraction.** The original issue listed `测试开发 - 上海冰鲸科技有限公司` as a pattern to support. Per the [[Location]] entry in CONTEXT.md, `Location.city` means *workplace*, not company HQ — so this is a different signal that needs a different field (e.g. `Location.company_city`) and a different probe (regex for `<city><词>(科技|网络|...)有限公司`). Open as a separate issue if/when downstream analytics actually need company-HQ info.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-23-issue-6-parse-location-patterns.md`.
