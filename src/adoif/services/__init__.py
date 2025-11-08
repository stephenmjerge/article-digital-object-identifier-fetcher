"""Service abstractions for the ADOIF application."""

from .resolvers import CrossrefResolver, MetadataResolver, ResolverRegistry
from .storage import LibraryStorage, LocalLibrary

__all__ = [
    "CrossrefResolver",
    "MetadataResolver",
    "ResolverRegistry",
    "LibraryStorage",
    "LocalLibrary",
]
