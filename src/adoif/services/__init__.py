"""Service abstractions for the ADOIF application."""

from .batch import BatchCandidate, BatchScanner, summarize_candidates
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
from .screening import PrismaSummary, ScreeningService
from .extraction import ExtractionService
from .storage import LibraryStorage, LocalLibrary
from .verification import CrossrefVerifier, VerificationResult
from .notes import NoteService, Note

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
    "ScreeningService",
    "PrismaSummary",
    "ExtractionService",
    "BatchScanner",
    "BatchCandidate",
    "summarize_candidates",
    "NoteService",
    "Note",
]
