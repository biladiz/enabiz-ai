"""Pytest shared fixtures and configurations for enabiz-ai test suite."""

import asyncio
from datetime import datetime
from pathlib import Path
import pytest

from enabiz_ai.config import AppConfig
from enabiz_ai.extraction.models import LabReport, LabTest, Prescription
from enabiz_ai.storage.database import HealthDatabase


@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    """Provide a temporary clean data directory."""
    d = tmp_path / "enabiz_test_data"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def mock_config(temp_data_dir: Path) -> AppConfig:
    """Provide an AppConfig instance pointing to the temporary directory."""
    return AppConfig(
        enabiz_data_dir=str(temp_data_dir),
        telegram_bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        telegram_chat_id="123456789",
        ollama_base_url="http://localhost:11434",
        ollama_model="test-model",
    )


@pytest.fixture
async def temp_db(tmp_path: Path):
    """Provide an initialized SQLite database in a temporary directory."""
    db_path = tmp_path / "test_health.db"
    db = HealthDatabase(db_path)
    async with db:
        yield db


@pytest.fixture
def sample_lab_report() -> LabReport:
    """Provide a sample valid LabReport instance."""
    return LabReport(
        report_id="lab_20240315_a1b2c3d4e5f6",
        date=datetime(2024, 3, 15, 10, 30),
        hospital="Ankara Şehir Hastanesi",
        doctor="Dr. Ahmet Yılmaz",
        tests=[
            LabTest(
                test_name="Glukoz",
                value="95",
                unit="mg/dL",
                reference_range="74-106",
                is_abnormal=False,
                notes="Normal",
            ),
            LabTest(
                test_name="Hemoglobin",
                value="17.5",
                unit="g/dL",
                reference_range="13.2-16.6",
                is_abnormal=True,
                notes="Yüksek",
            ),
        ],
        raw_text="Laboratuvar sonuç örneği",
    )


@pytest.fixture
def sample_prescription() -> Prescription:
    """Provide a sample valid Prescription instance."""
    return Prescription(
        prescription_id="rx_20240315_p12345678901",
        date=datetime(2024, 3, 15, 11, 0),
        medication="Parol 500mg Tablet",
        dosage="500mg",
        frequency="3x1",
        quantity="1 Kutu",
        prescriber="Dr. Mehmet Öz",
        hospital="Hacettepe Üniversitesi Hastanesi",
    )
