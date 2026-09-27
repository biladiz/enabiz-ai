"""Tests for SyncService, SchedulerService, and clinical RAGEngine."""

from datetime import datetime
from unittest.mock import AsyncMock, patch
import pytest

from enabiz_ai.analysis.rag_engine import RAGEngine
from enabiz_ai.config import AppConfig
from enabiz_ai.extraction.models import LabReport, LabTest
from enabiz_ai.profiles.models import ProfileInfo
from enabiz_ai.services.pipeline import SyncService
from enabiz_ai.services.scheduler import SchedulerService
from enabiz_ai.storage.database import HealthDatabase


@pytest.mark.unit
class TestServices:
    """Test service layer workflows and coordination."""

    async def test_sync_service_batch_stats(self, mock_config: AppConfig, tmp_path):
        sync_svc = SyncService(mock_config)
        profiles = [
            ProfileInfo(id="p1", display_name="Person 1", relation="Kendim", created_at=datetime.now()),
            ProfileInfo(id="p2", display_name="Person 2", relation="Anne", created_at=datetime.now()),
        ]

        # Populate p1 database
        db1_path = sync_svc.pm.get_db_path("p1")
        async with HealthDatabase(db1_path) as db:
            await db.save_lab_report(LabReport(
                report_id="r1",
                date=datetime(2024, 1, 1),
                tests=[LabTest(test_name="WBC", value="7.0")],
            ))

        stats_map = await sync_svc.get_all_profiles_stats(profiles)
        assert "p1" in stats_map
        assert stats_map["p1"].get("lab_reports") == 1
        assert "p2" in stats_map
        assert stats_map["p2"].get("lab_reports", 0) == 0

    async def test_rag_engine_context_building(self, temp_db: HealthDatabase):
        await temp_db.save_lab_report(LabReport(
            report_id="lab_test_context",
            date=datetime(2024, 3, 1),
            hospital="Test Hospital",
            tests=[
                LabTest(
                    test_name="Kolesterol",
                    value="240",
                    unit="mg/dL",
                    reference_range="< 200",
                    is_abnormal=True,
                )
            ],
        ))

        rag = RAGEngine(db=temp_db)
        context = await rag.build_patient_context()
        assert "Kolesterol" in context
        assert "240" in context
        assert "ANORMAL / REFERANS DIŞI" in context

    @patch("httpx.AsyncClient.post")
    async def test_rag_engine_generate_report_mocked(self, mock_post, temp_db: HealthDatabase):
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "Tahlil Değerlendirmesi: Her şey kontrol altında."}
        }
        mock_post.return_value = mock_response

        rag = RAGEngine(db=temp_db)
        report = await rag.generate_weekly_report(person_name="Ahmet")
        assert "Tahlil Değerlendirmesi" in report

    @patch("httpx.AsyncClient.post")
    async def test_rag_engine_deepseek_r1_think_stripping(self, mock_post, temp_db: HealthDatabase):
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "content": "<think>\nPatient has elevated liver transaminases. Ruling out acute hepatitis.\n</think>\nKlinik Sonuç: Karaciğer enzimlerinde hafif yükselme gözlenmiştir."
            }
        }
        mock_post.return_value = mock_response

        rag = RAGEngine(db=temp_db, model="deepseek-r1:70b")
        report = await rag.generate_weekly_report(person_name="Ahmet")
        assert "<think>" not in report
        assert "</think>" not in report
        assert "Ruling out acute hepatitis" not in report
        assert "Klinik Sonuç: Karaciğer enzimlerinde hafif yükselme" in report

    @patch("httpx.AsyncClient.post")
    async def test_rag_engine_medgemma_model_support(self, mock_post, temp_db: HealthDatabase):
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "content": "🏥 MedGemma Klinik Değerlendirme:\n• Hemoglobin ve Ferritin değerleri normal sınırlardadır."
            }
        }
        mock_post.return_value = mock_response

        rag = RAGEngine(db=temp_db, model="medgemma:27b")
        report = await rag.generate_weekly_report(person_name="Fatma")
        assert "MedGemma Klinik Değerlendirme" in report
        assert "Hemoglobin ve Ferritin" in report
