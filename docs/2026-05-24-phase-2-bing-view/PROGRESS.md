# PROGRESS — Phase 2: Bing Aggregator + `jma view`

Legend: ⏳ pending · 🔄 in-progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped · ⛔ refused gate

| id | spec | grill | plan | branch | impl | drift | PR (ship) | verify | review | pr-review | fix | merge |
|----|------|-------|------|--------|------|-------|-----------|--------|--------|-----------|-----|-------|
| 001 | ⏭️ user-provided | ⏭️ user-grilled | ✅ | ✅ `claude/phase-2-bing-view-001` | ✅ `d24d289` | ✅ [001-drift.md](items/001-drift.md) | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |

## Notes

- **spec ⏭️** — user provided source spec at `docs/superpowers/specs/2026-05-23-phase-2-bing-aggregator-and-view-design.md`; copied verbatim to `items/001-spec.md`.
- **grill ⏭️** — pre-completed per spec-mode contract; source spec resolves 18 decisions and declares "ready for implementation plan". Orchestrator does not auto-invoke grill.
- **qa column omitted** — non-web project; uses `verify` instead (project-type XOR per MASTER-PLAN).

## Artifact links

| File | Status |
|------|--------|
| [items/001-spec.md](items/001-spec.md) | ✅ written |
| [items/001-plan.md](items/001-plan.md) | ✅ written by Opus `superpowers:writing-plans` (commit `366eda7`, 100 steps, 29 TDD test steps) |
| items/001-drift.md | ⏳ |
| items/001-ship.md | ⏳ |
| items/001-verify.md | ⏳ |
| items/001-review.md | ⏳ (captured inline from `/ship`) |
| items/001-pr-review.md | ⏳ |
