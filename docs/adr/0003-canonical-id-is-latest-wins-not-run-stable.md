# `canonical_id` reflects best-known extraction, not what a Run originally saw

Detail-page enrichment (#7) populates `company` for a [[JobObservation]]
that listing-only crawls left as `None`. Because `canonical_id` is
derived from `normalize(title | company | city)` (ADR-0001), enriching
`company` shifts the row's `canonical_id`. `INSERT OR REPLACE` on
`jobs.id` then overwrites the previous canonical_id. The same
JobObservation can therefore carry different canonical_ids across
[[Run]]s.

We accept this — richer extraction is strictly better — and define
`canonical_id` to be the **latest-wins** view of a JobObservation, not a
snapshot of what any particular Run observed.

`job_id` stays stable across enrichment for any source that exposes an
`internal_id` (TesterHome's `/topics/NNN`): `job_id` is
`sha1(source:internal_id)` and ignores company/title/city in that path.
`_enrich_from_detail` therefore must **not** recompute `id` — only
`canonical_id`, `company`, and `salary`.

## Considered options

- **Freeze `canonical_id` at first observation.** Rejected: locks in
  the lower-quality canonical_id and breaks cross-source dedup once a
  better extraction arrives from any source.
- **Snapshot `canonical_id` into `run_jobs(run_id, job_id, canonical_id_at_observation)`.** Rejected for Phase 1: speculative complexity for a Phase-6 question we don't have evidence for yet. Revisit when trend reports actually need per-Run canonical groupings.
- **Use only `internal_id`-based identity, drop `canonical_id` entirely.** Rejected by ADR-0001 — we need cross-source dedup, and not every source will expose an `internal_id`.

## Consequences

- Phase-6 trend queries that ask "what canonical Jobs did Run X cover?"
  see the current canonical_id, not what was on disk during Run X. If a
  report needs Run-time canonical grouping later, it must snapshot
  canonical_id into `run_jobs` at observation time — a forward
  migration, not a Phase-1 concern.
- `_enrich_from_detail` recomputes only the fields whose inputs changed
  (`canonical_id`, `company`, `salary`). Tests must assert that `id` is
  unchanged when `internal_id` is present, not vacuously assert
  equality against a `job_id(...)` call that happens to ignore
  `company`.
- Aggregation helpers (`domain/stats.py`, when they land) should treat
  `canonical_id` as a function of the current `jobs` row and not join
  through `run_jobs` for canonical grouping.
