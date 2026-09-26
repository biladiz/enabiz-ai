import asyncio
import os
import sys
import json

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright

async def inspect_accordion():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        storage_path = os.path.expanduser('~/.enabiz-ai/session/storage_state.json')
        context = await browser.new_context(storage_state=storage_path)
        page = await context.new_page()

        await page.goto('https://enabiz.gov.tr/Home/Tahlillerim', wait_until='networkidle')
        await asyncio.sleep(2)

        # Trigger filter to 2014
        await page.evaluate("""() => {
            if (window.jQuery && $('#baslangicyilSelect').length) {
                $('#baslangicyilSelect').val($('#baslangicyilSelect option').last().val()).trigger('change');
                $('.tarihFiltreBtn').click();
            }
        }""")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(3)

        # Inspect the accordion HTML structure
        accordion_info = await page.eval_on_selector(
            "#accordionTahlilListe",
            """el => {
                const items = Array.from(el.querySelectorAll('.accordion-item, .accordion-header, [id^="flush-tahlil"]'));
                return items.map(item => ({
                    id: item.id,
                    className: item.className,
                    html: item.outerHTML.slice(0, 500)
                }));
            }"""
        )
        print("Accordion structure:")
        for idx, item in enumerate(accordion_info):
            print(f"--- Item {idx} [id={item['id']} class={item['className']}] ---")
            print(item['html'][:300])

        # Click the first accordion button / header
        btn = await page.query_selector("#accordionTahlilListe button.accordion-button, #flush-tahlil1 button, #flush-tahlil1")
        if btn:
            print("\nClicking accordion button...")
            await btn.click()
            await asyncio.sleep(2)

            # Check what's in the expanded body
            collapse_body = await page.eval_on_selector(
                "#accordionTahlilListe .accordion-collapse.show, #accordionTahlilListe .collapse.show, [id^='flush-collapse']",
                "el => el ? el.innerText : 'None'"
            )
            print("\nExpanded Collapse Body Text:\n", collapse_body[:1000])

        await browser.close()

if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(inspect_accordion())
