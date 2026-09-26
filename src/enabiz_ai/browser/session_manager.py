"""Browser session management — cookie persistence, encryption, and session validation.

Saves and restores Playwright storage state (cookies + localStorage)
to avoid re-authentication when sessions are still valid.
Supports Fernet encryption at rest to protect sensitive e-Devlet session tokens.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

# e-Devlet sessions typically expire after ~15 minutes of inactivity
SESSION_MAX_AGE_SECONDS = 14 * 60  # 14 minutes (with safety margin)


class SessionManager:
    """Manages browser session persistence for e-Devlet/e-Nabız.

    Saves Playwright storage state (cookies, localStorage) to disk
    and validates freshness before reuse.
    """

    def __init__(
        self,
        data_dir: Path,
        chrome_cdp_url: str | None = None,
        chrome_path: str | None = None,
        headless: bool = False,
    ) -> None:
        """Initialize session manager.

        Args:
            data_dir: Base directory for session files.
            chrome_cdp_url: Chrome DevTools Protocol URL (e.g., http://127.0.0.1:9222).
            chrome_path: Path to Chrome executable (auto-detected if None).
            headless: Whether to run browser in headless mode.
        """
        self.data_dir = data_dir
        self.session_dir = data_dir / "session"
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.storage_state_path = self.session_dir / "storage_state.json"
        self.encrypted_storage_path = self.session_dir / "storage_state.enc"
        self.session_meta_path = self.session_dir / "session_meta.json"
        self.chrome_cdp_url = chrome_cdp_url
        self.chrome_path = chrome_path
        self.headless = headless

    @property
    def session_file(self) -> Path:
        """Alias for storage_state_path or encrypted_storage_path for backward compatibility."""
        if self.encrypted_storage_path.exists():
            return self.encrypted_storage_path
        return self.storage_state_path

    @staticmethod
    def _derive_key(passphrase: str, salt: bytes) -> bytes:
        """Derive a 32-byte Fernet key from passphrase using PBKDF2."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))

    async def save_storage_state(self, context: Any, passphrase: str | None = None) -> None:
        """Save the current browser context's storage state to disk.

        If a passphrase is provided, the session state is encrypted using Fernet
        derived from the passphrase.

        Args:
            context: A Playwright BrowserContext instance.
            passphrase: Optional master passphrase for encryption at rest.
        """
        try:
            storage = await context.storage_state()

            if passphrase:
                salt = os.urandom(16)
                key = self._derive_key(passphrase, salt)
                fernet = Fernet(key)
                raw_json = json.dumps(storage).encode("utf-8")
                ciphertext = fernet.encrypt(raw_json)

                enc_payload = {
                    "version": 1,
                    "salt": base64.b64encode(salt).decode("ascii"),
                    "ciphertext": ciphertext.decode("ascii"),
                }
                with open(self.encrypted_storage_path, "w", encoding="utf-8") as f:
                    json.dump(enc_payload, f, indent=2)

                # Remove legacy unencrypted file if present
                if self.storage_state_path.exists():
                    try:
                        self.storage_state_path.unlink()
                    except OSError:
                        pass
                logger.info("Encrypted session state saved to %s", self.encrypted_storage_path)
            else:
                with open(self.storage_state_path, "w", encoding="utf-8") as f:
                    json.dump(storage, f, indent=2)
                logger.info("Session state saved to %s (unencrypted)", self.storage_state_path)

            # Save metadata with timestamp
            meta = {
                "saved_at": time.time(),
                "saved_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "is_encrypted": bool(passphrase),
            }
            with open(self.session_meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)

        except Exception as e:
            logger.error("Failed to save session state: %s", e)

    def load_storage_state(self, passphrase: str | None = None) -> dict[str, Any] | None:
        """Load storage state as dictionary in memory, decrypting if necessary.

        Args:
            passphrase: Optional passphrase required if session is encrypted.

        Returns:
            Storage state dict if valid, None otherwise.
        """
        if not self.is_session_valid():
            logger.info("Saved session has expired or does not exist")
            return None

        # Try encrypted session first
        if self.encrypted_storage_path.exists():
            if not passphrase:
                logger.warning("Session is encrypted but no passphrase provided")
                return None
            try:
                with open(self.encrypted_storage_path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                salt = base64.b64decode(payload["salt"].encode("ascii"))
                ciphertext = payload["ciphertext"].encode("ascii")
                key = self._derive_key(passphrase, salt)
                fernet = Fernet(key)
                decrypted_bytes = fernet.decrypt(ciphertext)
                return json.loads(decrypted_bytes.decode("utf-8"))
            except (InvalidToken, KeyError, json.JSONDecodeError, OSError) as e:
                logger.error("Failed to decrypt session state: %s", e)
                return None

        # Fallback to unencrypted session
        if self.storage_state_path.exists():
            try:
                with open(self.storage_state_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.error("Failed to read unencrypted session: %s", e)
                return None

        return None

    def load_storage_state_path(self) -> str | None:
        """Get the path to saved storage state if it exists, is unencrypted, and valid.

        Returns:
            Path string to storage_state.json if valid, None otherwise.
        """
        if not self.storage_state_path.exists():
            return None

        if not self.is_session_valid():
            logger.info("Saved session has expired")
            return None

        return str(self.storage_state_path)

    def is_session_valid(self) -> bool:
        """Check if the saved session is still fresh (< 14 min old).

        Returns:
            True if session exists and hasn't expired.
        """
        if not self.session_meta_path.exists():
            return False

        try:
            with open(self.session_meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)

            saved_at = meta.get("saved_at", 0)
            age = time.time() - saved_at
            is_valid = age < SESSION_MAX_AGE_SECONDS

            if is_valid:
                logger.debug("Session age: %.0f seconds (valid)", age)
            else:
                logger.debug("Session age: %.0f seconds (expired)", age)

            return is_valid
        except (json.JSONDecodeError, KeyError, OSError) as e:
            logger.warning("Failed to read session metadata: %s", e)
            return False

    def clear_session(self) -> None:
        """Delete saved session files."""
        for path in [self.storage_state_path, self.encrypted_storage_path, self.session_meta_path]:
            if path.exists():
                try:
                    path.unlink()
                    logger.debug("Deleted %s", path.name)
                except OSError:
                    pass

        logger.info("Session cleared")

    def get_screenshots_dir(self) -> Path:
        """Get directory for saving browser screenshots."""
        screenshots_dir = self.data_dir / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        return screenshots_dir
