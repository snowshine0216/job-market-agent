# Issue #10 — first-known-city wins (parse_location) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change `parse_location()` so the bracket / paren / base-prefix probes fall through when their captured CJK token is not a known city in `_CITY_PINYIN`, recovering common patterns like `（高级）测试 base 北京` (currently → `city=None`, expected → `city="Beijing"`).

**Architecture:** A small refactor of one pure function plus one new shared helper in `src/jma/domain/normalize.py`. Three near-duplicate probe blocks collapse into one helper that returns `Location | None` (None = fall through). `work_mode` extraction stays at the top of `parse_location()` so it survives every probe miss. Bare-scan is unchanged. `_CITY_PINYIN` is unchanged.

**Tech Stack:** Python 3.12, pydantic v2 (frozen models), pytest 8 + pytest-asyncio (auto), ruff. All commands go through `uv run …` — never use bare `python`, `pip`, or `pytest`.

**Spec source:** `docs/2026-05-23-issue-10-non-city-cjk-tokens/items/001-spec.md` (Issue #10).

**Spec ambiguity resolved (noted here so impl agent has the answer):**
The spec lists a "stretch" acceptance case `base 团队 招聘 北京站 → city=Beijing` (note the trailing `→ city=Beijing (if scope allows)`). This case requires changing `_scan_bare_city`'s substring behaviour to match `北京` inside `北京站`, which `_scan_bare_city` *already* does via `s.find(native)`. The case therefore works automatically once the base-prefix probe falls through (because `团队` is not in `_CITY_PINYIN`). It IS in scope as a passing test; no change to `_scan_bare_city` is required.

---

## Acceptance criteria (restated from spec, must all hold at the end)

1. **`（高级）测试工程师 base 北京`** → `city == "Beijing"` (was `None`).
2. **`（资深）开发 base 上海`** → `city == "Shanghai"`.
3. **`（实习）数据分析师 base 杭州`** → `city == "Hangzhou"`.
4. **`（兼职）前端 base 深圳`** → `city == "Shenzhen"`.
5. **`（兼职/实习）后端 base 广州`** → `city == "Guangzhou"`.
6. **`【高级】QA base 成都`** → `city == "Chengdu"` (bracket non-city, base-prefix known city).
7. **`base 团队 招聘 北京站`** → `city == "Beijing"` (base-prefix non-city, bare-scan known city; substring match into `北京站` is fine — `_scan_bare_city` unchanged).
8. Existing tests in `tests/domain/test_normalize_location.py` still pass — in particular `test_unknown_native_city_in_brackets_yields_none_district` (no probe fall-through silently fabricates a city when nothing matches), `test_bare_city_at_start`, `test_bare_scan_leftmost_city_wins`, `test_chinese_paren_city`, `test_base_prefix_city`, `test_base_prefix_city_followed_by_cjk`, `test_base_prefix_unknown_city_followed_by_cjk`, `test_english_paren_does_not_match`, `test_database_does_not_trigger_base_prefix`.
9. `work_mode` continues to be extracted independently — e.g. a `（高级）远程` title with no known city should still yield `work_mode=REMOTE` and `city=None`.
10. New ADR added at `docs/adr/0004-location-probe-first-known-city-wins.md` marking ADR `0003-location-probe-precedence.md` as superseded.
11. `0003-location-probe-precedence.md` status updated to `Superseded by 0004` with a forward link.
12. `CONTEXT.md` `[[Location]]` entry mentions the new precedence rule and links the new ADR.
13. `uv run ruff check .` passes clean.
14. `uv run ruff format .` produces no diff (impl agent runs it as part of the work).
15. `uv run pytest` is fully green (live tests excluded by default per `pyproject.toml`).

## Out of scope (DO NOT change)

- Adding cities to `_CITY_PINYIN` (vocabulary stays as-is — `北京/上海/杭州/深圳/广州/南京/成都/苏州/武汉/西安/重庆`).
- Changing `_scan_bare_city` (the substring-matching behaviour is documented behaviour, see `test_bare_city_at_start` and `test_bare_scan_leftmost_city_wins`).
- The `work_mode` regex / token set.
- Any storage / source / pipeline / CLI changes.
- Closing GitHub issue #10 (the orchestrator handles this after merge).

## File map (what gets touched)

| Path | Change |
|---|---|
| `tests/domain/test_normalize_location.py` | **Modify** — add 7 adversarial tests (steps 1–2) and 1 work-mode-preserved test (step 1). |
| `src/jma/domain/normalize.py` | **Modify** — introduce `_resolve_native_city()` helper; refactor `parse_location()` to call it for each shape probe and fall through on `None`. |
| `docs/adr/0004-location-probe-first-known-city-wins.md` | **Create** — new ADR documenting "first known-city wins". |
| `docs/adr/0003-location-probe-precedence.md` | **Modify** — change Status to `Superseded by 0004` and add a forward link. |
| `CONTEXT.md` | **Modify** — `[[Location]]` entry references 0004 and rewords the precedence sentence. |

---

## Task 1: Add failing adversarial tests (RED)

**Files:**
- Modify: `tests/domain/test_normalize_location.py` (append at the end, do not reorder existing tests)

- [ ] **Step 1: Append the eight new tests to `tests/domain/test_normalize_location.py`**

Add the following block to the END of the file. Do not delete or reorder anything that already exists. The block intentionally uses the same import surface that the file already imports (`parse_location`, `Location`, `WorkMode`).

```python


# Issue #10 — first-known-city wins (paren/base/bracket probes fall through
# when the captured CJK token is not in _CITY_PINYIN). See ADR 0004.


def test_paren_role_descriptor_falls_through_to_base_prefix_beijing() -> None:
    # （高级）matches the paren shape but "高级" is not a city; the base-prefix
    # probe must win.
    loc = parse_location("（高级）测试工程师 base 北京")
    assert loc.city == "Beijing"
    assert loc.country == "CN"


def test_paren_senior_falls_through_to_base_prefix_shanghai() -> None:
    loc = parse_location("（资深）开发 base 上海")
    assert loc.city == "Shanghai"
    assert loc.country == "CN"


def test_paren_intern_falls_through_to_base_prefix_hangzhou() -> None:
    loc = parse_location("（实习）数据分析师 base 杭州")
    assert loc.city == "Hangzhou"
    assert loc.country == "CN"


def test_paren_parttime_falls_through_to_base_prefix_shenzhen() -> None:
    loc = parse_location("（兼职）前端 base 深圳")
    assert loc.city == "Shenzhen"
    assert loc.country == "CN"


def test_paren_parttime_or_intern_falls_through_to_base_prefix_guangzhou() -> None:
    # （兼职/实习）— the slash is inside the parens; the paren probe captures
    # only the leading CJK run via its [一-鿿]{2,4} shape, but "兼职" is not a
    # city. Base-prefix probe must win.
    loc = parse_location("（兼职/实习）后端 base 广州")
    assert loc.city == "Guangzhou"
    assert loc.country == "CN"


def test_bracket_non_city_falls_through_to_base_prefix_chengdu() -> None:
    # 【高级】matches the bracket shape but "高级" is not a city. Base-prefix
    # probe must win.
    loc = parse_location("【高级】QA base 成都")
    assert loc.city == "Chengdu"
    assert loc.country == "CN"


def test_base_prefix_non_city_falls_through_to_bare_scan_beijing() -> None:
    # base 团队: "团队" is not a city. Fall through to bare-scan, which finds
    # 北京 inside 北京站 (substring match is _scan_bare_city's documented
    # behaviour — see test_bare_city_at_start; unchanged by this task).
    loc = parse_location("base 团队 招聘 北京站")
    assert loc.city == "Beijing"
    assert loc.country == "CN"


def test_paren_role_descriptor_preserves_work_mode_when_no_city() -> None:
    # Regression guard: probe fall-through must NOT lose work_mode. The paren
    # captures a non-city token, every shape probe misses, bare-scan misses,
    # but "remote" is still in the string so work_mode stays REMOTE.
    loc = parse_location("（高级）Backend Engineer Remote")
    assert loc.city is None
    assert loc.work_mode is WorkMode.REMOTE
```

- [ ] **Step 2: Run the new tests to confirm they fail RED for the right reason**

Run:
```bash
uv run pytest tests/domain/test_normalize_location.py -v
```

Expected: the eight new tests FAIL with `AssertionError: assert None == 'Beijing'` (or `'Shanghai'`, etc.) and `test_paren_role_descriptor_preserves_work_mode_when_no_city` passes (because the existing code already extracts work_mode independently — that test guards against regressing during the refactor). All previously-existing tests in the file must still PASS.

If any *previously-existing* test fails, STOP — the appended block has a syntax problem or accidentally redefines something. Read the diff and fix before continuing.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/domain/test_normalize_location.py
git commit -m "test(domain): add failing cases for first-known-city-wins (#10)"
```

---

## Task 2: Refactor `parse_location()` to make the tests pass (GREEN)

**Files:**
- Modify: `src/jma/domain/normalize.py` (only the location section, lines ~152–263)

The current code has three separate probe blocks. We collapse the *resolution* step into one helper that returns `Location | None` (None = "this probe captured a token but it is not a known city; caller should fall through").

- [ ] **Step 1: Replace the location section of `src/jma/domain/normalize.py`**

The existing file currently has, in the location section, the constants `_CITY_PINYIN`, `_RE_BRACKET`, `_RE_PAREN`, `_RE_BASE_PREFIX`, `_REMOTE_TOKENS_CN`, `_REMOTE_TOKENS_EN`, then the helpers `_build_location`, `_scan_bare_city`, then `parse_location`.

Replace **only** the helpers and `parse_location` (everything from `def _build_location(` through the end of the file) with the block below. Do NOT touch `_CITY_PINYIN`, the regex constants, or the `_REMOTE_TOKENS_*` constants — they stay exactly as they are.

```python
def _build_location(
    city_native: str,
    district: str | None,
    work_mode: WorkMode,
) -> Location:
    """Map a native-Chinese city string to a Location using _CITY_PINYIN.

    Unknown native cities yield city=None, district=None — we do NOT stuff
    the native form into `district`. See CONTEXT.md (Location) and
    docs/adr/0004-location-probe-first-known-city-wins.md.
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


def _resolve_native_city(
    city_native: str,
    district: str | None,
    work_mode: WorkMode,
) -> Location | None:
    """Probe-resolution helper used by bracket/paren/base-prefix.

    Returns a Location when the captured token resolves to a known city
    (or to the REMOTE work-mode sentinel). Returns None when the token
    is a CJK string that isn't in _CITY_PINYIN — signalling the caller
    to fall through to the next probe.

    "First-known-city wins": this replaces the previous "first shape-match
    wins" rule from ADR 0003. See ADR 0004.
    """
    city_native = city_native.strip()
    if city_native == "":
        return None
    if city_native in _REMOTE_TOKENS_CN:
        return Location(work_mode=WorkMode.REMOTE)
    if city_native not in _CITY_PINYIN:
        return None
    return _build_location(city_native, district, work_mode)


def _scan_bare_city(s: str) -> str | None:
    """Return the native city whose first occurrence in `s` is leftmost.

    The tiebreak is *string position*, not dict-insertion order — stable
    under any `_CITY_PINYIN` reordering. See ADR 0003 (still valid for
    the bare-scan tiebreak; ADR 0004 only changes shape-probe semantics).

    Lowest-priority probe: only runs after bracket, paren, and
    base-prefix all fail to resolve to a known city.
    """
    best_native: str | None = None
    best_pos = len(s) + 1
    for native in _CITY_PINYIN:
        pos = s.find(native)
        if pos != -1 and pos < best_pos:
            best_pos = pos
            best_native = native
    return best_native


def _try_shape_probe(
    pattern: re.Pattern[str],
    s: str,
    work_mode: WorkMode,
    *,
    group: str,
    split_on_middot: bool,
) -> Location | None:
    """Run one shape probe (bracket / paren / base-prefix) and resolve.

    Returns a Location when the probe matches AND the captured token
    resolves to a known city. Returns None when the probe doesn't match
    at all, OR when it matches but the captured token isn't in
    _CITY_PINYIN — in both cases the caller falls through.

    `split_on_middot=True` enables the `city·district` split used by
    bracket and paren probes. The base-prefix probe captures only the
    city and additionally runs a progressive-shorter-prefix lookup to
    handle greedy over-capture like "base 北京工作" → "北京".
    """
    m = pattern.search(s)
    if m is None:
        return None
    captured = m[group].strip()
    if split_on_middot:
        parts = [p.strip() for p in captured.split("·") if p.strip()]
        city_native = parts[0] if parts else ""
        district = parts[1] if len(parts) > 1 else None
        return _resolve_native_city(city_native, district, work_mode)
    # base-prefix: no district, but try progressive-shorter prefixes so
    # "base 北京工作" resolves to 北京.
    for n in range(len(captured), 1, -1):
        prefix = captured[:n]
        if prefix in _CITY_PINYIN:
            return _build_location(prefix, None, work_mode)
    # Whole capture is not a known-city prefix → fall through.
    return None


def parse_location(text: str) -> Location:
    if text == "":
        return Location()
    s = _nfkc(text)
    lower = s.lower()

    work_mode = WorkMode.UNKNOWN
    if any(tok in s for tok in _REMOTE_TOKENS_CN) or any(tok in lower for tok in _REMOTE_TOKENS_EN):
        work_mode = WorkMode.REMOTE

    # Shape probes in fixed precedence order. Each returns None when its
    # captured token isn't a known city, letting the next probe try. See
    # ADR 0004 (first-known-city wins).
    for pattern, group, split_on_middot in (
        (_RE_BRACKET, "inside", True),
        (_RE_PAREN, "inside", True),
        (_RE_BASE_PREFIX, "city", False),
    ):
        loc = _try_shape_probe(
            pattern, s, work_mode, group=group, split_on_middot=split_on_middot
        )
        if loc is not None:
            return loc

    bare = _scan_bare_city(s)
    if bare is not None:
        return _build_location(bare, None, work_mode)

    return Location(work_mode=work_mode)
```

- [ ] **Step 2: Run the location tests to confirm GREEN**

Run:
```bash
uv run pytest tests/domain/test_normalize_location.py -v
```

Expected: ALL tests in the file pass, including the eight new tests from Task 1 and every previously-existing test (especially `test_unknown_native_city_in_brackets_yields_none_district` — the bracket probe must now fall through past `【厦门】` instead of silently fabricating a city, and bare-scan must also miss because `厦门` isn't in `_CITY_PINYIN` either; the test expects `city is None`, which is still the correct outcome).

If any previously-existing test regresses, do NOT proceed. Read the failing assertion and revisit Task 2 Step 1 — the most likely cause is missing the `_REMOTE_TOKENS_CN` short-circuit in `_resolve_native_city` (a `（远程）` paren must yield `WorkMode.REMOTE`, not fall through).

- [ ] **Step 3: Run the full suite to catch cross-module regressions**

Run:
```bash
uv run pytest
```

Expected: all tests green. The `live` marker is excluded by default per `pyproject.toml` so no network is hit.

- [ ] **Step 4: Lint and format**

Run:
```bash
uv run ruff check .
uv run ruff format .
```

Expected: `ruff check` exits 0 with no findings. `ruff format` reports `X files left unchanged` (or formats `normalize.py` once — if so, re-run and confirm it's stable).

- [ ] **Step 5: Commit the refactor**

```bash
git add src/jma/domain/normalize.py
git commit -m "feat(domain): first-known-city wins in parse_location probes (#10)"
```

---

## Task 3: Author ADR 0004 (supersedes 0003)

**Files:**
- Create: `docs/adr/0004-location-probe-first-known-city-wins.md`

- [ ] **Step 1: Confirm the slot is free**

Run:
```bash
ls docs/adr/ | grep -E "^000[4-9]"
```

Expected: no output (no `0004-*` file exists). If output appears, pick the next free slot (`0005-…`, `0006-…`) and use that number throughout the rest of Task 3 and Task 4.

- [ ] **Step 2: Write the new ADR**

Create `docs/adr/0004-location-probe-first-known-city-wins.md` with exactly this content:

````markdown
# 0004 — parse_location: first-known-city wins (supersedes 0003)

## Status

Accepted — 2026-05-23. Supersedes
[ADR 0003 — parse_location probe precedence and tiebreak](0003-location-probe-precedence.md).

## Context

ADR 0003 established the probe order
`bracket → paren → base-prefix → bare-scan` and the rule "first hit
wins". "Hit" was interpreted as **first shape-match wins**: as soon as
a probe's regex matched, that probe's captured token was the answer,
even if the token wasn't in `_CITY_PINYIN`. The unknown-city case then
yielded `Location(city=None, district=None, country="CN")` — the
"vocabulary gap exposed honestly" property.

In practice that interpretation silently drops the workplace city for a
very common CN title pattern: a leading paren or bracket containing a
**role descriptor** (not a city) followed by a `base 城市` keyword.
Issue #10's canonical example:

```python
parse_location("（高级）测试工程师 base 北京")
# → Location(country='CN', city=None, ...)   # under ADR 0003
# → Location(country='CN', city='Beijing')   # under this ADR
```

`（高级）` ("senior") matches the paren probe's CJK-shape regex
`[一-鿿]{2,4}` but is obviously not a city. Real-world incidence is
HIGH: `（高级）`, `（资深）`, `（实习）`, `（兼职）`, `（兼职/实习）`,
bracket equivalents, etc. are extremely common in CN job titles. Any
of them in combination with a downstream `base 城市` keyword silently
lost the city.

## Decision

`parse_location()` keeps the probe order from ADR 0003 unchanged:

```
bracket  →  paren  →  base-prefix  →  bare-scan
```

What changes is the resolution rule: **first known-city wins**. A
shape probe that matches but whose captured token is not in
`_CITY_PINYIN` no longer returns; it **falls through** to the next
probe. Bare-scan still runs only if every shape probe falls through.

Concretely: `（高级）测试 base 北京` matches the paren probe (captures
`高级`), `高级` is not in `_CITY_PINYIN`, the paren probe falls
through, the base-prefix probe matches `北京`, and the result is
`city="Beijing"`.

`work_mode` extraction stays at the top of `parse_location()` and is
independent of every probe — fall-through never loses the work_mode
signal. A native-city token equal to `远程` (a `_REMOTE_TOKENS_CN`
member) is treated as REMOTE inside the shape resolver, not as a
fall-through.

The three shape probes share a single resolver helper
(`_try_shape_probe`) to keep their semantics in lockstep — adding a
fourth shape probe in the future requires a single new tuple entry,
not a fourth copy of the resolution logic.

## Consequences

- **Recovered property** — the very common `（role-descriptor）... base 城市`
  shape now resolves to the correct workplace city. The fix
  generalises to bracket non-city tokens too (e.g. `【高级】QA base 成都`).
- **Lost property** — ADR 0003's "vocabulary gap exposed honestly via
  bracket-match-to-unknown-city" signal is gone. A `【厦门】` title
  used to encode "we saw a bracket-shaped city annotation but didn't
  recognise the city"; now it falls through to bare-scan, which also
  misses (because `厦门` isn't in `_CITY_PINYIN`), and the result is
  `city=None`. Same end state, but the probe behaviour is no longer
  evidence that a bracket was even seen. Acceptable because we have no
  current consumer of that signal and the recovered case is high-volume.
- **Probe order is still part of the wire contract** — same caveat as
  ADR 0003 §Consequences. Changing the order silently re-attributes
  already-collected [[JobObservation]]s when re-parsed. Any future
  change must call this ADR out.
- **`_CITY_PINYIN` is still a data-only knob** — adding a city changes
  recall and now also which probe answers (a probe that previously
  fell through might start winning), but never the precedence
  *between* probes. Tests should pin probe-winner expectations on
  fixed inputs, not on assumptions about which probe answered.
- **`_scan_bare_city`'s substring-matching behaviour is unchanged.**
  It already matches `北京` inside `北京站` (see
  `tests/domain/test_normalize_location.py::test_bare_city_at_start`),
  which is what makes `base 团队 招聘 北京站` → Beijing work as a
  consequence of this ADR.
````

- [ ] **Step 3: Mark ADR 0003 as superseded**

Open `docs/adr/0003-location-probe-precedence.md`. Replace the
existing `## Status` block:

```markdown
## Status

Accepted — 2026-05-23.
```

with:

```markdown
## Status

Superseded by [ADR 0004 — first-known-city wins](0004-location-probe-first-known-city-wins.md) — 2026-05-23.

The probe **order** described below (bracket → paren → base-prefix →
bare-scan) is still authoritative. The **resolution rule** ("first
shape-match wins") was replaced by "first known-city wins" in ADR 0004
to recover the common `（role-descriptor）... base 城市` pattern from
issue #10. The `_scan_bare_city` leftmost-occurrence tiebreak
documented in this ADR is still in force.
```

Do not delete or edit any other section of `0003-location-probe-precedence.md` — Context, Decision, and Consequences stay as historical record.

- [ ] **Step 4: Verify the ADR files are syntactically clean**

Run:
```bash
ls docs/adr/0004-location-probe-first-known-city-wins.md && \
  grep -n "Superseded by" docs/adr/0003-location-probe-precedence.md
```

Expected: the file exists, and the grep prints one line containing
`Superseded by [ADR 0004 …]`. If the grep finds zero or more than one
match, re-do Step 3.

- [ ] **Step 5: Commit the ADRs**

```bash
git add docs/adr/0004-location-probe-first-known-city-wins.md docs/adr/0003-location-probe-precedence.md
git commit -m "docs(adr): 0004 first-known-city wins, supersedes 0003 (#10)"
```

---

## Task 4: Update `CONTEXT.md` glossary entry

**Files:**
- Modify: `CONTEXT.md` — only the `[[Location]]` section (`## Location` heading)

- [ ] **Step 1: Update the `## Location` section**

The current `## Location` section ends with a paragraph about `district`
that says:

```
A title like `【厦门】X` (where `厦门` isn't in the city vocabulary yet)
yields `city=None, district=None`, not `district="厦门"`. See ADR 0003
for the parser precedence rules.
```

Replace **only** that "See ADR 0003 for the parser precedence rules."
sentence (and the leading sentence about `【厦门】X`) with the
following paragraph. Keep the surrounding paragraphs about `city`,
`district`, and `work_mode` untouched.

```
A title like `【厦门】X` (where `厦门` isn't in the city vocabulary
yet) yields `city=None, district=None`, not `district="厦门"`. The
shape-based probes (bracket / paren / base-prefix) are tried in fixed
precedence order and the **first probe whose captured token is a known
city wins** — probes that capture a non-city CJK token (e.g. a role
descriptor like `（高级）`) fall through to the next probe. See
[ADR 0004](docs/adr/0004-location-probe-first-known-city-wins.md)
(which supersedes [ADR 0003](docs/adr/0003-location-probe-precedence.md))
for the parser precedence rules.
```

- [ ] **Step 2: Verify the edit**

Run:
```bash
grep -n "ADR 0004" CONTEXT.md && grep -n "ADR 0003" CONTEXT.md
```

Expected: at least one `ADR 0004` match (in the new `[[Location]]`
paragraph) and at least one `ADR 0003` match (also in `[[Location]]`,
in the same paragraph, marking 0003 as superseded). If `ADR 0003`
appears without the "supersedes" framing, re-read Step 1.

- [ ] **Step 3: Commit the glossary update**

```bash
git add CONTEXT.md
git commit -m "docs(context): location entry references ADR 0004 (#10)"
```

---

## Task 5: Final verification (the impl agent runs this before declaring done)

- [ ] **Step 1: Lint and format are clean**

```bash
uv run ruff check .
uv run ruff format .
```

Expected: `ruff check` exits 0. `ruff format` reports `N files left unchanged` (no files were reformatted). If `ruff format` *does* reformat a file at this point, stage and commit the formatting change as `style: apply ruff format`.

- [ ] **Step 2: Full test suite green**

```bash
uv run pytest
```

Expected: 100% pass. The summary should show 0 failures, 0 errors. Live tests are skipped by default — confirm none of them ran (they'd appear as `s` for skipped, not as failures).

- [ ] **Step 3: Targeted location-tests run printed verbose**

```bash
uv run pytest tests/domain/test_normalize_location.py -v
```

Expected: every test in the file shows `PASSED`. Eyeball the eight new
test names from Task 1 to confirm they all ran and all passed:

- `test_paren_role_descriptor_falls_through_to_base_prefix_beijing`
- `test_paren_senior_falls_through_to_base_prefix_shanghai`
- `test_paren_intern_falls_through_to_base_prefix_hangzhou`
- `test_paren_parttime_falls_through_to_base_prefix_shenzhen`
- `test_paren_parttime_or_intern_falls_through_to_base_prefix_guangzhou`
- `test_bracket_non_city_falls_through_to_base_prefix_chengdu`
- `test_base_prefix_non_city_falls_through_to_bare_scan_beijing`
- `test_paren_role_descriptor_preserves_work_mode_when_no_city`

- [ ] **Step 4: Git status is clean**

```bash
git status
```

Expected: `nothing to commit, working tree clean`. If anything is
staged or modified, decide whether it's an intentional follow-up (rare)
or a missed commit (re-stage and commit before declaring done).

---

## Verification checklist (tick before reporting done)

- [ ] All eight new tests in `tests/domain/test_normalize_location.py` pass.
- [ ] All previously-existing tests in `tests/domain/test_normalize_location.py` still pass — especially `test_unknown_native_city_in_brackets_yields_none_district`, `test_bare_city_at_start`, `test_bare_scan_leftmost_city_wins`, `test_base_prefix_city_followed_by_cjk`, `test_base_prefix_unknown_city_followed_by_cjk`, `test_english_paren_does_not_match`, `test_database_does_not_trigger_base_prefix`.
- [ ] `uv run pytest` is fully green (no regressions outside the location module).
- [ ] `uv run ruff check .` is clean.
- [ ] `uv run ruff format .` produces no diff after the last commit.
- [ ] `_CITY_PINYIN` is unchanged (`git diff main -- src/jma/domain/normalize.py` shows no edits to that dict).
- [ ] `_scan_bare_city` is unchanged (same git diff confirms).
- [ ] `_REMOTE_TOKENS_CN` / `_REMOTE_TOKENS_EN` constants are unchanged.
- [ ] The work_mode extraction at the top of `parse_location()` is unchanged.
- [ ] `docs/adr/0004-location-probe-first-known-city-wins.md` exists, status is `Accepted — 2026-05-23. Supersedes ADR 0003…`.
- [ ] `docs/adr/0003-location-probe-precedence.md` status now reads `Superseded by ADR 0004…`; the rest of its body is intact.
- [ ] `CONTEXT.md` `[[Location]]` entry links ADR 0004 and notes that 0004 supersedes 0003.
- [ ] No source/pipeline/storage/CLI files were touched (only domain/normalize.py, the test file, the two ADRs, and CONTEXT.md).
- [ ] No GitHub issues were closed (the orchestrator handles that after merge).
- [ ] Commit log shows at least four commits (failing tests → refactor → ADRs → CONTEXT) — discrete, atomic.
