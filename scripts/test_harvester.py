import asyncio
import os
import sys
import json
import re

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright

async def harvest_test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        storage_path = os.path.expanduser('~/.enabiz-ai/session/storage_state.json')
        context = await browser.new_context(storage_state=storage_path)
        page = await context.new_page()

        harvested_data = {
            "labs": [],
            "prescriptions": [],
            "diagnoses": [],
            "visits": [],
        }

        # ── 1. HARVEST LAB RESULTS (Tahlillerim) ──────────────────────
        print(">>> 1. Harvesting Tahlillerim...")
        await page.goto('https://enabiz.gov.tr/Home/Tahlillerim', wait_until='networkidle')
        await page.evaluate("""() => {
            if (window.jQuery && jQuery('#baslangicyilSelect').length) {
                jQuery('#baslangicyilSelect').val(jQuery('#baslangicyilSelect option').last().val()).trigger('change');
                jQuery('.tarihFiltreBtn').click();
            }
        }""")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(2)

        # Extract all accordion items
        labs_raw = await page.eval_on_selector_all(
            ".accordion-item",
            """items => {
                return items.map(item => {
                    const header = item.querySelector('.accordion-header');
                    const headerText = header ? header.innerText : '';
                    
                    // Extract tests
                    const testEls = Array.from(item.querySelectorAll('.tahlilList'));
                    const tests = testEls.map(t => {
                        const nameEl = t.querySelector('#islemAdi') || t.querySelector('.degerDurumBox span');
                        const isRefDisi = t.querySelector('.refDisi') !== null;
                        
                        let value = '';
                        let unit = '';
                        let refRange = '';
                        
                        const cols = Array.from(t.querySelectorAll('.columnContainer'));
                        cols.forEach(c => {
                            const txt = c.innerText.trim();
                            if (txt.startsWith('Sonuç :')) {
                                value = txt.replace('Sonuç :', '').trim();
                            } else if (txt.startsWith('Sonuç Birimi :')) {
                                unit = txt.replace('Sonuç Birimi :', '').trim();
                            } else if (txt.startsWith('Referans Değeri :')) {
                                refRange = txt.replace('Referans Değeri :', '').trim();
                            }
                        });
                        
                        return {
                            test_name: nameEl ? nameEl.innerText.trim() : 'Unknown',
                            value: value,
                            unit: unit,
                            reference_range: refRange,
                            is_abnormal: isRefDisi
                        };
                    });
                    
                    return {
                        headerText: headerText,
                        tests: tests
                    };
                });
            }"""
        )

        for l in labs_raw:
            # Parse header text for date, hospital
            lines = [x.strip() for x in l["headerText"].split("\n") if x.strip()]
            date_str = ""
            hospital_str = ""
            # e.g. ["8", "Nisan", "2022", "ÖZEL ACIBADEM ADANA HASTANESİ", ...]
            for idx, line in enumerate(lines):
                if any(m in line.lower() for m in ["ocak", "şubat", "subat", "mart", "nisan", "mayıs", "mayis", "haziran", "temmuz", "ağustos", "agustos", "eylül", "eylul", "ekim", "kasım", "kasim", "aralık", "aralik"]):
                    # construct day month year
                    day = lines[idx-1] if idx > 0 else ""
                    month = line
                    year = lines[idx+1] if idx+1 < len(lines) else ""
                    date_str = f"{day} {month} {year}".strip()
                    if idx+2 < len(lines):
                        hospital_str = lines[idx+2]
                    break
            
            report = {
                "date": date_str,
                "hospital": hospital_str,
                "test_count": len(l["tests"]),
                "tests": l["tests"]
            }
            if l["tests"]:
                harvested_data["labs"].append(report)

        print(f"  Harvested {len(harvested_data['labs'])} lab reports with a total of {sum(len(r['tests']) for r in harvested_data['labs'])} tests!")

        # ── 2. HARVEST DIAGNOSES (Hastalıklarım) ──────────────────────
        print(">>> 2. Harvesting Hastalıklarım...")
        await page.goto('https://enabiz.gov.tr/Home/Hastaliklarim', wait_until='networkidle')
        await page.evaluate("""() => {
            if (window.jQuery && jQuery('#baslangicyilSelect').length) {
                jQuery('#baslangicyilSelect').val(jQuery('#baslangicyilSelect option').last().val()).trigger('change');
                jQuery('.tarihFiltreBtn').click();
            }
        }""")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(2)

        diag_rows = await page.eval_on_selector_all(
            "table tbody tr",
            """rows => rows.map(r => {
                const cols = Array.from(r.querySelectorAll('td')).map(td => td.innerText.trim());
                return cols;
            })"""
        )
        for row in diag_rows:
            if len(row) >= 3 and row[0]:
                harvested_data["diagnoses"].append({
                    "date": row[0],
                    "diagnosis": row[1] if len(row) > 1 else "",
                    "clinic": row[2] if len(row) > 2 else "",
                    "doctor": row[3] if len(row) > 3 else "",
                })
        print(f"  Harvested {len(harvested_data['diagnoses'])} diagnosis records!")

        # ── 3. HARVEST PRESCRIPTIONS (Reçetelerim) ──────────────────────
        print(">>> 3. Harvesting Reçetelerim...")
        await page.goto('https://enabiz.gov.tr/Home/Recetelerim', wait_until='networkidle')
        await page.evaluate("""() => {
            if (window.jQuery && jQuery('#baslangicyilSelect').length) {
                jQuery('#baslangicyilSelect').val(jQuery('#baslangicyilSelect option').last().val()).trigger('change');
                jQuery('.tarihFiltreBtn').click();
            }
        }""")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(2)

        rx_rows = await page.eval_on_selector_all(
            "table tbody tr",
            """rows => rows.map(r => {
                const cols = Array.from(r.querySelectorAll('td')).map(td => td.innerText.trim());
                return cols;
            })"""
        )
        for row in rx_rows:
            if len(row) >= 4 and row[0] and not "Kayıtlı bilginiz" in row[0]:
                harvested_data["prescriptions"].append({
                    "date": row[0],
                    "rx_number": row[1] if len(row) > 1 else "",
                    "rx_type": row[2] if len(row) > 2 else "",
                    "doctor": row[3] if len(row) > 3 else "",
                })
        print(f"  Harvested {len(harvested_data['prescriptions'])} prescription records!")

        # ── 4. HARVEST VISITS (Ziyaretlerim) ──────────────────────
        print(">>> 4. Harvesting Ziyaretlerim...")
        await page.goto('https://enabiz.gov.tr/Home/Ziyaretlerim', wait_until='networkidle')
        await page.evaluate("""() => {
            if (window.jQuery && jQuery('#baslangicyilSelect').length) {
                jQuery('#baslangicyilSelect').val(jQuery('#baslangicyilSelect option').last().val()).trigger('change');
                jQuery('.tarihFiltreBtn').click();
            }
        }""")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(2)

        visits_raw = await page.eval_on_selector_all(
            ".zCard, [class*='ziyaret'], .card",
            """cards => cards.map(c => c.innerText.trim())"""
        )
        for v in visits_raw:
            if "Hastane Takip No" in v or "20" in v:
                lines = [l.strip() for l in v.split("\n") if l.strip()]
                harvested_data["visits"].append(" | ".join(lines[:4]))
        print(f"  Harvested {len(harvested_data['visits'])} visit records!")

        # Save to a local json cache for review
        dump_path = os.path.expanduser('~/.enabiz-ai/harvested_health_data.json')
        with open(dump_path, 'w', encoding='utf-8') as f:
            json.dump(harvested_data, f, ensure_ascii=False, indent=2)
        print(f"\nAll health data safely harvested and saved to: {dump_path}")

        # Print summary preview
        print("\n=== SAMPLE HARVESTED LABS ===")
        for r in harvested_data["labs"][:2]:
            print(f"Date: {r['date']} | Hospital: {r['hospital']}")
            for t in r["tests"]:
                flag = "🔴 ABNORMAL" if t["is_abnormal"] else "🟢 Normal"
                print(f"   {t['test_name']}: {t['value']} {t['unit']} (Ref: {t['reference_range']}) [{flag}]")

        print("\n=== SAMPLE DIAGNOSES ===")
        for d in harvested_data["diagnoses"][:4]:
            print(f"Date: {d['date']} | Tanı: {d['diagnosis']} | Klinik: {d['clinic']} | Hekim: {d['doctor']}")

        print("\n=== SAMPLE PRESCRIPTIONS ===")
        for rx in harvested_data["prescriptions"][:4]:
            print(f"Date: {rx['date']} | No: {rx['rx_number']} | Türü: {rx['rx_type']} | Hekim: {rx['doctor']}")

        await browser.close()

if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(harvest_test())
