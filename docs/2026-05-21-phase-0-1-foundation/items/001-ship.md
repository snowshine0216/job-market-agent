PR: https://github.com/snowshine0216/job-market-agent/pull/2
Mode: A
Branch: claude/phase-0-1-foundation-001
Base: autodev/phase-0-1-foundation-feature
Title: feat(jma): phase-0-1 foundation + testerhome vertical slice (001)

## Ship notes

- Sub-PR is targeted at the autodev feature branch, NOT `main`. The user did not opt into a protected-branch merge in this turn; pre-merge gate must enforce.
- `gstack-ship` skill is not installed in this environment; ship phase used the autodev-documented `gh pr create` fallback. Logging here so the user knows. PR title + body still follow the autodev convention from `references/ship.md`.
- All 13 task commits (`4ff44f9..060f858`) are in the PR.

## Pre-merge gate inputs

- `items/001-ship.md` — this file (PR URL line above is canonical)
- `items/001-qa.md` — to be written by QA subagent
- `items/001-review.md` — to be written by review subagent
- PR base check: must equal `autodev/phase-0-1-foundation-feature` (the gate verifies this is non-protected)
