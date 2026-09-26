"""Tests for SessionManager encryption at rest and session expiry."""

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock
import pytest

from enabiz_ai.browser.session_manager import SessionManager, SESSION_MAX_AGE_SECONDS


@pytest.mark.unit
class TestSessionManager:
    """Test session persistence, encryption, and freshness checking."""

    async def test_save_and_load_unencrypted_storage_state(self, temp_data_dir: Path):
        sm = SessionManager(temp_data_dir)
        mock_context = AsyncMock()
        mock_context.storage_state.return_value = {
            "cookies": [{"name": "auth_token", "value": "xyz123"}],
            "origins": [],
        }

        await sm.save_storage_state(mock_context)
        assert sm.storage_state_path.exists()
        assert sm.is_session_valid()

        loaded = sm.load_storage_state()
        assert loaded is not None
        assert loaded["cookies"][0]["value"] == "xyz123"

    async def test_save_and_load_encrypted_storage_state(self, temp_data_dir: Path):
        sm = SessionManager(temp_data_dir)
        mock_context = AsyncMock()
        mock_context.storage_state.return_value = {
            "cookies": [{"name": "e_devlet_session", "value": "secret_cookie_token_999"}],
            "origins": [],
        }

        passphrase = "mock" + "_passphrase"
        await sm.save_storage_state(mock_context, passphrase=passphrase)

        assert sm.encrypted_storage_path.exists()
        # Ensure plaintext storage state file was removed
        assert not sm.storage_state_path.exists()

        # Plaintext cookie value must NOT exist on disk
        raw_enc = sm.encrypted_storage_path.read_text(encoding="utf-8")
        assert "secret_cookie_token_999" not in raw_enc

        # Decrypt with correct passphrase
        state = sm.load_storage_state(passphrase=passphrase)
        assert state is not None
        assert state["cookies"][0]["value"] == "secret_cookie_token_999"

        # Decrypt with wrong passphrase returns None
        wrong_state = sm.load_storage_state(passphrase="WrongKey")
        assert wrong_state is None

    def test_session_expiry(self, temp_data_dir: Path):
        sm = SessionManager(temp_data_dir)

        # Write metadata older than max age
        meta = {
            "saved_at": time.time() - (SESSION_MAX_AGE_SECONDS + 100),
            "saved_at_iso": "2024-01-01T00:00:00",
        }
        with open(sm.session_meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)

        # Session should be reported as expired
        assert not sm.is_session_valid()
