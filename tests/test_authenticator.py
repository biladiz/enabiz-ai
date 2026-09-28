"""Unit tests for browser authenticator strategy selection and fallback."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from enabiz_ai.browser.authenticator import _login_method_label, _run_login_strategy
from enabiz_ai.browser.edevlet_login import LoginError
from enabiz_ai.browser.enabiz_login import EnabizLoginError
from enabiz_ai.credentials.models import Credentials


class TestAuthenticatorStrategy:
    """Test suite for authenticator strategy selection and fallback logic."""

    def test_login_method_labels(self):
        edevlet_only = Credentials(tc_no="12345678901", password="secret_edevlet")
        assert _login_method_label(edevlet_only) == "e-Devlet"

        enabiz_only = Credentials(tc_no="12345678901", enabiz_password="secret_enabiz")
        assert _login_method_label(enabiz_only) == "e-Nabız doğrudan giriş"

        both = Credentials(
            tc_no="12345678901",
            password="secret_edevlet",
            enabiz_password="secret_enabiz",
        )
        assert _login_method_label(both) == "e-Devlet + e-Nabız yedek"

    @pytest.mark.asyncio
    @patch("enabiz_ai.browser.authenticator.EDevletLogin")
    async def test_strategy_edevlet_only_success(self, mock_edevlet_cls):
        mock_handler = MagicMock()
        mock_handler.login = AsyncMock(return_value=True)
        mock_edevlet_cls.return_value = mock_handler

        creds = Credentials(tc_no="12345678901", password="secret_edevlet")
        mock_page = MagicMock()
        mock_session_mgr = MagicMock()
        mock_twofa = MagicMock()

        result = await _run_login_strategy(
            page=mock_page,
            session_manager=mock_session_mgr,
            twofa_relay=mock_twofa,
            credentials=creds,
        )

        assert result is True
        mock_handler.login.assert_awaited_once_with(mock_page)

    @pytest.mark.asyncio
    @patch("enabiz_ai.browser.authenticator.EDevletLogin")
    async def test_strategy_edevlet_only_failure(self, mock_edevlet_cls):
        mock_handler = MagicMock()
        mock_handler.login = AsyncMock(side_effect=LoginError("Invalid password"))
        mock_edevlet_cls.return_value = mock_handler

        creds = Credentials(tc_no="12345678901", password="secret_edevlet")
        mock_page = MagicMock()
        mock_page.goto = AsyncMock()
        mock_session_mgr = MagicMock()
        mock_twofa = MagicMock()

        result = await _run_login_strategy(
            page=mock_page,
            session_manager=mock_session_mgr,
            twofa_relay=mock_twofa,
            credentials=creds,
        )

        assert result is False
        assert mock_handler.login.await_count == 2

    @pytest.mark.asyncio
    @patch("enabiz_ai.browser.authenticator.EnabizLogin")
    async def test_strategy_enabiz_only_success(self, mock_enabiz_cls):
        mock_handler = MagicMock()
        mock_handler.login = AsyncMock(return_value=True)
        mock_enabiz_cls.return_value = mock_handler

        creds = Credentials(tc_no="12345678901", enabiz_password="secret_enabiz")
        mock_page = MagicMock()
        mock_session_mgr = MagicMock()
        mock_twofa = MagicMock()

        result = await _run_login_strategy(
            page=mock_page,
            session_manager=mock_session_mgr,
            twofa_relay=mock_twofa,
            credentials=creds,
        )

        assert result is True
        mock_handler.login.assert_awaited_once_with(mock_page)

    @pytest.mark.asyncio
    @patch("enabiz_ai.browser.authenticator.EnabizLogin")
    async def test_strategy_enabiz_only_failure(self, mock_enabiz_cls):
        mock_handler = MagicMock()
        mock_handler.login = AsyncMock(side_effect=EnabizLoginError("Account locked"))
        mock_enabiz_cls.return_value = mock_handler

        creds = Credentials(tc_no="12345678901", enabiz_password="secret_enabiz")
        mock_page = MagicMock()
        mock_session_mgr = MagicMock()
        mock_twofa = MagicMock()

        result = await _run_login_strategy(
            page=mock_page,
            session_manager=mock_session_mgr,
            twofa_relay=mock_twofa,
            credentials=creds,
        )

        assert result is False
        mock_handler.login.assert_awaited_once_with(mock_page)

    @pytest.mark.asyncio
    @patch("enabiz_ai.browser.authenticator.EnabizLogin")
    @patch("enabiz_ai.browser.authenticator.EDevletLogin")
    async def test_strategy_fallback_from_edevlet_to_enabiz_on_failure(
        self, mock_edevlet_cls, mock_enabiz_cls
    ):
        mock_edevlet = MagicMock()
        mock_edevlet.login = AsyncMock(side_effect=LoginError("e-Devlet gateway down"))
        mock_edevlet_cls.return_value = mock_edevlet

        mock_enabiz = MagicMock()
        mock_enabiz.login = AsyncMock(return_value=True)
        mock_enabiz_cls.return_value = mock_enabiz

        creds = Credentials(
            tc_no="12345678901",
            password="secret_edevlet",
            enabiz_password="secret_enabiz",
        )
        mock_page = MagicMock()
        mock_page.goto = AsyncMock()
        mock_session_mgr = MagicMock()
        mock_twofa = MagicMock()
        mock_twofa.send_notification = AsyncMock()

        result = await _run_login_strategy(
            page=mock_page,
            session_manager=mock_session_mgr,
            twofa_relay=mock_twofa,
            credentials=creds,
        )

        assert result is True
        assert mock_edevlet.login.await_count == 2
        mock_enabiz.login.assert_awaited_once_with(mock_page)
        mock_twofa.send_notification.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("enabiz_ai.browser.authenticator.EnabizLogin")
    @patch("enabiz_ai.browser.authenticator.EDevletLogin")
    async def test_strategy_both_edevlet_succeeds_without_fallback(
        self, mock_edevlet_cls, mock_enabiz_cls
    ):
        mock_edevlet = MagicMock()
        mock_edevlet.login = AsyncMock(return_value=True)
        mock_edevlet_cls.return_value = mock_edevlet

        mock_enabiz = MagicMock()
        mock_enabiz.login = AsyncMock(return_value=True)
        mock_enabiz_cls.return_value = mock_enabiz

        creds = Credentials(
            tc_no="12345678901",
            password="secret_edevlet",
            enabiz_password="secret_enabiz",
        )
        mock_page = MagicMock()
        mock_session_mgr = MagicMock()
        mock_twofa = MagicMock()

        result = await _run_login_strategy(
            page=mock_page,
            session_manager=mock_session_mgr,
            twofa_relay=mock_twofa,
            credentials=creds,
        )

        assert result is True
        mock_edevlet.login.assert_awaited_once_with(mock_page)
        mock_enabiz.login.assert_not_called()
