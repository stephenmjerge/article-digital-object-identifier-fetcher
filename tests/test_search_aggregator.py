import asyncio
from dataclasses import dataclass
from typing import List

import pytest

from adoif.services.search import SearchAggregator, SearchResult, SearchResolver


@dataclass
class DummyResolver:
    name: str
    results: List[SearchResult]

    async def search(self, query: str, *, limit: int) -> List[SearchResult]:
        return self.results[:limit]


@pytest.mark.asyncio
async def test_search_aggregator_deduplicates() -> None:
    res1 = SearchResult(
        identifier="10.1/foo",
        title="Sample",
        authors=[],
        journal=None,
        year=None,
        url=None,
        source="one",
    )
    res2 = SearchResult(
        identifier="10.1/foo",
        title="Sample",
        authors=[],
        journal=None,
        year=None,
        url=None,
        source="two",
    )
    aggregator = SearchAggregator([DummyResolver("one", [res1]), DummyResolver("two", [res2])])
    results = await aggregator.search("query", sources={"all"}, limit=10)
    assert len(results) == 1
    assert results[0].source == "one"
