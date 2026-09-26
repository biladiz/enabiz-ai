"""Console-based 2FA relay for local development and testing.

Uses terminal input/output when Telegram is not configured.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

logger = logging.getLogger(__name__)
console = Console()


class ConsoleRelay:
    """Console-based 2FA relay for development and testing.

    Falls back to terminal input when no Telegram bot is configured.

    Usage:
        relay = ConsoleRelay()
        otp = await relay.request_otp("Enter SMS code:")
    """

    async def start(self) -> None:
        """No-op for console relay."""
        console.print("[green]✓[/green] Console 2FA relay active")

    async def stop(self) -> None:
        """No-op for console relay."""
        pass

    async def __aenter__(self) -> ConsoleRelay:
        await self.start()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.stop()

    async def request_otp(self, prompt: str, timeout: float = 120.0) -> str:
        """Request OTP via terminal input.

        Args:
            prompt: The prompt message to display.
            timeout: Max seconds to wait (enforced via asyncio timeout).

        Returns:
            The code entered by the user.

        Raises:
            TimeoutError: If no input within timeout.
        """
        console.print(Panel(
            f"[bold yellow]🔐 2FA Doğrulama Gerekli[/bold yellow]\n\n{prompt}",
            title="OTP Required",
            border_style="yellow",
        ))

        loop = asyncio.get_running_loop()
        try:
            code = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: input("▶ OTP Kodu: ").strip()),
                timeout=timeout,
            )
            console.print(f"[green]✓ Kod alındı:[/green] {code}")
            return code
        except asyncio.TimeoutError:
            console.print("[red]✗ Zaman aşımı — OTP girilmedi[/red]")
            raise TimeoutError(f"No OTP input within {timeout} seconds")

    async def send_notification(self, message: str) -> None:
        """Print a notification to the console.

        Args:
            message: The notification text.
        """
        console.print(Panel(message, title="📢 Bildirim", border_style="blue"))

    async def send_photo(self, photo_path: str, caption: str = "") -> None:
        """Log photo path to console (can't display images in terminal).

        Args:
            photo_path: Path to the image file.
            caption: Optional caption.
        """
        path = Path(photo_path)
        console.print(
            f"[dim]📷 Screenshot kaydedildi: {path.name}[/dim]"
            + (f" — {caption}" if caption else "")
        )
