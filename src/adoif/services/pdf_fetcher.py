"""PDF fetching services that integrate with open-access providers."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import httpx
import structlog

from adoif.settings import Settings

logger = structlog.get_logger(__name__)


class PDFFetcher(Protocol):
    """Protocol for components that download PDFs."""

    async def fetch(self, doi: str, target: Path) -> Path | None:
        ...


class UnpaywallPDFFetcher:
    """Downloads PDFs discovered via the Unpaywall API."""

    name = "unpaywall"

    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings
        self._semaphore = asyncio.Semaphore(3)

    async def fetch(self, doi: str, target: Path) -> Path | None:
        if not self._settings.unpaywall_email:
            logger.debug("pdf.fetch.skipped", reason="missing_unpaywall_email")
            return None
        async with self._semaphore:
            try:
                location = await self._lookup_pdf_url(doi)
            except httpx.HTTPError as exc:
                logger.warning("pdf.lookup_failed", doi=doi, error=str(exc))
                return None
            if not location:
                logger.info("pdf.location_missing", doi=doi)
                return None
            try:
                return await self._download(location, target)
            except httpx.HTTPError as exc:
                logger.warning("pdf.download_failed", doi=doi, error=str(exc))
                return None

    async def _lookup_pdf_url(self, doi: str) -> str | None:
        url = f"{self._settings.unpaywall_base_url}/{quote(doi)}"
        params = {"email": self._settings.unpaywall_email}
        response = await self._client.get(url, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        best = payload.get("best_oa_location") or {}
        return best.get("url_for_pdf")

    async def _download(self, url: str, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        async with self._client.stream("GET", url, timeout=60) as stream:
            stream.raise_for_status()
            with target.open("wb") as fh:
                async for chunk in stream.aiter_bytes():
                    fh.write(chunk)
        logger.info("pdf.downloaded", target=str(target))
        return target
