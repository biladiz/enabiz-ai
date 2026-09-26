import asyncio
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright

async def test_filter():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        storage_path = os.path.expanduser('~/.enabiz-ai/session/storage_state.json')
        context = await browser.new_context(storage_state=storage_path)
        page = await context.new_page()

        # Let's inspect Hastaliklarim first since we saw 25.05.2022
        print("=== Hastaliklarim ===")
        await page.goto('https://enabiz.gov.tr/Home/Hastaliklarim', wait_until='networkidle')
        await asyncio.sleep(2)

        # Trigger Select2 change via JS
        await page.evaluate("""() => {
            if (window.jQuery && $('#baslangicyilSelect').length) {
                $('#baslangicyilSelect').val($('#baslangicyilSelect option').last().val()).trigger('change');
                $('.tarihFiltreBtn').click();
            }
        }""")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(3)

        h_text = await page.inner_text("body")
        for line in [l.strip() for l in h_text.split('\n') if l.strip()]:
            if any(year in line for year in ['201', '202', 'Tanı', 'Hastalık', 'Doktor', 'Hastane']):
                print("  [Hastalık Record]", line)

        # Let's inspect Tahlillerim with jQuery trigger
        print("\n=== Tahlillerim with jQuery filter ===")
        await page.goto('https://enabiz.gov.tr/Home/Tahlillerim', wait_until='networkidle')
        await asyncio.sleep(2)
        await page.evaluate("""() => {
            if (window.jQuery && $('#baslangicyilSelect').length) {
                $('#baslangicyilSelect').val($('#baslangicyilSelect option').last().val()).trigger('change');
                $('.tarihFiltreBtn').click();
            }
        }""")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(3)

        t_text = await page.inner_text("body")
        for line in [l.strip() for l in t_text.split('\n') if l.strip()]:
            if any(k in line for k in ['201', '202', 'Hastane', 'Test', 'Glukoz', 'Hemogram', 'Kayıt', 'Tarih']):
                print("  [Tahlil Record]", line)

        # Let's check Recetelerim with jQuery filter
        print("\n=== Recetelerim with jQuery filter ===")
        await page.goto('https://enabiz.gov.tr/Home/Recetelerim', wait_until='networkidle')
        await asyncio.sleep(2)
        await page.evaluate("""() => {
            if (window.jQuery && $('#baslangicyilSelect').length) {
                $('#baslangicyilSelect').val($('#baslangicyilSelect option').last().val()).trigger('change');
                $('.tarihFiltreBtn').click();
            }
        }""")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(3)

        r_text = await page.inner_text("body")
        for line in [l.strip() for l in r_text.split('\n') if l.strip()]:
            if any(k in line for k in ['201', '202', 'İlaç', 'Reçete', 'mg', 'Doktor']):
                print("  [Reçete Record]", line)

        # Let's check Ziyaretlerim with jQuery filter
        print("\n=== Ziyaretlerim with jQuery filter ===")
        await page.goto('https://enabiz.gov.tr/Home/Ziyaretlerim', wait_until='networkidle')
        await asyncio.sleep(2)
        await page.evaluate("""() => {
            if (window.jQuery && $('#baslangicyilSelect').length) {
                $('#baslangicyilSelect').val($('#baslangicyilSelect option').last().val()).trigger('change');
                $('.tarihFiltreBtn').click();
            }
        }""")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(3)

        z_text = await page.inner_text("body")
        for line in [l.strip() for l in z_text.split('\n') if l.strip()]:
            if any(k in line for k in ['201', '202', 'Hastane', 'Poliklinik', 'Hekim', 'Doktor']):
                print("  [Ziyaret Record]", line)

        await browser.close()

if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(test_filter())
