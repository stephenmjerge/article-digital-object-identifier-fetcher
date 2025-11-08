"""Resolver interfaces responsible for turning identifiers into metadata."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

import httpx
import structlog

from adoif.models import FetchRequest, FetchResult
from adoif.settings import Settings

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
        # Placeholder implementation – real HTTP call will live here.
        return None


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
