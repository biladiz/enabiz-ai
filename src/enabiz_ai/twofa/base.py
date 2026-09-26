"""Abstract base protocol for 2FA relay implementations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TwoFARelay(Protocol):
    """Protocol defining the interface for 2FA relay implementations.

    Any class implementing this protocol can be used as a 2FA relay
    in the automation pipeline. Current implementations:
    - TelegramRelay: Uses Telegram Bot API for mobile OTP relay
    - ConsoleRelay: Uses terminal input for local development
    """

    async def request_otp(self, prompt: str, timeout: float = 120.0) -> str:
        """Send a prompt to the user and wait for their OTP response.

        Args:
            prompt: The message to display to the user (e.g., "Enter SMS code").
            timeout: Maximum seconds to wait for a response.

        Returns:
            The OTP code entered by the user.

        Raises:
            TimeoutError: If the user doesn't respond within the timeout.
        """
        ...

    async def send_notification(self, message: str) -> None:
        """Send a one-way notification to the user.

        Args:
            message: The notification text to send.
        """
        ...

    async def send_photo(self, photo_path: str, caption: str = "") -> None:
        """Send a photo/screenshot to the user.

        Args:
            photo_path: Absolute path to the image file.
            caption: Optional caption for the photo.
        """
        ...

    async def start(self) -> None:
        """Initialize and start the relay service."""
        ...

    async def stop(self) -> None:
        """Gracefully shut down the relay service."""
        ...
