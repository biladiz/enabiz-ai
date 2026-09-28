"""Telegram Bot-based 2FA relay for interactive OTP exchange.

Uses python-telegram-bot v21+ async API with long polling.
No public IP or open ports required — all communication is outbound.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logger = logging.getLogger(__name__)


class TelegramRelay:
    """Telegram Bot 2FA relay for exchanging OTP codes with the user.

    Usage:
        relay = TelegramRelay(token="BOT_TOKEN", authorized_chat_id=123456)
        async with relay:
            otp = await relay.request_otp("Enter your e-Devlet SMS code:")
    """

    def __init__(self, token: str, authorized_chat_id: int) -> None:
        """Initialize the Telegram relay.

        Args:
            token: Telegram Bot API token from @BotFather.
            authorized_chat_id: The only chat ID allowed to interact.
                Get this by messaging your bot and using /start command.
        """
        self.token = token
        self.authorized_chat_id = authorized_chat_id
        self._pending_request: asyncio.Future[str] | None = None
        self._app: Application | None = None
        self._started = False

    async def start(self) -> None:
        """Initialize and start the Telegram bot polling loop."""
        if self._started:
            logger.warning("TelegramRelay is already started")
            return

        self._app = (
            Application.builder()
            .token(self.token)
            .build()
        )

        # Register handlers
        self._app.add_handler(CommandHandler("start", self._handle_start))
        self._app.add_handler(CommandHandler("status", self._handle_status))
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_reply)
        )

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        self._started = True
        logger.info("TelegramRelay started — listening for messages")

    async def stop(self) -> None:
        """Gracefully shut down the bot."""
        if not self._started or self._app is None:
            return

        # Cancel any pending OTP request
        if self._pending_request and not self._pending_request.done():
            self._pending_request.cancel()

        await self._app.updater.stop()
        await self._app.stop()
        await self._app.shutdown()
        self._started = False
        logger.info("TelegramRelay stopped")

    async def __aenter__(self) -> TelegramRelay:
        await self.start()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.stop()

    async def request_otp(self, prompt: str, timeout: float = 120.0) -> str:
        """Send a prompt and wait for the user to reply with an OTP code.

        Args:
            prompt: The message to send (e.g., "Enter your SMS verification code").
            timeout: Max seconds to wait for a reply.

        Returns:
            The text the user sent back (typically a 6-digit OTP).

        Raises:
            TimeoutError: If no reply is received within the timeout.
            RuntimeError: If the relay hasn't been started.
        """
        if not self._started or self._app is None:
            raise RuntimeError("TelegramRelay is not started. Call start() first.")

        loop = asyncio.get_running_loop()
        self._pending_request = loop.create_future()

        # Send the OTP prompt with a lock emoji
        await self._app.bot.send_message(
            chat_id=self.authorized_chat_id,
            text=(
                f"🔐 *2FA Doğrulama Gerekli*\n\n"
                f"{prompt}\n\n"
                f"_Bu mesaja {int(timeout)} saniye içinde yanıt verin._"
            ),
            parse_mode="Markdown",
        )
        logger.info("OTP request sent to Telegram chat %s", self.authorized_chat_id)

        try:
            code = await asyncio.wait_for(self._pending_request, timeout=timeout)
            logger.info("OTP code received from Telegram")
            return code
        except asyncio.TimeoutError:
            await self._app.bot.send_message(
                chat_id=self.authorized_chat_id,
                text="❌ 2FA zaman aşımına uğradı. Lütfen tekrar deneyin.",
            )
            raise TimeoutError(
                f"No OTP response received within {timeout} seconds"
            )
        finally:
            self._pending_request = None

    async def send_notification(self, message: str, parse_mode: str | None = None) -> None:
        """Send a one-way notification to the user.

        Args:
            message: The notification text.
            parse_mode: Optional parse mode ('HTML', 'Markdown', or None).
                Auto-detects HTML tags if None.
        """
        if not self._started or self._app is None:
            logger.warning("Cannot send notification — relay not started")
            return

        if parse_mode is None:
            # Auto-detect HTML tags like <b>, <i>, <code>, <a>
            if re.search(r"<(b|i|code|a|strong|em|pre)[^>]*>", message, re.IGNORECASE):
                parse_mode = "HTML"
            else:
                parse_mode = "Markdown"

        try:
            await self._app.bot.send_message(
                chat_id=self.authorized_chat_id,
                text=message,
                parse_mode=parse_mode,
            )
        except Exception as e:
            # Fallback to plain text if formatting fails
            logger.warning(
                "Failed to send formatted message (%s), retrying as plain text: %s",
                parse_mode,
                e,
            )
            try:
                await self._app.bot.send_message(
                    chat_id=self.authorized_chat_id,
                    text=message,
                )
            except Exception as inner_e:
                logger.error("Failed to send plain text message: %s", inner_e)

    async def send_photo(self, photo_path: str, caption: str = "") -> None:
        """Send a photo (screenshot, report preview) to the user.

        Args:
            photo_path: Path to the image file.
            caption: Optional caption text.
        """
        if not self._started or self._app is None:
            logger.warning("Cannot send photo — relay not started")
            return

        path = Path(photo_path)
        if not path.exists():
            logger.error("Photo file not found: %s", photo_path)
            return

        with open(path, "rb") as photo_file:
            await self._app.bot.send_photo(
                chat_id=self.authorized_chat_id,
                photo=photo_file,
                caption=caption or path.stem,
            )

    # ── Handler methods ──────────────────────────────────────────────

    async def _handle_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /start command — shows the user's chat ID for configuration."""
        chat_id = update.effective_chat.id
        await update.message.reply_text(
            f"🤖 e-Nabız AI Bot aktif!\n\n"
            f"Chat ID'niz: `{chat_id}`\n\n"
            f"Bu ID'yi `.env` dosyanızdaki `TELEGRAM_CHAT_ID` alanına ekleyin.",
            parse_mode="Markdown",
        )

    async def _handle_status(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /status command — shows current bot status."""
        chat_id = update.effective_chat.id
        if chat_id != self.authorized_chat_id:
            await update.message.reply_text("⛔ Yetkisiz erişim.")
            return

        pending = "Evet ⏳" if self._pending_request and not self._pending_request.done() else "Hayır"
        await update.message.reply_text(
            f"📊 *Bot Durumu*\n\n"
            f"Aktif: ✅\n"
            f"Bekleyen OTP isteği: {pending}",
            parse_mode="Markdown",
        )

    async def _handle_reply(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle text messages — resolves pending OTP requests."""
        chat_id = update.effective_chat.id

        # Security: only accept from authorized user
        if chat_id != self.authorized_chat_id:
            logger.warning("Unauthorized message from chat_id=%s", chat_id)
            await update.message.reply_text("⛔ Yetkisiz erişim / Unauthorized.")
            return

        text = update.message.text.strip()

        # If there's a pending OTP request, resolve it
        if self._pending_request and not self._pending_request.done():
            self._pending_request.set_result(text)
            await update.message.reply_text(
                f"✅ Kod alındı: `{text}`\nGiriş devam ediyor...",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                "ℹ️ Şu anda bekleyen bir doğrulama isteği yok.\n"
                "Durum kontrolü için /status komutunu kullanın."
            )
