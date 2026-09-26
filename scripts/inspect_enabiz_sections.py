import asyncio
import json
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright

async def inspect_enabiz():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        storage_path = os.path.expanduser('~/.enabiz-ai/session/storage_state.json')
        context = await browser.new_context(storage_state=storage_path)
        page = await context.new_page()

        print("Navigating to https://enabiz.gov.tr/Home/Index ...")
        await page.goto('https://enabiz.gov.tr/Home/Index', wait_until='networkidle')
        print("Current URL:", page.url)

        # Find all navigation links
        links = await page.eval_on_selector_all(
            "a[href]",
            "elements => elements.map(e => ({ text: e.innerText.trim(), href: e.getAttribute('href') }))"
        )
        print("\n--- Available Navigation Links ---")
        seen = set()
        for link in links:
            t = link['text'].replace('\n', ' ')
            h = link['href']
            if h and not h.startswith('#') and not h.startswith('javascript:') and h not in seen:
                seen.add(h)
                if t or 'Tahlil' in h or 'Recete' in h or 'Radyoloji' in h:
                    print(f"[{t}] -> {h}")

        # Let's inspect Tahlillerim
        print("\nNavigating to Tahlillerim...")
        # Common e-Nabiz URL is /Tahlil/Index or similar
        tahlil_url = "https://enabiz.gov.tr/Tahlil/Index"
        for link in links:
            if "tahlil" in link['href'].lower() or "tahlil" in link['text'].lower():
                if link['href'].startswith('http'):
                    tahlil_url = link['href']
                else:
                    tahlil_url = f"https://enabiz.gov.tr{link['href']}"
                break
        
        print("Visiting Tahlil URL:", tahlil_url)
        await page.goto(tahlil_url, wait_until='networkidle')
        await asyncio.sleep(2)
        print("Tahlil Page URL:", page.url)

        # Screenshot Tahlil
        ss_dir = os.path.expanduser('~/.enabiz-ai/debug')
        os.makedirs(ss_dir, exist_ok=True)
        tahlil_ss = os.path.join(ss_dir, 'tahlil_page.png')
        await page.screenshot(path=tahlil_ss)
        print(f"Saved Tahlil screenshot to: {tahlil_ss}")

        # Let's get page text summary
        body_text = await page.inner_text("body")
        lines = [line.strip() for line in body_text.split('\n') if line.strip()]
        print(f"\nTahlil page text snippet (first 30 non-empty lines):\n" + "\n".join(lines[:30]))

        # Check for tables or accordion items
        tables = await page.query_selector_all("table")
        print(f"\nNumber of <table> elements found: {len(tables)}")
        
        # Check for card/accordion items
        cards = await page.query_selector_all(".card, .panel, .accordion, .timeline, tr")
        print(f"Number of cards/rows found: {len(cards)}")

        await browser.close()

if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(inspect_enabiz())
