# 0003 — parse_location probe precedence and tiebreak

## Status

Accepted — 2026-05-23.

## Context

TesterHome (and other CN job boards we plan to add) write the workplace
city in several distinct title shapes. From a survey of live TesterHome
listings, at least four shapes appear in the wild:

| Shape | Example |
|---|---|
| Full-width brackets | `【杭州·余杭】AI Agent Engineer` |
| Full-width parens   | `招聘中高级测试工程师（武汉）` |
| `base` keyword      | `APP测试工程师热招中！base 北京` |
| Bare city token     | `深圳招聘~AI独角兽急招` |

A single title can carry evidence for more than one city — e.g.
`【杭州】base 北京` (bracket says Hangzhou, keyword says Beijing), or
`深圳/广州招聘` (two bare cities). We need a deterministic rule for which
shape wins, and a deterministic rule for ties within a shape, because
the same title parsed differently across runs would silently
re-attribute historical [[JobObservation]]s.

Three things were specifically considered and rejected before settling:

1. **Most-specific-match wins.** Attractive in theory ("the longest /
   most explicit annotation should win"), but in practice there's no
   stable "specificity" ordering across these shapes — a `base` keyword
   is arguably more explicit than a bracket, but bracket is the older
   TesterHome convention.
2. **Dict-insertion-order tiebreak within bare-scan.** The vocabulary
   (`_CITY_PINYIN`) is a data-only knob that we expect to grow. Tying
   semantics to dict order means adding a city silently changes which
   one wins for some titles. Tests would silently flip.
3. **Ambiguous-returns-None.** Too conservative — loses the very common
   `深圳/广州招聘` shape entirely, where the first city named is
   conventionally the primary workplace.

## Decision

`parse_location()` tries four probes in fixed order and returns on the
first hit:

```
bracket  →  paren  →  base-prefix  →  bare-scan
```

This order reflects how explicitly each shape annotates *workplace* on
real TesterHome data. Brackets are the established convention; parens
are an informal but still positional annotation; `base X` is an
explicit keyword; bare-scan is a last-resort heuristic over the
[[Location]]-vocabulary.

Within bare-scan, when the title mentions more than one known city, the
**leftmost** occurrence in the (NFKC-normalised) title wins. This is
stable under any reordering of `_CITY_PINYIN`, and it matches the
reading convention that the first-named city in a Chinese job title is
the primary workplace.

A native-city string that matches the *shape* of one of these probes
but isn't in `_CITY_PINYIN` (e.g. `【厦门】`) yields
`Location(city=None, district=None, country="CN", …)` — the vocabulary
gap is exposed honestly, not papered over by stuffing the city name
into the `district` field.

## Consequences

- Probe order is part of the wire contract. Changing it silently
  re-attributes already-collected [[JobObservation]]s when re-parsed.
  Any future change to the order must call this ADR out explicitly and
  consider re-parsing existing rows.
- Bare-scan cannot disambiguate a title that genuinely encodes two
  workplaces (`深圳/广州招聘` → Shenzhen). We accept losing the secondary
  city.
- `_CITY_PINYIN` is a data-only knob: adding a city changes recall (we
  parse more titles successfully) but never precedence semantics.
- A future "company city" attribute, if needed, is a *separate field*
  on `Location` — never a fifth probe in this chain. See the
  [[Location]] entry in `CONTEXT.md`.
