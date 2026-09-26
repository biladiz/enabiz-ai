"""Tests for HealthDatabase and HealthRepository protocol implementation."""

from datetime import datetime
from pathlib import Path
import pytest

from enabiz_ai.extraction.models import LabReport, LabTest, Prescription
from enabiz_ai.storage.database import HealthDatabase
from enabiz_ai.storage.repository import HealthRepository


@pytest.mark.unit
class TestHealthDatabase:
    """Test SQLite health database operations, deduplication, and constraints."""

    async def test_repository_protocol_conformance(self, temp_db: HealthDatabase):
        assert isinstance(temp_db, HealthRepository)

    async def test_access_without_context_raises_runtime_error(self, tmp_path: Path):
        uninit_db = HealthDatabase(tmp_path / "uninit.db")
        with pytest.raises(RuntimeError):
            await uninit_db.get_stats()

    async def test_lab_report_deduplication(
        self,
        temp_db: HealthDatabase,
        sample_lab_report: LabReport,
    ):
        # First save succeeds
        saved_first = await temp_db.save_lab_report(sample_lab_report)
        assert saved_first is True

        # Second save is detected as duplicate and returns False
        saved_second = await temp_db.save_lab_report(sample_lab_report)
        assert saved_second is False

        reports = await temp_db.get_lab_reports()
        assert len(reports) == 1
        assert len(reports[0].tests) == 2

    async def test_prescription_deduplication(
        self,
        temp_db: HealthDatabase,
        sample_prescription: Prescription,
    ):
        saved_first = await temp_db.save_prescription(sample_prescription)
        assert saved_first is True

        saved_second = await temp_db.save_prescription(sample_prescription)
        assert saved_second is False

        prescriptions = await temp_db.get_prescriptions()
        assert len(prescriptions) == 1

    async def test_visit_deduplication_with_tracking_no(self, temp_db: HealthDatabase):
        # Dedup with tracking_no
        s1 = await temp_db.save_visit(
            date="2024-03-10",
            hospital="Ankara Numune",
            tracking_no="TRK12345",
        )
        assert s1 is True

        s2 = await temp_db.save_visit(
            date="2024-03-10",
            hospital="Ankara Numune",
            tracking_no="TRK12345",
        )
        assert s2 is False

    async def test_visit_deduplication_composite_fallback(self, temp_db: HealthDatabase):
        # BUG-2: When tracking_no is None, composite key (date, hospital, raw_details[:100]) dedupes
        s1 = await temp_db.save_visit(
            date="2024-03-12",
            hospital="Gazi Hastanesi",
            doctor="Dr. Ali",
            tracking_no=None,
            raw_details="Kardiyoloji Polikliniği Muayenesi",
        )
        assert s1 is True

        s2 = await temp_db.save_visit(
            date="2024-03-12",
            hospital="Gazi Hastanesi",
            doctor="Dr. Ali",
            tracking_no=None,
            raw_details="Kardiyoloji Polikliniği Muayenesi",
        )
        assert s2 is False

        visits = await temp_db.get_visits()
        assert len(visits) == 1

    async def test_get_stats_and_table_whitelist(
        self,
        temp_db: HealthDatabase,
        sample_lab_report: LabReport,
    ):
        await temp_db.save_lab_report(sample_lab_report)
        stats = await temp_db.get_stats()
        assert stats["lab_reports"] == 1
        assert stats["lab_tests"] == 2
        assert stats["prescriptions"] == 0

    async def test_export_csv_and_invalid_table_rejected(
        self,
        temp_db: HealthDatabase,
        sample_lab_report: LabReport,
        tmp_path: Path,
    ):
        await temp_db.save_lab_report(sample_lab_report)
        csv_file = tmp_path / "labs.csv"

        count = await temp_db.export_csv("lab_reports", csv_file)
        assert count == 1
        assert csv_file.exists()

        # SEC-4: Invalid table names are rejected
        with pytest.raises(ValueError):
            await temp_db.export_csv("users; DROP TABLE lab_reports; --", csv_file)
