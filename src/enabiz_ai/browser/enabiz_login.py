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

from enabiz_ai.browser.base_login import (
    BaseLoginHandler,
    DELAY_AFTER_PAGE_LOAD,
    DELAY_BEFORE_SUBMIT,
    DELAY_BETWEEN_ACTIONS,
)
from enabiz_ai.browser.session_manager import SessionManager
from enabiz_ai.credentials.models import Credentials
from enabiz_ai.exceptions import (
    EnabizCaptchaRequired,
    EnabizLoginError,
    EnabizOTPTimeout,
)
from enabiz_ai.twofa.base import TwoFARelay

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────
ENABIZ_LOGIN_URL = "https://enabiz.gov.tr/Account/Login"
ENABIZ_DASHBOARD_URL = "enabiz.gov.tr"

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
    # Cloudflare Turnstile bot challenge
    "turnstile_widget": "#bot-challenge-widget, .cf-turnstile, [data-sitekey]",
    "turnstile_iframe": 'iframe[src*="challenges.cloudflare.com"], iframe[src*="turnstile"], #bot-challenge-widget iframe',
}


class EnabizLogin(BaseLoginHandler):
    """Handles the ENabız direct TC+password login flow.

    Uses deterministic Playwright selectors for the known login page at
    enabiz.gov.tr. Handles Cloudflare Turnstile bot verification challenges
    and integrates with a TwoFARelay for SMS OTP verification when 2FA is
    enabled for the account.

    Usage:
        login = EnabizLogin(session_manager, twofa_relay, credentials)
        success = await login.login(page)
    """

    async def login(self, page: Page) -> bool:
        """Execute the full ENabız direct login flow.

        Steps:
            1. Check if existing session is still valid
            2. Navigate to ENabız login page
            3. Fill TC Kimlik No and ENabız password
            4. Resolve Cloudflare Turnstile bot challenge if present
            5. Submit the form
            6. Handle 2FA/SMS verification if prompted
            7. Verify redirect to e-Nabız dashboard
            8. Save session cookies

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

            # Step 3: Check for traditional CAPTCHA before proceeding
            if await self._detect_captcha(page):
                await self._handle_captcha(page)

            # Step 4: Fill credentials
            await self._fill_credentials(page)

            # Step 5: Resolve Cloudflare Turnstile before submission
            await self._resolve_turnstile(page)

            # Step 6: Submit the form
            await self._submit_login(page)

            # Step 7: Handle 2FA if prompted
            await self._handle_2fa(page)

            # Step 8: Verify we reached e-Nabız dashboard
            await self._verify_dashboard(page)

            # Step 9: Save session
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

    async def _detect_turnstile(self, page: Page) -> bool:
        """Check if Cloudflare Turnstile bot challenge is active on the page."""
        try:
            return await page.evaluate(
                "() => (typeof isBotChallengeEnabled !== 'undefined' && isBotChallengeEnabled) || "
                "!!document.getElementById('bot-challenge-widget') || "
                "!!document.querySelector('.cf-turnstile') || "
                "!!document.querySelector('iframe[src*=\"challenges.cloudflare.com\"]')"
            )
        except Exception:
            return False

    async def _get_challenge_token(self, page: Page) -> str | None:
        """Retrieve the current Turnstile challenge token if resolved."""
        try:
            token = await page.evaluate(
                "() => (typeof getChallengeToken === 'function' ? getChallengeToken() : "
                "(document.querySelector('[name=\"cf-turnstile-response\"]') ? "
                "document.querySelector('[name=\"cf-turnstile-response\"]').value : null))"
            )
            if token and isinstance(token, str) and token.strip():
                return token.strip()
            return None
        except Exception:
            return None

    async def _resolve_turnstile(self, page: Page) -> None:
        """Handle Cloudflare Turnstile verification before form submission."""
        if not await self._detect_turnstile(page):
            return

        # Check if already resolved
        token = await self._get_challenge_token(page)
        if token:
            logger.info("Cloudflare Turnstile token already available")
            return

        logger.info("Cloudflare Turnstile challenge detected — attempting verification")

        # 1. Attempt auto-clicking the Turnstile widget
        widget = await page.query_selector(ENABIZ_SELECTORS["turnstile_widget"])
        if widget:
            box = await widget.bounding_box()
            if box:
                try:
                    await page.mouse.click(box["x"] + 30, box["y"] + (box["height"] / 2))
                except Exception as e:
                    logger.debug("Failed to auto-click turnstile widget: %s", e)

        # Wait briefly to check if auto-click resolved the challenge
        await asyncio.sleep(2.0)
        token = await self._get_challenge_token(page)
        if token:
            logger.info("Cloudflare Turnstile verified automatically")
            return

        # 2. Inform user via notification & console
        prompt_msg = (
            "🧩 Cloudflare robot doğrulaması gerekiyor. "
            "Lütfen ekrandaki 'Verify you are human' (Robot olmadığınızı doğrulayın) kutucuğuna tıklayın."
        )
        logger.warning(prompt_msg)
        await self.twofa.send_notification(
            "🧩 <b>Güvenlik Doğrulaması (Cloudflare Turnstile):</b>\n"
            "Lütfen açılan tarayıcı penceresinde <b>'Verify you are human'</b> kutucuğuna tıklayarak doğrulamayı tamamlayın."
        )

        # 3. Wait for user or Turnstile completion (up to 90 seconds)
        for second in range(90):
            token = await self._get_challenge_token(page)
            if token:
                logger.info("Cloudflare Turnstile challenge resolved after %d seconds", second + 1)
                await self.twofa.send_notification("✅ Güvenlik doğrulaması tamamlandı, giriş yapılıyor...")
                return
            await asyncio.sleep(1.0)

        # Timed out
        await self._save_debug_screenshot(page, "enabiz_turnstile_timeout")
        raise EnabizLoginError(
            "Cloudflare Turnstile doğrulaması zaman aşımına uğradı. "
            "Lütfen açılan tarayıcı penceresindeki 'Verify you are human' kutucuğunu işaretleyin."
        )

    async def _submit_login(self, page: Page) -> None:
        """Submit the ENabız login form and wait for response."""
        logger.info("Submitting ENabız login form")
        submit_btn = await self._find_element(
            page, ENABIZ_SELECTORS["submit_button"], "Submit button"
        )
        await submit_btn.click()

        # Poll immediately for toastr notifications, errors, 2FA prompt, or redirect
        for _ in range(30):
            await asyncio.sleep(0.3)

            # Check if redirected to dashboard
            if ENABIZ_DASHBOARD_URL in page.url and "Account/Login" not in page.url:
                logger.info("Redirected away from login page immediately")
                return

            # Check if 2FA container is visible
            twofa_el = await page.query_selector(ENABIZ_SELECTORS["twofa_container"])
            if twofa_el and await twofa_el.is_visible():
                logger.info("2FA container (#ikiAsamaliOnay) is now visible")
                return

            # Check for frozen account
            frozen_el = await page.query_selector(ENABIZ_SELECTORS["frozen_account"])
            if frozen_el and await frozen_el.is_visible():
                logger.error("Account is frozen (dondurulmuş)")
                await self.twofa.send_notification(
                    "❌ Hesap dondurulmuş! Lütfen e-Devlet üzerinden hesabınızı aktif hâle getirin."
                )
                raise EnabizLoginError("Account is frozen (dondurulmuş hesap). Lütfen e-Devlet ile giriş yapınız.")

            # Check for error toast notifications
            error_el = await page.query_selector(ENABIZ_SELECTORS["error_toast"])
            if error_el and await error_el.is_visible():
                error_text = await error_el.text_content()
                if error_text and error_text.strip():
                    msg = error_text.strip()
                    logger.error("ENabız login error toast: %s", msg)
                    await self.twofa.send_notification(f"❌ Giriş hatası: {msg}")
                    raise EnabizLoginError(f"e-Nabız giriş hatası: {msg}")

    async def _handle_2fa(self, page: Page) -> None:
        """Handle SMS OTP verification for ENabız 2FA.

        After form submission, the ENabız page may show an AJAX-driven 2FA
        panel (#ikiAsamaliOnay) if the account has 2FA enabled.
        """
        # Check if we've already been redirected to the dashboard (no 2FA needed)
        if ENABIZ_DASHBOARD_URL in page.url and "Account/Login" not in page.url:
            logger.info("No 2FA required — already on dashboard")
            return

        # Check if 2FA container is visible or wait briefly for it
        twofa_container = await page.query_selector(ENABIZ_SELECTORS["twofa_container"])
        for _ in range(6):
            if twofa_container and await twofa_container.is_visible():
                break
            await asyncio.sleep(0.5)
            twofa_container = await page.query_selector(ENABIZ_SELECTORS["twofa_container"])

        if not twofa_container or not await twofa_container.is_visible():
            if ENABIZ_DASHBOARD_URL in page.url and "Account/Login" not in page.url:
                return
            logger.info("No visible 2FA container found")
            return

        logger.info("2FA page detected (#ikiAsamaliOnay) — requesting OTP from user")

        # Request OTP via the relay (Telegram or Console)
        otp_code = await self.twofa.request_otp(
            "📱 e-Nabız SMS doğrulama kodu telefonunuza gönderildi.\n"
            "Lütfen SMS ile gelen 6 haneli kodu girin:"
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

        # Wait for redirect or check for SMS errors
        for _ in range(20):
            await asyncio.sleep(0.5)
            if ENABIZ_DASHBOARD_URL in page.url and "Account/Login" not in page.url:
                return
            error_el = await page.query_selector(ENABIZ_SELECTORS["error_toast"])
            if error_el and await error_el.is_visible():
                txt = await error_el.text_content()
                if txt and txt.strip():
                    raise EnabizLoginError(f"2FA SMS doğrulama hatası: {txt.strip()}")

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

        # Check if an error message or incomplete turnstile is present
        error_el = await page.query_selector(
            ENABIZ_SELECTORS["error_toast"] + ", .alert-danger, .validation-summary-errors"
        )
        if error_el and await error_el.is_visible():
            err_txt = await error_el.text_content()
            if err_txt and err_txt.strip():
                raise EnabizLoginError(f"e-Nabız giriş hatası: {err_txt.strip()}")

        if await self._detect_turnstile(page) and not await self._get_challenge_token(page):
            await self._save_debug_screenshot(page, "enabiz_turnstile_incomplete")
            raise EnabizLoginError(
                "e-Nabız giriş ekranında Cloudflare güvenlik doğrulaması (Turnstile) tamamlanamadı. "
                "Lütfen tarayıcıdaki 'Verify you are human' kutucuğunu işaretleyin veya e-Devlet ile giriş yapın."
            )

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
        return await self._wait_for_any_selector(page, selector, name=name)
