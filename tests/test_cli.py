"""Tests for Typer CLI commands."""

from typer.testing import CliRunner
import pytest

from enabiz_ai import __version__
from enabiz_ai.cli import app

runner = CliRunner()


@pytest.mark.unit
class TestCliCommands:
    """Test CLI commands and argument handling."""

    def test_version_command(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert __version__ in result.stdout

    def test_help_command(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "e-Nabız AI" in result.stdout

    def test_profile_list_command(self):
        result = runner.invoke(app, ["profile", "list"])
        assert result.exit_code == 0
        assert "Kayıtlı Aile Profilleri" in result.stdout

    def test_schedule_add_invalid_profile(self):
        result = runner.invoke(app, ["schedule", "add", "--profile", "../../etc"])
        assert result.exit_code != 0

    def test_ask_help_command(self):
        result = runner.invoke(app, ["ask", "--help"])
        assert result.exit_code == 0
        assert "Soru-Cevap" in result.stdout

    def test_ask_nonexistent_profile(self):
        result = runner.invoke(app, ["ask", "Son kan testim neydi?", "--profile", "nonexistent_user"])
        assert result.exit_code != 0
        assert "Profil bulunamadı" in result.stdout
