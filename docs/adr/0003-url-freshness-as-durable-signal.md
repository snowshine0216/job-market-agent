# URL freshness is a durable signal, decoupled from `data_quality`

A [[JobObservation]]'s `url_status` records the best-known truth about
whether the underlying posting still exists — not the most recent raw
HTTP outcome of fetching it. Only definitive outcomes (HTTP 200, 404,
410) update the field; transient outcomes (3xx, 429, other 4xx, 5xx,
network errors) preserve whatever signal we last earned. `url_status`
does not lower `data_quality`; the two carry independent information and
aggregations filter on `url_status='gone'` directly.

`UrlStatus(StrEnum)` is one of `live` / `gone` / `unknown`. The companion
`url_last_checked_at` is updated only when `url_status` is written, so a
non-NULL timestamp implies the row has been definitively verified at
least once.

Persistence uses `INSERT … ON CONFLICT(id) DO UPDATE` so the two
freshness columns can be conditionally preserved on re-insert. Every
other column on `jobs` still overwrites on conflict (`field =
excluded.field`) — same semantic as the previous `INSERT OR REPLACE`.

## Considered options

- **"Last raw outcome" model** (write whatever the last fetch returned, including `unknown` on 429). Rejected: a transient rate-limit on Day 2 would erase a `live` signal earned on Day 1, making `url_status='live'` an unstable answer that the next crawl can silently invalidate. The whole point of the column is to be queryable as evidence.
- **Treat 5xx as `gone`** (the original plan grouped 4xx-permanent and 5xx together). Rejected: a 20-minute site outage returning 502 across every detail fetch would mass-mark every URL touched during the outage as gone, and the rows that don't re-appear on the next listing would stay mismarked forever. 5xx is server health, not resource existence.
- **Clamp `data_quality` to `0.5` when `url_status='gone'`** (issue #8's Option 2). Rejected: (a) the listing-time fields (`title`, `company`, `salary`) are *still legitimately captured* — the URL going dead later doesn't retroactively make our extraction worse; (b) `data_quality` becomes an overloaded number once multiple penalty sources stack (URL gone, partial extraction, parse failures), and aggregations lose the ability to ask "*why* is this row low quality?"; (c) `url_status='gone'` is strictly richer information than `data_quality<1.0` — it tells you *what* is wrong. Filter on `url_status` directly.
- **Read-then-merge in the pipeline** (look up the existing row's freshness fields before applying the helper). Rejected: forces a per-job DB read inside the crawl loop, and the merge logic ends up duplicating in the pipeline what the SQL upsert can express in one place. The conditional `ON CONFLICT DO UPDATE` keeps the helper pure and centralises the rule.
- **Add `url_last_attempt_at` as a second timestamp** (distinguish "haven't fetched in 30 days" from "have fetched 5× and always got 429"). Deferred: no current aggregation needs the distinction, and the column is purely additive when we do.
- **Expand `UrlStatus` to include `redirected` / `auth_required` / `soft_deleted`** (carry richer HTTP semantics). Deferred: TesterHome posts in practice are either present (200) or deleted (404); no observed need yet. Re-open with an ADR if a second source forces the issue.

## Consequences

- `_apply_url_freshness` is pure and stateless: same `(job, status_code, checked_at)` always returns the same Job. Idempotent by construction — the helper never reads from or writes to the DB.
- Listing-only crawls (no `--with-detail`) never set freshness. Rows from listing-only crawls keep `url_status='unknown'`, `url_last_checked_at=NULL` until a later `--with-detail` invocation visits the same URL. Aggregation queries that care about freshness should treat `url_status='unknown'` AND `url_last_checked_at IS NULL` as "never verified."
- The CLI summary's `gone_urls=N` segment is *omitted* (not zeroed) when no Job in the run has a `url_last_checked_at` — so the operator can distinguish "we checked, found none gone" from "we didn't check at all."
- `_INSERT_JOB` is now an explicit upsert with a long `DO UPDATE SET` clause. Future fields added to `jobs` need a line in that clause too; the cost of forgetting is silent data-loss-on-listing-only-re-crawl. A future ADR should generalise this into a "merge by confidence" policy covering `company`, `salary`, `description_text`, `posted_at`, etc. — the same overwrite-on-listing-crawl problem affects all detail-fetched fields, not just freshness.
- `data_quality` remains undefined in CONTEXT.md. This ADR explicitly does not introduce a quality penalty, so the field stays a free `float = 1.0` for now. When a second source of quality degradation arrives, that's the right moment for a glossary entry, not this one.
