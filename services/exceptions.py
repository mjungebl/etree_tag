from __future__ import annotations


class TaggerError(Exception):
    """Base error for tagging operations."""


class MetadataImportError(TaggerError):
    """Raised when track metadata cannot be imported or derived."""


class ArtworkError(TaggerError):
    """Raised when artwork cannot be applied or staged."""


class PersistenceError(TaggerError):
    """Raised when persistence/repository operations fail."""


class ConfigurationError(TaggerError):
    """Raised when application configuration cannot be loaded."""


class FolderProcessingError(TaggerError):
    """Raised when processing a concert folder fails."""
