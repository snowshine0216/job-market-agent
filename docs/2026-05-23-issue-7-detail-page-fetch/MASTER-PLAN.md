# MASTER-PLAN — Issue #7 detail-page fetch

Mode: plan
Project type: non-web   # Python 3.12 CLI (`jma`) — post-ship verifier = /verify
PR shape: A             # default; user did not pass --rollup
Item order: 001 only
Base branch: main (protected — synthetic feature branch in use)
Feature branch: autodev/issue-7-detail-page-fetch-feature
Sub-branch prefix: claude/issue-7-detail-page-fetch-

## Skill skips (plan mode)

- superpowers:brainstorming  → ⏭️ skipped (user provided plan)
- grill-with-docs            → ⏭️ skipped (plan mode never auto-grills user-authored input)
- superpowers:writing-plans  → ⏭️ skipped (user-authored plan copied verbatim to items/001-plan.md)

## Per-item phases (run for 001)

branch → impl → drift → ship (PR + docs + inline review) → (verify ‖ pr-review) → fix → merge

## Degraded subagent mode (environmental)

Agent dispatch from this orchestrator session is blocked by:
> "API Error: Usage credits required for 1M context · turn on usage credits at claude.ai/settings/usage"
(Orchestrator runs on Opus 4.7 1M; the Agent tool inherits the parent context window and Anthropic refuses without 1M credits enabled.)

Workaround: execute impl + drift + ship + verify + pr-review + fix INLINE in the orchestrator session.
Quality trade-off:
- No fresh-context isolation per phase (single orchestrator context across all gates)
- /ship subagent dispatch unavailable → use `gh pr create` directly (last-resort path)
- /code-review subagent dispatch unavailable → run /code-review skill inline against the PR
- All verdict files (drift, ship, verify, review, pr-review) are still written to disk and merge-gated identically
User dismissed the AskUserQuestion prompt and said "continue", so this is the chosen path.

## Loop exit contract (item 001)

All three post-ship verdicts must be PASS or PASS-WITH-NITS:
- items/001-verify.md   (non-web → /verify; XOR /qa)
- items/001-review.md   (captured inline by /ship steps 8+9)
- items/001-pr-review.md (/code-review against the open PR)

Plus items/001-drift.md and items/001-ship.md PASS, items/001-spec.md + items/001-plan.md present.
items/001-grill.md does NOT exist — PROGRESS shows ⏭️ user-authored input.

## Dependency notes

The user's plan references documents currently uncommitted on main:
- CONTEXT.md modifications (PartialHarvest covers detail-fetch blocks)
- docs/adr/0001-...md amendment (data_quality deferred)
- docs/adr/0003-canonical-id-is-latest-wins-not-run-stable.md (load-bearing for Task 4)

These are committed together with the design artifacts at Phase 1 close-out.
Two unrelated files on the working tree (docs/adr/0003-url-freshness-as-durable-signal.md
and docs/superpowers/plans/2026-05-23-issue-8-url-freshness.md) belong to Issue #8 and
are explicitly excluded from this run.
