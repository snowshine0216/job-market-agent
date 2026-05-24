"""JobSource Protocol + SourceConfig loader (Phase 2: Bing-shaped).

The old TesterHome-shaped SourceConfig (with ListingConfig / DetailConfig /
content_block_markers / known_good_list_selector / base_url) was deleted
when TesterHomeSource was retired in Phase 2. A discriminated-union shape
(direct: DirectCrawlConfig | None + aggregator: AggregatorConfig | None)
is deferred until a second source ships that genuinely needs both branches.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

import yaml
from pydantic import BaseModel, ConfigDict

from jma.domain.models import SourceResult


class RateConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    delay_ms: int = 800
    max_retries: int = 3
    backoff_base_s: int = 2
    max_retries_5xx: int = 1


class SourceConfig(BaseModel):
    """Bing-aggregator shape. See config/sources/bing.yaml."""

    model_config = ConfigDict(frozen=True)
    name: str
    engine: str
    endpoint: str
    api_key_env: str
    results_per_query: int = 50
    target_sites: tuple[str, ...]
    id_patterns: dict[str, str] = {}
    site_names: dict[str, str] = {}
    query_template: str
    region_aliases: dict[str, list[str]] = {}
    rate: RateConfig = RateConfig()


def load_source_config(path: str | Path) -> SourceConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return SourceConfig.model_validate(raw)


@runtime_checkable
class JobSource(Protocol):
    name: str

    async def crawl(
        self,
        region: str,
        keywords: tuple[str, ...],
        max_pages: int,
        max_jobs: int,
    ) -> SourceResult: ...
