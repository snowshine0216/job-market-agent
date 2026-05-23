# Cheaper 5xx Retries — Master Plan

Mode: **spec** (single feature, in-chat goal, no concrete plan steps — input IS the spec)
Project type: **non-web** (Python CLI; `/verify` not `/qa`)
PR shape: **A** (per-item PR; no `--rollup` opt-in)
Base branch: `autodev/cheaper-5xx-retries-feature` (synthetic feature branch off `main`; protected-branch rule prevents auto-merge to main)
Default branch: `main`

## Pipeline (single item, N=1)

1. `001-spec` ⏭️ pre-completed (input is the spec — copied to `items/001-spec.md`)
2. `001-grill` ⏭️ pre-completed (spec mode does not auto-invoke grill)
3. `001-plan` — Opus subagent via `superpowers:writing-plans` → `items/001-plan.md`
4. `001-branch` — cut `fix/cheaper-5xx-retries` off `autodev/cheaper-5xx-retries-feature`
5. `001-impl` — Sonnet subagent via `superpowers:subagent-driven-development` (TDD per project CLAUDE.md)
6. `001-drift` — diff vs plan checklist
7. `001-ship` — `/ship` opens PR into `autodev/cheaper-5xx-retries-feature`; captures inline review verdict
8. Parallel post-ship dispatches:
   - `001-verify` — `/verify` smoke-test (non-web project)
   - `001-pr-review` — `/code-review` on the PR
9. `001-fix` — triage 3 verdicts (verify + review + pr-review); loop until all PASS / PASS-WITH-NITS
10. `001-merge` — pre-merge gate (protected-base check passes since base = feature branch, not main) + `gh pr merge --squash`

## Final landing

Phase 3 leaves `autodev/cheaper-5xx-retries-feature` open for the user to merge into `main` themselves.
