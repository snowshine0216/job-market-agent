"""JobSource Protocol + SourceConfig loader (spec §7.1, §7.2)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

import yaml
from pydantic import BaseModel, ConfigDict

from jma.domain.models import SourceResult


class ListingConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    url_template: str
    list_item_selector: str
    title_selector: str
    href_attr: str
    posted_at_attr: str


class DetailConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    body_selector: str


class RateConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    delay_ms: int = 800
    max_retries: int = 3
    backoff_base_s: int = 2


class SourceConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    base_url: str
    listing: ListingConfig
    detail: DetailConfig
    requires_browser: bool = False
    content_block_markers: tuple[str, ...] = ()
    known_good_list_selector: str
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
