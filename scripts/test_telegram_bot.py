"""Quick test script to verify Telegram Bot Relay connectivity with your phone.

Sends a test prompt to your Telegram app and waits for your reply.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel

from enabiz_ai.config import AppConfig
from enabiz_ai.twofa.telegram_relay import TelegramRelay

console = Console()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


async def main():
    config = AppConfig()

    console.print(Panel(
        "[bold cyan]🤖 e-Nabız AI — Telegram Bot Relay Test[/bold cyan]\n"
        "[dim]Testing outbound secure connection to Telegram (zero open ports)[/dim]",
        title="Telegram 2FA Test",
        border_style="cyan",
    ))

    if not config.telegram_bot_token or not config.telegram_chat_id:
        console.print("[red]❌ TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing in .env![/red]")
        console.print("Please set them in .env before running this test.")
        return

    chat_id = int(config.telegram_chat_id)
    console.print(f"Connecting to bot with Chat ID: [green]{chat_id}[/green]...")

    relay = TelegramRelay(token=config.telegram_bot_token, authorized_chat_id=chat_id)
    async with relay:
        console.print("[cyan]Sending test ping to your Telegram app...[/cyan]")
        await relay.send_notification("👋 *e-Nabız AI Test:* Bot bağlantısı başarılı!")
        
        console.print("\n[yellow]⏳ Check your phone! Please reply to the bot with any 6-digit test code (e.g. 123456):[/yellow]")
        try:
            received_code = await relay.request_otp(
                "Bu bir test mesajıdır. Lütfen test için herhangi bir 6 haneli kod yazın (örnek: 123456):",
                timeout=60.0,
            )
            console.print(Panel(
                f"[bold green]🎉 SUCCESS! Code received from your phone:[/bold green] [bold yellow]{received_code}[/bold yellow]\n\n"
                "The Telegram 2FA relay is working perfectly!\n"
                "When you run e-Devlet login, you can now enter your SMS code directly from Telegram on your phone.",
                title="Relay Test Passed",
                border_style="green",
            ))
        except TimeoutError:
            console.print("[red]❌ Timed out waiting for reply from Telegram.[/red]")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
