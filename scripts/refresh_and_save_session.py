import asyncio
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright

async def save_enabiz_session():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        storage_path = os.path.expanduser('~/.enabiz-ai/session/storage_state.json')
        context = await b.new_context(storage_state=storage_path)
        page = await context.new_page()
        print("Checking if e-Devlet session is still alive...")
        await page.goto('https://www.turkiye.gov.tr/saglik-bakanligi-e-nabiz-kisisel-saglik-sistemi')
        sso_link = await page.query_selector('a.ssoLink')
        if sso_link:
            print("e-Devlet session is ALIVE! Clicking SSO link...")
            async with context.expect_page() as new_page_info:
                await sso_link.click()
            new_page = await new_page_info.value
            await new_page.wait_for_load_state('domcontentloaded')
            await asyncio.sleep(2)
            onayla = await new_page.query_selector("input[value='Onayla'], .btn-send")
            if onayla:
                print("Clicking Onayla on OAuth consent...")
                await onayla.click()
                await new_page.wait_for_url("**/enabiz.gov.tr/**", timeout=20000)
            
            print("Landed on URL:", new_page.url)
            # Save storage state of the authenticated context!
            await context.storage_state(path=storage_path)
            print("Saved updated full session state to:", storage_path)
        else:
            print("e-Devlet session expired (login button displayed).")
        await b.close()

if __name__ == "__main__":
    asyncio.run(save_enabiz_session())
