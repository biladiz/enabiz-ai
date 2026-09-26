"""Organized file storage for downloaded health documents.

Maintains a structured directory layout for PDFs, reports, and screenshots
downloaded from e-Nabız.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Directory categories ──────────────────────────────────────────
CATEGORIES = {
    "lab_results": "Laboratuvar Sonuçları",
    "prescriptions": "Reçeteler",
    "radiology": "Radyoloji Raporları",
    "vaccinations": "Aşı Kayıtları",
    "screenshots": "Ekran Görüntüleri",
    "raw_downloads": "Ham İndirmeler",
}


class FileStore:
    """Organized file storage for health documents.

    Directory structure:
        base_dir/
        ├── lab_results/
        │   ├── 2024-09-15_hemogram.pdf
        │   └── 2024-09-15_hemogram.json
        ├── prescriptions/
        ├── radiology/
        ├── vaccinations/
        ├── screenshots/
        └── raw_downloads/

    Usage:
        store = FileStore(Path("~/.enabiz-ai/data"))
        path = store.save_download(pdf_bytes, "lab_results", "hemogram.pdf")
    """

    def __init__(self, base_dir: Path) -> None:
        """Initialize the file store and create directory structure.

        Args:
            base_dir: Root directory for all stored files.
        """
        self.base_dir = base_dir
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create all category directories."""
        for category in CATEGORIES:
            category_dir = self.base_dir / category
            category_dir.mkdir(parents=True, exist_ok=True)

    def save_download(
        self,
        content: bytes,
        category: str,
        filename: str,
        date: Optional[datetime] = None,
    ) -> Path:
        """Save a downloaded file to the appropriate category directory.

        The file is prefixed with the date (YYYY-MM-DD_originalname.ext).

        Args:
            content: File content as bytes.
            category: Category name (e.g., 'lab_results', 'prescriptions').
            filename: Original filename.
            date: Date to prefix (defaults to today).

        Returns:
            Path to the saved file.

        Raises:
            ValueError: If category is invalid.
        """
        if category not in CATEGORIES:
            raise ValueError(f"Invalid category: {category}. Valid: {list(CATEGORIES.keys())}")

        date = date or datetime.now()
        date_prefix = date.strftime("%Y-%m-%d")
        safe_filename = self._sanitize_filename(filename)
        full_filename = f"{date_prefix}_{safe_filename}"

        save_path = self.base_dir / category / full_filename

        # Avoid overwriting — add counter suffix if needed
        if save_path.exists():
            stem = save_path.stem
            suffix = save_path.suffix
            counter = 1
            while save_path.exists():
                save_path = save_path.parent / f"{stem}_{counter}{suffix}"
                counter += 1

        save_path.write_bytes(content)
        logger.info("Saved %s to %s/%s", filename, category, full_filename)
        return save_path

    def save_file(
        self,
        source_path: Path,
        category: str,
        date: Optional[datetime] = None,
    ) -> Path:
        """Copy an existing file to the store.

        Args:
            source_path: Path to the source file.
            category: Target category.
            date: Date prefix (defaults to today).

        Returns:
            Path to the stored copy.
        """
        content = source_path.read_bytes()
        return self.save_download(content, category, source_path.name, date)

    def get_files(
        self,
        category: str,
        extension: Optional[str] = None,
    ) -> list[Path]:
        """List all files in a category, sorted by name (newest first).

        Args:
            category: Category to list.
            extension: Optional file extension filter (e.g., '.pdf').

        Returns:
            List of file paths, sorted newest-first.
        """
        if category not in CATEGORIES:
            raise ValueError(f"Invalid category: {category}")

        category_dir = self.base_dir / category
        files = list(category_dir.iterdir())

        if extension:
            files = [f for f in files if f.suffix.lower() == extension.lower()]

        # Sort by name descending (date-prefixed files sort chronologically)
        files.sort(key=lambda p: p.name, reverse=True)
        return files

    def get_latest(
        self,
        category: str,
        extension: Optional[str] = None,
    ) -> Optional[Path]:
        """Get the most recent file in a category.

        Args:
            category: Category to search.
            extension: Optional extension filter.

        Returns:
            Path to the latest file, or None if empty.
        """
        files = self.get_files(category, extension)
        return files[0] if files else None

    def get_category_size(self, category: str) -> int:
        """Get total size of files in a category (in bytes).

        Args:
            category: Category to measure.

        Returns:
            Total size in bytes.
        """
        files = self.get_files(category)
        return sum(f.stat().st_size for f in files if f.is_file())

    def get_stats(self) -> dict[str, dict]:
        """Get statistics for all categories.

        Returns:
            Dict mapping category to {count, total_size_mb}.
        """
        stats = {}
        for category in CATEGORIES:
            files = self.get_files(category)
            total_bytes = sum(f.stat().st_size for f in files if f.is_file())
            stats[category] = {
                "count": len(files),
                "total_size_mb": round(total_bytes / (1024 * 1024), 2),
            }
        return stats

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """Remove or replace characters that are unsafe for filenames.

        Handles null bytes, control characters, Windows reserved characters, and unicode.

        Args:
            filename: Original filename.

        Returns:
            Sanitized filename.
        """
        import unicodedata

        # Remove null bytes and control chars
        cleaned = "".join(ch for ch in filename if ch != "\x00" and ord(ch) >= 32)
        cleaned = unicodedata.normalize("NFKC", cleaned)

        # Replace Windows/POSIX reserved characters
        unsafe = '<>:"/\\|?*'
        for char in unsafe:
            cleaned = cleaned.replace(char, "_")

        sanitized = cleaned.strip(". ")
        return sanitized or "unnamed_file"
