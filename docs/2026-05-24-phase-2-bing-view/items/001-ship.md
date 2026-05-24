PR: https://github.com/snowshine0216/job-market-agent/pull/24
Mode: A
Branch: claude/phase-2-bing-view-001
Base: autodev/phase-2-bing-view-feature
Title: feat(phase-2): Bing aggregator (SerpAPI) + jma view + retire TesterHome (001)

## /ship workflow summary

- Step 0 (platform): GitHub
- Step 1 (preflight): on `claude/phase-2-bing-view-001`, 19 commits + 3 fix commits + 1 lint reformat + 1 review-verdict commit ahead of `autodev/phase-2-bing-view-feature`; large-diff warning (~50 files / ~2950+ / ~2230-) noted
- Step 2 (distribution check): SCOPE_NEW_BINARY=false (`jma` script entry pre-existing in pyproject.toml), skipped
- Step 3 (merge base): `origin/autodev/phase-2-bing-view-feature` already up to date
- Step 4 (test bootstrap): pytest already present, skipped
- Step 5 (run tests): `uv run pytest -m 'not live' -q` → 174 passed / 1 skipped / 1 deselected
- Step 6 (coverage audit): new modules have TDD-paired tests (8 new test files covering bing source, company heuristic, run_jobs, view context, view template, view CLI, live smoke); no gaps to flag
- Step 7 (plan completion): plan at `items/001-plan.md`, drift verdict at `items/001-drift.md` already confirmed all 19 tasks done; skipped silently
- **Step 8 (pre-landing review): 2 P0 + 12 P1 findings — fixed in flow** (commits `c44858c`, `246d7c1`, `e87445e`)
- **Step 9 (adversarial review): post-fix verification CLEAN** (no regressions, all fixes hold)
- Step 10 (version bump): skipped (`--no-version-bump`)
- Step 11 (CHANGELOG): no CHANGELOG.md in repo, skipped
- Step 12 (TODOS): no TODOS.md in repo, skipped
- Step 13 (commit): working tree clean (review verdict already committed)
- Step 14 (push): `b02c7fb` pushed to `origin/claude/phase-2-bing-view-001`
- Step 15 (create PR): #24 opened against `autodev/phase-2-bing-view-feature` — title and body per /ship template

## Review verdict captured inline

`items/001-review.md` — **PASS-WITH-NITS**. Pre-fix snapshot at `items/001-ship-blocked.md`.

## Next phases

- `001-verify` (`/verify` on the branch — non-web project per `Project type: non-web` in MASTER-PLAN.md)
- `001-pr-review` (`/code-review` on PR #24)
- Both run in parallel; results feed `001-fix` then `001-merge` gate.
