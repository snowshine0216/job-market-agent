# Cross-source dedup via a shared `canonical_id` column

The same real-world [[Job]] often surfaces from multiple [[Source]]s — a
TesterHome posting can also appear via `bing:zhaopin.com` and
`bing:liepin.com`. We want one canonical view per Job for aggregations
(salary medians, skill frequencies) but we also want to keep every
per-source raw payload around. We also need to distinguish two
genuinely different postings that happen to share `(title, company,
city)` — e.g. two teams at one company hiring the same role.

The `jobs` table keeps its source-scoped primary key
(`sha1(source ':' source_internal_id)` when available, fallback
`sha1(source ':' normalize(title) '|' company '|' city)`), and we add a
non-unique `canonical_id TEXT NOT NULL` column derived from
`sha1(normalize(title) '|' normalize(company) '|' normalize(city))`.
Aggregations `GROUP BY canonical_id` and pick the highest
`data_quality` row per group; INSERT semantics stay dumb
(`INSERT OR REPLACE` per [[JobObservation]]).

## Considered options

- **A — Drop `internal_id` from the key entirely** (`id = sha1(title|company|city)`). Cross-source collapse happens at INSERT time. Rejected: loses intra-source disambiguation (two distinct postings collide), and requires conditional UPSERT logic so a low-quality snippet can't overwrite a high-quality full extraction.
- **C — Two-table model**: `jobs` keyed by canonical id + `job_sightings` keyed by `(source, internal_id)` with FK. Cleanest data model, but Phase 1 ships only one Source, so `job_sightings` would be 1:1 with `jobs` for the entire phase. Defer until two Sources exist to design against.

## Consequences

- Every aggregation that summarises "Jobs" rather than "JobObservations" **must** `GROUP BY canonical_id`. Forgetting that double-counts. Codify in `domain/stats.py` helpers.
- Row counts in `jobs` reflect observations, not unique jobs. The CLI summary and report metadata should distinguish the two ("47 jobs from 39 unique postings").
- Promoting to a two-table model later (Option C) remains an option once a second Source ships and gives us evidence about what `job_sightings` actually needs to hold.
