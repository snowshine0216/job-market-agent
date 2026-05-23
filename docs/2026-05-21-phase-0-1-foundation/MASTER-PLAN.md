# MASTER-PLAN — Phase 0 + Phase 1 Foundation

**Mode:** spec (N=1)
**PR shape:** A (default — per-item PR; no `--rollup` opt-in this turn)
**Run dir:** `docs/2026-05-21-phase-0-1-foundation/`
**Feature branch:** `autodev/phase-0-1-foundation-feature` — synthesized off `main` (which is the repo default and protected; no merge-to-main opt-in this turn)
**Sub-branch for item 001:** `claude/phase-0-1-foundation-001`
**Target for sub-PR:** the feature branch (not `main`)
**Final landing:** feature branch is left open at end of run; user PRs/merges to `main` themselves.

## Per-mode skill skips (spec mode)

| Phase | Skill | Skipped? | Reason |
|-------|-------|----------|--------|
| spec | `superpowers:brainstorming` | ⏭️ skipped | User authored the spec at [items/001-spec.md](items/001-spec.md); already includes goals + acceptance + decisions. |
| plan | `superpowers:writing-plans` | run | Spec is goals-shaped, not step-shaped — we still need an implementation plan. Plan subagent dispatches on **opus**. |
| branch | n/a | run | Cut `claude/phase-0-1-foundation-001` off the feature branch. |
| impl | `superpowers:subagent-driven-development` | run | Implementation subagent on **sonnet**, follows the plan; TDD per CLAUDE.md (red-green-refactor). |
| ship | `gstack-ship` | run | Opens PR for the sub-branch into the feature branch. |
| QA | `gstack-qa` | run | Subagent on **sonnet**; produces `items/001-qa.md`. |
| review | `superpowers:requesting-code-review` | run | Subagent on **sonnet**; produces `items/001-review.md`. |
| fix | (triage loop) | run as needed | Fresh subagent per round of findings until QA=PASS and review has zero blockers/latent. |
| merge | (gh pr merge) | run | Pre-merge gate: protected-base check + ship + QA verdict + review verdict. Squash-merge into feature branch. |

## Subagent model contract

- Orchestrator (this session): session-default model, no override.
- Plan subagent: `model="opus"` (plans are source of truth for impl subagent — must be right).
- Implement / QA / ship / review / fix subagents: `model="sonnet"`.

## Branching & merging policy

- Feature branch `autodev/phase-0-1-foundation-feature` was created off `main` HEAD and includes the design-artifact commit (this directory + companion docs that were uncommitted on `main` — spec rev2 changes, `CONTEXT.md`, `docs/adr/0001-*.md`, `docs/adr/0002-*.md`).
- Sub-branch PRs target the feature branch only. Pre-merge gate aborts any attempt to land into `main` (or any other protected branch) absent explicit user opt-in.
- Mode A (per-item PRs): squash-merge each sub-branch PR into the feature branch via `gh pr merge --squash --delete-branch`.
- With N=1, this run produces exactly one sub-PR.

## Risks specific to this run

| Risk | Mitigation |
|------|------------|
| Spec is long and dense (13 TDD slices); plan subagent might under-decompose. | Plan subagent runs on opus with the full spec as input; `superpowers:writing-plans` enforces step-with-verification structure. |
| Per-source `respx`-mocked tests vs reality drift. | Spec already designs against this (HTML fixtures + opt-in `-m live` smoke). Live smoke is part of exit criteria but not CI-blocking. |
| `pytest-asyncio` setup friction at slice 0.1. | Slice 0.1 explicitly red-tests `pytest exits 0` — TDD will catch config errors before any domain code. |
| Listing-only parser doesn't see TesterHome's actual current DOM. | Live smoke at slice 1.13 catches drift; selectors live in YAML so a fix is one file edit. |
| Feature branch left open at end — user might forget to land it. | `final-validation.md` close-out explicitly states "Merged into protected branch: no (left open for user review)" in PROGRESS.md. |
