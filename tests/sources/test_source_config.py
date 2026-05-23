from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from jma.sources.base import JobSource, SourceConfig, load_source_config

REPO = Path(__file__).resolve().parents[2]


def test_loads_testerhome_yaml() -> None:
    cfg = load_source_config(REPO / "config/sources/testerhome.yaml")
    assert isinstance(cfg, SourceConfig)
    assert cfg.name == "testerhome"
    assert cfg.base_url == "https://testerhome.com"
    assert cfg.listing.url_template.endswith("/jobs?page={page}")
    assert cfg.listing.list_item_selector == ".topics .topic"
    assert cfg.listing.title_selector == ".title a"
    assert cfg.listing.href_attr == "href"
    assert cfg.listing.posted_at_attr == ".time@title"
    assert cfg.detail.body_selector == ".topic-detail .markdown-body"
    assert cfg.requires_browser is False
    assert cfg.content_block_markers == ()
    assert cfg.known_good_list_selector == ".topics .topic"
    assert cfg.rate.delay_ms == 800
    assert cfg.rate.max_retries == 3
    assert cfg.rate.backoff_base_s == 2


def test_missing_required_key_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump({"name": "x"}))  # no base_url, listing, etc.
    with pytest.raises(ValidationError):
        load_source_config(bad)


def test_jobsource_protocol_runtime_checkable() -> None:
    # A trivial class matching the Protocol signature should pass isinstance.
    class _Fake:
        name = "fake"

        async def crawl(self, region, keywords, max_pages, max_jobs):
            return None

    assert isinstance(_Fake(), JobSource)
