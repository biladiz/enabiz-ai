"""LLM-driven e-Nabız portal navigation using browser-use.

Uses browser-use Agent with a local vision model (qwen2.5-vl) to
navigate the e-Nabız portal dynamically. Falls back to deterministic
Playwright selectors for known stable paths.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from browser_use import Agent, Browser, BrowserConfig, Controller, ActionResult
from browser_use.browser.context import BrowserContext, BrowserContextConfig
from langchain_ollama import ChatOllama
from playwright.async_api import Page

logger = logging.getLogger(__name__)

# ── Known e-Nabız section URLs and selectors ──────────────────────
ENABIZ_SECTIONS = {
    "lab_results": {
        "name": "Tahlillerim",
        "url_hint": "Tahlil",
        "task": "Tahlillerim (Lab Results) sayfasına git ve mevcut tahlil listesini bul.",
    },
    "prescriptions": {
        "name": "Reçetelerim",
        "url_hint": "Recete",
        "task": "Reçetelerim (Prescriptions) sayfasına git ve reçete listesini bul.",
    },
    "radiology": {
        "name": "Radyoloji Sonuçlarım",
        "url_hint": "Radyoloji",
        "task": "Radyoloji Sonuçlarım sayfasına git ve rapor listesini bul.",
    },
    "vaccinations": {
        "name": "Aşı Kayıtlarım",
        "url_hint": "Asi",
        "task": "Aşı Kayıtlarım sayfasına git ve aşı listesini bul.",
    },
    "appointments": {
        "name": "Randevularım",
        "url_hint": "Randevu",
        "task": "Randevularım sayfasına git.",
    },
}


class ENabizNavigator:
    """LLM-driven navigator for the e-Nabız health portal.

    Combines deterministic Playwright for known paths with
    browser-use Agent (local qwen2.5-vl) for dynamic navigation.

    Usage:
        nav = ENabizNavigator(
            ollama_base_url="http://localhost:11434",
            model="qwen2.5-vl:14b",
            browser=browser,
        )
        results = await nav.navigate_to_lab_results(page)
    """

    def __init__(
        self,
        ollama_base_url: str = "http://localhost:11434",
        model: str = "qwen2.5-vl:14b",
        use_vision: bool = True,
        download_dir: Path | None = None,
    ) -> None:
        """Initialize the navigator.

        Args:
            ollama_base_url: Ollama server URL.
            model: Model name for browser-use Agent.
            use_vision: Whether to send screenshots to the LLM.
            download_dir: Directory for downloaded files.
        """
        self.ollama_base_url = ollama_base_url
        self.model = model
        self.use_vision = use_vision
        self.download_dir = download_dir or Path.home() / ".enabiz-ai" / "downloads"
        self.download_dir.mkdir(parents=True, exist_ok=True)

        # Initialize the LLM
        self._llm = ChatOllama(
            model=self.model,
            base_url=self.ollama_base_url,
            num_ctx=32000,
            temperature=0.0,
        )

        # Setup controller with custom actions
        self._controller = Controller()
        self._register_custom_actions()

    def _register_custom_actions(self) -> None:
        """Register custom browser-use actions for structured data extraction."""

        @self._controller.action(
            "Extract the list of lab results visible on the current page. "
            "Return a JSON array of objects with fields: id, date, hospital, test_type."
        )
        def extract_lab_list(data: str) -> ActionResult:
            return ActionResult(extracted_content=data)

        @self._controller.action(
            "Extract prescription details from the current page. "
            "Return a JSON array with: id, date, medication, dosage, prescriber."
        )
        def extract_prescriptions(data: str) -> ActionResult:
            return ActionResult(extracted_content=data)

        @self._controller.action(
            "Extract radiology report details from the current page. "
            "Return a JSON array with: id, date, modality, body_part, hospital."
        )
        def extract_radiology(data: str) -> ActionResult:
            return ActionResult(extracted_content=data)

    async def navigate_to_section(
        self,
        page: Page,
        section: str,
        browser: Browser,
    ) -> str | None:
        """Navigate to a specific e-Nabız section using the LLM agent.

        Args:
            page: Current Playwright page.
            section: Section key from ENABIZ_SECTIONS.
            browser: browser-use Browser instance.

        Returns:
            Extracted content from the Agent, or None on failure.
        """
        if section not in ENABIZ_SECTIONS:
            raise ValueError(f"Unknown section: {section}. Valid: {list(ENABIZ_SECTIONS.keys())}")

        section_info = ENABIZ_SECTIONS[section]
        task = (
            f"Sen şu anda e-Nabız portalında (enabiz.gov.tr) giriş yapmış durumdasın. "
            f"{section_info['task']} "
            f"Sayfadaki verileri JSON formatında çıkar."
        )

        logger.info("Navigating to section: %s (%s)", section, section_info["name"])

        agent = Agent(
            task=task,
            llm=self._llm,
            browser=browser,
            controller=self._controller,
            use_vision=self.use_vision,
            max_steps=20,
            max_failures=3,
        )

        try:
            history = await agent.run()
            if history.is_successful():
                result = history.final_result()
                logger.info("Successfully navigated to %s", section_info["name"])
                return result
            else:
                logger.warning("Agent failed to complete task for %s", section)
                return None
        except Exception as e:
            logger.error("Error navigating to %s: %s", section, e)
            return None

    async def navigate_to_lab_results(
        self, page: Page, browser: Browser
    ) -> str | None:
        """Navigate to the lab results section and extract the list.

        Args:
            page: Current Playwright page (must be on e-Nabız).
            browser: browser-use Browser instance.

        Returns:
            JSON string of lab results list, or None.
        """
        return await self.navigate_to_section(page, "lab_results", browser)

    async def navigate_to_prescriptions(
        self, page: Page, browser: Browser
    ) -> str | None:
        """Navigate to prescriptions and extract the list."""
        return await self.navigate_to_section(page, "prescriptions", browser)

    async def navigate_to_radiology(
        self, page: Page, browser: Browser
    ) -> str | None:
        """Navigate to radiology reports and extract the list."""
        return await self.navigate_to_section(page, "radiology", browser)

    async def download_file_from_page(
        self,
        page: Page,
        download_button_selector: str,
        filename: str,
    ) -> Path | None:
        """Click a download button and save the resulting file.

        Args:
            page: Playwright page with the download button.
            download_button_selector: CSS selector for the download button/link.
            filename: Desired filename for the download.

        Returns:
            Path to the downloaded file, or None on failure.
        """
        try:
            async with page.expect_download(timeout=30000) as download_info:
                await page.click(download_button_selector)

            download = await download_info.value
            save_path = self.download_dir / filename
            await download.save_as(str(save_path))
            logger.info("Downloaded file: %s", save_path)
            return save_path
        except Exception as e:
            logger.error("Failed to download file: %s", e)
            return None

    async def get_page_content(self, page: Page) -> str:
        """Extract the text content of the current page.

        Args:
            page: Playwright page.

        Returns:
            The visible text content of the page.
        """
        return await page.inner_text("body")

    async def take_screenshot(self, page: Page, name: str, save_dir: Path) -> Path:
        """Take a screenshot of the current page.

        Args:
            page: Playwright page.
            name: Name for the screenshot file.
            save_dir: Directory to save the screenshot.

        Returns:
            Path to the saved screenshot.
        """
        save_dir.mkdir(parents=True, exist_ok=True)
        import time
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        path = save_dir / f"{name}_{timestamp}.png"
        await page.screenshot(path=str(path), full_page=True)
        logger.info("Screenshot saved: %s", path)
        return path
