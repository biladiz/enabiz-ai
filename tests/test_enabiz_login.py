"""Unit tests for direct e-Nabız login handler, Cloudflare Turnstile handling, and 2FA flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from enabiz_ai.browser.enabiz_login import EnabizLogin, EnabizLoginError
from enabiz_ai.credentials.models import Credentials


@pytest.fixture
def mock_enabiz_env(tmp_path):
    session_mgr = MagicMock()
    session_mgr.data_dir = tmp_path
    session_mgr.get_screenshots_dir.return_value = tmp_path / "screenshots"
    session_mgr.is_session_valid.return_value = False
    session_mgr.save_storage_state = AsyncMock()

    twofa = MagicMock()
    twofa.send_notification = AsyncMock()
    twofa.request_otp = AsyncMock(return_value="123456")

    creds = Credentials(
        tc_no="12345678901",
        enabiz_password="my_secret_enabiz_pass",
        twofa_enabled=False,
    )
    handler = EnabizLogin(session_mgr, twofa, creds)
    return handler, session_mgr, twofa, creds


class TestEnabizTurnstileAndLogin:
    """Test suite for Cloudflare Turnstile detection, resolution, and submission."""

    @pytest.mark.asyncio
    async def test_detect_turnstile_true(self, mock_enabiz_env):
        handler, _, _, _ = mock_enabiz_env
        page = MagicMock()
        page.evaluate = AsyncMock(return_value=True)

        res = await handler._detect_turnstile(page)
        assert res is True
        page.evaluate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_detect_turnstile_false(self, mock_enabiz_env):
        handler, _, _, _ = mock_enabiz_env
        page = MagicMock()
        page.evaluate = AsyncMock(return_value=False)

        res = await handler._detect_turnstile(page)
        assert res is False

    @pytest.mark.asyncio
    async def test_get_challenge_token_success(self, mock_enabiz_env):
        handler, _, _, _ = mock_enabiz_env
        page = MagicMock()
        page.evaluate = AsyncMock(return_value="valid_turnstile_token_12345")

        token = await handler._get_challenge_token(page)
        assert token == "valid_turnstile_token_12345"

    @pytest.mark.asyncio
    async def test_resolve_turnstile_already_available(self, mock_enabiz_env):
        handler, _, twofa, _ = mock_enabiz_env
        page = MagicMock()
        page.evaluate = AsyncMock(side_effect=[True, "existing_token"])

        await handler._resolve_turnstile(page)
        # Should not need to notify or wait
        twofa.send_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_turnstile_waiting_success(self, mock_enabiz_env):
        handler, _, twofa, _ = mock_enabiz_env
        page = MagicMock()
        widget = MagicMock()
        widget.bounding_box = AsyncMock(return_value={"x": 100, "y": 200, "width": 300, "height": 70})
        page.query_selector = AsyncMock(return_value=widget)
        page.mouse = MagicMock()
        page.mouse.click = AsyncMock()

        # 1. detect: True
        # 2. initial get_challenge_token: None
        # 3. post auto-click token: None
        # 4. in polling loop 1st iteration: "user_clicked_token_abc"
        page.evaluate = AsyncMock(side_effect=[True, None, None, "user_clicked_token_abc"])

        await handler._resolve_turnstile(page)
        twofa.send_notification.assert_awaited()
        page.mouse.click.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_submit_login_catches_error_toast(self, mock_enabiz_env):
        handler, _, twofa, _ = mock_enabiz_env
        page = MagicMock()
        page.url = "https://enabiz.gov.tr/Account/Login"

        submit_btn = MagicMock()
        submit_btn.click = AsyncMock()

        async def query_selector_mock(selector):
            if "submit" in selector or "btnGiris" in selector:
                return submit_btn
            if "toast" in selector:
                toast = MagicMock()
                toast.is_visible = AsyncMock(return_value=True)
                toast.text_content = AsyncMock(return_value="T.C. Kimlik Numaranız veya Şifreniz Hatalı")
                return toast
            return None

        page.query_selector = AsyncMock(side_effect=query_selector_mock)
        handler._wait_for_any_selector = AsyncMock(return_value=submit_btn)

        with pytest.raises(EnabizLoginError, match="T.C. Kimlik Numaranız veya Şifreniz Hatalı"):
            await handler._submit_login(page)

    @pytest.mark.asyncio
    async def test_submit_login_catches_frozen_account(self, mock_enabiz_env):
        handler, _, twofa, _ = mock_enabiz_env
        page = MagicMock()
        page.url = "https://enabiz.gov.tr/Account/Login"

        submit_btn = MagicMock()
        submit_btn.click = AsyncMock()

        async def query_selector_mock(selector):
            if "submit" in selector or "btnGiris" in selector:
                return submit_btn
            if "dondurulmus" in selector:
                frozen = MagicMock()
                frozen.is_visible = AsyncMock(return_value=True)
                return frozen
            return None

        page.query_selector = AsyncMock(side_effect=query_selector_mock)
        handler._wait_for_any_selector = AsyncMock(return_value=submit_btn)

        with pytest.raises(EnabizLoginError, match="dondurulmuş hesap"):
            await handler._submit_login(page)

    @pytest.mark.asyncio
    async def test_handle_2fa_flow_success(self, mock_enabiz_env):
        handler, _, twofa, _ = mock_enabiz_env
        page = MagicMock()
        page.url = "https://enabiz.gov.tr/Account/Login"

        twofa_container = MagicMock()
        twofa_container.is_visible = AsyncMock(return_value=True)

        otp_input = MagicMock()
        otp_input.click = AsyncMock()
        otp_input.fill = AsyncMock()

        otp_submit = MagicMock()
        otp_submit.click = AsyncMock()

        async def query_selector_mock(selector):
            if "ikiAsamaliOnay" in selector:
                return twofa_container
            if "ikiasamaligiris" in selector:
                return otp_submit
            return None

        page.query_selector = AsyncMock(side_effect=query_selector_mock)
        handler._find_element = AsyncMock(return_value=otp_input)

        # In wait loop, URL switches to dashboard
        async def sleep_mock(sec):
            page.url = "https://enabiz.gov.tr/"

        with patch("asyncio.sleep", side_effect=sleep_mock):
            await handler._handle_2fa(page)

        twofa.request_otp.assert_awaited_once()
        otp_input.fill.assert_awaited_once_with("123456")
        otp_submit.click.assert_awaited_once()
