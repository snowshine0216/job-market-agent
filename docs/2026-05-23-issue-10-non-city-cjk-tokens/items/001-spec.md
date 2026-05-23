# 001 — Spec (from Issue #10)

Source: https://github.com/snowshine0216/job-market-agent/issues/10

Mode = **spec**, so this document is the user-provided issue body verbatim, plus the user-locked design direction appended at the end.

---

## Title

parse_location: paren/base/bracket probes consume non-city CJK tokens

## The gap (concrete)

```python
from jma.domain.normalize import parse_location
parse_location("（高级）测试工程师 base 北京")
# Returns: Location(country='CN', city=None)
# Expected by anyone reading the title: city='Beijing'
```

`（高级）` (meaning "senior") matches the paren probe's CJK-shape regex `[一-鿿]{2,4}` — but `高级` is not a city, it's a role descriptor. Per ADR 0003's "first hit wins + vocabulary gap exposed honestly" rule, the implementation correctly returns `city=None` and never tries the `base 北京` probe. The result is a silent misattribution — the title clearly says workplace is Beijing.

Real-world incidence is HIGH: `（高级）`, `（资深）`, `（实习）`, `（兼职）`, `（兼职/实习）`, etc. are extremely common in CN job titles. Any of these in combination with a `base 城市` keyword anywhere downstream silently loses the city.

## The design question

Should "first hit wins" mean **"first SHAPE-match wins"** (current behavior, locked in [ADR 0003](../../adr/0003-location-probe-precedence.md)) or **"first KNOWN-CITY hit wins"** (proposed change)? The second reading would have paren/base/bracket probes fall through to the next probe when their captured token isn't in `_CITY_PINYIN`.

### Tradeoffs

- **"First known-city wins"** loses ADR 0003's "vocabulary gap exposed honestly" property — a `【厦门】` title would no longer attribute the bracket to a known city, it'd just fall through to bare-scan (which would also miss because `厦门` isn't in vocab). Net effect: same `city=None` outcome, but probe behavior is harder to predict.
- **"First known-city wins"** recovers the common `（role descriptor）... base 城市` case.

The fix likely needs both a design decision (probably a sibling ADR amending 0003) and code changes across all three shape-based probes (bracket, paren, base-prefix). It is NOT a localized one-line tweak.

## Acceptance criteria

1. Add adversarial test cases for `（高级）测试 base 北京` and 3-4 similar patterns (`（资深）`, `（实习）`, `（兼职）`, etc.) to `tests/domain/test_normalize_location.py`.
2. Decide on the design via a follow-up ADR: either amend [ADR 0003](../../adr/0003-location-probe-precedence.md) to "first-known-city wins" + update [CONTEXT.md](../../../CONTEXT.md) `[[Location]]` entry, OR explicitly document the limitation as accepted-tradeoff (and the tests above become known-failure / xfail markers).
3. If "first-known-city wins" is chosen, refactor all three probes consistently (`_RE_BRACKET`, `_RE_PAREN`, `_RE_BASE_PREFIX` post-match resolution in [src/jma/domain/normalize.py](../../../src/jma/domain/normalize.py)).

## NOT in scope

Changing `_scan_bare_city`'s substring-matching behavior (`北京东路` matching `北京`, `苏州河` matching `苏州`). That is a separate concern — required by plan tests `test_bare_city_at_start` and `test_bare_scan_leftmost_city_wins`. Track separately if/when it becomes a real pain point.

## References

- ADR: [docs/adr/0003-location-probe-precedence.md](../../adr/0003-location-probe-precedence.md)
- Glossary entry: [CONTEXT.md](../../../CONTEXT.md) `[[Location]]`
- Autodev run that surfaced this: [docs/2026-05-23-issue-6-parse-location-patterns/items/001-review.md](../../2026-05-23-issue-6-parse-location-patterns/items/001-review.md) (P1 finding from adversarial review)

---

## User-locked design direction (this run)

**Choice: "first-known-city wins" (acceptance criterion #2, option A; acceptance criterion #3 in scope).**

Implementation requirements derived from the choice:

- Refactor `_RE_BRACKET`, `_RE_PAREN`, `_RE_BASE_PREFIX` resolution in [src/jma/domain/normalize.py](../../../src/jma/domain/normalize.py) so a probe match that resolves to **no known city** (i.e. `_CITY_PINYIN.get(captured) is None`) **falls through** to the next probe instead of returning `Location(city=None)`.
- The three shape probes must be tried in their existing precedence order; only the *first probe that resolves to a known city* wins. If no probe finds a known city, the bare-scan still runs (per current ordering).
- The `work_mode` extraction (e.g. "remote", "WFH") must continue to run independently — the fall-through must not lose work-mode signal.

ADR authoring:

- New ADR amending ADR 0003 (suggested filename: `docs/adr/0004-location-probe-first-known-city-wins.md` — pick the next free 4-digit slot at impl time; there are already three files numbered `0003-*` in `docs/adr/` so confirm the next slot is genuinely free or pick the next available).
- The new ADR must:
  - State the change in precedence semantics ("first shape-match wins" → "first known-city wins").
  - Cite #10 as the motivating case and `（高级）测试 base 北京` as the canonical example.
  - Document the lost property (vocabulary-gap signal from a bracket-match-to-unknown-city) and the recovered property (paren-role-descriptor doesn't shadow a downstream `base 城市`).
  - Mark ADR 0003 as **superseded** by the new ADR (do not delete 0003 — link forward).
- Update [CONTEXT.md](../../../CONTEXT.md) `[[Location]]` entry to use the new precedence rule and link the new ADR.

Tests:

- Add adversarial cases to [tests/domain/test_normalize_location.py](../../../tests/domain/test_normalize_location.py):
  - `（高级）测试工程师 base 北京` → city=Beijing
  - `（资深）开发 base 上海` → city=Shanghai
  - `（实习）数据分析师 base 杭州` → city=Hangzhou
  - `（兼职）前端 base 深圳` → city=Shenzhen
  - `（兼职/实习）后端 base 广州` → city=Guangzhou
  - At least one bracket case where the bracket token is non-city and the base prefix is a known city: `【高级】QA base 成都` → city=Chengdu
  - At least one base-prefix case where the base token is non-city and a bare-scan would catch the real city: e.g. `base 团队 招聘 北京站` → city=Beijing (if scope allows)
- Existing tests must still pass — especially `test_bare_city_at_start`, `test_bare_scan_leftmost_city_wins`, and any test that pins the precedence ordering.

Out of scope (do NOT change):

- `_scan_bare_city`'s substring behavior.
- The `_CITY_PINYIN` vocabulary (do not silently add cities to make a test pass).
- The `work_mode` extraction regex.
