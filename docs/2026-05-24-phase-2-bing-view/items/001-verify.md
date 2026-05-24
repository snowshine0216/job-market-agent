Verdict: PASS

Subagent: sonnet
Source: Fallback used: direct entry-point invocation (manual smoke commands)
Entry point exercised:
  - uv run pytest -m 'not live' -q
  - uv run jma --help
  - uv run jma view --help
  - uv run jma crawl --help
  - env -u SERPAPI_KEY uv run jma crawl --source bing --region Hangzhou --keywords test
  - JMA_DATA_ROOT=$(mktemp -d) uv run jma view
  - file-existence checks (ls / grep)

Acceptance criteria observed:
  - 1: TesterHome retired — `src/jma/sources/testerhome.py` absent (ls: No such file or directory); no testerhome YAML in config/sources/ (only bing.yaml present); no testerhome tests in tests/sources/ (test_bing.py, test_bing_company_heuristic.py, test_http.py, test_source_config.py only); tests/live/ contains test_bing_live.py only; docs/diagrams/phase-1-testerhome-crawl.html absent; jma crawl --help shows `[default: bing]` (not testerhome); README.md and CLAUDE.md contain "testerhome" only as a legacy data-wipe migration instruction (not as a current source); CONTEXT.md clean.
  - 2: Bing aggregator wired — `src/jma/sources/bing.py` exists; `jma crawl --help` shows `--source TEXT [default: bing]`; invocation without SERPAPI_KEY exits 1 with message "missing env var SERPAPI_KEY (required by source 'bing')".
  - 3: `jma view` subcommand present — `jma --help` lists `view` command; `jma view --help` exits 0 and shows `--open`, `--run`, `--out` flags; `jma view` against an empty DB exits 2 with "no finished runs in <db_path>/jobs.db; run 'jma crawl ...' first".
  - 4: `run_jobs.raw_payload_ref` column — `grep raw_payload_ref src/jma/storage/db.py` returns 10+ matches including DDL line `raw_payload_ref TEXT NOT NULL`, migration ALTER TABLE, and INSERT into run_jobs with raw_payload_ref.
  - 5: ADR-0005 exists at `docs/adr/0005-bing-aggregator-source-and-snippet-data-quality.md` (ls exit 0).
  - 6: `docs/diagrams/phase-2-bing-aggregator-crawl.html` exists (ls exit 0); `docs/diagrams/phase-1-testerhome-crawl.html` absent (ls: No such file or directory).

Failures: none
