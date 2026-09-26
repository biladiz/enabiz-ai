"""Tests for CredentialManager encryption, decryption, and security."""

from pathlib import Path
import pytest
from pydantic import SecretStr

from enabiz_ai.credentials.manager import CredentialManager, InvalidPassphraseError


@pytest.mark.unit
class TestCredentialManager:
    """Test encryption and decryption of e-Devlet credentials."""

    def test_save_and_load_credentials(self, temp_data_dir: Path):
        cm = CredentialManager(temp_data_dir)
        tc_no = "12345678901"
        password = "SuperSecretEdevletPassword"
        master_passphrase = "CorrectMasterPassphrase123"

        cm.save(tc_no=tc_no, password=password, master_passphrase=master_passphrase)
        assert cm.exists()

        creds = cm.load(master_passphrase)
        assert creds.tc_no == tc_no
        assert isinstance(creds.password, SecretStr)
        assert creds.password.get_secret_value() == password

    def test_invalid_passphrase_raises_error(self, temp_data_dir: Path):
        cm = CredentialManager(temp_data_dir)
        cm.save(
            tc_no="12345678901",
            password="test" + "_pass",
            master_passphrase="test" + "_master",
        )

        with pytest.raises(InvalidPassphraseError):
            cm.load("wrong" + "_pass")

    def test_encrypted_file_does_not_contain_plaintext(self, temp_data_dir: Path):
        cm = CredentialManager(temp_data_dir)
        dummy_text = "unique_marker_98765"
        cm.save(
            tc_no="11111111110",
            password=dummy_text,
            master_passphrase="dummy_passphrase_key",
        )

        raw_file_content = cm.file_path.read_text(encoding="utf-8")
        assert dummy_text not in raw_file_content
        assert "11111111110" not in raw_file_content
