Verdict: PASS

## Branch

`claude/issue-10-first-known-city-001` (4 commits on top of `autodev/issue-10-first-known-city-feature`)

Key source change: `src/jma/domain/normalize.py` — 154 additions / 31 deletions.
New helpers: `_resolve_native_city`, `_try_shape_probe`. Refactored `parse_location` to
"first-known-city wins" loop with probe-excision before bare-scan.

---

## Acceptance Walkthrough

All inputs driven through `uv run python -c "from jma.domain.normalize import parse_location; ..."`.

| Input | Expected city | Actual output | |
|---|---|---|---|
| `（高级）测试工程师 base 北京` | Beijing | `Location(country='CN', city='Beijing', district=None, work_mode=<WorkMode.UNKNOWN: 'unknown'>)` | ✅ |
| `（资深）开发 base 上海` | Shanghai | `Location(country='CN', city='Shanghai', district=None, work_mode=<WorkMode.UNKNOWN: 'unknown'>)` | ✅ |
| `（实习）数据分析师 base 杭州` | Hangzhou | `Location(country='CN', city='Hangzhou', district=None, work_mode=<WorkMode.UNKNOWN: 'unknown'>)` | ✅ |
| `（兼职）前端 base 深圳` | Shenzhen | `Location(country='CN', city='Shenzhen', district=None, work_mode=<WorkMode.UNKNOWN: 'unknown'>)` | ✅ |
| `（兼职/实习）后端 base 广州` | Guangzhou | `Location(country='CN', city='Guangzhou', district=None, work_mode=<WorkMode.UNKNOWN: 'unknown'>)` | ✅ |
| `【高级】QA base 成都` | Chengdu | `Location(country='CN', city='Chengdu', district=None, work_mode=<WorkMode.UNKNOWN: 'unknown'>)` | ✅ |

---

## In-Flow Regression Cases

| Input | Expected city | Actual output | |
|---|---|---|---|
| `【北京路】QA工程师` | None | `Location(country='CN', city=None, district=None, work_mode=<WorkMode.UNKNOWN: 'unknown'>)` | ✅ |
| `软件测试工程师【北京东路招聘中心】` | None | `Location(country='CN', city=None, district=None, work_mode=<WorkMode.UNKNOWN: 'unknown'>)` | ✅ |

The bracket probe matches `【北京路】` / `【北京东路招聘中心】`, excises those spans, then bare-scan
runs on the remainder — which no longer contains the street-name token. `city=None` confirmed.

---

## Test Summary

```
154 passed, 1 deselected, 4 warnings in 16.83s
```

4 warnings are pre-existing `PytestCollectionWarning` about `TesterHomeSource` class (not introduced by this branch). 1 deselected = live marker tests excluded per `pyproject.toml`.

---

## Lint Summary

```
All checks passed!
```

`uv run ruff check .` — zero findings.

---

## CLI Sanity

```
 Usage: jma [OPTIONS] COMMAND [ARGS]...

 jma — job-market-agent CLI.

╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ crawl                                                                        │
╰──────────────────────────────────────────────────────────────────────────────╯
```

---

## Additional Probes

All driven through `parse_location` at the installed-package surface.

| Probe | Input | Result | Note |
|---|---|---|---|
| 🔍 REMOTE sentinel in bracket | `【远程】Python工程师` | `work_mode=REMOTE, city=None, country='CN'` | ✅ REMOTE preserved |
| 🔍 Non-city bracket → bare-scan fallback | `【高级工程师】做测试 北京` | `city='Beijing'` | ✅ excision + bare-scan pipeline works |
| 🔍 Bracket with middot city·district | `工作地点【北京·朝阳】测试` | `city='Beijing', district='朝阳'` | ✅ middot split intact |
| 🔍 Paren non-city → base-prefix wins | `（实习生）base 成都` | `city='Chengdu'` | ✅ fall-through chain works |
| 🔍 Empty brackets | `【】测试工程师` | `Location()` (all None) | ✅ no crash |
| 🔍 No city at all | `软件工程师招聘` | `Location()` (all None) | ✅ |
| 🔍 Bracket precedence over paren | `【上海】（杭州）工程师` | `city='Shanghai'` | ✅ bracket wins |
| 🔍 base-prefix greedy over-capture | `base 北京工作` | `city='Beijing'` | ✅ progressive prefix trim works |
| 🔍 Unbracketed 北京路 (bare-scan) | `北京路软件工程师` | `city='Beijing'` | ⚠️ see Findings |

---

## Findings

- ⚠️ `北京路软件工程师` (unbracketed street name) → `city='Beijing'`. The excision mechanism only fires on probe-matched spans (bracket/paren/base-prefix). A bare street name like `北京路` is invisible to the excision step, so bare-scan still matches `北京`. This is expected per the spec (excision is only for probe-captured substrings per ADR 0004 §Subtlety), but callers relying on street-name-heavy titles without brackets will still get false city matches. No new regression introduced by this branch — this was the pre-existing bare-scan behaviour.

- 🔍 `【远程】` inside a bracket correctly returns `country='CN', work_mode=REMOTE` (not just work_mode=REMOTE with no country), because `_resolve_native_city` now sets `country="CN"` for REMOTE inside the CN shape context. This is a subtle improvement over the old code path where REMOTE detection happened before `_build_location`.

- The `PytestCollectionWarning` about `TesterHomeSource` (4 occurrences) is pre-existing noise unrelated to this branch.
