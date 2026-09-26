"""Tests for ProfileManager and profile validation."""

from pathlib import Path
import pytest

from enabiz_ai.exceptions import InvalidProfileIdError
from enabiz_ai.profiles.manager import ProfileManager


@pytest.mark.unit
class TestProfileValidation:
    """Test security constraints and validation rules for profile IDs."""

    def test_valid_profile_ids(self):
        valid_ids = ["anne", "baba", "my-profile", "user_1", "default", "a", "1234"]
        for pid in valid_ids:
            assert ProfileManager.validate_profile_id(pid) == pid.lower().strip()

    def test_uppercase_trimmed_and_lowercased(self):
        assert ProfileManager.validate_profile_id("  ANNE  ") == "anne"
        assert ProfileManager.validate_profile_id("Baba_1") == "baba_1"

    def test_path_traversal_attacks_rejected(self):
        malicious_ids = [
            "../../etc",
            "../windows",
            r"..\..\System32",
            "dir/name",
            "dir\\name",
            "/absolute",
            "c:/windows",
        ]
        for bad_id in malicious_ids:
            with pytest.raises(InvalidProfileIdError):
                ProfileManager.validate_profile_id(bad_id)

    def test_invalid_characters_rejected(self):
        invalid_ids = [
            "",
            "   ",
            "user@email.com",
            "user;rm -rf",
            "admin' OR '1'='1",
            "a" * 33,  # Exceeds max length 32
            "user name",
            "test$var",
        ]
        for bad_id in invalid_ids:
            with pytest.raises(InvalidProfileIdError):
                ProfileManager.validate_profile_id(bad_id)


@pytest.mark.unit
class TestProfileManagerOperations:
    """Test profile CRUD operations and filesystem isolation."""

    def test_default_profile_created(self, temp_data_dir: Path):
        pm = ProfileManager(temp_data_dir)
        profiles = pm.list_profiles()
        assert len(profiles) >= 1
        default_prof = pm.get_profile("default")
        assert default_prof is not None
        assert default_prof.display_name == "Default User"

    def test_add_and_get_profile(self, temp_data_dir: Path):
        pm = ProfileManager(temp_data_dir)
        prof = pm.add_profile("anne", display_name="Annem", relation="Anne")
        assert prof.id == "anne"
        assert prof.display_name == "Annem"

        fetched = pm.get_profile("anne")
        assert fetched is not None
        assert fetched.relation == "Anne"

    def test_profile_directory_isolation(self, temp_data_dir: Path):
        pm = ProfileManager(temp_data_dir)
        anne_dir = pm.get_profile_dir("anne")
        baba_dir = pm.get_profile_dir("baba")

        assert anne_dir.exists()
        assert baba_dir.exists()
        assert anne_dir != baba_dir
        assert anne_dir.is_relative_to(pm.profiles_dir)

    def test_delete_profile(self, temp_data_dir: Path):
        pm = ProfileManager(temp_data_dir)
        pm.add_profile("kardes", display_name="Kardeşim", relation="Kardeş")
        assert pm.get_profile("kardes") is not None

        deleted = pm.delete_profile("kardes", delete_data=True)
        assert deleted is True
        assert pm.get_profile("kardes") is None
