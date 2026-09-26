"""Dedicated test script for e-Devlet to e-Nabız login with SMS 2FA.

Runs locally on Windows with a visible Chromium browser window.
No credentials or browser sessions touch the remote server.
"""

from __future__ import annotations

import asyncio
import getpass
import logging
import os
import sys
from pathlib import Path

# Add src to sys.path so it works directly from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from playwright.async_api import async_playwright
from rich.console import Console
from rich.panel import Panel

from enabiz_ai.browser.edevlet_login import EDevletLogin
from enabiz_ai.browser.session_manager import SessionManager
from enabiz_ai.config import config
from enabiz_ai.credentials.manager import CredentialManager, InvalidPassphraseError
from enabiz_ai.credentials.models import Credentials
from enabiz_ai.twofa.console_relay import ConsoleRelay
from enabiz_ai.twofa.telegram_relay import TelegramRelay

console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("trial_login")


async def run_trial_login():
    console.print(Panel(
        "[bold cyan]🏥 e-Nabız AI — e-Devlet & SMS 2FA Trial Access Test[/bold cyan]\n"
        "[dim]Privacy-First: Running 100% locally on your Windows machine.[/dim]",
        title="e-Nabız Login Test",
        border_style="cyan",
    ))

    data_dir = config.data_dir
    cred_manager = CredentialManager(data_dir)

    # 1. Master Passphrase & Credentials Setup
    passphrase = os.environ.get("MASTER_PASSPHRASE") or os.environ.get("ENABIZ_PASSPHRASE")
    if cred_manager.exists():
        console.print("[yellow]🔑 Found encrypted credential vault in ~/.enabiz-ai.[/yellow]")
        if passphrase:
            try:
                creds = cred_manager.load(passphrase)
                console.print(f"[green]✓ Vault decrypted successfully for TC: {creds.tc_no[:3]}*****{creds.tc_no[-2:]}[/green]")
            except InvalidPassphraseError:
                console.print("[red]✗ Master passphrase provided is incorrect.[/red]")
                passphrase = None

        if not passphrase:
            while True:
                try:
                    passphrase = getpass.getpass("Enter master encryption passphrase: ")
                except Exception:
                    passphrase = input("Enter master encryption passphrase: ")
                try:
                    creds = cred_manager.load(passphrase)
                    console.print(f"[green]✓ Vault decrypted successfully for TC: {creds.tc_no[:3]}*****{creds.tc_no[-2:]}[/green]")
                    break
                except InvalidPassphraseError:
                    console.print("[red]✗ Incorrect master passphrase. Please try again.[/red]")
    else:
        console.print("[yellow]ℹ️ No credential vault found. Initializing secure vault...[/yellow]")
        while True:
            passphrase = getpass.getpass("Create a new master encryption passphrase: ")
            confirm = getpass.getpass("Confirm master encryption passphrase: ")
            if passphrase == confirm and passphrase:
                break
            console.print("[red]✗ Passphrases do not match or empty. Try again.[/red]")

        console.print("\n[bold]Enter your e-Devlet login credentials (will be encrypted locally):[/bold]")
        tc_no = input("TC Kimlik No (11 digits): ").strip()
        while len(tc_no) != 11 or not tc_no.isdigit():
            console.print("[red]TC Kimlik No must be an 11-digit number.[/red]")
            tc_no = input("TC Kimlik No (11 digits): ").strip()

        password = getpass.getpass("e-Devlet Password: ")
        cred_manager.save(tc_no=tc_no, password=password, master_passphrase=passphrase)
        creds = cred_manager.load(passphrase)
        console.print("[green]✓ Credentials safely encrypted and saved with AES-Fernet + PBKDF2.[/green]")

    # 2. Setup Playwright & Session
    session_manager = SessionManager(
        data_dir=data_dir,
        chrome_cdp_url=config.chrome_cdp_url,
        chrome_path=config.chrome_path,
        headless=False,  # Visible browser for trial test
    )

    # Use Telegram relay if configured, otherwise Console fallback
    if config.telegram_bot_token and config.telegram_chat_id:
        twofa_relay = TelegramRelay(
            token=config.telegram_bot_token,
            authorized_chat_id=int(config.telegram_chat_id),
        )
        console.print("[green]📱 Using Telegram 2FA Relay — you will receive the OTP prompt directly on your phone![/green]")
    else:
        twofa_relay = ConsoleRelay()
        console.print("[yellow]⌨️ Using Console 2FA Relay[/yellow]")

    console.print("\n[bold cyan]🚀 Launching Chromium browser (visible mode)...[/bold cyan]")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--start-maximized",
            ],
        )

        context_kwargs = {
            "viewport": {"width": 1280, "height": 800},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        }
        
        # Check if existing session state is available
        storage_path = session_manager.load_storage_state_path()
        if storage_path:
            context_kwargs["storage_state"] = storage_path

        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()

        login_handler = EDevletLogin(
            session_manager=session_manager,
            twofa_relay=twofa_relay,
            credentials=creds,
        )

        if isinstance(twofa_relay, TelegramRelay):
            await twofa_relay.start()

        console.print("[cyan]Navigating to e-Devlet login portal for e-Nabız...[/cyan]")
        try:
            success = await login_handler.login(page)
            if success:
                target_page = page
                for p in context.pages:
                    if "enabiz.gov.tr" in p.url:
                        target_page = p
                        break

                console.print(Panel(
                    f"[bold green]🎉 SUCCESS! Logged into e-Nabız successfully![/bold green]\n\n"
                    f"Current URL: {target_page.url}\n"
                    f"Session storage saved to: {session_manager.session_file}\n"
                    f"You are now authenticated to e-Nabız.",
                    title="Trial Test Passed",
                    border_style="green",
                ))

                # Capture confirmation screenshot
                screenshot_path = data_dir / "enabiz_login_success.png"
                await target_page.screenshot(path=str(screenshot_path))
                console.print(f"[green]📸 Dashboard screenshot saved to: {screenshot_path}[/green]")

                if isinstance(twofa_relay, TelegramRelay):
                    await twofa_relay.send_notification("🎉 *e-Nabız Girişi Başarılı!* Oturum kaydedildi.")
                    await twofa_relay.send_photo(str(screenshot_path), caption="🏥 e-Nabız Dashboard Başarılı Giriş")

                console.print("\n[dim]Browser will remain open for 15 seconds so you can inspect...[/dim]")
                await asyncio.sleep(15)
            else:
                console.print("[red]❌ Login did not complete successfully.[/red]")

        except Exception as e:
            console.print(f"[bold red]❌ Login failed with error:[/bold red] {e}")
            err_shot = data_dir / "login_error_debug.png"
            try:
                await page.screenshot(path=str(err_shot))
                console.print(f"[yellow]📸 Debug screenshot captured at: {err_shot}[/yellow]")
            except Exception:
                pass
            raise
        finally:
            if isinstance(twofa_relay, TelegramRelay):
                await twofa_relay.stop()
            await context.close()
            await browser.close()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(run_trial_login())
