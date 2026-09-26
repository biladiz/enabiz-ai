import asyncio
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright
from enabiz_ai.extraction.harvester import ENabizHarvester
from enabiz_ai.storage.database import HealthDatabase

async def main():
    db_path = Path(os.path.expanduser('~/.enabiz-ai/health.db'))
    storage_path = os.path.expanduser('~/.enabiz-ai/session/storage_state.json')

    async with HealthDatabase(db_path) as db:
        print("Connected to database at:", db_path)
        harvester = ENabizHarvester(db)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(storage_state=storage_path)
            page = await context.new_page()

            print("Starting full e-Nabız medical data harvest into SQLite...")
            results = await harvester.harvest_all(page)
            print("Harvest Results:", results)

            await browser.close()

        stats = await db.get_stats()
        print("\n=== Current Database Statistics ===")
        for table, count in stats.items():
            print(f"  {table}: {count} records")

if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
