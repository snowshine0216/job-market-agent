# Bing aggregator source + snippet-only data quality

Phase 2 retires the TesterHome direct crawler and ships a single
**Bing-aggregator** source via SerpAPI's Bing engine. The new source
surfaces [[JobObservation]]s from BOSS Zhipin, Lagou, Liepin, 51job, and
Zhilian — all reached via `site:` operators in one SerpAPI query — and
maps each organic result to a `Job` using only the SERP snippet. No
detail-fetch in Phase 2.

This ADR captures the conventions that future sources must respect.

## `bing:<host>` source-naming convention

A [[Source]] string for a Bing-surfaced row is `bing:<host>` where
`<host>` is the **matched `target_sites` entry from `config/sources/bing.yaml`**,
*not* the raw URL `netloc`. So `www.zhipin.com`, `m.zhipin.com`, and
`app.zhipin.com` all collapse to `bing:zhipin.com`. Results whose host
doesn't match any `target_sites` entry are dropped (the count surfaces in
`SourceResult.reason`) so the universe of `source` values stays bounded
by the YAML.

Implications:
- `WHERE source LIKE 'bing:%'` returns every Bing row.
- `WHERE source = 'bing:zhipin.com'` returns BOSS rows regardless of which
  subdomain Bing surfaced.
- [ADR-0001](0001-cross-source-dedup-via-canonical-id.md)'s cross-source
  collapse works without further changes — `canonical_id` is computed from
  `(title, company, city)` and is source-independent by construction.
- `CONTEXT.md` already documents the `bing:<host>` shape in the [[Source]]
  glossary entry; this ADR is the formal decision record.

## Per-host URL regex YES, per-host snippet regex NO

`config/sources/bing.yaml` ships an `id_patterns` map (host → URL-path
regex) that the source uses to extract `source_internal_id` when the URL
has a stable pattern (e.g. `zhipin.com /job_detail/(\d+)\.html`). Hosts
without a stable pattern are left out of the map; `source_internal_id`
stays `None` and `dedup.py:job_id()` falls through to the content-hash
branch.

The same `bing.yaml` does **not** ship — and **must not** ship — per-host
snippet regexes. Company extraction from `title` is heuristic-only:
generic `[|\-_]` delim-split, with a per-host `site_names` YAML anchor for
2-part titles (so `"AI Agent | BOSS直聘"` yields `company=None` rather
than `company="BOSS直聘"`).

The asymmetry is intentional. URL path schemes are stable vendor
convention and change rarely — a `id_patterns` map costs little to
maintain. Snippet formats are noisy, vary across boards, and Phase 3's
LLM extraction will replace any per-site snippet regex anyway, so paying
that tax now would be premature work that has to be torn out.

## `data_quality=0.4` is the snippet-only baseline

Phase 2 emits `data_quality=0.4` for every Bing row. This reflects
snippet-only confidence: the SERP snippet is rich enough to parse a
salary token or a years-of-experience in ~70-80% of cases, but it's
unreliable for `company`, `city`, `skills`, and `description`.

Reserved values for later phases:
- **1.0** — full structured-source row. No source emits this in Phase 2.
- **0.9** — Bing row + successful detail-fetch enrichment. Reserved for
  the deferred Phase 2.1.
- **0.7** — LLM-enriched row. Reserved for Phase 3 (DeepSeek extraction).

PLAN.md's Phase 4 aggregation rule — "salary medians use rows with
`data_quality >= 0.7`, top-skills weight linearly" — stands and is
forward-compatible: in Phase 2 it filters every Bing row out of salary
medians, which is the right outcome until a higher-confidence row class
exists.

The raw SERP snippet is stored in `Job.description_text` as Phase 3's
LLM-extraction input. `Location.city` is always `None` in Phase 2
(per [CONTEXT.md "Location"](../../CONTEXT.md#location) — we do not
best-guess city from a SERP snippet).

## Detail-fetch deferred to Phase 2.1 (with a trigger)

Detail-fetch enrichment is explicitly deferred. Every target board
(zhipin / lagou / liepin / 51job / zhaopin) sits inside the set whose
anti-bot stack we already chose not to crawl directly, so most detail
fetches would return BLOCKED/429 for no Job-row gain — paying ~50-150
HTTP calls per crawl for a row that snippet-only already produced.

**Trigger to re-open:** a live SerpAPI sample where at least one target
board's detail pages return useful 200s (evidence that anti-bot is not
uniform across the target set). When that happens, this ADR grows a
**no-halt-on-detail-block** clause (losing one JD fetch is one row's
data-quality drop, not a crawl-ender, because the SerpAPI page is
already in hand) and `bing.py` gains an `--with-detail`-style code path.
The column footprint is already in place: `url_status`,
`url_last_checked_at`, and the `data_quality=0.9` reserved value.

## SerpAPI as the SERP provider

Microsoft's Bing Web Search v7 was retired 2025-08-11. SerpAPI is the
closest in-spirit replacement that preserves Bing SERP semantics and
strong `site:` operator support. Free tier 100 queries/month is enough
for personal-use crawl cadence (~20 crawls/month at 5 SERP pages each).
**Reconsider when:** SerpAPI's $75/mo dev tier becomes a budget concern,
SerpAPI starts blocking the `site:` queries we rely on, or a comparable
free alternative emerges (Brave Search API, a revived Bing endpoint).

## First concrete instance of "merge by confidence"

[ADR-0003](0003-url-freshness-as-durable-signal.md) flagged "merge by
confidence" as a future generalisation of its conditional `ON CONFLICT
DO UPDATE` rule. Phase 2 introduces the first concrete split:
`raw_payload_ref` is now stored in two places — `jobs.raw_payload_ref`
(latest-seen, for aggregation-level reads that don't care which Run
observed which blob) and `run_jobs.raw_payload_ref` (per-Run snapshot,
read by `jobs_for_run` so `jma view --run <old>` links to the blob
captured during *that* Run). The same split will eventually apply to
`company`, `salary`, `description_text`, `posted_at` when a future ADR
generalises the rule.

## Consequences

- Every aggregation that summarises "Jobs from Bing" must use
  `WHERE source LIKE 'bing:%'` (or filter by canonical_id and prefer
  high-`data_quality` rows per ADR-0001).
- `Job.source_internal_id` is best-effort and `None` on hosts without an
  `id_patterns` entry — code that uses it must already tolerate `None`
  (it does, via `dedup.py:job_id()`'s content-hash branch).
- The `_apply_url_freshness` helper is dead code in Phase 2 (deleted
  alongside `sources/testerhome.py`). It will be reborn in `sources/bing.py`
  when Phase 2.1 ships, with its tests re-ported from the old
  `tests/sources/test_url_freshness.py`.
- The "snippet quality is now the floor of Phase 2 data quality" risk is
  mitigated by the opt-in live tripwire in `tests/live/test_bing_live.py`
  asserting >=1 row each with parsed salary, posted_at, and experience —
  not as a flaky CI gate, but as a manual checkpoint when SerpAPI behaviour
  is questioned.
