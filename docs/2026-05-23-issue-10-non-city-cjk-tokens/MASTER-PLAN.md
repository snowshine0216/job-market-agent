# MASTER-PLAN — Issue #10

- **Mode:** spec (single-feature; user-provided issue body is the spec)
- **PR shape:** A (per-item PR into a feature branch; user did not pass `--rollup`)
- **Project type:** non-web (Python CLI + library)
- **Verifier:** `/verify` (entry-point smoke against `parse_location`)
- **Base branch (final):** `main` (user lands the feature branch themselves; autodev never auto-merges into main)
- **Feature branch:** `autodev/issue-10-first-known-city-feature`
- **Sub-branch (001):** `claude/issue-10-first-known-city-001`

## Phase loop (one item)

1. ⏭️ spec (copied from issue body)
2. ⏭️ grill (pre-completed; spec mode contract)
3. plan — Opus `superpowers:writing-plans` → `items/001-plan.md`
4. branch — cut feature + sub-branch
5. impl — Sonnet `superpowers:subagent-driven-development`
6. drift — Sonnet drift subagent (must PASS before ship)
7. ship — `/ship` opens PR into feature branch; captures review inline → `items/001-review.md`
8. verify ‖ pr-review (parallel) — `/verify` → `items/001-verify.md`; `/code-review` → `items/001-pr-review.md`
9. fix loop — triage 3 verdicts (verify + review + pr-review); fix until all PASS / PASS-WITH-NITS
10. merge — pre-merge gate then `gh pr merge --squash --delete-branch` (base = feature branch, not protected)

## Final landing

Feature branch left open. User lands `autodev/issue-10-first-known-city-feature` → `main` themselves.

## Model contract (subagent dispatch)

- Plan: `model=opus`
- Impl / Drift / Verify / PR-review / Fix: `model=sonnet`
- Orchestrator (this session): respect user's default
