"""Deterministic e-Devlet login flow using direct Playwright automation.

Uses hardcoded selectors for the known e-Devlet login page structure.
Falls back to LLM-driven navigation only when the page structure changes.
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
EDEVLET_SERVICE_URL = "https://www.turkiye.gov.tr/saglik-bakanligi-e-nabiz-kisisel-saglik-sistemi"
EDEVLET_LOGIN_URL = "https://giris.turkiye.gov.tr/Giris/gir"
ENABIZ_DASHBOARD_URL = "enabiz.gov.tr"

# Politeness delays (seconds) to avoid triggering anti-bot
DELAY_BETWEEN_ACTIONS = 1.5
DELAY_AFTER_PAGE_LOAD = 2.0
DELAY_BEFORE_SUBMIT = 1.0

# Known e-Devlet login page selectors (may need updating if page changes)
SELECTORS = {
    # TC Kimlik No input field
    "tc_input": 'input[name="tridField"], input[id="tridField"], input[placeholder*="T.C."]',
    # Password input field
    "password_input": 'input[name="egpField"], input[id="egpField"], input[type="password"]',
    # Login/submit button
    "submit_button": 'button[type="submit"], input[type="submit"], #submitButton, .submitBtn',
    # OTP/SMS verification code input
    "otp_input": 'input[name="singleFactorOtpField"], input[id="singleFactorOtpField"], input[name="otpField"], input[id="otpField"], input[name="smsCode"], input[name*="Otp"], input[id*="Otp"], input[placeholder*="Doğrulama"]',
    # OTP submit button
    "otp_submit": '#otpSubmitBtn, input[value*="Onayla"], button:has-text("Onayla"), button[type="submit"], input[type="submit"]',
    # CAPTCHA indicators
    "captcha": '.captcha, #captchaImage, [class*="captcha"], [id*="captcha"]',
    # Error messages
    "error_message": '.alert-danger, .error-message, [class*="hata"], [class*="error"]',
}


class LoginError(Exception):
    """Raised when login fails."""
    pass


class CaptchaRequired(LoginError):
    """Raised when CAPTCHA challenge is detected."""
    pass


class OTPTimeout(LoginError):
    """Raised when OTP entry times out."""
    pass


class EDevletLogin:
    """Handles the e-Devlet authentication flow for e-Nabız access.

    Uses deterministic Playwright selectors for the known login page.
    Integrates with a TwoFARelay for SMS OTP verification.

    Usage:
        login = EDevletLogin(session_manager, twofa_relay, credentials)
        success = await login.login(page)
    """

    def __init__(
        self,
        session_manager: SessionManager,
        twofa_relay: TwoFARelay,
        credentials: Credentials,
    ) -> None:
        """Initialize the login handler.

        Args:
            session_manager: For saving/loading session cookies.
            twofa_relay: 2FA relay for OTP exchange (Telegram or Console).
            credentials: Encrypted credentials (TC no + password).
        """
        self.session_manager = session_manager
        self.twofa = twofa_relay
        self.credentials = credentials

    async def login(self, page: Page) -> bool:
        """Execute the full e-Devlet login flow.

        Steps:
            1. Check if existing session is still valid
            2. Navigate to e-Devlet login page
            3. Fill TC Kimlik No and password
            4. Submit the form
            5. Handle 2FA/SMS verification if prompted
            6. Wait for redirect to e-Nabız
            7. Save session cookies

        Args:
            page: A Playwright Page instance.

        Returns:
            True if login was successful.

        Raises:
            LoginError: If login fails for any reason.
            CaptchaRequired: If a CAPTCHA challenge appears.
            OTPTimeout: If the user doesn't provide OTP in time.
        """
        # Step 1: Check existing session
        if self.session_manager.is_session_valid():
            logger.info("Existing session is still valid — skipping login")
            await self.twofa.send_notification("ℹ️ Mevcut oturum geçerli, giriş atlanıyor.")
            return True

        logger.info("Starting e-Devlet login flow")
        await self.twofa.send_notification("🔄 e-Devlet girişi başlatılıyor...")

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

            # Step 6: Handle 2FA if needed
            await self._handle_2fa(page)

            # Step 7: Verify we reached e-Nabız
            target_page = await self._verify_dashboard(page)

            # Step 8: Save session
            context = target_page.context
            await self.session_manager.save_storage_state(context)

            logger.info("Login successful!")
            await self.twofa.send_notification("✅ e-Nabız girişi başarılı!")
            return True

        except PlaywrightTimeout as e:
            logger.error("Login timed out: %s", e)
            await self._save_debug_screenshot(page, "login_timeout")
            raise LoginError(f"Login timed out: {e}")
        except Exception as e:
            logger.error("Login failed: %s", e)
            await self._save_debug_screenshot(page, "login_error")
            raise

    async def _navigate_to_login(self, page: Page) -> None:
        """Navigate to the e-Devlet service page and open login gateway."""
        logger.info("Navigating to e-Devlet service page: %s", EDEVLET_SERVICE_URL)
        await page.goto(EDEVLET_SERVICE_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(DELAY_AFTER_PAGE_LOAD)

        # If already on dashboard or e-Nabız
        if ENABIZ_DASHBOARD_URL in page.url:
            logger.info("Already on e-Nabız dashboard")
            return

        # Check if we need to click "Kimliğimi Şimdi Doğrula" to enter giris.turkiye.gov.tr
        login_btn = await page.query_selector(
            "a.btn-login, a[href*='giris.turkiye.gov.tr'], a.btn:has-text('Kimliğimi Şimdi Doğrula'), a:has-text('Giriş Yap')"
        )
        if login_btn:
            logger.info("Clicking 'Kimliğimi Şimdi Doğrula' to proceed to login gateway...")
            await login_btn.click()
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(DELAY_AFTER_PAGE_LOAD)

        # Verify we're on the login page
        current_url = page.url
        if "giris.turkiye.gov.tr" not in current_url and "turkiye.gov.tr" not in current_url:
            logger.warning("Unexpected URL after navigation: %s", current_url)

    async def _fill_credentials(self, page: Page) -> None:
        """Fill in TC Kimlik No and password."""
        logger.info("Filling credentials")

        # Find and fill TC Kimlik No
        tc_input = await self._find_element(page, SELECTORS["tc_input"], "TC Kimlik No input")
        await tc_input.click()
        await asyncio.sleep(0.3)
        await tc_input.fill(self.credentials.tc_no)
        await asyncio.sleep(DELAY_BETWEEN_ACTIONS)

        # Find and fill password
        pw_input = await self._find_element(page, SELECTORS["password_input"], "Password input")
        await pw_input.click()
        await asyncio.sleep(0.3)
        await pw_input.fill(self.credentials.password.get_secret_value())
        await asyncio.sleep(DELAY_BEFORE_SUBMIT)

    async def _submit_login(self, page: Page) -> None:
        """Submit the login form and wait for response."""
        logger.info("Submitting login form")
        submit_btn = await self._find_element(page, SELECTORS["submit_button"], "Submit button")
        await submit_btn.click()

        # Wait for navigation or response
        await asyncio.sleep(DELAY_AFTER_PAGE_LOAD)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightTimeout:
            logger.debug("Network didn't fully settle — continuing anyway")

        # Check for error messages
        error_el = await page.query_selector(SELECTORS["error_message"])
        if error_el:
            error_text = await error_el.text_content()
            if error_text and error_text.strip():
                logger.error("Login error displayed: %s", error_text.strip())
                await self.twofa.send_notification(
                    f"❌ Giriş hatası: {error_text.strip()}"
                )
                raise LoginError(f"e-Devlet login error: {error_text.strip()}")

    async def _handle_2fa(self, page: Page) -> None:
        """Handle SMS OTP verification or mobile app push approval."""
        # Check if we've already been redirected (no 2FA needed)
        if ENABIZ_DASHBOARD_URL in page.url or "kisisel-saglik-sistemi" in page.url:
            logger.info("No 2FA required — already on service or dashboard")
            return

        # Check if Mobile App Notification Approval (Mobil Onay) is active
        page_content = await page.content()
        if "İki Aşamalı Giriş Onay" in page_content or "bildirime tıklayarak" in page_content or "Kayıtlı Cihaz" in page_content:
            logger.info("Mobile push approval (Mobil Onay) detected — waiting for user approval on phone")
            await self.twofa.send_notification(
                "📱 *e-Devlet Mobil Onay Bildirimi Gönderildi*\n\n"
                "Lütfen telefonunuzdaki e-Devlet uygulamasını açıp girişi onaylayın. "
                "Onay bekleniyor..."
            )
            # Wait for user to approve on phone (page will automatically navigate away)
            for _ in range(90):
                await asyncio.sleep(1.0)
                if "giris.turkiye.gov.tr/Giris" not in page.url:
                    logger.info("Mobile notification approved! URL changed to: %s", page.url)
                    return
                # Check if SMS OTP input appeared as a fallback
                otp_input = await page.query_selector(SELECTORS["otp_input"])
                if otp_input:
                    logger.info("SMS OTP input appeared as fallback")
                    break

        # Look for the OTP input field
        otp_input = await page.query_selector(SELECTORS["otp_input"])
        if not otp_input:
            await asyncio.sleep(2.0)
            otp_input = await page.query_selector(SELECTORS["otp_input"])

        if not otp_input:
            if ENABIZ_DASHBOARD_URL in page.url or "kisisel-saglik-sistemi" in page.url:
                return
            logger.warning("No OTP field found and not on dashboard — checking URL: %s", page.url)
            await self._save_debug_screenshot(page, "unknown_state_after_login")
            return

        logger.info("2FA page detected — requesting OTP from user")

        # Request OTP via the relay (Telegram or Console)
        otp_code = await self.twofa.request_otp(
            "📱 e-Devlet SMS doğrulama kodu telefonunuza gönderildi.\n"
            "Lütfen 6 haneli kodu girin:"
        )

        # Fill in the OTP
        await otp_input.click()
        await asyncio.sleep(0.3)
        await otp_input.fill(otp_code)
        await asyncio.sleep(DELAY_BEFORE_SUBMIT)

        # Submit OTP
        otp_submit = await page.query_selector(SELECTORS["otp_submit"])
        if otp_submit:
            await otp_submit.click()
        else:
            await otp_input.press("Enter")

        await asyncio.sleep(DELAY_AFTER_PAGE_LOAD)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightTimeout:
            logger.debug("Network didn't fully settle after OTP — continuing")

    async def _verify_dashboard(self, page: Page) -> Page:
        """Verify that we've successfully reached the e-Nabız dashboard."""
        target_page = page

        # Check if service page displays 'Uygulamaya Git' (a.ssoLink) and click it
        for _ in range(15):
            for p in page.context.pages:
                if ENABIZ_DASHBOARD_URL in p.url:
                    target_page = p
                    break
            if ENABIZ_DASHBOARD_URL in target_page.url:
                break

            sso_link = await page.query_selector("a.ssoLink, a:has-text('Uygulamaya Git')")
            if sso_link:
                logger.info("Found 'Uygulamaya Git' (ssoLink) button — clicking to open e-Nabız...")
                try:
                    async with page.context.expect_page(timeout=10000) as new_page_info:
                        await sso_link.click()
                    target_page = await new_page_info.value
                    logger.info("New tab opened: %s", target_page.url)
                except Exception:
                    await sso_link.click()
                break
            await asyncio.sleep(1.0)

        # On the target tab, handle OAuth authorization consent ('Onayla' button)
        for _ in range(15):
            for p in page.context.pages:
                if "AuthorizationController" in p.url or ENABIZ_DASHBOARD_URL in p.url:
                    target_page = p
                    break

            if "AuthorizationController" in target_page.url:
                logger.info("OAuth Authorization page detected. Looking for 'Onayla' button...")
                onayla_btn = await target_page.query_selector("input[value='Onayla'], button:has-text('Onayla'), .btn-send")
                if onayla_btn:
                    logger.info("Clicking OAuth 'Onayla' button...")
                    await onayla_btn.click()
                    await asyncio.sleep(2.0)
                    break

            if ENABIZ_DASHBOARD_URL in target_page.url:
                break
            await asyncio.sleep(1.0)

        # Wait for redirect to e-Nabız dashboard
        try:
            await target_page.wait_for_url(
                f"**/{ENABIZ_DASHBOARD_URL}/**",
                timeout=25000,
            )
            logger.info("Successfully redirected to e-Nabız dashboard: %s", target_page.url)
        except PlaywrightTimeout:
            for p in page.context.pages:
                if ENABIZ_DASHBOARD_URL in p.url:
                    target_page = p
                    break

            if ENABIZ_DASHBOARD_URL not in target_page.url:
                current_url = target_page.url
                logger.error("Failed to reach e-Nabız dashboard. Current URL: %s", current_url)
                await self._save_debug_screenshot(target_page, "dashboard_redirect_failed")
                raise LoginError(
                    f"Failed to redirect to e-Nabız. Stuck at: {current_url}"
                )

        return target_page

    async def _detect_captcha(self, page: Page) -> bool:
        """Check if a CAPTCHA challenge is present on the page."""
        captcha_el = await page.query_selector(SELECTORS["captcha"])
        if captcha_el:
            logger.warning("CAPTCHA detected on login page")
            return True
        return False

    async def _handle_captcha(self, page: Page) -> None:
        """Handle CAPTCHA by taking a screenshot and asking user to solve it."""
        screenshot_path = await self._save_debug_screenshot(page, "captcha_challenge")

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
            timeout=300.0,  # 5 minutes for manual CAPTCHA solving
        )

    async def _find_element(self, page: Page, selector: str, name: str):
        """Find a page element using a compound selector string.

        Tries each selector in the comma-separated list.

        Args:
            page: Playwright Page.
            selector: CSS selector (may contain comma-separated alternatives).
            name: Human-readable name for logging.

        Returns:
            The found ElementHandle.

        Raises:
            LoginError: If element is not found.
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

        raise LoginError(f"Could not find {name} on page (selector: {selector})")

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
