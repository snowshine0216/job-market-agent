# MASTER-PLAN — Phase 2: Bing Aggregator + `jma view`

Mode: spec
Project type: non-web
PR shape: A
Base branch: main
Feature branch: autodev/phase-2-bing-view-feature
Item order: 001 (degenerate N=1)

## Skill skips (spec mode)

| Phase | Skill | Status |
|-------|-------|--------|
| spec | `superpowers:brainstorming` | ⏭️ skipped — user authored the spec; copied verbatim to `items/001-spec.md` |
| grill | `grill-with-docs` | ⏭️ pre-completed — user-grilled. The source spec resolved 18 decisions, declares "Status: ready for implementation plan", lists explicit out-of-scope items with re-open triggers, and includes a tested acceptance demo. Orchestrator must NOT auto-invoke grill (decision lock per mode-spec.md entry contract). |
| plan | `superpowers:writing-plans` | runs (Opus subagent) |
| impl | `superpowers:subagent-driven-development` | runs (Sonnet) |
| drift | in-prompt | runs (Sonnet) |
| ship | `/ship` | runs (primary) |
| qa | `/qa` | ⏭️ skipped — non-web project |
| verify | `/verify` | runs (Sonnet) — XOR branch |
| review | captured inline from `/ship` steps 8+9 | runs |
| pr-review | `/code-review` | runs (Sonnet) |
| fix | triage subagent | runs only if any post-ship verdict FAILs |
| merge | `gh pr merge --squash --delete-branch` | runs (Mode A) |

## Loop exit contract

The single item exits the per-item loop only when ALL THREE post-ship verdicts pass:

1. `items/001-verify.md` → `^Verdict: PASS`
2. `items/001-review.md` → `^Verdict: PASS|PASS-WITH-NITS` (inline from `/ship`)
3. `items/001-pr-review.md` → `^Verdict: PASS|PASS-WITH-NITS`

Plus the upstream gates: `items/001-drift.md` PASS, `items/001-ship.md` exists with `PR:` first line, `items/001-spec.md` + `items/001-plan.md` present.

`items/001-grill.md` is **absent by design** in spec mode (PROGRESS shows ⏭️); merge gate treats grill verdict as absence-OK in spec mode per mode-spec.md.

## Protected-branch posture

`main` is protected. The synthetic feature branch `autodev/phase-2-bing-view-feature` is the base for the per-item PR. The orchestrator does NOT merge anything into `main` — the feature branch is left open for the user to land manually after the run.

## Out-of-scope guard (passes through to plan phase)

The source spec §1 lists deferred items (Randstad, Playwright, LLM extraction, `sources status`, view filters, direct BOSS, Phase 2.1 detail-fetch, live CI quota burn). The Opus plan subagent MUST NOT plan implementation for any of those. If it tries, the orchestrator rejects the plan and re-dispatches with the violation cited.
