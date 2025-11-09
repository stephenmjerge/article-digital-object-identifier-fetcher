"""External search resolvers for discovering candidate papers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable, Protocol
from urllib.parse import quote

import httpx
import structlog

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class SearchResult:
    identifier: str
    title: str
    authors: list[str]
    journal: str | None
    year: str | None
    url: str | None
    source: str


class SearchResolver(Protocol):
    name: str

    async def search(self, query: str, *, limit: int) -> list[SearchResult]:
        ...


class OpenAlexSearchResolver:
    name = "openalex"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def search(self, query: str, *, limit: int) -> list[SearchResult]:
        url = "https://api.openalex.org/works"
        params = {"search": query, "per-page": min(limit, 200)}
        try:
            response = await self._client.get(url, params=params, timeout=20)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("search.openalex_error", error=str(exc))
            return []
        payload = response.json()
        results: list[SearchResult] = []
        for item in payload.get("results", [])[:limit]:
            authors = [
                auth.get("author", {}).get("display_name", "")
                for auth in item.get("authorships", [])
            ]
            results.append(
                SearchResult(
                    identifier=item.get("doi") or item.get("id"),
                    title=item.get("display_name", "Untitled"),
                    authors=[name for name in authors if name],
                    journal=(item.get("host_venue") or {}).get("display_name"),
                    year=str(item.get("publication_year")) if item.get("publication_year") else None,
                    url=item.get("primary_location", {}).get("source", {}).get("url"),
                    source=self.name,
                )
            )
        return results


class PubMedSearchResolver:
    name = "pubmed"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def search(self, query: str, *, limit: int) -> list[SearchResult]:
        term = quote(query)
        esearch = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {"db": "pubmed", "term": term, "retmode": "json", "retmax": limit}
        try:
            search_resp = await self._client.get(esearch, params=params, timeout=20)
            search_resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("search.pubmed_error", stage="esearch", error=str(exc))
            return []
        ids = (search_resp.json().get("esearchresult", {}).get("idlist") or [])[:limit]
        if not ids:
            return []
        summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        summary_params = {"db": "pubmed", "id": ",".join(ids), "retmode": "json"}
        try:
            summary_resp = await self._client.get(summary_url, params=summary_params, timeout=20)
            summary_resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("search.pubmed_error", stage="esummary", error=str(exc))
            return []
        summaries = summary_resp.json().get("result", {})
        results: list[SearchResult] = []
        for pmid in ids:
            entry = summaries.get(pmid)
            if not entry:
                continue
            results.append(
                SearchResult(
                    identifier=entry.get("elocationid") or pmid,
                    title=entry.get("title", "Untitled"),
                    authors=[author.get("name", "") for author in entry.get("authors", []) if author.get("name")],
                    journal=entry.get("fulljournalname"),
                    year=str(entry.get("pubdate", "").split(" ")[0]) or None,
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    source=self.name,
                )
            )
        return results


class SearchAggregator:
    def __init__(self, resolvers: Iterable[SearchResolver]) -> None:
        self._resolvers = list(resolvers)

    async def search(self, query: str, *, sources: set[str], limit: int) -> list[SearchResult]:
        tasks = []
        for resolver in self._resolvers:
            if "all" not in sources and resolver.name not in sources:
                continue
            tasks.append(resolver.search(query, limit=limit))
        if not tasks:
            return []
        results_lists = await asyncio.gather(*tasks)
        combined: list[SearchResult] = []
        seen: set[str] = set()
        for chunk in results_lists:
            for result in chunk:
                key = (result.identifier or result.title).lower()
                if key in seen:
                    continue
                seen.add(key)
                combined.append(result)
        return combined[:limit]
