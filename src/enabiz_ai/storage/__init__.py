"""Data storage module for health records."""

from .database import HealthDatabase
from .file_store import FileStore

__all__ = ["HealthDatabase", "FileStore"]
