"""Service abstractions for the ADOIF application."""

from .pdf_fetcher import PDFFetcher, UnpaywallPDFFetcher
from .pipeline import IngestError, IngestOutcome, IngestPipeline, ManualOverrides
from .resolvers import CrossrefResolver, MetadataResolver, ResolverRegistry
from .search import (
    OpenAlexSearchResolver,
    PubMedSearchResolver,
    SearchAggregator,
    SearchResolver,
    SearchResult,
)
from .storage import LibraryStorage, LocalLibrary
from .verification import CrossrefVerifier, VerificationResult

__all__ = [
    "CrossrefResolver",
    "MetadataResolver",
    "ResolverRegistry",
    "LibraryStorage",
    "LocalLibrary",
    "PDFFetcher",
    "UnpaywallPDFFetcher",
    "IngestPipeline",
    "IngestOutcome",
    "ManualOverrides",
    "IngestError",
    "CrossrefVerifier",
    "VerificationResult",
    "SearchAggregator",
    "SearchResolver",
    "SearchResult",
    "OpenAlexSearchResolver",
    "PubMedSearchResolver",
]
