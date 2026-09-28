"""Browser authentication runner for profiles.

Supports two login strategies:
    1. e-Devlet (TC No + e-Devlet password + 2FA)
    2. ENabız direct (TC No + ENabız password ± 2FA)

The strategy is auto-selected based on which credentials are configured.
If both are present, e-Devlet is attempted first with ENabız as fallback.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from playwright.async_api import async_playwright

from enabiz_ai.browser.edevlet_login import EDevletLogin, LoginError
from enabiz_ai.browser.enabiz_login import EnabizLogin, EnabizLoginError
from enabiz_ai.browser.session_manager import SessionManager
from enabiz_ai.config import AppConfig
from enabiz_ai.profiles.manager import ProfileManager
from enabiz_ai.twofa.console_relay import ConsoleRelay
from enabiz_ai.twofa.telegram_relay import TelegramRelay

logger = logging.getLogger(__name__)

# Maximum e-Devlet attempts before falling back to ENabız
MAX_EDEVLET_ATTEMPTS = 2


async def authenticate_profile(
    profile_id: str,
    config: AppConfig,
    master_passphrase: str,
    headless: bool = False,
) -> bool:
    """Run interactive or automated login for a specific family member profile.

    Strategy selection:
        - If e-Devlet password is configured → try e-Devlet first (up to 2 attempts).
        - If e-Devlet fails (or not configured) and ENabız password is available
          → fall back to ENabız direct login.
        - If only one method is configured → use that method directly.

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

        method_label = _login_method_label(credentials)
        await twofa_relay.send_notification(
            f"🔐 <b>{profile.display_name} ({profile.relation})</b> için giriş başlatılıyor "
            f"({method_label})...\n"
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

        try:
            success = await _run_login_strategy(
                page=page,
                session_manager=session_manager,
                twofa_relay=twofa_relay,
                credentials=credentials,
            )

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


async def _run_login_strategy(
    page,
    session_manager: SessionManager,
    twofa_relay,
    credentials,
) -> bool:
    """Execute the login strategy with optional fallback.

    Tries e-Devlet first (if configured), then falls back to ENabız.
    """
    has_edevlet = credentials.has_edevlet
    has_enabiz = credentials.has_enabiz

    # ── Try e-Devlet first ─────────────────────────────────────────
    if has_edevlet:
        edevlet_handler = EDevletLogin(
            session_manager=session_manager,
            twofa_relay=twofa_relay,
            credentials=credentials,
        )
        for attempt in range(1, MAX_EDEVLET_ATTEMPTS + 1):
            try:
                logger.info(
                    "Attempting e-Devlet login (attempt %d/%d)",
                    attempt,
                    MAX_EDEVLET_ATTEMPTS,
                )
                success = await edevlet_handler.login(page)
                if success:
                    return True
            except (LoginError, Exception) as e:
                logger.warning(
                    "e-Devlet attempt %d failed: %s", attempt, e
                )
                if attempt < MAX_EDEVLET_ATTEMPTS:
                    await page.goto("about:blank")
                    await asyncio.sleep(1.0)

        if has_enabiz:
            logger.info("e-Devlet login exhausted, falling back to ENabız direct login...")
            await twofa_relay.send_notification(
                "⚠️ e-Devlet girişi başarısız. e-Nabız şifresi ile giriş deneniyor..."
            )
            await page.goto("about:blank")
            await asyncio.sleep(1.0)
        else:
            return False

    # ── ENabız direct login ────────────────────────────────────────
    if has_enabiz:
        enabiz_handler = EnabizLogin(
            session_manager=session_manager,
            twofa_relay=twofa_relay,
            credentials=credentials,
        )
        try:
            logger.info("Attempting ENabız direct login")
            return await enabiz_handler.login(page)
        except EnabizLoginError as e:
            logger.error("ENabız login failed: %s", e)
            return False

    # Neither method configured (shouldn't happen due to model validation)
    logger.error("No login credentials configured for this profile")
    return False


def _login_method_label(credentials) -> str:
    """Return a human-readable label for the configured login method."""
    if credentials.has_edevlet and credentials.has_enabiz:
        return "e-Devlet + e-Nabız yedek"
    elif credentials.has_edevlet:
        return "e-Devlet"
    else:
        return "e-Nabız doğrudan giriş"

