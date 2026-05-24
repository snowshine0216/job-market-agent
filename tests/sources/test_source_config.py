from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from jma.sources.base import JobSource, SourceConfig, load_source_config

REPO = Path(__file__).resolve().parents[2]


def test_loads_bing_yaml() -> None:
    cfg = load_source_config(REPO / "config/sources/bing.yaml")
    assert isinstance(cfg, SourceConfig)
    assert cfg.name == "bing"
    assert cfg.engine == "bing"
    assert cfg.endpoint == "https://serpapi.com/search"
    assert cfg.api_key_env == "SERPAPI_KEY"
    assert cfg.results_per_query == 50
    # Hosts that ship as targets in Phase 2.
    assert "zhipin.com" in cfg.target_sites
    assert "lagou.com" in cfg.target_sites
    assert "liepin.com" in cfg.target_sites
    assert "51job.com" in cfg.target_sites
    assert "zhaopin.com" in cfg.target_sites
    # URL-pattern map: zhipin + liepin populated; others intentionally absent.
    assert cfg.id_patterns["zhipin.com"] == r"/job_detail/(\d+)\.html"
    assert cfg.id_patterns["liepin.com"] == r"/job/(\d+)\.html"
    assert "lagou.com" not in cfg.id_patterns
    # Site-name map for the company heuristic.
    assert cfg.site_names["zhipin.com"] == "BOSS直聘"
    assert cfg.site_names["liepin.com"] == "猎聘"
    # Query template is multi-line YAML; key tokens present.
    assert "{keywords}" in cfg.query_template
    assert "{region_variants}" in cfg.query_template
    assert "{site_clause}" in cfg.query_template
    # Region aliases — Hangzhou variant set.
    assert cfg.region_aliases["Hangzhou"] == ["Hangzhou", "杭州", "杭州市"]
    # Rate config carries through unchanged.
    assert cfg.rate.delay_ms == 800
    assert cfg.rate.max_retries == 3


def test_missing_required_key_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump({"name": "x"}))  # no engine, endpoint, etc.
    with pytest.raises(ValidationError):
        load_source_config(bad)


def test_jobsource_protocol_runtime_checkable() -> None:
    class _Fake:
        name = "fake"

        async def crawl(self, region, keywords, max_pages, max_jobs):
            return None

    assert isinstance(_Fake(), JobSource)
