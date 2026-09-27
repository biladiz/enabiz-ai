"""Tests for CredentialManager encryption, decryption, and security."""

from pathlib import Path
import pytest
from pydantic import SecretStr, ValidationError

from enabiz_ai.credentials.manager import CredentialManager, InvalidPassphraseError
from enabiz_ai.credentials.models import Credentials


@pytest.mark.unit
class TestCredentialManager:
    """Test encryption and decryption of credentials (e-Devlet and ENabız)."""

    def test_save_and_load_edevlet_only(self, temp_data_dir: Path):
        """e-Devlet credentials only (original behavior)."""
        cm = CredentialManager(temp_data_dir)
        tc_no = "12345678901"
        password = "SuperSecretEdevletPassword"
        master_passphrase = "CorrectMasterPassphrase123"

        cm.save(
            tc_no=tc_no,
            master_passphrase=master_passphrase,
            password=password,
        )
        assert cm.exists()

        creds = cm.load(master_passphrase)
        assert creds.tc_no == tc_no
        assert isinstance(creds.password, SecretStr)
        assert creds.password.get_secret_value() == password
        assert creds.enabiz_password is None
        assert creds.twofa_enabled is True

    def test_save_and_load_enabiz_only(self, temp_data_dir: Path):
        """ENabız-only credentials with 2FA disabled."""
        cm = CredentialManager(temp_data_dir)
        tc_no = "98765432101"
        enabiz_pass = "ENabizPasswordForMom"
        master_passphrase = "MasterKey456"

        cm.save(
            tc_no=tc_no,
            master_passphrase=master_passphrase,
            enabiz_password=enabiz_pass,
            twofa_enabled=False,
        )
        assert cm.exists()

        creds = cm.load(master_passphrase)
        assert creds.tc_no == tc_no
        assert creds.password is None
        assert isinstance(creds.enabiz_password, SecretStr)
        assert creds.enabiz_password.get_secret_value() == enabiz_pass
        assert creds.twofa_enabled is False

    def test_save_and_load_both_methods(self, temp_data_dir: Path):
        """Both e-Devlet and ENabız credentials stored together."""
        cm = CredentialManager(temp_data_dir)
        tc_no = "11122233344"
        edevlet_pass = "EDevletPass"
        enabiz_pass = "ENabizPass"
        master = "DualMaster789"

        cm.save(
            tc_no=tc_no,
            master_passphrase=master,
            password=edevlet_pass,
            enabiz_password=enabiz_pass,
            twofa_enabled=True,
        )

        creds = cm.load(master)
        assert creds.tc_no == tc_no
        assert creds.password.get_secret_value() == edevlet_pass
        assert creds.enabiz_password.get_secret_value() == enabiz_pass
        assert creds.twofa_enabled is True
        assert creds.has_edevlet is True
        assert creds.has_enabiz is True

    def test_twofa_enabled_false_roundtrip(self, temp_data_dir: Path):
        """twofa_enabled=False should survive encrypt/decrypt cycle."""
        cm = CredentialManager(temp_data_dir)
        cm.save(
            tc_no="55566677788",
            master_passphrase="pass123",
            enabiz_password="enabiz_pw",
            twofa_enabled=False,
        )
        creds = cm.load("pass123")
        assert creds.twofa_enabled is False

    def test_invalid_passphrase_raises_error(self, temp_data_dir: Path):
        cm = CredentialManager(temp_data_dir)
        cm.save(
            tc_no="12345678901",
            master_passphrase="test" + "_master",
            password="test" + "_pass",
        )

        with pytest.raises(InvalidPassphraseError):
            cm.load("wrong" + "_pass")

    def test_encrypted_file_does_not_contain_plaintext(self, temp_data_dir: Path):
        cm = CredentialManager(temp_data_dir)
        dummy_text = "unique_marker_98765"
        enabiz_marker = "enabiz_marker_12345"
        cm.save(
            tc_no="11111111110",
            master_passphrase="dummy_passphrase_key",
            password=dummy_text,
            enabiz_password=enabiz_marker,
        )

        raw_file_content = cm.file_path.read_text(encoding="utf-8")
        assert dummy_text not in raw_file_content
        assert "11111111110" not in raw_file_content
        assert enabiz_marker not in raw_file_content


@pytest.mark.unit
class TestCredentialModel:
    """Test Credentials Pydantic model validation."""

    def test_at_least_one_password_required(self):
        """Model should reject credentials with neither password."""
        with pytest.raises(ValidationError, match="At least one"):
            Credentials(tc_no="12345678901")

    def test_empty_passwords_rejected(self):
        """Empty-string passwords should be treated as not set."""
        with pytest.raises(ValidationError, match="At least one"):
            Credentials(
                tc_no="12345678901",
                password=SecretStr(""),
                enabiz_password=SecretStr(""),
            )

    def test_has_edevlet_property(self):
        creds = Credentials(tc_no="12345678901", password=SecretStr("pw"))
        assert creds.has_edevlet is True
        assert creds.has_enabiz is False

    def test_has_enabiz_property(self):
        creds = Credentials(tc_no="12345678901", enabiz_password=SecretStr("pw"))
        assert creds.has_edevlet is False
        assert creds.has_enabiz is True

    def test_has_both_properties(self):
        creds = Credentials(
            tc_no="12345678901",
            password=SecretStr("edevlet"),
            enabiz_password=SecretStr("enabiz"),
        )
        assert creds.has_edevlet is True
        assert creds.has_enabiz is True

    def test_backward_compat_old_format(self):
        """Old credential format (tc_no + password only) should deserialize fine."""
        old_data = {"tc_no": "12345678901", "password": "old_password"}
        creds = Credentials(**old_data)
        assert creds.has_edevlet is True
        assert creds.has_enabiz is False
        assert creds.twofa_enabled is True  # default

