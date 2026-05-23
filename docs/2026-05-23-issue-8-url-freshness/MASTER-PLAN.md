# MASTER-PLAN — Issue #8 URL freshness

Mode: plan
Project type: non-web   # Python 3.12 CLI (`jma`) — post-ship verifier = /verify
PR shape: A             # default; user did not pass --rollup
Item order: 001 only
Base branch: main (protected — synthetic feature branch in use)
Feature branch: autodev/issue-8-url-freshness-feature
Sub-branch prefix: claude/issue-8-url-freshness-

## Skill skips (plan mode)

- superpowers:brainstorming  → ⏭️ skipped (user provided plan)
- grill-with-docs            → ⏭️ skipped (plan mode never auto-grills user-authored input; ADR 0003 is the user-authored grilling output)
- superpowers:writing-plans  → ⏭️ skipped (user-authored plan copied verbatim to items/001-plan.md)

## Per-item phases (run for 001)

branch → impl → drift → ship (PR + docs + inline review) → (verify ‖ pr-review) → fix → merge

## Loop exit contract (item 001)

All three post-ship verdicts must be PASS or PASS-WITH-NITS:
- items/001-verify.md   (non-web → /verify; XOR /qa)
- items/001-review.md   (captured inline by /ship steps 8+9)
- items/001-pr-review.md (/code-review against the open PR)

Plus items/001-drift.md and items/001-ship.md PASS, items/001-spec.md + items/001-plan.md present.
items/001-grill.md does NOT exist — PROGRESS shows ⏭️ user-authored input (ADR 0003).

## Dependency notes

- Issue #7 (`_enrich_page` detail-fetch) is already merged on `main` at commit `f307226`.
- The user's plan references two currently-untracked files belonging to this issue:
  - `docs/adr/0003-url-freshness-as-durable-signal.md`
  - `docs/superpowers/plans/2026-05-23-issue-8-url-freshness.md`
- Both are committed together with the run-dir artifacts at Phase 1 close-out
  (on the feature branch).

## Subagent dispatch contract

| Phase | Model | Skill |
|-------|-------|-------|
| 001-impl    | sonnet | superpowers:subagent-driven-development (per-task fresh-context subagents) |
| 001-drift   | sonnet | inline diff-vs-plan check (no skill) |
| 001-ship    | sonnet | /ship (captures inline review) — fallback to `gh pr create` |
| 001-verify  | sonnet | /verify (Python CLI smoke + tests + lint) |
| 001-pr-review | sonnet | /code-review on open PR |
| 001-fix     | sonnet | fresh subagent per round, reads prior verdict files |

If Agent dispatch fails with "Usage credits required for 1M context" (as occurred
on the Issue #7 run), fall back to inline execution in the orchestrator session.
All verdict files are still written to disk and the merge gate stays enforced.

## Protected-branch handling

`main` is the repo default branch and listed in the autodev protected-branches set.
The user's invocation contained no explicit "merge to main" opt-in this turn, so:
- A synthetic feature branch `autodev/issue-8-url-freshness-feature` is created off `main`.
- The sub-branch PR lands into the feature branch (Mode A).
- The feature-branch-to-`main` PR is **left open at end of run** for the user to land themselves.
