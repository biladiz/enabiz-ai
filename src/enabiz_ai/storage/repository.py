"""Repository protocol/interface for health record storage.

Decouples data access and persistence from specific storage engines (SQLite, PostgreSQL, etc.).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

from enabiz_ai.extraction.models import LabReport, Prescription


@runtime_checkable
class HealthRepository(Protocol):
    """Protocol defining the storage and retrieval interface for health records."""

    async def initialize(self) -> None:
        """Initialize database schema and connections."""
        ...

    async def close(self) -> None:
        """Close database connection."""
        ...

    async def save_lab_report(self, report: LabReport) -> bool:
        """Save a lab report with its tests. Skips if already exists."""
        ...

    async def get_lab_reports(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> list[LabReport]:
        """Retrieve lab reports, optionally filtered by date range."""
        ...

    async def save_prescription(self, prescription: Prescription) -> bool:
        """Save a prescription. Skips if already exists."""
        ...

    async def get_prescriptions(
        self,
        since: Optional[datetime] = None,
    ) -> list[Prescription]:
        """Retrieve prescriptions, optionally filtered by date."""
        ...

    async def save_diagnosis(
        self,
        date: str,
        diagnosis: str,
        clinic: str | None = None,
        doctor: str | None = None,
    ) -> bool:
        """Save a diagnosis record. Skips duplicate entries."""
        ...

    async def get_diagnoses(self) -> list[dict]:
        """Retrieve all diagnoses ordered by date descending."""
        ...

    async def save_visit(
        self,
        date: str | None,
        hospital: str | None,
        clinic: str | None = None,
        doctor: str | None = None,
        tracking_no: str | None = None,
        raw_details: str | None = None,
    ) -> bool:
        """Save a doctor visit. Skips duplicate entries."""
        ...

    async def get_visits(self) -> list[dict]:
        """Retrieve all doctor visits ordered by date descending."""
        ...

    async def get_stats(self) -> dict[str, int]:
        """Get counts of records in all tables."""
        ...

    async def export_csv(self, table: str, output_path: Path) -> int:
        """Export table contents to CSV."""
        ...
