import asyncio
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright

async def print_recete_html():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        ctx = await b.new_context(storage_state=os.path.expanduser('~/.enabiz-ai/session/storage_state.json'))
        page = await ctx.new_page()
        await page.goto('https://enabiz.gov.tr/Home/Recetelerim', wait_until='networkidle')
        await page.evaluate("""() => {
            if (window.jQuery && jQuery('#baslangicyilSelect').length) {
                jQuery('#baslangicyilSelect').val(jQuery('#baslangicyilSelect option').last().val()).trigger('change');
                jQuery('.tarihFiltreBtn').click();
            }
        }""")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(2)

        items = await page.eval_on_selector_all(
            ".accordion-item, tr, .card, [class*='recete']",
            "els => els.map(e => e.outerHTML)"
        )
        print(f"Total prescription candidate elements: {len(items)}")
        for idx, item in enumerate(items[:5]):
            print(f"--- Recete Element {idx} ---")
            print(item[:1000])

        await b.close()

if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(print_recete_html())
