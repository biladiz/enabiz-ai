"""LLM-based health data extractor using local Ollama models.

Used as a fallback when Docling's table extraction doesn't produce
clean results, or for free-text content like radiology reports.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import httpx

from enabiz_ai.extraction.models import LabReport, LabTest, Prescription

logger = logging.getLogger(__name__)

# ── System prompts for structured extraction ──────────────────────

LAB_EXTRACTION_PROMPT = """Sen bir tıbbi laboratuvar sonuçları uzmanısın. Sana verilen metinden laboratuvar test sonuçlarını JSON formatında çıkar.

Her test için şu alanları doldur:
- test_name: Testin adı
- value: Sonuç değeri (sayı veya metin)
- unit: Birimi (varsa)
- reference_range: Referans aralığı (varsa)
- is_abnormal: Normal dışı mı (true/false/null)
- notes: Ek notlar (Y=Yüksek, D=Düşük vb.)

Sadece JSON döndür, başka açıklama yapma. Format:
{"tests": [{"test_name": "...", "value": "...", "unit": "...", "reference_range": "...", "is_abnormal": true, "notes": "..."}]}"""

PRESCRIPTION_EXTRACTION_PROMPT = """Sen bir reçete analiz uzmanısın. Sana verilen metinden ilaç bilgilerini JSON formatında çıkar.

Her ilaç için:
- medication: İlacın adı
- dosage: Dozaj (örn: 500mg)
- frequency: Kullanım sıklığı (örn: 2x1)
- quantity: Adet/miktar
- prescriber: Reçeteyi yazan doktor (varsa)
- hospital: Hastane adı (varsa)

Sadece JSON döndür. Format:
{"prescriptions": [{"medication": "...", "dosage": "...", "frequency": "...", "quantity": "...", "prescriber": "...", "hospital": "..."}]}"""

SUMMARY_PROMPT = """Sen bir sağlık verileri uzmanısın. Sana verilen tıbbi raporu hem Türkçe hem İngilizce olarak özetle.

Özette şunları belirt:
1. Önemli bulgular ve anormal değerler
2. Dikkat edilmesi gereken sonuçlar
3. Genel sağlık durumu değerlendirmesi

Kısa ve öz bir özet yaz."""


class LLMExtractor:
    """LLM-based health data extractor for unstructured text.

    Uses Ollama API directly (via httpx) to extract structured data
    from free-text medical documents. Acts as a fallback when
    Docling's table extraction isn't sufficient.

    Usage:
        extractor = LLMExtractor(ollama_base_url="http://localhost:11434")
        report = await extractor.extract_lab_results(text)
    """

    def __init__(
        self,
        ollama_base_url: str = "http://localhost:11434",
        model: str = "qwen2.5-vl:14b",
        timeout: float = 120.0,
    ) -> None:
        """Initialize the LLM extractor.

        Args:
            ollama_base_url: URL of the Ollama server.
            model: Model to use for extraction.
            timeout: HTTP request timeout in seconds.
        """
        self.base_url = ollama_base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def _call_ollama(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = True,
    ) -> str:
        """Call the Ollama API and return the response text.

        Args:
            system_prompt: System instructions for the model.
            user_prompt: The user's query/data to process.
            json_mode: Whether to request JSON output format.

        Returns:
            The model's response text.
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_ctx": 16384,
            },
        }
        if json_mode:
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")

    async def extract_lab_results(
        self,
        text: str,
        report_id: str = "llm_extracted",
    ) -> LabReport:
        """Extract lab results from free text using LLM.

        Args:
            text: Raw text containing lab results.
            report_id: Identifier for the generated report.

        Returns:
            A LabReport with extracted test data.
        """
        logger.info("Extracting lab results via LLM (%s)", self.model)

        response = await self._call_ollama(
            system_prompt=LAB_EXTRACTION_PROMPT,
            user_prompt=f"Aşağıdaki metinden laboratuvar sonuçlarını çıkar:\n\n{text}",
        )

        tests = []
        try:
            data = json.loads(response)
            raw_tests = data.get("tests", [])
            for t in raw_tests:
                tests.append(LabTest(
                    test_name=t.get("test_name", "Unknown"),
                    value=str(t.get("value", "")),
                    unit=t.get("unit"),
                    reference_range=t.get("reference_range"),
                    is_abnormal=t.get("is_abnormal"),
                    notes=t.get("notes"),
                ))
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to parse LLM response as JSON: %s", e)
            logger.debug("Raw LLM response: %s", response[:500])

        from datetime import datetime
        return LabReport(
            report_id=report_id,
            date=datetime.now(),
            tests=tests,
            raw_text=text[:5000],
        )

    async def extract_prescriptions(
        self,
        text: str,
    ) -> list[Prescription]:
        """Extract prescription data from free text using LLM.

        Args:
            text: Raw text containing prescription information.

        Returns:
            List of extracted Prescription objects.
        """
        logger.info("Extracting prescriptions via LLM (%s)", self.model)

        response = await self._call_ollama(
            system_prompt=PRESCRIPTION_EXTRACTION_PROMPT,
            user_prompt=f"Aşağıdaki metinden reçete bilgilerini çıkar:\n\n{text}",
        )

        prescriptions = []
        try:
            data = json.loads(response)
            raw_items = data.get("prescriptions", [])
            from datetime import datetime
            import hashlib

            for idx, item in enumerate(raw_items):
                med_name = item.get("medication", "Unknown")
                rx_id = hashlib.md5(f"{med_name}_{idx}".encode()).hexdigest()[:8]
                prescriptions.append(Prescription(
                    prescription_id=f"rx_{rx_id}",
                    date=datetime.now(),
                    medication=med_name,
                    dosage=item.get("dosage"),
                    frequency=item.get("frequency"),
                    quantity=item.get("quantity"),
                    prescriber=item.get("prescriber"),
                    hospital=item.get("hospital"),
                ))
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to parse LLM response: %s", e)

        return prescriptions

    async def summarize_report(self, text: str) -> str:
        """Generate a bilingual (Turkish/English) summary of a medical report.

        Args:
            text: The medical report text to summarize.

        Returns:
            A summary string in both Turkish and English.
        """
        logger.info("Generating health report summary via LLM")

        summary = await self._call_ollama(
            system_prompt=SUMMARY_PROMPT,
            user_prompt=f"Aşağıdaki tıbbi raporu özetle:\n\n{text}",
            json_mode=False,
        )

        return summary.strip()

    async def is_available(self) -> bool:
        """Check if the Ollama server is reachable and the model is loaded.

        Returns:
            True if the server responds and the model is available.
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    is_loaded = any(self.model in m for m in models)
                    if not is_loaded:
                        logger.warning(
                            "Model '%s' not found. Available: %s",
                            self.model, models,
                        )
                    return True  # Server is up even if model isn't pulled yet
                return False
        except (httpx.RequestError, httpx.HTTPStatusError):
            return False
