# CONTEXT.md

Glossary for the job-market-agent project. Defines the domain language used
across the codebase, specs, and ADRs. Implementation details belong in code
and `docs/adr/`, not here.

> Resolution log lives in `docs/superpowers/specs/` and ADRs. This file is
> the vocabulary only.

---

## Job

A real-world job posting that exists (or recently existed) on at least one
recruiting site. A Job is identified by its content — title, company, and
city — not by which site we found it on. The same Job can be seen by
multiple sources (e.g. surfaced on both `bing:zhipin.com` and on
`bing:zhaopin.com`); collapsing those into one Job is the responsibility of
aggregation queries, not the crawl path.

A Job's identity is the **canonical id** derived from normalised
`title | company | city`. See [[JobObservation]] for the per-source record
the crawler actually writes.

## JobObservation

A single sighting of a [[Job]] by one [[Source]] in one crawl. Each row in
the `jobs` table is a JobObservation. Two distinct postings at the same
company with the same title and city (e.g. two different teams hiring
"AI Platform Engineer @ Hangzhou") are two JobObservations *and* two Jobs
— their `source_internal_id` differs and we keep them apart.

A JobObservation carries one [[Source]]'s view: the URL it was found at,
the raw HTML blob, the `data_quality` of the extraction, and the
`source_internal_id`. Aggregations across the dataset collapse
JobObservations sharing a canonical id and prefer the highest
`data_quality` row when a single canonical view is needed.

## Run

One execution of `jma crawl` — a single CLI invocation. Each invocation
gets a fresh `Run` row regardless of inputs; re-running with identical
`--region`/`--keywords` produces a new Run, not a reused one. This is
what makes cross-Run trend analysis (Phase 6) possible: every invocation
leaves a permanent record of what it observed.

A Run does not own its [[JobObservation]]s — JobObservations are
long-lived rows keyed by `(source, source_internal_id)`, and the same
JobObservation can be observed in multiple Runs over time. Run ↔
JobObservation membership is recorded in a separate `run_jobs` join
table.

## PartialHarvest

A [[Source]]'s crawl outcome when some [[JobObservation]]s were
collected but the crawl was cut short by a block on a later fetch (the
classifier returned `RATE_LIMITED`, `BLOCKED`, or `ERROR` after at least
one earlier page succeeded). PartialHarvests are reported as
`SourceResult(status=OK, reason="partial: stopped at page N (…)", …)`
— the status describes data usability, the `reason` carries the block
detail.

"Fetch" here covers both listing pages and per-job detail pages. A
block tripped during detail-fetch enrichment also converts the crawl
to a PartialHarvest: the listing data we already have is still useful,
but we must not poison the URL cache by writing blob/cache rows for
blocked responses, and we must stop further detail fetches against the
same wall.

PartialHarvests bias the sample toward early listing pages (which on
most boards are the freshest postings), so downstream reports should
footnote the share of sources that were PartialHarvests when summarising
posting-age or freshness statistics.

## SalaryDisclosure

The three-way state a [[JobObservation]]'s salary can be in. Derived
from the `Salary` model's `parsed` flag plus whether `raw` is empty:

- **parseable** — the listing disclosed a salary and the parser
  extracted numeric `min`/`max` (and currency). `Salary.parsed=True`.
- **unparseable** — the listing disclosed a salary but in non-numeric
  form (`面议`, `Competitive`, "DOE"). `Salary.parsed=False` with
  `raw` non-empty. `currency` is `None` regardless of the input
  language; geographic currency assumption belongs at aggregation time,
  not parse time.
- **absent** — the listing did not mention a salary at all.
  `Salary.parsed=False` with `raw=""`.

Phase 4's monthly-salary aggregations consume only `parseable` rows
*and* only those whose original `period` was monthly or annual — daily
and hourly disclosures keep their per-period figure in `raw` but leave
`min`/`max` as `None`.

## CrawlScope

The `(region, keywords)` pair that defines a [[Run]]'s query intent.
Region and keywords always travel together — they are the user-facing
inputs to `jma crawl` and the natural grouping key for "the same crawl
re-run later" (Phase 6 trend deltas group by CrawlScope across Runs).

- **region** — free-text place name (`Hangzhou`, `北京`, `Berlin`). Used
  to filter [[JobObservation]]s by `Location.city`: drop observations
  whose city is set and does not match region; keep observations whose
  city is unparseable. Phase 2 expands region against
  `region_aliases.yaml` for multilingual matching.
