import asyncio
import json
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright

async def explore_all():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        storage_path = os.path.expanduser('~/.enabiz-ai/session/storage_state.json')
        context = await browser.new_context(storage_state=storage_path)
        page = await context.new_page()

        # 1. Check Tahlillerim with broader date range
        print("=== Checking Tahlillerim ===")
        await page.goto('https://enabiz.gov.tr/Home/Tahlillerim', wait_until='networkidle')
        await asyncio.sleep(2)

        # Inspect the date dropdowns
        selects = await page.eval_on_selector_all(
            "select, .select2, [data-select], input[type='text']",
            "els => els.map(e => ({ id: e.id, name: e.name, class: e.className, options: Array.from(e.querySelectorAll('option')).map(o => ({ val: o.value, text: o.innerText })) }))"
        )
        print("Selects found:", json.dumps(selects, ensure_ascii=False, indent=2))

        # Check if we can select an earlier year or click the date dropdown
        # Look for select elements on page
        page_selects = await page.query_selector_all("select")
        print(f"Number of select elements: {len(page_selects)}")
        for s in page_selects:
            s_id = await s.get_attribute("id")
            s_name = await s.get_attribute("name")
            opts = await s.eval_on_selector_all("option", "opts => opts.map(o => ({ val: o.value, text: o.innerText }))")
            print(f"Select id={s_id} name={s_name}: {opts}")

        # Let's try selecting earliest year in the first select (usually start year)
        if page_selects:
            first_select = page_selects[0]
            # select e.g. 2015 or earliest
            opts = await first_select.eval_on_selector_all("option", "opts => opts.map(o => o.value)")
            if opts:
                earliest = opts[-1] # or earliest year
                print(f"Selecting {earliest} in first select...")
                await first_select.select_option(value=earliest)
                await asyncio.sleep(1)
                # Click 'Ara' button
                ara_btn = await page.query_selector(".tarihFiltreBtn, a:has-text('Ara'), button:has-text('Ara')")
                if ara_btn:
                    print("Clicking Ara button...")
                    await ara_btn.click()
                    await page.wait_for_load_state('networkidle')
                    await asyncio.sleep(3)

        # Re-check content after search
        body_text = await page.inner_text("body")
        lines = [l.strip() for l in body_text.split('\n') if l.strip()]
        print("\nTahlillerim content after filter (first 40 lines):")
        for l in lines[:40]:
            print("  ", l)

        # 2. Check Ziyaretlerim (Doctor Visits)
        print("\n=== Checking Ziyaretlerim ===")
        await page.goto('https://enabiz.gov.tr/Home/Ziyaretlerim', wait_until='networkidle')
        await asyncio.sleep(2)
        z_text = await page.inner_text("body")
        z_lines = [l.strip() for l in z_text.split('\n') if l.strip()]
        for l in z_lines[15:45]:
            print("  ", l)

        # 3. Check Recetelerim (Prescriptions)
        print("\n=== Checking Recetelerim ===")
        await page.goto('https://enabiz.gov.tr/Home/Recetelerim', wait_until='networkidle')
        await asyncio.sleep(2)
        r_text = await page.inner_text("body")
        r_lines = [l.strip() for l in r_text.split('\n') if l.strip()]
        for l in r_lines[15:45]:
            print("  ", l)

        # 4. Check Hastaliklarim (Diagnoses / Diseases)
        print("\n=== Checking Hastaliklarim ===")
        await page.goto('https://enabiz.gov.tr/Home/Hastaliklarim', wait_until='networkidle')
        await asyncio.sleep(2)
        h_text = await page.inner_text("body")
        h_lines = [l.strip() for l in h_text.split('\n') if l.strip()]
        for l in h_lines[15:45]:
            print("  ", l)

        # 5. Check RadyolojikGoruntulerim (Radiology)
        print("\n=== Checking RadyolojikGoruntulerim ===")
        await page.goto('https://enabiz.gov.tr/Home/RadyolojikGoruntulerim', wait_until='networkidle')
        await asyncio.sleep(2)
        rad_text = await page.inner_text("body")
        rad_lines = [l.strip() for l in rad_text.split('\n') if l.strip()]
        for l in rad_lines[15:45]:
            print("  ", l)

        await browser.close()

if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(explore_all())
