"""Browser session management — cookie persistence and session validation.

Saves and restores Playwright storage state (cookies + localStorage)
to avoid re-authentication when sessions are still valid.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

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
        self.session_meta_path = self.session_dir / "session_meta.json"
        self.chrome_cdp_url = chrome_cdp_url
        self.chrome_path = chrome_path
        self.headless = headless

    async def save_storage_state(self, context) -> None:
        """Save the current browser context's storage state to disk.

        Args:
            context: A Playwright BrowserContext instance.
        """
        try:
            storage = await context.storage_state()
            with open(self.storage_state_path, "w", encoding="utf-8") as f:
                json.dump(storage, f, indent=2)

            # Save metadata with timestamp
            meta = {
                "saved_at": time.time(),
                "saved_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
            with open(self.session_meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)

            logger.info("Session state saved to %s", self.storage_state_path)
        except Exception as e:
            logger.error("Failed to save session state: %s", e)

    def load_storage_state_path(self) -> str | None:
        """Get the path to saved storage state if it exists and is valid.

        Returns:
            Path string to storage_state.json if valid, None otherwise.
        """
        if not self.storage_state_path.exists():
            logger.debug("No saved session found")
            return None

        if not self.is_session_valid():
            logger.info("Saved session has expired")
            return None

        logger.info("Valid saved session found")
        return str(self.storage_state_path)

    def is_session_valid(self) -> bool:
        """Check if the saved session is still fresh (< 15 min old).

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
        for path in [self.storage_state_path, self.session_meta_path]:
            if path.exists():
                path.unlink()
                logger.debug("Deleted %s", path.name)

        logger.info("Session cleared")

    def get_screenshots_dir(self) -> Path:
        """Get directory for saving browser screenshots."""
        screenshots_dir = self.data_dir / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        return screenshots_dir
