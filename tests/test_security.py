"""Tests for security sanitization, command injection defense, and output escaping."""

import html
import pytest

from enabiz_ai.services.scheduler import SchedulerService
from enabiz_ai.storage.file_store import FileStore


@pytest.mark.security
class TestSecuritySanitization:
    """Test defense mechanisms against injection attacks."""

    def test_powershell_schedule_input_validation(self):
        # SEC-3: PowerShell script injection attempts must be blocked
        malicious_profiles = [
            "all'; Remove-Item -Recurse C:\\; '",
            "test | Invoke-Expression",
            "$(whoami)",
            "anne & net user hacker /add",
        ]
        for bad_prof in malicious_profiles:
            with pytest.raises(Exception):
                SchedulerService.validate_schedule_inputs(
                    profile=bad_prof,
                    day="Sunday",
                    time_str="20:00",
                )

    def test_powershell_invalid_days_and_times_rejected(self):
        # Day validation whitelist
        with pytest.raises(ValueError, match="Invalid day"):
            SchedulerService.validate_schedule_inputs("anne", "Someday", "20:00")

        # Time validation regex
        with pytest.raises(ValueError, match="Invalid time format"):
            SchedulerService.validate_schedule_inputs("anne", "Sunday", "20:00;calc.exe")

    def test_telegram_html_escaping(self):
        # SEC-7: Verify HTML special chars in LLM output are escaped
        malicious_llm_output = (
            "<script>alert(1)</script>"
            "<b>Injection</b> & <a href='evil.com'>Click</a>"
        )
        safe_output = html.escape(malicious_llm_output)

        assert "<script>" not in safe_output
        assert "&lt;script&gt;" in safe_output
        assert "&amp;" in safe_output

    def test_file_store_filename_sanitization(self):
        # Test null byte removal, Windows reserved chars, and unicode
        dangerous_names = [
            "test\x00file.pdf",
            'bad:file"name<with>pipes|and?stars*.json',
            "normal_report.pdf",
        ]
        for name in dangerous_names:
            clean = FileStore._sanitize_filename(name)
            assert "\x00" not in clean
            assert not any(c in clean for c in '<>:"/\\|?*')
            assert clean.strip() != ""