- **keywords** — one or more free-text phrases. Each `--keywords`
  argument is one literal phrase (NFKC + case-insensitive substring on
  `title_raw`); multiple `--keywords` are OR'd. A `--keywords "AI agent"`
  argument matches the literal substring `"ai agent"`, **not** the
  individual tokens — this is intentional, not a tokenised search.

## Source

The named origin of a [[JobObservation]]. Written as
`<crawler>[':' <origin_site>]`:

- **Direct crawler** — a site we fetch and parse directly. Source is just
  the crawler name (e.g. `randstad`). TesterHome was the Phase-1 direct crawler
  (retired in Phase 2 — volume too low for AI-eng market stats).
- **Aggregator** — a search engine or meta-site that surfaces JDs hosted
  on third-party sites. Source is the crawler name plus the matched
  `target_sites` entry (subdomain-collapsed): `bing:zhipin.com`,
  `bing:lagou.com`, `bing:liepin.com`, `bing:51job.com`, `bing:zhaopin.com`.
  Phase 2 ships only the Bing aggregator via SerpAPI (ADR-0005).

Implications:
- `source_internal_id` for an aggregator-prefixed source is the
  *third-party site's* internal id (e.g. zhaopin's job id parsed out of
  the URL), not anything internal to the aggregator.
- "Show me everything that came from Bing" is `WHERE source LIKE 'bing:%'`.
- The crawler segment matches `[a-z0-9_]+`; the optional site segment is
  a lowercase hostname.

## Location

The geographic and work-mode attribution of a [[JobObservation]].
Carries `country`, `city`, `district`, and `work_mode`.

`city` always means **workplace** — where the role will be performed —
not where the employer is registered. The same Shanghai-headquartered
company hiring for a Beijing role yields `city="Beijing"`. When the
posting doesn't disclose the workplace (e.g. only the company name and
job title are present), `city` is `None`; it is never a best-guess
inferred from company HQ. A future "company city" attribute, if
needed, belongs in a separate field, not as a fallback for `city`.

`district` is a sub-city locality (`余杭`, `Pudong`) and is only set
when both a known city *and* its district are explicitly disclosed
together — never as a fallback container for unknown city names. A
title like `【厦门】X` (where `厦门` isn't in the city vocabulary yet)
yields `city=None, district=None`, not `district="厦门"`. The
shape-based probes (bracket / paren / base-prefix) are tried in fixed
precedence order and the **first probe whose captured token is a known
city wins** — probes that capture a non-city CJK token (e.g. a role
descriptor like `（高级）`) fall through to the next probe. See
[ADR 0004](docs/adr/0004-location-probe-first-known-city-wins.md)
(which supersedes [ADR 0003](docs/adr/0003-location-probe-precedence.md))
for the parser precedence rules.

`work_mode` is independent of city: a posting can be both
`city="Beijing"` and `work_mode=REMOTE` if it's a Beijing-anchored
remote role.

## URL freshness

A [[JobObservation]]'s `url` is captured at listing time and persists in
the DB forever — but the underlying forum post can be deleted by the
author (e.g. when the role is filled). `url_status` records the
**durable best-known truth** about whether the URL still resolves, not
the most recent raw HTTP outcome:

- `live` — the last detail-fetch returned 200.
- `gone` — the last detail-fetch returned 404 or 410. Aggregations
  filter on `url_status='gone'` to discount or drop these rows. (5xx
  is *not* in this set: a server outage is not evidence that a post
  was deleted — see [ADR 0003](docs/adr/0003-url-freshness-as-durable-signal.md).)
- `unknown` — the URL has never been verified. Either the row was
  inserted from a listing-only crawl, or every detail-fetch attempt
  so far returned a transient outcome (3xx, 429, 5xx, network error).

`url_last_checked_at` is the UTC timestamp of the last detail-fetch
that produced a *definitive* outcome (200 / 404 / 410). Transient
outcomes never write either field — they preserve whatever signal we
last earned. A row whose `url_last_checked_at IS NULL` has never been
verified; aggregation queries should treat such rows differently from
those that were verified in the past and may have drifted.

Listing-only crawls (default `jma crawl`, no `--with-detail`) do not
update freshness for any row. To detect stale URLs, run with
`--with-detail`.
