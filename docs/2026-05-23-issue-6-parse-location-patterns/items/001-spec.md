# 001-spec (inferred from plan)

Goal: Extend `parse_location()` in `src/jma/domain/normalize.py` so TesterHome titles that use Chinese parentheses, a `base 城市` prefix, or a bare city token at the start yield a populated `location_city` instead of `None` — while preserving workplace-only semantics and removing the existing "stuff unknown city into district" fallback.

Acceptance criteria:
  - `parse_location("招聘中高级测试工程师（武汉）")` → `city="Wuhan"`, `country="CN"`, `district=None`.
  - `parse_location("招聘高级开发（杭州·余杭）")` → `city="Hangzhou"`, `district="余杭"`, `country="CN"`.
  - `parse_location("APP测试工程师热招中！base 北京")` → `city="Beijing"`, `country="CN"`.
  - `parse_location("深圳招聘~AI独角兽急招测试")` → `city="Shenzhen"`, `country="CN"`.
  - `parse_location("Senior Backend Engineer (Remote)")` → `city=None`, `district=None`, `country=None`, `work_mode=REMOTE` (ASCII paren around English content must NOT trip the paren probe; English-remote token detection still wins on work_mode).
  - `parse_location("资深 Database 测试工程师")` → `city=None`, `district=None` (the `base` substring inside `Database` must NOT trigger the base-prefix probe; lookbehind requires non-letter boundary).
  - `parse_location("深圳/广州招聘 AI 工程师")` → `city="Shenzhen"` (bare-scan returns the leftmost city by string position, NOT dict-insertion order).
  - `parse_location("【厦门】Senior QA")` → `city=None`, `district=None`, `country="CN"` (unknown native city must NOT be stuffed into the `district` field — this is a behavior change from the previous code that returned `district="厦门"`).
  - Probe precedence is `bracket → paren → base-prefix → bare-scan`, first hit wins (ADR 0003).
  - Existing five tests (`test_brackets_city_only`, `test_brackets_city_district`, `test_remote_token_inside_brackets`, `test_remote_english_no_brackets`, `test_no_brackets_no_city`) continue to pass.
  - `uv run pytest tests/domain` is green.
  - `uv run pytest` (full suite, `live` excluded) is green.
  - `uv run ruff check . && uv run ruff format --check .` is clean.

Constraints: Pure-domain change — modify only `src/jma/domain/normalize.py` and `tests/domain/test_normalize_location.py`. No source/storage/pipeline files are touched. Workplace semantics only (`Location.city` is the workplace, not company HQ). Feature branch `autodev/issue-6-location-patterns-feature` is the merge target; `main` is protected and not part of this run.
