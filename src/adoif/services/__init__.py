"""Service abstractions for the ADOIF application."""

from .pdf_fetcher import PDFFetcher, UnpaywallPDFFetcher
from .pipeline import IngestOutcome, IngestPipeline, IngestError, ManualOverrides
from .resolvers import CrossrefResolver, MetadataResolver, ResolverRegistry
from .storage import LibraryStorage, LocalLibrary

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
]
