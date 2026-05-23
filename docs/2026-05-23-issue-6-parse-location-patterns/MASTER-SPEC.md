# Master Spec — Issue #6: parse_location coverage for non-bracket city patterns

**Mode:** plan
**Source:** `docs/superpowers/plans/2026-05-23-issue-6-parse-location-patterns.md` (user-provided)
**Issue:** [snowshine0216/job-market-agent#6](https://github.com/snowshine0216/job-market-agent/issues/6)
**Date:** 2026-05-23
**Project type:** non-web (Python 3.12 CLI — use `/verify`, not `/qa`)
**PR shape:** A (per-item PR into feature branch — default; no `--rollup` opt-in)
**Feature branch:** `autodev/issue-6-location-patterns-feature` (synthesized off `main`; `main` is protected, no merge-to-main opt-in)

## IN scope

| # | Title | Source file |
|---|-------|-------------|
| 001 | Extend `parse_location()` so TesterHome titles using Chinese parens (`（武汉）`), `base 城市` prefix, or a bare city token at the start yield a populated `location_city` instead of `None` — plus refactor unknown-city handling to never stuff native form into `district` | `docs/superpowers/plans/2026-05-23-issue-6-parse-location-patterns.md` |

## OUT of scope (explicit follow-ups, tracked in the source plan)

1. Expanding `_CITY_PINYIN` vocabulary beyond the 11 first-tier cities (data-only change; separate issue).
2. Company-city extraction (`测试开发 - 上海冰鲸科技有限公司` pattern) — different field, different probe; per [[Location]] in CONTEXT.md.

## Decisions inherited from the plan

- Probe precedence: `bracket → paren → base-prefix → bare-scan` (locked in ADR 0003).
- Paren probe accepts only CJK-shaped content (`(Remote)` / `(NYC)` must not match).
- `base` keyword requires non-letter left boundary (`database`, `firebase` must not trigger).
- Bare-scan returns leftmost city by string position (stable under `_CITY_PINYIN` reordering).
- Unknown native city → `Location(country="CN", city=None, district=None)` — district pollution removed in both new probes AND existing bracket path.
- Workplace semantics only — company HQ extraction is out of scope.
