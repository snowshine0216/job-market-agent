# 001 — Inline review verdict (captured from /ship steps 8 + 9)

Verdict: PASS-WITH-NITS

## Sources

- Step 8 — pre-landing review:
  - `pr-review-toolkit:code-reviewer` (Sonnet)
  - `pr-review-toolkit:silent-failure-hunter` (Sonnet)
- Step 9 — adversarial review: `general-purpose` (Sonnet)

## P0 — must fix before landing

1. **`_RE_BASE_PREFIX` greedy over-capture silently drops city to None** — `src/jma/domain/normalize.py` (base-prefix probe). Greedy `[一-鿿]{2,4}` captured `北京工作` from `"base 北京工作"`, failed `_CITY_PINYIN` lookup, returned `city=None` instead of `Beijing`. Contradicts plan intent (extract city from `base 城市`).
   - **Status: FIXED.** Commits [`1890696`](#) (tests) + [`8422884`](#) (fix) added progressive-shorter-prefix resolution after the regex match. Three new tests cover the case and the unknown-city-with-CJK-suffix variant.

## P1 — accepted as known limitations (documented follow-ups)

1. **`_scan_bare_city` substring match permits famous-street-name false positives** — `北京东路` matching `北京`, `苏州河` matching `苏州`, etc. The plan EXPLICITLY tests `parse_location("深圳招聘~AI独角兽急招测试") → city="Shenzhen"` and `parse_location("深圳/广州招聘 AI 工程师") → city="Shenzhen"`, both of which require bare-scan to match CJK-followed cities. Adding a strict word boundary would break the plan's locked tests. Accepting the tradeoff for now; follow-up needed for a separator-aware bare-scan.

2. **Paren probe consumes non-city CJK descriptors, blocking downstream probes** — `（高级）测试工程师 base 北京` silently returns `city=None` because the paren probe greedily matches `高级` (a role descriptor, not a city), then ADR 0003's "first hit wins" rule prevents the `base 北京` probe from ever being tried. Real-world incidence is high (`（高级）`, `（资深）`, `（实习）`, `（兼职）` are extremely common). This contradicts a reader's intuition but is the documented behavior of ADR 0003. Resolving it requires a design decision (amend ADR 0003 to "first-known-city hit wins" + apply to all three shape-based probes consistently), so it doesn't fit inside this PR.
   - **Follow-up:** spawned during autodev run (chip surfaced to user; will become a separate GitHub issue against `snowshine0216/job-market-agent`).

3. **No test for unknown-city WITH district in brackets** — code-reviewer flagged a coverage gap; `test_unknown_native_city_in_brackets_yields_none_district` only covers bare-city. **Status: FIXED.** Commit [`1890696`](#) added `test_unknown_native_city_with_district_in_brackets_yields_none_district` exercising `【厦门·鼓楼】`.

## P2 / Notes

- `_RE_PAREN` CJK range `[一-鿿]` stops at U+9FFF. No current `_CITY_PINYIN` city is outside this range, but future additions in CJK Extension B+ would silently bypass the paren probe. Cheap to widen the range if/when needed.
- `_RE_BASE_PREFIX` lookbehind `(?<![A-Za-z])` allows digit prefixes like `1base 北京`. Vanishingly rare in real titles; not worth tightening.
- `_scan_bare_city` iterates 11 cities × `str.find` per title — not a hot path concern.
- No try/except blocks, no async-without-await, no I/O side effects. Pure-domain implementation as designed.
- `Location` pydantic shape unchanged; no callers in `storage/` or `sources/` need updating.

## Adversarial verdict

RISKS (one P1 — paren-probe descriptor consumption above). No P0 attack vector succeeded. All explored edge inputs (empty string, null byte, very long string, NFKC quirks, multiple `base` keywords, Latin in city slot, single-char CJK) handled correctly.

## Final commit chain on this sub-branch

```
8422884 fix(domain): base-prefix probe resolves city via progressive-prefix lookup (#6)
1890696 test(domain): cover base-prefix over-capture + unknown-city-with-district (#6)
f7b721c autodev(001): drift check PASS — diff matches plan tasks 1-5
89714a3 feat(domain): parse_location bare-city fallback scan, leftmost wins (#6)
6c14cde feat(domain): parse_location handles 'base <city>' prefix (#6)
c4e544c feat(domain): parse_location handles （city） and （city·district） parens (#6)
ea34b6c refactor(domain): extract _build_location, drop district fallback (#6)
f6a6ccb test(domain): cover paren/base-prefix/bare-city location patterns (#6)
```

Test counts: 104 passed, 1 deselected (live marker excluded by default). Ruff: clean for the two touched files.
