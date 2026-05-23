# MASTER-SPEC — Issue #10: non-city CJK tokens

Single-feature autodev run. Mode: **spec**. The user-provided issue body is the spec; per-item spec/grill phases are pre-completed.

## Scope

| ID  | Source     | Status | Title                                                          |
|-----|------------|--------|----------------------------------------------------------------|
| 001 | Issue #10  | IN     | Paren/base/bracket probes consume non-city CJK tokens          |

## OUT

None. Single-issue run.

## Sibling admin work (completed before this run)

- Closed Issue #6 — acceptance criteria met by PR #12, follow-up PR #14.
- Closed Issue #8 — acceptance criteria met by PR #16.

## User-locked decisions (this turn)

- **Design direction for #10:** "first-known-city wins" — paren/base/bracket probes fall through to the next probe when the captured token is not in `_CITY_PINYIN`. Refactor all three shape-based probes consistently.
- **Authoring artifact:** new ADR amending ADR 0003 (location-probe-precedence). Update `CONTEXT.md` `[[Location]]` entry to reflect the new rule.
