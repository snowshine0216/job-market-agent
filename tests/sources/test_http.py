
import httpx
import pytest
import respx

from jma.sources.base import RateConfig
from jma.sources.http import AsyncHttpClient


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def fake_sleep(sleeps: list[float]):
    async def _sleep(seconds: float) -> None:
        sleeps.append(seconds)
    return _sleep


@respx.mock
@pytest.mark.asyncio
async def test_fetch_200_first_try(fake_sleep, sleeps) -> None:
    respx.get("https://example.com/x").mock(return_value=httpx.Response(200, text="hi"))
    async with httpx.AsyncClient() as ac:
        client = AsyncHttpClient(ac, rate=RateConfig(), sleep=fake_sleep)
        result = await client.fetch("https://example.com/x")
    assert result.status_code == 200
    assert result.body == "hi"
    assert result.attempts == 1
    assert sleeps == []


@respx.mock
@pytest.mark.asyncio
async def test_fetch_403_returned_without_retry(fake_sleep, sleeps) -> None:
    respx.get("https://example.com/x").mock(return_value=httpx.Response(403, text="forbid"))
    async with httpx.AsyncClient() as ac:
        client = AsyncHttpClient(ac, rate=RateConfig(max_retries=3, backoff_base_s=2), sleep=fake_sleep)
        result = await client.fetch("https://example.com/x")
    assert result.status_code == 403
    assert result.attempts == 1
    assert sleeps == []


@respx.mock
@pytest.mark.asyncio
async def test_fetch_429_then_200_with_backoff(fake_sleep, sleeps) -> None:
    route = respx.get("https://example.com/x")
    route.side_effect = [
        httpx.Response(429, headers={"retry-after": "1"}, text=""),
        httpx.Response(200, text="ok"),
    ]
    async with httpx.AsyncClient() as ac:
        client = AsyncHttpClient(ac, rate=RateConfig(max_retries=3, backoff_base_s=2), sleep=fake_sleep)
        result = await client.fetch("https://example.com/x")
    assert result.status_code == 200
    assert result.attempts == 2
    # First retry waits backoff_base_s ** 1 = 2s.
    assert sleeps == [2]


@respx.mock
@pytest.mark.asyncio
async def test_fetch_5xx_exhausts_retries(fake_sleep, sleeps) -> None:
    route = respx.get("https://example.com/x")
    route.side_effect = [httpx.Response(503, text="")] * 4  # initial + 3 retries
    async with httpx.AsyncClient() as ac:
        client = AsyncHttpClient(ac, rate=RateConfig(max_retries=3, backoff_base_s=2), sleep=fake_sleep)
        result = await client.fetch("https://example.com/x")
    assert result.status_code == 503
    assert result.attempts == 4
    assert sleeps == [2, 4, 8]  # 2^1, 2^2, 2^3
