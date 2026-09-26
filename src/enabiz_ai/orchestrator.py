"""Main orchestrator — coordinates the full automation pipeline.

Pipeline flow:
    Login → Navigate → Download → Parse → Store → Notify
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from browser_use import Browser, BrowserConfig
from browser_use.browser.context import BrowserContext, BrowserContextConfig
from playwright.async_api import async_playwright
from pydantic import SecretStr

from enabiz_ai.browser.edevlet_login import EDevletLogin
from enabiz_ai.browser.enabiz_navigator import ENabizNavigator
from enabiz_ai.browser.session_manager import SessionManager
from enabiz_ai.config import AppConfig
from enabiz_ai.credentials.manager import CredentialManager
from enabiz_ai.extraction.lab_parser import LabParser
from enabiz_ai.extraction.llm_extractor import LLMExtractor
from enabiz_ai.storage.database import HealthDatabase
from enabiz_ai.storage.file_store import FileStore
from enabiz_ai.twofa.console_relay import ConsoleRelay
from enabiz_ai.twofa.telegram_relay import TelegramRelay

logger = logging.getLogger(__name__)


class Orchestrator:
    """Main automation pipeline coordinator.

    Manages the full lifecycle:
    1. Initialize services (browser, 2FA relay, database)
    2. Login to e-Devlet
    3. Navigate e-Nabız sections
    4. Download and parse documents
    5. Store structured data
    6. Notify user of results

    Usage:
        config = AppConfig()
        orch = Orchestrator(config, master_passphrase="my_secret")
        await orch.sync_lab_results()
    """

    def __init__(
        self,
        config: AppConfig,
        master_passphrase: str,
    ) -> None:
        """Initialize the orchestrator.

        Args:
            config: Application configuration.
            master_passphrase: Passphrase to decrypt stored credentials.
        """
        self.config = config
        self._passphrase = SecretStr(master_passphrase) if isinstance(master_passphrase, str) else master_passphrase

        # Initialize components
        self.credential_manager = CredentialManager(config.data_dir)
        self.session_manager = SessionManager(
            data_dir=config.data_dir,
            chrome_cdp_url=config.chrome_cdp_url,
            chrome_path=config.chrome_path,
            headless=config.headless,
        )
        self.file_store = FileStore(config.data_dir / "data")
        self.lab_parser = LabParser()
        self.llm_extractor = LLMExtractor(
            ollama_base_url=config.ollama_base_url,
            model=config.ollama_model,
        )

        # 2FA relay — Telegram if configured, otherwise Console
        if config.telegram_bot_token and config.telegram_chat_id:
            self.twofa = TelegramRelay(
                token=config.telegram_bot_token,
                authorized_chat_id=int(config.telegram_chat_id),
            )
            logger.info("Using Telegram 2FA relay")
        else:
            self.twofa = ConsoleRelay()
            logger.info("Using Console 2FA relay (Telegram not configured)")

        # Database path
        self.db_path = config.data_dir / "health.db"

        # Browser and page references (set during run)
        self._browser: Optional[Browser] = None
        self._page = None

    async def _setup_browser(self) -> tuple[Browser, BrowserContext]:
        """Initialize the browser with appropriate configuration.

        Returns:
            Tuple of (Browser, BrowserContext).
        """
        # Try CDP connection first (attach to existing Chrome)
        browser_config = BrowserConfig(
            headless=self.config.headless,
            cdp_url=self.config.chrome_cdp_url,
        )

        try:
            browser = Browser(config=browser_config)
            logger.info("Browser configured with CDP: %s", self.config.chrome_cdp_url)
        except Exception as e:
            logger.warning("CDP connection failed (%s), launching new browser", e)
            browser_config = BrowserConfig(
                headless=self.config.headless,
            )
            browser = Browser(config=browser_config)

        # Create context with session persistence
        storage_state = self.session_manager.load_storage_state_path()
        context_config = BrowserContextConfig(
            storage_state=storage_state,
            wait_for_network_idle_page_load_time=3.0,
        )

        context = await browser.new_context(config=context_config)
        self._browser = browser
        return browser, context

    async def _login(self, page) -> bool:
        """Execute the e-Devlet login flow.

        Args:
            page: Playwright page to use for login.

        Returns:
            True if login successful.
        """
        passphrase_val = self._passphrase.get_secret_value() if isinstance(self._passphrase, SecretStr) else self._passphrase
        credentials = self.credential_manager.load(passphrase_val)

        login_handler = EDevletLogin(
            session_manager=self.session_manager,
            twofa_relay=self.twofa,
            credentials=credentials,
        )

        return await login_handler.login(page)

    async def sync_lab_results(self) -> int:
        """Download and parse all new lab results from e-Nabız.

        Returns:
            Number of new reports synced.
        """
        logger.info("Starting lab results sync")
        await self.twofa.start()

        try:
            browser, context = await self._setup_browser()
            page = await context.get_current_page()

            # Login
            await self._login(page)

            # Navigate to lab results
            navigator = ENabizNavigator(
                ollama_base_url=self.config.ollama_base_url,
                model=self.config.ollama_model,
                download_dir=self.config.lab_results_dir,
            )

            results_json = await navigator.navigate_to_lab_results(page, browser)

            if not results_json:
                logger.warning("No lab results found or navigation failed")
                await self.twofa.send_notification("⚠️ Tahlil sonuçları bulunamadı.")
                return 0

            # Parse and store results
            synced = 0
            async with HealthDatabase(self.db_path) as db:
                # If we got page content, try LLM extraction
                page_text = await navigator.get_page_content(page)
                if page_text:
                    report = await self.llm_extractor.extract_lab_results(page_text)
                    saved = await db.save_lab_report(report)
                    if saved:
                        synced += 1

                await db.record_sync("labs", records_synced=synced)

            await self.twofa.send_notification(
                f"✅ Tahlil senkronizasyonu tamamlandı.\n"
                f"📊 {synced} yeni rapor kaydedildi."
            )

            logger.info("Lab sync complete: %d new reports", synced)
            return synced

        except Exception as e:
            logger.error("Lab sync failed: %s", e)
            await self.twofa.send_notification(f"❌ Tahlil senkronizasyonu başarısız: {e}")
            raise
        finally:
            await self.twofa.stop()
            if self._browser:
                await self._browser.close()

    async def sync_prescriptions(self) -> int:
        """Download and parse prescription history.

        Returns:
            Number of new prescriptions synced.
        """
        logger.info("Starting prescriptions sync")
        await self.twofa.start()

        try:
            browser, context = await self._setup_browser()
            page = await context.get_current_page()
            await self._login(page)

            navigator = ENabizNavigator(
                ollama_base_url=self.config.ollama_base_url,
                model=self.config.ollama_model,
            )

            await navigator.navigate_to_prescriptions(page, browser)
            page_text = await navigator.get_page_content(page)

            synced = 0
            if page_text:
                prescriptions = await self.llm_extractor.extract_prescriptions(page_text)
                async with HealthDatabase(self.db_path) as db:
                    for rx in prescriptions:
                        if await db.save_prescription(rx):
                            synced += 1
                    await db.record_sync("prescriptions", records_synced=synced)

            await self.twofa.send_notification(
                f"✅ Reçete senkronizasyonu tamamlandı.\n"
                f"💊 {synced} yeni reçete kaydedildi."
            )
            return synced

        except Exception as e:
            logger.error("Prescription sync failed: %s", e)
            await self.twofa.send_notification(f"❌ Reçete senkronizasyonu başarısız: {e}")
            raise
        finally:
            await self.twofa.stop()
            if self._browser:
                await self._browser.close()

    async def sync_all(self) -> dict[str, int]:
        """Run all sync tasks sequentially.

        Returns:
            Dict mapping sync type to count of new records.
        """
        results = {}

        try:
            results["labs"] = await self.sync_lab_results()
        except Exception as e:
            logger.error("Lab sync failed in sync_all: %s", e)
            results["labs"] = -1

        try:
            results["prescriptions"] = await self.sync_prescriptions()
        except Exception as e:
            logger.error("Prescription sync failed in sync_all: %s", e)
            results["prescriptions"] = -1

        return results

    async def parse_local_pdf(self, pdf_path: Path) -> None:
        """Parse a locally stored lab result PDF and save to database.

        Args:
            pdf_path: Path to the PDF file to parse.
        """
        logger.info("Parsing local PDF: %s", pdf_path)

        report = self.lab_parser.parse_pdf(pdf_path)

        async with HealthDatabase(self.db_path) as db:
            saved = await db.save_lab_report(report)
            if saved:
                logger.info("Saved report %s with %d tests", report.report_id, len(report.tests))
            else:
                logger.info("Report %s already exists", report.report_id)

        # Store the PDF in the file store
        self.file_store.save_file(pdf_path, "lab_results", report.date)

    async def query_data(
        self,
        data_type: str = "labs",
        since: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[dict]:
        """Query the local health database.

        Args:
            data_type: Type of data to query ('labs', 'prescriptions').
            since: ISO date string to filter from.
            search: Search term.

        Returns:
            List of matching records as dicts.
        """
        from datetime import datetime as dt

        since_dt = dt.fromisoformat(since) if since else None

        async with HealthDatabase(self.db_path) as db:
            if search:
                return await db.search(search)

            if data_type == "labs":
                reports = await db.get_lab_reports(since=since_dt)
                return [r.model_dump(mode="json") for r in reports]
            elif data_type == "prescriptions":
                rxs = await db.get_prescriptions(since=since_dt)
                return [r.model_dump(mode="json") for r in rxs]
            else:
                return []

    async def get_stats(self) -> dict:
        """Get statistics from both database and file store.

        Returns:
            Combined stats dict.
        """
        stats = {"files": self.file_store.get_stats()}

        async with HealthDatabase(self.db_path) as db:
            stats["database"] = await db.get_stats()
            stats["last_sync"] = {
                "labs": str(await db.get_latest_sync("labs")),
                "prescriptions": str(await db.get_latest_sync("prescriptions")),
                "all": str(await db.get_latest_sync("all")),
            }

        return stats
