"""Browser authentication runner for profiles."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from playwright.async_api import async_playwright

from enabiz_ai.browser.edevlet_login import EDevletLogin
from enabiz_ai.browser.session_manager import SessionManager
from enabiz_ai.config import AppConfig
from enabiz_ai.profiles.manager import ProfileManager
from enabiz_ai.twofa.console_relay import ConsoleRelay
from enabiz_ai.twofa.telegram_relay import TelegramRelay

logger = logging.getLogger(__name__)


async def authenticate_profile(
    profile_id: str,
    config: AppConfig,
    master_passphrase: str,
    headless: bool = False,
) -> bool:
    """Run interactive or automated login for a specific family member profile.

    Args:
        profile_id: Profile ID ('default', 'anne', 'baba', etc.)
        config: Application configuration.
        master_passphrase: Master passphrase to decrypt stored credentials.
        headless: Whether to run Chromium headless.

    Returns:
        True if login succeeded and storage_state.json was saved.
    """
    pm = ProfileManager(config.data_dir)
    profile = pm.get_profile(profile_id)
    if not profile:
        raise ValueError(f"Profile '{profile_id}' not found.")

    profile_dir = pm.get_profile_dir(profile_id)
    cred_mgr = pm.get_credential_manager(profile_id)
    credentials = cred_mgr.load(master_passphrase)

    session_manager = SessionManager(
        data_dir=profile_dir,
        headless=headless,
    )

    # Setup 2FA relay with customized person banner
    chat_id = profile.telegram_chat_id or config.telegram_chat_id
    if config.telegram_bot_token and chat_id:
        twofa_relay = TelegramRelay(
            token=config.telegram_bot_token,
            authorized_chat_id=int(chat_id),
        )
        await twofa_relay.start()
        await twofa_relay.send_notification(
            f"🔐 <b>{profile.display_name} ({profile.relation})</b> için e-Devlet girişi başlatılıyor...\n"
            f"Telefona SMS veya Mobil Onay bildirimi gelirse lütfen onaylayın."
        )
    else:
        twofa_relay = ConsoleRelay()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            channel="chrome" if not config.chrome_path else None,
            executable_path=config.chrome_path,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
        )

        context_kwargs = {
            "viewport": {"width": 1280, "height": 800},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/134.0.0.0 Safari/537.36"
            ),
        }
        storage_path = session_manager.load_storage_state_path()
        if storage_path:
            context_kwargs["storage_state"] = storage_path

        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()

        login_handler = EDevletLogin(
            session_manager=session_manager,
            twofa_relay=twofa_relay,
            credentials=credentials,
        )

        try:
            success = await login_handler.login(page)
            if success:
                logger.info("Successfully authenticated profile %s", profile_id)
                if isinstance(twofa_relay, TelegramRelay):
                    await twofa_relay.send_notification(
                        f"✅ <b>{profile.display_name}</b> için e-Nabız oturumu başarıyla kaydedildi!"
                    )
                return True
            else:
                logger.warning("Authentication failed for profile %s", profile_id)
                return False
        finally:
            if isinstance(twofa_relay, TelegramRelay):
                await twofa_relay.stop()
            await browser.close()
