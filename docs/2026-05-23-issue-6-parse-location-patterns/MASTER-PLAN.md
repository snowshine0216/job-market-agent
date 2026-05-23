# Master Plan — Issue #6: parse_location coverage

**Mode:** plan
**Project type:** non-web (use `/verify` for post-ship verification; `/qa` is XOR'd out)
**PR shape:** A (per-item PR; default — no `--rollup`)
**Base / merge target:** `autodev/issue-6-location-patterns-feature` (feature branch off `main`; protected `main` left untouched at run end for user to merge themselves)
**Sub-branch:** `claude/issue-6-location-patterns-001` (will be cut off feature branch)

## Skill skips (plan mode)

- `superpowers:brainstorming` — SKIPPED (user-provided plan; spec stub inferred)
- `grill-with-docs` — SKIPPED (orchestrator never auto-invokes in plan mode; user authored the supporting context already)
- `superpowers:writing-plans` — SKIPPED (user-authored plan is verbatim)

## Phase 2 dispatches (per item)

| Phase | Skill / command | Model | Verdict file |
|-------|------------------|-------|--------------|
| branch | `git switch -c` (orchestrator) | — | (presence checked) |
| impl | `superpowers:subagent-driven-development` (ENTRY) | sonnet | commit SHA(s) recorded |
| drift | in-prompt logic (no skill) | sonnet | `items/001-drift.md` |
| ship | `/ship` (orchestrator-direct) | — | `items/001-ship.md` + `items/001-review.md` (inline) |
| verify | `/verify` (non-web XOR) | sonnet | `items/001-verify.md` |
| pr-review | `/code-review` on open PR | sonnet | `items/001-pr-review.md` |
| fix | triage subagent (if any verdict FAIL) | sonnet | re-dispatches failed verifiers |
| merge | `gh pr merge --squash --delete-branch` (Mode A) | — | merge commit SHA |

## Pre-merge gate (per item)

The pre-merge check requires PASS / PASS-WITH-NITS on each of:
- `items/001-drift.md`
- `items/001-ship.md`
- `items/001-verify.md`
- `items/001-review.md`
- `items/001-pr-review.md`
- Plus presence of `items/001-spec.md` and `items/001-plan.md`.

`items/001-grill.md` is **not** required in plan mode — PROGRESS row will show `⏭️ user-authored input`.

Pre-merge also verifies the PR base is **not** a protected branch (the feature branch `autodev/issue-6-location-patterns-feature` is non-protected by definition).

## Phase 3 — final validation

Single-task run: build / test sanity check (`uv run ruff check . && uv run ruff format --check . && uv run pytest`), run-level doc-sync (likely no-op — plan already encoded intent), final `/verify` smoke. Leave the feature branch open for the user to land into `main`.

## Working-tree provenance

This run started from a `main` working tree that contained uncommitted prep for issues #6, #7, and #8. Only the #6 supporting docs (Location glossary entry + ADR 0003 location-probe-precedence + plan file) were committed to this feature branch in `36ada55`. The #7 PartialHarvest changes in CONTEXT.md and the #7/#8 ADR + plan files remain uncommitted on the feature branch — they ride along but won't be touched by this implementation.
