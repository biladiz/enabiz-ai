"""Custom exception hierarchy for enabiz-ai."""

from __future__ import annotations


class EnabizError(Exception):
    """Base exception for all enabiz-ai errors."""


class AuthenticationError(EnabizError):
    """Authentication or login failure."""


class SessionExpiredError(AuthenticationError):
    """Browser session cookies/tokens have expired."""


class TwoFARequiredError(AuthenticationError):
    """2FA challenge could not be completed."""


class HarvestError(EnabizError):
    """Error during web data harvesting or extraction."""


class DateParseError(HarvestError):
    """Failed to parse date string from e-Nabız portal."""


class StorageError(EnabizError):
    """Error in database or file persistence layer."""


class DatabaseNotInitializedError(StorageError):
    """Attempted to use database without active connection context."""


class AnalysisError(EnabizError):
    """Error during clinical RAG analysis or report generation."""


class ProfileError(EnabizError):
    """Error in profile management operations."""


class InvalidProfileIdError(ProfileError):
    """Profile ID contains invalid characters or path traversal elements."""
