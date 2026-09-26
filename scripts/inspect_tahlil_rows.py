import asyncio
import os
import sys
import json

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright

async def inspect_tahlil_details():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        storage_path = os.path.expanduser('~/.enabiz-ai/session/storage_state.json')
        context = await browser.new_context(storage_state=storage_path)
        page = await context.new_page()

        print("Navigating to Tahlillerim...")
        await page.goto('https://enabiz.gov.tr/Home/Tahlillerim', wait_until='networkidle')
        await asyncio.sleep(2)

        # Trigger filter to 2014 so all records show
        await page.evaluate("""() => {
            if (window.jQuery && $('#baslangicyilSelect').length) {
                $('#baslangicyilSelect').val($('#baslangicyilSelect option').last().val()).trigger('change');
                $('.tarihFiltreBtn').click();
            }
        }""")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(3)

        # Let's inspect the DOM elements that represent lab results
        # Look for rows, cards, links with '08.04.2022' or similar
        lab_items = await page.eval_on_selector_all(
            "[class*='tahlil'], [id*='tahlil'], tr, .card, .accordion, .panel, [data-date], [data-id]",
            """els => els.map(e => ({
                tag: e.tagName,
                id: e.id,
                class: e.className,
                text: e.innerText.slice(0, 150).trim(),
                dataId: e.getAttribute('data-id'),
                dataDate: e.getAttribute('data-date')
            }))"""
        )
        print(f"Found {len(lab_items)} candidate elements.")
        for item in lab_items[:30]:
            if item['text'] and any(y in item['text'] for y in ['2022', '2018', '2017', 'Test', 'Tahlil']):
                print(f"<{item['tag']} id='{item['id']}' class='{item['class']}'> -> {repr(item['text'][:80])}")

        # Let's see what happens if we click on '08.04.2022'
        date_el = await page.query_selector("text='08.04.2022'")
        if date_el:
            print("\nFound element with '08.04.2022'! Clicking...")
            await date_el.click()
            await asyncio.sleep(2)

        # Check for any tables or test rows that appeared
        tables = await page.eval_on_selector_all(
            "table",
            """tables => tables.map(t => ({
                id: t.id,
                class: t.className,
                headers: Array.from(t.querySelectorAll('th')).map(th => th.innerText.trim()),
                rows: Array.from(t.querySelectorAll('tr')).slice(0, 5).map(tr => Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim()))
            }))"""
        )
        print(f"\nTables after clicking 08.04.2022: {json.dumps(tables, ensure_ascii=False, indent=2)}")

        # Screenshot the expanded state
        ss_path = os.path.expanduser('~/.enabiz-ai/debug/tahlil_expanded.png')
        await page.screenshot(path=ss_path)
        print(f"Saved expanded screenshot to: {ss_path}")

        await browser.close()

if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(inspect_tahlil_details())
