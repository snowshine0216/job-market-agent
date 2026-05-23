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

## Subtlety — probe-excised bare-scan

After all shape probes fall through, bare-scan runs on a
**probe-excised** copy of the string: every substring matched (but not
resolved) by a shape probe is removed before `_scan_bare_city` is
called. This prevents the `【北京路】→ Beijing` misattribution, where
the bracket probe captures `北京路` (a street in Shanghai), fails to
resolve it, and the old code then let bare-scan find `北京` inside that
same captured text.

The cost of this rule: `【北京朝阳】` (city + district concatenated
without a middot separator) no longer falls through to bare-scan and
resolves to `city=None` instead of Beijing. Mitigation: use
`【北京·朝阳】` with a middot — the bracket probe's
`(?:·[一-鿿]{2,6})?` group already handles city·district splitting and
correctly returns `city=Beijing, district=Chaoyang`.

**Multiple spans per title:** excision before bare-scan uses
`re.sub(pattern, ' ', s)` applied to each of the three shape patterns in
sequence, not just the per-probe captured span. This prevents a *second*
bracket or paren later in the same title (e.g. `【高级】工程师【北京路】`)
from leaking its internal CJK content into `_scan_bare_city` when the
first probe fell through. The old approach (`str.replace(captured, ' ', 1)`)
only removed the first match seen by each probe's `pattern.search()` call.
