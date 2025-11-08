"""Resolver interfaces responsible for turning identifiers into metadata."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol
from urllib.parse import quote

import httpx
import structlog

from adoif.models import ArticleMetadata, Author, FetchRequest, FetchResult
from adoif.settings import Settings
from adoif.utils import extract_doi

logger = structlog.get_logger(__name__)


class MetadataResolver(Protocol):
    """Protocol for metadata resolvers."""

    name: str

    async def resolve(self, request: FetchRequest) -> FetchResult | None:
        ...


class CrossrefResolver:
    """Fetches metadata from the Crossref Works API."""

    name = "crossref"

    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    async def resolve(self, request: FetchRequest) -> FetchResult | None:
        logger.info("resolver.attempt", resolver=self.name, identifier=request.identifier)
        doi = extract_doi(request.identifier)
        try:
            message = await self._fetch_payload(doi or request.identifier)
        except httpx.HTTPError as exc:
            logger.warning("resolver.error", resolver=self.name, error=str(exc))
            return None
        if not message:
            logger.info("resolver.empty", identifier=request.identifier)
            return None
        metadata = self._parse_metadata(message)
        return FetchResult(metadata=metadata, provider=self.name, raw_payload=message)

    async def _fetch_payload(self, identifier: str) -> dict:
        if extract_doi(identifier):
            url = f"{self._settings.crossref_base_url}/{quote(identifier)}"
            response = await self._client.get(url, timeout=30)
        else:
            params = {"query": identifier, "rows": 1}
            response = await self._client.get(self._settings.crossref_base_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        message = data.get("message", data)
        if isinstance(message, dict) and "items" in message:
            items = message.get("items") or []
            return items[0] if items else {}
        return message

    def _parse_metadata(self, payload: dict) -> ArticleMetadata:
        journal = None
        if payload.get("container-title"):
            journal = payload["container-title"][0]
        issued = payload.get("issued", {}).get("date-parts", [])
        published = _parse_date_parts(issued[0]) if issued else None
        authors = [
            Author(
                given_name=entry.get("given", ""),
                family_name=entry.get("family", ""),
                affiliation=", ".join(a.get("name", "") for a in entry.get("affiliation", []) or []),
            )
            for entry in payload.get("author", []) or []
        ]
        return ArticleMetadata(
            doi=payload.get("DOI", "").lower(),
            title=payload.get("title", ["Untitled"])[0],
            authors=authors,
            journal=journal,
            abstract=(payload.get("abstract") or "").strip() or None,
            publication_date=published,
            url=payload.get("URL"),
            tags=[],
            source_payload=payload,
        )


class ResolverRegistry:
    """Simple registry that tries available resolvers in order."""

    def __init__(self, resolvers: Iterable[MetadataResolver]) -> None:
        self._resolvers = list(resolvers)

    async def resolve(self, request: FetchRequest) -> FetchResult | None:
        for resolver in self._resolvers:
            logger.debug("registry.invoke", resolver=resolver.name)
            result = await resolver.resolve(request)
            if result is not None:
                logger.info("registry.hit", resolver=resolver.name)
                return result
        logger.warning("registry.miss", identifier=request.identifier)
        return None


def _parse_date_parts(parts: list[int]) -> datetime | None:
    if not parts:
        return None
    year = parts[0]
    month = parts[1] if len(parts) > 1 else 1
    day = parts[2] if len(parts) > 2 else 1
    try:
        return datetime(year, month, day)
    except ValueError:
        return None
