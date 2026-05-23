"""Async HTTP wrapper with retry/backoff (spec §6 + slice 1.6).

Retry policy:
- status 429 → retry up to `rate.max_retries` (default 3) with exponential
  backoff (`backoff_base_s ** attempt_index`, starting at 1).
- status >= 500 → retry up to `rate.max_retries_5xx` (default 1) with the
  same exponential backoff curve. Asymmetry is intentional: 429 means
  "back off, server is rate-limiting" (retry generously); 5xx on a single
  resource path is overwhelmingly a permanent server-side breakage
  (retry once for a true transient hiccup, then move on).
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
            status = resp.status_code
            if status == 429:
                budget = self._rate.max_retries
            elif status >= 500:
                budget = self._rate.max_retries_5xx
            else:
                budget = 0  # no retry for 2xx/3xx/4xx (excluding 429)
            if budget == 0 or attempts > budget:
                return FetchResult(
                    status_code=status,
                    headers=dict(resp.headers),
                    body=resp.text,
                    attempts=attempts,
                )
            await self._sleep(self._rate.backoff_base_s**attempts)
