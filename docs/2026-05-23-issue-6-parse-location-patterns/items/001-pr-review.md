# 001 — PR-review verdict (/code-review on PR #9)

Verdict: PASS

## Tool used

`code-review` skill (invoked via Skill tool), medium effort, 3 angles × candidates → 1-vote verify.
Target: PR #9 (`claude/issue-6-location-patterns-001` → `autodev/issue-6-location-patterns-feature`).
Diff reviewed via `git diff autodev/issue-6-location-patterns-feature...claude/issue-6-location-patterns-001`.

## New findings (not in items/001-review.md)

One nit surfaced and verified as low severity:

- **`src/jma/domain/normalize.py`, `_RE_BASE_PREFIX` lookbehind, severity: nit**
  The lookbehind `(?<![A-Za-z])` rejects ASCII letters before `base` (blocking `database`,
  `firebase`, `codebase`) but allows CJK characters immediately before `base` — e.g.
  `'测试base 北京'` would match and return `city="Beijing"`. This is functionally correct
  (extracting Beijing is right) but the case is untested and undocumented. Suggested fix:
  add one guard test — `parse_location("测试base 北京") → city="Beijing"` to pin the behavior
  as intentional, or expand the lookbehind to `(?<!\w)` if CJK-glued `base` should be
  rejected. This does not affect correctness for any known real-world input.

## Re-raised findings (already triaged in items/001-review.md)

All four known limitations from `items/001-review.md` were examined during the review but
are **not** re-raised as blockers:

1. **`_scan_bare_city` substring false positives** (`北京东路` → `北京`): plan-locked behavior,
   documented as P1 in `items/001-review.md §P1-1`.
2. **Paren probe consumes non-city CJK descriptors** (`（高级）` blocks downstream probes):
   design decision per ADR 0003, documented as P1 in `items/001-review.md §P1-2`.
3. **`_RE_PAREN` CJK range stops at U+9FFF**: documented as P2 nit in `items/001-review.md`.
4. **`_RE_BASE_PREFIX` digit prefix** (`1base 北京`): documented as P2 nit in `items/001-review.md`.

## Posted as PR comments?

No. The `code-review` skill ran in analysis mode only; no `gh` PR comment calls were made.

## Recommendation

The implementation is sound. All 17 location tests pass, ruff is clean, and no new
correctness bugs were found. The single new nit (untested CJK-before-`base` path) does
not change behavior and carries negligible real-world risk given TesterHome job title
conventions. This PR is clear to merge into `autodev/issue-6-location-patterns-feature`.
