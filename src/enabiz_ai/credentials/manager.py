import base64
import json
import os
from pathlib import Path
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from pydantic import SecretStr

from enabiz_ai.credentials.models import Credentials


class CredentialManagerError(Exception):
    """Base exception for credential manager errors."""
    pass


class InvalidPassphraseError(CredentialManagerError):
    """Raised when an incorrect master passphrase is provided."""
    pass


class CredentialManager:
    """Manages encrypted storage and retrieval of e-Nabiz credentials."""

    def __init__(self, data_dir: Path):
        """
        Initialize the CredentialManager.

        Args:
            data_dir (Path): Directory where credentials will be stored.
        """
        self.data_dir = data_dir
        self.file_path = self.data_dir / "credentials.enc.json"
        
        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _derive_key(self, passphrase: str, salt: bytes) -> bytes:
        """Derive a Fernet key from a passphrase and salt using PBKDF2."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        return base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))

    def save(self, tc_no: str, password: str, master_passphrase: str) -> None:
        """
        Encrypt and save the credentials.

        Args:
            tc_no (str): 11-digit Turkish Identity Number.
            password (str): e-Nabiz password.
            master_passphrase (str): Passphrase used to encrypt the credentials.
        """
        # Validate using the model
        creds = Credentials(tc_no=tc_no, password=SecretStr(password))
        
        salt = os.urandom(16)
        key = self._derive_key(master_passphrase, salt)
        fernet = Fernet(key)
        
        raw_data = json.dumps({
            "tc_no": creds.tc_no,
            "password": creds.password.get_secret_value()
        }).encode("utf-8")
        
        encrypted_data = fernet.encrypt(raw_data)
        
        storage_data = {
            "salt": base64.b64encode(salt).decode("utf-8"),
            "encrypted_data": base64.b64encode(encrypted_data).decode("utf-8")
        }
        
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(storage_data, f)

    def load(self, master_passphrase: str) -> Credentials:
        """
        Load and decrypt the credentials.

        Args:
            master_passphrase (str): Passphrase used to decrypt the credentials.

        Returns:
            Credentials: The decrypted credentials object.

        Raises:
            FileNotFoundError: If the credential file doesn't exist.
            InvalidPassphraseError: If the passphrase is wrong.
            CredentialManagerError: If the file is corrupted.
        """
        if not self.exists():
            raise FileNotFoundError(f"Credential file not found at {self.file_path}")

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                storage_data = json.load(f)
                
            salt = base64.b64decode(storage_data["salt"])
            encrypted_data = base64.b64decode(storage_data["encrypted_data"])
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise CredentialManagerError(f"Credential file is corrupted: {e}")

        key = self._derive_key(master_passphrase, salt)
        fernet = Fernet(key)

        try:
            decrypted_data = fernet.decrypt(encrypted_data)
        except (InvalidToken, InvalidSignature):
            raise InvalidPassphraseError("Incorrect master passphrase.")
            
        try:
            raw_data = json.loads(decrypted_data.decode("utf-8"))
            return Credentials(**raw_data)
        except json.JSONDecodeError as e:
            raise CredentialManagerError(f"Decrypted data is corrupted: {e}")

    def exists(self) -> bool:
        """Check if the credential file exists."""
        return self.file_path.exists() and self.file_path.is_file()

    def delete(self) -> None:
        """Securely delete the credential file."""
        if self.exists():
            try:
                # Overwrite with random data before deleting for security
                file_size = self.file_path.stat().st_size
                with open(self.file_path, "wb") as f:
                    f.write(os.urandom(file_size))
                
                self.file_path.unlink()
            except OSError as e:
                raise CredentialManagerError(f"Failed to delete credential file: {e}")
