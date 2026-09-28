"""Deterministic ENabız direct login flow using Playwright automation.

Handles the direct TC Kimlik No + ENabız password login at enabiz.gov.tr,
as an alternative to e-Devlet gateway authentication.  Supports optional
2FA/SMS verification.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from enabiz_ai.browser.session_manager import SessionManager
from enabiz_ai.credentials.models import Credentials
from enabiz_ai.twofa.base import TwoFARelay

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────
ENABIZ_LOGIN_URL = "https://enabiz.gov.tr/Account/Login"
ENABIZ_DASHBOARD_URL = "enabiz.gov.tr"

# Politeness delays (seconds) to avoid triggering anti-bot
DELAY_BETWEEN_ACTIONS = 1.5
DELAY_AFTER_PAGE_LOAD = 2.0
DELAY_BEFORE_SUBMIT = 1.0

# Known ENabız login page selectors
ENABIZ_SELECTORS = {
    # TC Kimlik No input field
    "tc_input": '#TCKimlikNo, input[name="TCKimlikNo"]',
    # ENabız password input field
    "password_input": '#eNabiz, input[name="Sifre"]',
    # Login submit button
    "submit_button": '#btnGiris, button.loginBtn',
    # 2FA SMS verification container (becomes visible after login if 2FA enabled)
    "twofa_container": "#ikiAsamaliOnay",
    # 2FA SMS code input
    "twofa_input": '#IkiAsamaSmsKod, input[name="IkiAsamaSmsKod"]',
    # 2FA submit button
    "twofa_submit": "#ikiasamaligiris",
    # Error toast notification
    "error_toast": ".toast-error, .toast-message, #toast-container .toast",
    # Frozen account warning
    "frozen_account": ".dondurulmusHesapUyari",
    # CAPTCHA indicators
    "captcha": '.captcha, #captchaImage, [class*="captcha"], [id*="captcha"]',
}


class EnabizLoginError(Exception):
    """Raised when ENabız direct login fails."""
    pass


class EnabizCaptchaRequired(EnabizLoginError):
    """Raised when CAPTCHA challenge is detected on ENabız login."""
    pass


class EnabizOTPTimeout(EnabizLoginError):
    """Raised when OTP entry times out during ENabız 2FA."""
    pass


class EnabizLogin:
    """Handles the ENabız direct TC+password login flow.

    Uses deterministic Playwright selectors for the known login page at
    enabiz.gov.tr.  Integrates with a TwoFARelay for SMS OTP verification
    when 2FA is enabled for the account.

    Usage:
        login = EnabizLogin(session_manager, twofa_relay, credentials)
        success = await login.login(page)
    """

    def __init__(
        self,
        session_manager: SessionManager,
        twofa_relay: TwoFARelay,
        credentials: Credentials,
    ) -> None:
        """Initialize the ENabız login handler.

        Args:
            session_manager: For saving/loading session cookies.
            twofa_relay: 2FA relay for OTP exchange (Telegram or Console).
            credentials: Encrypted credentials (must have enabiz_password set).
        """
        self.session_manager = session_manager
        self.twofa = twofa_relay
        self.credentials = credentials

    async def login(self, page: Page) -> bool:
        """Execute the full ENabız direct login flow.

        Steps:
            1. Check if existing session is still valid
            2. Navigate to ENabız login page
            3. Fill TC Kimlik No and ENabız password
            4. Submit the form
            5. Handle 2FA/SMS verification if enabled
            6. Verify redirect to e-Nabız dashboard
            7. Save session cookies

        Args:
            page: A Playwright Page instance.

        Returns:
            True if login was successful.

        Raises:
            EnabizLoginError: If login fails for any reason.
            EnabizCaptchaRequired: If a CAPTCHA challenge appears.
            EnabizOTPTimeout: If the user doesn't provide OTP in time.
        """
        # Step 1: Check existing session
        if self.session_manager.is_session_valid():
            logger.info("Existing session is still valid — skipping ENabız login")
            await self.twofa.send_notification("ℹ️ Mevcut oturum geçerli, giriş atlanıyor.")
            return True

        logger.info("Starting ENabız direct login flow")
        await self.twofa.send_notification("🔄 e-Nabız doğrudan girişi başlatılıyor...")

        try:
            # Step 2: Navigate to login page
            await self._navigate_to_login(page)

            # Step 3: Check for CAPTCHA before proceeding
            if await self._detect_captcha(page):
                await self._handle_captcha(page)

            # Step 4: Fill credentials
            await self._fill_credentials(page)

            # Step 5: Submit the form
            await self._submit_login(page)

            # Step 6: Handle 2FA if enabled
            if self.credentials.twofa_enabled:
                await self._handle_2fa(page)

            # Step 7: Verify we reached e-Nabız dashboard
            await self._verify_dashboard(page)

            # Step 8: Save session
            context = page.context
            await self.session_manager.save_storage_state(context)

            logger.info("ENabız direct login successful!")
            await self.twofa.send_notification("✅ e-Nabız girişi başarılı!")
            return True

        except PlaywrightTimeout as e:
            logger.error("ENabız login timed out: %s", e)
            await self._save_debug_screenshot(page, "enabiz_login_timeout")
            raise EnabizLoginError(f"ENabız login timed out: {e}")
        except EnabizLoginError:
            raise
        except Exception as e:
            logger.error("ENabız login failed: %s", e)
            await self._save_debug_screenshot(page, "enabiz_login_error")
            raise EnabizLoginError(f"ENabız login failed: {e}")

    async def _navigate_to_login(self, page: Page) -> None:
        """Navigate to the ENabız login page."""
        logger.info("Navigating to ENabız login page: %s", ENABIZ_LOGIN_URL)
        await page.goto(ENABIZ_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(DELAY_AFTER_PAGE_LOAD)

        # If already on dashboard
        if ENABIZ_DASHBOARD_URL in page.url and "Account/Login" not in page.url:
            logger.info("Already on e-Nabız dashboard")
            return

    async def _fill_credentials(self, page: Page) -> None:
        """Fill in TC Kimlik No and ENabız password."""
        logger.info("Filling ENabız credentials")

        if not self.credentials.has_enabiz:
            raise EnabizLoginError("ENabız password is not configured for this profile.")

        # Find and fill TC Kimlik No
        tc_input = await self._find_element(
            page, ENABIZ_SELECTORS["tc_input"], "TC Kimlik No input"
        )
        await tc_input.click()
        await asyncio.sleep(0.3)
        await tc_input.fill(self.credentials.tc_no)
        await asyncio.sleep(DELAY_BETWEEN_ACTIONS)

        # Find and fill ENabız password
        pw_input = await self._find_element(
            page, ENABIZ_SELECTORS["password_input"], "ENabız password input"
        )
        await pw_input.click()
        await asyncio.sleep(0.3)
        await pw_input.fill(self.credentials.enabiz_password.get_secret_value())
        await asyncio.sleep(DELAY_BEFORE_SUBMIT)

    async def _submit_login(self, page: Page) -> None:
        """Submit the ENabız login form and wait for response."""
        logger.info("Submitting ENabız login form")
        submit_btn = await self._find_element(
            page, ENABIZ_SELECTORS["submit_button"], "Submit button"
        )
        await submit_btn.click()

        # Wait for navigation or AJAX response
        await asyncio.sleep(DELAY_AFTER_PAGE_LOAD)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightTimeout:
            logger.debug("Network didn't fully settle — continuing anyway")

        # Check for frozen account
        frozen_el = await page.query_selector(ENABIZ_SELECTORS["frozen_account"])
        if frozen_el:
            frozen_visible = await frozen_el.is_visible()
            if frozen_visible:
                logger.error("Account is frozen (dondurulmuş)")
                await self.twofa.send_notification(
                    "❌ Hesap dondurulmuş! Lütfen e-Nabız üzerinden hesabınızı açın."
                )
                raise EnabizLoginError("Account is frozen (dondurulmuş hesap).")

        # Check for error toast notifications
        error_el = await page.query_selector(ENABIZ_SELECTORS["error_toast"])
        if error_el:
            error_visible = await error_el.is_visible()
            if error_visible:
                error_text = await error_el.text_content()
                if error_text and error_text.strip():
                    logger.error("ENabız login error: %s", error_text.strip())
                    await self.twofa.send_notification(
                        f"❌ Giriş hatası: {error_text.strip()}"
                    )
                    raise EnabizLoginError(f"ENabız login error: {error_text.strip()}")

    async def _handle_2fa(self, page: Page) -> None:
        """Handle SMS OTP verification for ENabız 2FA.

        After form submission, the ENabız page may show an AJAX-driven 2FA
        panel (#ikiAsamaliOnay) if the account has 2FA enabled.
        """
        # Check if we've already been redirected to the dashboard (no 2FA needed)
        if ENABIZ_DASHBOARD_URL in page.url and "Account/Login" not in page.url:
            logger.info("No 2FA required — already on dashboard")
            return

        # Wait for the 2FA container to appear
        twofa_container = await page.query_selector(ENABIZ_SELECTORS["twofa_container"])
        if not twofa_container:
            await asyncio.sleep(2.0)
            twofa_container = await page.query_selector(ENABIZ_SELECTORS["twofa_container"])

        if not twofa_container:
            # 2FA might not be required, or we may already be on the dashboard
            if ENABIZ_DASHBOARD_URL in page.url and "Account/Login" not in page.url:
                return
            logger.info(
                "No 2FA container found — checking if login was successful (URL: %s)",
                page.url,
            )
            return

        # Check if the container is actually visible
        is_visible = await twofa_container.is_visible()
        if not is_visible:
            logger.info("2FA container exists but is not visible — no 2FA required")
            return

        logger.info("2FA page detected — requesting OTP from user")

        # Request OTP via the relay (Telegram or Console)
        otp_code = await self.twofa.request_otp(
            "📱 e-Nabız SMS doğrulama kodu telefonunuza gönderildi.\n"
            "Lütfen 6 haneli kodu girin:"
        )

        # Find and fill the OTP input
        otp_input = await self._find_element(
            page, ENABIZ_SELECTORS["twofa_input"], "2FA SMS code input"
        )
        await otp_input.click()
        await asyncio.sleep(0.3)
        await otp_input.fill(otp_code)
        await asyncio.sleep(DELAY_BEFORE_SUBMIT)

        # Submit OTP
        otp_submit = await page.query_selector(ENABIZ_SELECTORS["twofa_submit"])
        if otp_submit:
            await otp_submit.click()
        else:
            await otp_input.press("Enter")

        await asyncio.sleep(DELAY_AFTER_PAGE_LOAD)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightTimeout:
            logger.debug("Network didn't fully settle after 2FA — continuing")

    async def _verify_dashboard(self, page: Page) -> None:
        """Verify that we've successfully reached the e-Nabız dashboard."""
        # Wait for redirect to e-Nabız dashboard
        for _ in range(20):
            current_url = page.url
            if (
                ENABIZ_DASHBOARD_URL in current_url
                and "Account/Login" not in current_url
            ):
                logger.info(
                    "Successfully redirected to e-Nabız dashboard: %s", current_url
                )
                return
            await asyncio.sleep(1.0)

        # Final check
        current_url = page.url
        if ENABIZ_DASHBOARD_URL in current_url and "Account/Login" not in current_url:
            logger.info("On e-Nabız dashboard: %s", current_url)
            return

        logger.error(
            "Failed to reach e-Nabız dashboard. Current URL: %s", current_url
        )
        await self._save_debug_screenshot(page, "enabiz_dashboard_redirect_failed")
        raise EnabizLoginError(
            f"Failed to redirect to e-Nabız dashboard. Stuck at: {current_url}"
        )

    async def _detect_captcha(self, page: Page) -> bool:
        """Check if a CAPTCHA challenge is present on the page."""
        captcha_el = await page.query_selector(ENABIZ_SELECTORS["captcha"])
        if captcha_el:
            logger.warning("CAPTCHA detected on ENabız login page")
            return True
        return False

    async def _handle_captcha(self, page: Page) -> None:
        """Handle CAPTCHA by taking a screenshot and asking user to solve it."""
        screenshot_path = await self._save_debug_screenshot(page, "enabiz_captcha")

        await self.twofa.send_notification(
            "⚠️ CAPTCHA algılandı! Lütfen tarayıcıdan manuel olarak çözün."
        )

        if screenshot_path:
            await self.twofa.send_photo(
                str(screenshot_path),
                caption="CAPTCHA görüntüsü — lütfen tarayıcıda çözün",
            )

        # Wait for user to solve CAPTCHA manually
        await self.twofa.request_otp(
            "CAPTCHA'yı tarayıcıda çözdükten sonra 'tamam' yazın:",
            timeout=300.0,
        )

    async def _find_element(self, page: Page, selector: str, name: str):
        """Find a page element using a compound selector string.

        Args:
            page: Playwright Page.
            selector: CSS selector (may contain comma-separated alternatives).
            name: Human-readable name for logging.

        Returns:
            The found ElementHandle.

        Raises:
            EnabizLoginError: If element is not found.
        """
        # Try the compound selector first
        element = await page.query_selector(selector)
        if element:
            return element

        # Try each alternative individually
        for sel in selector.split(","):
            sel = sel.strip()
            element = await page.query_selector(sel)
            if element:
                return element

        # Last resort: wait for any of them
        try:
            await page.wait_for_selector(selector, timeout=10000)
            element = await page.query_selector(selector)
            if element:
                return element
        except PlaywrightTimeout:
            pass

        raise EnabizLoginError(
            f"Could not find {name} on page (selector: {selector})"
        )

    async def _save_debug_screenshot(self, page: Page, name: str) -> Path | None:
        """Save a debug screenshot to the screenshots directory.

        Args:
            page: Playwright Page.
            name: Name prefix for the screenshot file.

        Returns:
            Path to the saved screenshot, or None if failed.
        """
        try:
            screenshots_dir = self.session_manager.get_screenshots_dir()
            import time

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            screenshot_path = screenshots_dir / f"{name}_{timestamp}.png"
            await page.screenshot(path=str(screenshot_path), full_page=True)
            logger.debug("Debug screenshot saved: %s", screenshot_path)
            return screenshot_path
        except Exception as e:
            logger.warning("Failed to save screenshot: %s", e)
            return None
