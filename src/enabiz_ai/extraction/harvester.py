"""Automated data harvester for e-Nabız portal sections.

Harvests structured records directly from e-Nabız pages:
- Tahlillerim (Lab Results & Individual Tests)
- Hastalıklarım (Diagnoses & ICD Codes)
- Reçetelerim (Prescriptions & Doctors)
- Ziyaretlerim (Hospital Visits & Clinics)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import Page

from enabiz_ai.exceptions import DateParseError
from enabiz_ai.extraction.models import LabReport, LabTest, Prescription
from enabiz_ai.storage.database import HealthDatabase

logger = logging.getLogger(__name__)

MONTH_MAP = {
    "ocak": "01", "şubat": "02", "subat": "02", "mart": "03", "nisan": "04",
    "mayıs": "05", "mayis": "05", "haziran": "06", "temmuz": "07", "ağustos": "08",
    "agustos": "08", "eylül": "09", "eylul": "09", "ekim": "10", "kasım": "11",
    "kasim": "11", "aralık": "12", "aralik": "12"
}


def parse_turkish_date(date_str: str, default: datetime | None = None) -> datetime:
    """Parse Turkish date representations into standard datetime objects.

    Raises:
        DateParseError: If the date cannot be parsed and no default is provided.
    """
    clean = date_str.strip().lower()
    if not clean:
        if default is not None:
            return default
        raise DateParseError("Date string is empty")

    # Try DD.MM.YYYY
    if "." in clean:
        parts = clean.split()[0].split(".")
        if len(parts) == 3:
            try:
                day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                return datetime(year, month, day)
            except ValueError:
                pass

    # Try DD/MM/YYYY
    if "/" in clean:
        parts = clean.split()[0].split("/")
        if len(parts) == 3:
            try:
                day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                return datetime(year, month, day)
            except ValueError:
                pass

    # Try "8 Nisan 2022"
    tokens = clean.split()
    if len(tokens) >= 3 and tokens[1] in MONTH_MAP:
        try:
            day = int(tokens[0])
            month = int(MONTH_MAP[tokens[1]])
            year = int(tokens[2])
            return datetime(year, month, day)
        except ValueError:
            pass

    if default is not None:
        logger.warning("Could not parse Turkish date '%s', using provided default: %s", date_str, default)
        return default

    raise DateParseError(f"Could not parse Turkish date '{date_str}'")


class ENabizHarvester:
    """High-speed structured data harvester for the authenticated e-Nabız portal."""

    def __init__(self, db: HealthDatabase) -> None:
        self.db = db

    async def _apply_earliest_date_filter(self, page: Page) -> None:
        """Expand date filter to retrieve all historical records back to earliest year."""
        try:
            await page.evaluate("""() => {
                if (window.jQuery && jQuery('#baslangicyilSelect').length) {
                    const earliest = jQuery('#baslangicyilSelect option').last().val();
                    if (earliest) {
                        jQuery('#baslangicyilSelect').val(earliest).trigger('change');
                        jQuery('.tarihFiltreBtn').click();
                    }
                }
            }""")
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
            await asyncio.sleep(2)
        except Exception as e:
            logger.debug("Could not apply Select2 date filter: %s", e)

    async def harvest_labs(self, page: Page) -> int:
        """Harvest all lab reports and individual test markers."""
        logger.info("Harvesting Tahlillerim...")
        await page.goto("https://enabiz.gov.tr/Home/Tahlillerim", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        await self._apply_earliest_date_filter(page)

        labs_raw = await page.eval_on_selector_all(
            ".accordion-item",
            """items => items.map(item => {
                const header = item.querySelector('.accordion-header');
                const headerText = header ? header.innerText : '';
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
                        if (txt.startsWith('Sonuç :')) value = txt.replace('Sonuç :', '').trim();
                        else if (txt.startsWith('Sonuç Birimi :')) unit = txt.replace('Sonuç Birimi :', '').trim();
                        else if (txt.startsWith('Referans Değeri :')) refRange = txt.replace('Referans Değeri :', '').trim();
                    });
                    return {
                        test_name: nameEl ? nameEl.innerText.trim() : 'Unknown',
                        value: value,
                        unit: unit,
                        reference_range: refRange,
                        is_abnormal: isRefDisi
                    };
                });
                return { headerText: headerText, tests: tests };
            })"""
        )

        saved_count = 0
        for item in labs_raw:
            if not item["tests"]:
                continue

            lines = [x.strip() for x in item["headerText"].split("\n") if x.strip()]
            date_str = ""
            hospital_str = ""
            for idx, line in enumerate(lines):
                if any(m in line.lower() for m in MONTH_MAP):
                    day = lines[idx - 1] if idx > 0 else ""
                    month = line
                    year = lines[idx + 1] if idx + 1 < len(lines) else ""
                    date_str = f"{day} {month} {year}".strip()
                    if idx + 2 < len(lines):
                        hospital_str = lines[idx + 2]
                    break

            try:
                report_date = parse_turkish_date(date_str)
            except DateParseError:
                logger.warning("Skipping lab report with invalid date '%s'", date_str)
                continue

            h_hash = hashlib.sha256(hospital_str.encode("utf-8")).hexdigest()[:12]
            report_id = f"lab_{report_date:%Y%m%d}_{h_hash}"

            tests = []
            for t in item["tests"]:
                tname = t["test_name"].split("\n")[0].replace("Bu İşlem Bana Ait Değil", "").strip()
                tests.append(LabTest(
                    test_name=tname,
                    value=t["value"],
                    unit=t["unit"],
                    reference_range=t["reference_range"],
                    is_abnormal=t["is_abnormal"],
                    notes="Referans Dışı" if t["is_abnormal"] else "Normal",
                ))

            report = LabReport(
                report_id=report_id,
                date=report_date,
                hospital=hospital_str,
                tests=tests,
            )

            if await self.db.save_lab_report(report):
                saved_count += 1

        logger.info("Harvested %d new lab reports", saved_count)
        return saved_count

    async def harvest_diagnoses(self, page: Page) -> int:
        """Harvest diagnoses and ICD classifications."""
        logger.info("Harvesting Hastalıklarım...")
        await page.goto("https://enabiz.gov.tr/Home/Hastaliklarim", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        await self._apply_earliest_date_filter(page)

        diag_rows = await page.eval_on_selector_all(
            "table tbody tr",
            """rows => rows.map(r => Array.from(r.querySelectorAll('td')).map(td => td.innerText.trim()))"""
        )

        saved = 0
        for row in diag_rows:
            if len(row) >= 2 and row[0] and "Kayıtlı bilginiz" not in row[0]:
                date_val = row[0]
                diag_val = row[1]
                clinic_val = row[2] if len(row) > 2 else ""
                doctor_val = row[3] if len(row) > 3 else ""

                if await self.db.save_diagnosis(date_val, diag_val, clinic_val, doctor_val):
                    saved += 1

        logger.info("Harvested %d new diagnoses", saved)
        return saved

    async def harvest_prescriptions(self, page: Page) -> int:
        """Harvest prescriptions and medications."""
        logger.info("Harvesting Reçetelerim...")
        await page.goto("https://enabiz.gov.tr/Home/Recetelerim", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        await self._apply_earliest_date_filter(page)

        rx_rows = await page.eval_on_selector_all(
            "table tbody tr",
            """rows => rows.map(r => Array.from(r.querySelectorAll('td')).map(td => td.innerText.trim()))"""
        )

        saved = 0
        for row in rx_rows:
            if len(row) >= 4 and row[0] and "Kayıtlı bilginiz" not in row[0]:
                date_val = row[0]
                rx_no = row[1]
                rx_type = row[2]
                doctor = row[3]

                rx_obj = Prescription(
                    prescription_id=f"rx_{rx_no}",
                    date=parse_turkish_date(date_val),
                    medication=f"Reçete {rx_no} ({rx_type})",
                    prescriber=doctor,
                    frequency=rx_type,
                )

                if await self.db.save_prescription(rx_obj):
                    saved += 1

        logger.info("Harvested %d new prescriptions", saved)
        return saved

    async def harvest_visits(self, page: Page) -> int:
        """Harvest doctor and clinic visits."""
        logger.info("Harvesting Ziyaretlerim...")
        await page.goto("https://enabiz.gov.tr/Home/Ziyaretlerim", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        await self._apply_earliest_date_filter(page)

        visits_raw = await page.eval_on_selector_all(
            ".zCard, [class*='ziyaret'], .card",
            "cards => cards.map(c => c.innerText.trim())"
        )

        saved = 0
        for v in visits_raw:
            if "Hastane Takip No" in v or "20" in v:
                lines = [l.strip() for l in v.split("\n") if l.strip()]
                date_val = lines[0] if lines else ""
                tracking = ""
                for l in lines:
                    if "Takip No:" in l:
                        tracking = l.split("Takip No:")[-1].strip()
                        break
                hosp = lines[1] if len(lines) > 1 else ""

                if await self.db.save_visit(
                    date=date_val,
                    hospital=hosp,
                    tracking_no=tracking or None,
                    raw_details=" | ".join(lines[:4])
                ):
                    saved += 1

        logger.info("Harvested %d new doctor visits", saved)
        return saved

    async def harvest_all(self, page: Page) -> dict[str, int]:
        """Execute full harvest across all medical sections."""
        results = {
            "labs": await self.harvest_labs(page),
            "diagnoses": await self.harvest_diagnoses(page),
            "prescriptions": await self.harvest_prescriptions(page),
            "visits": await self.harvest_visits(page),
        }
        await self.db.record_sync("all", records_synced=sum(results.values()))
        return results
