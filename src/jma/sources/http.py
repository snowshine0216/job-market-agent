"""Async HTTP wrapper with retry/backoff (spec §6 + slice 1.6).

Retry policy:
- status 429 or >= 500 → retry up to max_retries with exponential backoff
  (backoff_base_s ** attempt_index, starting at 1).
- status 401/403/other non-200 → return immediately (no retry).
- network errors propagate as httpx exceptions; callers may catch.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

from jma.sources.base import RateConfig


@dataclass(frozen=True)
class FetchResult:
    status_code: int
    headers: dict[str, str]
    body: str
    attempts: int


_SleepFn = Callable[[float], Awaitable[None]]


class AsyncHttpClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        rate: RateConfig,
        sleep: _SleepFn | None = None,
    ) -> None:
        self._client = client
        self._rate = rate
        self._sleep: _SleepFn = sleep or asyncio.sleep

    async def fetch(self, url: str) -> FetchResult:
        attempts = 0
        while True:
            attempts += 1
            resp = await self._client.get(url)
            should_retry = resp.status_code == 429 or resp.status_code >= 500
            if not should_retry or attempts > self._rate.max_retries:
                return FetchResult(
                    status_code=resp.status_code,
                    headers=dict(resp.headers),
                    body=resp.text,
                    attempts=attempts,
                )
            await self._sleep(self._rate.backoff_base_s**attempts)
