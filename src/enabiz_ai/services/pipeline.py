"""Core pipeline service for e-Nabız automated harvesting and clinical intelligence."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from playwright.async_api import async_playwright

from enabiz_ai.analysis.rag_engine import RAGEngine
from enabiz_ai.browser.session_manager import SessionManager
from enabiz_ai.config import AppConfig
from enabiz_ai.exceptions import HarvestError, SessionExpiredError
from enabiz_ai.extraction.harvester import ENabizHarvester
from enabiz_ai.profiles.manager import ProfileManager
from enabiz_ai.profiles.models import ProfileInfo
from enabiz_ai.storage.database import HealthDatabase

logger = logging.getLogger(__name__)


class SyncService:
    """Coordinates browser-based harvesting and clinical analysis workflows."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.pm = ProfileManager(config.data_dir)

    async def get_profile_stats(self, profile_id: str) -> dict[str, int]:
        """Fetch database stats for a single profile."""
        db_path = self.pm.get_db_path(profile_id)
        if not db_path.exists():
            return {}
        async with HealthDatabase(db_path) as db:
            return await db.get_stats()

    async def get_all_profiles_stats(self, profiles: list[ProfileInfo]) -> dict[str, dict[str, int]]:
        """Fetch database stats for all profiles concurrently in one event loop."""
        tasks = [self.get_profile_stats(p.id) for p in profiles]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        stats_map: dict[str, dict[str, int]] = {}
        for p, res in zip(profiles, results):
            if isinstance(res, Exception):
                logger.warning("Failed to get stats for %s: %s", p.id, res)
                stats_map[p.id] = {}
            else:
                stats_map[p.id] = res
        return stats_map

    async def harvest_profile(
        self,
        profile_info: ProfileInfo,
        target: str = "all",
        passphrase: str | None = None,
    ) -> dict[str, int]:
        """Harvest data from e-Nabız portal for a specific profile.

        Args:
            profile_info: Profile to harvest data for.
            target: Sections to harvest ('all', 'labs', 'rx').
            passphrase: Optional passphrase for decrypting session if encrypted.

        Returns:
            Dictionary with harvested count metrics.
        """
        p_dir = self.pm.get_profile_dir(profile_info.id)
        session_mgr = SessionManager(p_dir)
        db = self.pm.get_database(profile_info.id)

        # Determine session storage
        storage_state = session_mgr.load_storage_state(passphrase=passphrase)
        if not storage_state and session_mgr.session_file.exists():
            # Fallback path if string path is accepted
            storage_path = str(session_mgr.session_file)
        else:
            storage_path = None

        if not storage_state and not storage_path:
            raise SessionExpiredError(
                f"No active session for {profile_info.display_name}. "
                f"Run 'enabiz-ai profile login {profile_info.id}' first."
            )

        results: dict[str, int] = {}
        async with db:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=self.config.headless,
                    executable_path=self.config.chrome_path,
                )
                try:
                    context_kwargs: dict[str, Any] = {
                        "user_agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/134.0.0.0 Safari/537.36"
                        ),
                    }
                    if storage_state:
                        context_kwargs["storage_state"] = storage_state
                    elif storage_path:
                        context_kwargs["storage_state"] = storage_path

                    context = await browser.new_context(**context_kwargs)
                    page = await context.new_page()

                    harvester = ENabizHarvester(db)

                    if target == "labs":
                        results["lab_reports"] = await harvester.harvest_lab_results(page)
                    elif target == "rx":
                        results["prescriptions"] = await harvester.harvest_prescriptions(page)
                    else:
                        harvest_res = await harvester.harvest_all(page)
                        results.update(harvest_res)

                    # Update and re-encrypt session state
                    await session_mgr.save_storage_state(context, passphrase=passphrase)

                except Exception as e:
                    logger.error("Harvesting failed for %s: %s", profile_info.id, e)
                    raise HarvestError(f"Harvesting failed: {e}") from e
                finally:
                    await browser.close()

        return results

    async def run_clinical_analysis(
        self,
        profile_info: ProfileInfo,
        notify: bool = True,
    ) -> str:
        """Run RAG clinical intelligence and optionally send report to Telegram."""
        db = self.pm.get_database(profile_info.id)
        async with db:
            rag = RAGEngine(
                db=db,
                ollama_base_url=self.config.ollama_base_url,
                model=self.config.ollama_model,
            )
            report = await rag.generate_weekly_report(person_name=profile_info.display_name)

            chat_id = profile_info.telegram_chat_id or self.config.telegram_chat_id
            if notify and self.config.telegram_bot_token and chat_id:
                await rag.send_to_telegram(
                    report_text=report,
                    bot_token=self.config.telegram_bot_token,
                    chat_id=chat_id,
                    person_name=profile_info.display_name,
                )

            return report

    async def run_weekly_pipeline(
        self,
        profile_info: ProfileInfo,
        passphrase: str | None = None,
    ) -> tuple[dict[str, int], str]:
        """Execute full weekly harvest and clinical report pipeline."""
        harvest_results: dict[str, int] = {}
        try:
            harvest_results = await self.harvest_profile(profile_info, target="all", passphrase=passphrase)
        except Exception as e:
            logger.warning("Weekly sync harvest issue for %s: %s", profile_info.id, e)

        report = await self.run_clinical_analysis(profile_info, notify=True)
        return harvest_results, report
