"""Tests for data extraction, Turkish date parsing, and abnormal detection."""

from datetime import datetime
import hashlib
from pathlib import Path
import pytest

from enabiz_ai.exceptions import DateParseError
from enabiz_ai.extraction.harvester import parse_turkish_date
from enabiz_ai.extraction.lab_parser import LabParser


@pytest.mark.unit
class TestTurkishDateParsing:
    """Test parse_turkish_date formats and error handling."""

    def test_standard_dot_format(self):
        dt = parse_turkish_date("14.03.2024")
        assert dt == datetime(2024, 3, 14)

    def test_standard_slash_format(self):
        dt = parse_turkish_date("25/12/2023")
        assert dt == datetime(2023, 12, 25)

    def test_textual_month_name(self):
        dt = parse_turkish_date("8 Nisan 2022")
        assert dt == datetime(2022, 4, 8)

        dt2 = parse_turkish_date("15 Ocak 2021")
        assert dt2 == datetime(2021, 1, 15)

    def test_invalid_date_raises_date_parse_error(self):
        # BUG-1: Must raise DateParseError instead of silently returning datetime.now()
        invalid_inputs = ["", "   ", "not_a_date", "32.13.2024", "99 Bilinmeyen 2025"]
        for bad_input in invalid_inputs:
            with pytest.raises(DateParseError):
                parse_turkish_date(bad_input)

    def test_explicit_default_fallback(self):
        default_dt = datetime(2020, 1, 1)
        res = parse_turkish_date("invalid_date_string", default=default_dt)
        assert res == default_dt


@pytest.mark.unit
class TestLabParserAbnormalDetection:
    """Test reference range parsing and abnormal flag evaluation."""

    def test_check_abnormal_standard_range(self):
        # Within range
        assert LabParser._check_abnormal("14.0", "12.0-16.0") is False
        # Below range
        assert LabParser._check_abnormal("10.5", "12.0-16.0") is True
        # Above range
        assert LabParser._check_abnormal("18.2", "12.0-16.0") is True

    def test_check_abnormal_less_than_format(self):
        assert LabParser._check_abnormal("0.5", "< 1.0") is False
        assert LabParser._check_abnormal("2.5", "< 1.0") is True

    def test_check_abnormal_greater_than_format(self):
        assert LabParser._check_abnormal("50", "> 30") is False
        assert LabParser._check_abnormal("15", "> 30") is True

    def test_check_abnormal_non_numeric(self):
        assert LabParser._check_abnormal("Negatif", "Negatif") is None


@pytest.mark.unit
class TestHashIDGeneration:
    """Test deterministic SHA-256 ID generation for lab reports."""

    def test_sha256_hash_id_generation(self):
        # SEC-9: Verify sha256 output is 12 chars hex
        hospital = "Hacettepe Üniversitesi Hastanesi"
        h_hash = hashlib.sha256(hospital.encode("utf-8")).hexdigest()[:12]
        report_date = datetime(2024, 3, 15)
        report_id = f"lab_{report_date:%Y%m%d}_{h_hash}"

        assert report_id.startswith("lab_20240315_")
        assert len(h_hash) == 12
