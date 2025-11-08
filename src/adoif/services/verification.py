"""Services that verify DOIs against Crossref relations."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import quote

import httpx
import structlog

from adoif.settings import Settings

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class VerificationResult:
    doi: str
    status: str
    notes: list[str]


class CrossrefVerifier:
    """Checks Crossref relations for retractions or updates."""

    _RELATION_FLAGS = {
        "is-retracted-by": "retracted",
        "is-corrected-by": "corrected",
        "is-updated-by": "updated",
        "is-replaced-by": "replaced",
    }

    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    async def verify(self, doi: str) -> VerificationResult:
        try:
            message = await self._fetch_crossref_message(doi)
        except httpx.HTTPError as exc:
            logger.warning("verify.crossref_error", doi=doi, error=str(exc))
            return VerificationResult(doi=doi, status="error", notes=[str(exc)])

        relations = message.get("relation", {}) or {}
        notes: list[str] = []
        status = "clean"
        for relation_type, human in self._RELATION_FLAGS.items():
            hits = relations.get(relation_type)
            if not hits:
                continue
            status = human
            ids = [entry.get("id") for entry in hits if entry.get("id")]
            if ids:
                notes.append(f"{human} by {', '.join(ids)}")
            else:
                notes.append(f"{human}")
            if relation_type == "is-retracted-by":
                break

        return VerificationResult(doi=doi, status=status, notes=notes)

    async def verify_many(self, dois: Iterable[str]) -> list[VerificationResult]:
        tasks = [self.verify(doi) for doi in dois]
        return await asyncio.gather(*tasks)

    async def _fetch_crossref_message(self, doi: str) -> dict:
        url = f"{self._settings.crossref_base_url}/{quote(doi)}"
        response = await self._client.get(url, timeout=20)
        response.raise_for_status()
        payload = response.json()
        return payload.get("message", {})
