import asyncio
import json
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright

async def inspect_tahlil_details():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        storage_path = os.path.expanduser('~/.enabiz-ai/session/storage_state.json')
        context = await browser.new_context(storage_state=storage_path)
        page = await context.new_page()

        # Capture network responses for JSON or API data
        async def handle_response(response):
            try:
                ct = response.headers.get("content-type", "")
                if "json" in ct or "javascript" in ct or "text/plain" in ct:
                    url = response.url
                    if any(k in url.lower() for k in ["tahlil", "lab", "sonuc", "get"]):
                        print(f"[API Response] {response.status} {url}")
            except Exception:
                pass

        page.on("response", handle_response)

        print("Navigating to https://enabiz.gov.tr/Home/Tahlillerim ...")
        await page.goto('https://enabiz.gov.tr/Home/Tahlillerim', wait_until='networkidle')
        await asyncio.sleep(3)

        # Let's see what interactive elements or containers exist
        # Look for buttons, dates, accordion headers
        elements = await page.eval_on_selector_all(
            "button, .btn, [role='tab'], .nav-link, .list-group-item, .panel, .collapse, .accordion-item, .tahlil, [id*='tahlil'], [class*='tahlil']",
            "els => els.map(e => ({ tag: e.tagName, id: e.id, class: e.className, text: e.innerText.slice(0, 100).trim() }))"
        )
        print(f"\nFound {len(elements)} relevant elements on Tahlillerim:")
        for el in elements[:25]:
            if el['text']:
                print(f"<{el['tag']} id='{el['id']}' class='{el['class']}'> -> {repr(el['text'])}")

        # Check all text inside the main container
        main_content = await page.eval_on_selector(
            "main, #content, .content, .container, body",
            "e => e.innerText"
        )
        print("\n--- Main Content Text (first 60 lines) ---")
        lines = [l.strip() for l in main_content.split('\n') if l.strip()]
        for l in lines[:60]:
            print("  ", l)

        await browser.close()

if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(inspect_tahlil_details())
