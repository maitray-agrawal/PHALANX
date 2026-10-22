"""Concurrency and race-condition test suite."""

import asyncio

import pytest


@pytest.mark.asyncio
async def test_concurrent_stub() -> None:
    """Verify concurrency test framework runner."""

    async def worker(worker_id: int) -> int:
        await asyncio.sleep(0.001)
        return worker_id

    results = await asyncio.gather(*(worker(i) for i in range(10)))
    assert len(results) == 10
    assert results == list(range(10))
