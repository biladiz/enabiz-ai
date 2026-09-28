"""RAG Clinical Reasoning and Medical Analysis Engine.

Retrieves longitudinal patient records from SQLite, groups biomarker trends over time,
correlates abnormal values with medical diagnoses, and synthesizes a comprehensive
weekly clinical evaluation report using the local LLM running on the DGX Spark.
"""

from __future__ import annotations

import html
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from enabiz_ai.storage.database import HealthDatabase
from enabiz_ai.storage.repository import HealthRepository

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Sen uzman bir Klinik Biyokimya ve Dahiliye hekimi gibi davranan, hastaya şefkatli, net, anlaşılır ve güven verici dille bilgi aktaran bir Yapay Zeka Medikal Asistanısın.

Görevin:
Sana sunulan e-Nabız sağlık geçmişi kayıtlarını (tahliller, tanılar, reçeteler, trendler) analiz ederek hastaya yönelik kapsamlı, net ve eyleme dönüştürülebilir bir "Haftalık Sağlık ve Klinik Değerlendirme Raporu" oluşturmak.

Rapor Formatı:
1. 🩺 **Genel Sağlık Durumu Özeti**: Hastanın genel tablosunu 2-3 cümleyle özetle.
2. 🚨 **Dikkat Çeken Değerler ve Klinik Korelasyon**:
   - Normal dışı çıkan tahlil sonuçlarını ve bunların ilişkili olduğu tıbbi tanıları klinik olarak birbiriyle ilişkilendirip anlaşılır dilde açıkla.
3. 📈 **Zaman İçindeki Trendler**:
   - Geçmiş yıllardaki testlerle son durum arasındaki değişimi karşılaştır (örn: karaciğer enzimleri veya kan şekeri değişimleri).
4. 💊 **Tedavi ve İlaç Takibi**: Reçeteler ve klinik takiplere dair gözlemler.
5. 🍏 **Önleyici Yaşam Tarzı ve Hekim Önerileri**:
   - İlgili organ sistemleri için beslenme, hidrasyon ve egzersiz tavsiyeleri.
   - Bir sonraki hekim kontrolünde doktora sorulabilecek kritik sorular ve yaptırılması tavsiye edilen takip testleri.

Önemli Kural: Tıbbi teşhis yerine geçmediğini, bunun bir AI destekli bilgilendirme olduğunu ve kesin kararların takip eden hekime ait olduğunu nazikçe belirt. Yanıtını şık Telegram formatında (emojiler, kalın başlıklar, madde işaretleri) Türkçe olarak üret."""


class RAGEngine:
    """Clinical RAG engine for patient health summaries and longitudinal analysis."""

    def __init__(
        self,
        db: HealthRepository | HealthDatabase,
        ollama_base_url: str = "http://localhost:11434",
        model: str = "deepseek-r1:70b",
        timeout: float = 180.0,
    ) -> None:
        self.db = db
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def build_patient_context(self) -> str:
        """Query SQLite database and construct the structured clinical context."""
        lab_reports = await self.db.get_lab_reports()
        diagnoses = await self.db.get_diagnoses()
        prescriptions = await self.db.get_prescriptions()
        visits = await self.db.get_visits()

        context_lines: list[str] = ["## HASTANIN TIBBİ GEÇMİŞİ VE E-NABIZ KAYITLARI\n"]

        # 1. Abnormal tests
        abnormal_items = []
        marker_history: dict[str, list[dict]] = defaultdict(list)

        for report in lab_reports:
            rdate = report.date.strftime("%Y-%m-%d")
            for t in report.tests:
                if t.is_abnormal:
                    abnormal_items.append({
                        "date": rdate,
                        "hospital": report.hospital,
                        "test": t.test_name,
                        "value": t.value,
                        "unit": t.unit or "",
                        "ref": t.reference_range or "",
                    })
                marker_history[t.test_name].append({
                    "date": rdate,
                    "value": t.value,
                    "unit": t.unit or "",
                    "is_abnormal": t.is_abnormal,
                })

        context_lines.append("### 1. ANORMAL / REFERANS DIŞI TAHLİL DEĞERLERİ:")
        if abnormal_items:
            for a in abnormal_items:
                context_lines.append(
                    f"- Tarih: {a['date']} | Test: {a['test']} | Sonuç: {a['value']} {a['unit']} "
                    f"(Referans: {a['ref']}) [🔴 REFERANS DIŞI]"
                )
        else:
            context_lines.append("Referans dışı değer saptanmadı.")

        # 2. Key Biomarker Trends
        context_lines.append("\n### 2. ZAMAN İÇİNDEKİ TEST KARŞILAŞTIRMALARI (TRENDLER):")
        multi_year_markers = {k: v for k, v in marker_history.items() if len(v) > 1}
        if multi_year_markers:
            for marker, records in multi_year_markers.items():
                sorted_recs = sorted(records, key=lambda x: x["date"])
                trend_str = " -> ".join([f"{r['date']}: {r['value']} {r['unit']}" for r in sorted_recs])
                context_lines.append(f"- **{marker}**: {trend_str}")
        else:
            # If few repeat tests, show all recent tests
            for report in lab_reports[:2]:
                context_lines.append(f"• Tahlil: {report.date:%Y-%m-%d} ({report.hospital})")
                for t in report.tests:
                    flag = "[🔴 ABNORMAL]" if t.is_abnormal else "[Normal]"
                    context_lines.append(f"   - {t.test_name}: {t.value} {t.unit or ''} (Ref: {t.reference_range or ''}) {flag}")

        # 3. Diagnoses
        context_lines.append("\n### 3. TANI VE HASTALIK KAYITLARI:")
        if diagnoses:
            for d in diagnoses:
                context_lines.append(f"- {d['date']}: {d['diagnosis']} | Klinik: {d.get('clinic', '-')} | Hekim: {d.get('doctor', '-')}")
        else:
            context_lines.append("Kayıtlı tanı bulunmamaktadır.")

        # 4. Prescriptions
        context_lines.append("\n### 4. REÇETE VE İLAÇ KAYITLARI:")
        if prescriptions:
            for rx in prescriptions:
                context_lines.append(f"- {rx.date:%Y-%m-%d}: {rx.medication} | Hekim: {rx.prescriber or '-'}")
        else:
            context_lines.append("Kayıtlı reçete bulunmamaktadır.")

        return "\n".join(context_lines)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        reraise=True,
    )
    async def generate_weekly_report(self, person_name: str = "Hasta") -> str:
        """Perform RAG synthesis via local LLM on DGX Spark."""
        context = await self.build_patient_context()
        logger.info("Sending RAG clinical context to Ollama (%s) for %s", self.model, person_name)

        user_prompt = (
            f"Kişi/Hasta: {person_name}\n"
            f"Aşağıdaki e-Nabız sağlık geçmişi verilerini ({person_name} için) analiz ederek "
            f"haftalık klinik değerlendirme raporunu hazırla:\n\n{context}"
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_ctx": 16384,
            },
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.ollama_base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            raw_content = data.get("message", {}).get("content", "").strip()

        # Handle DeepSeek-R1 <think> chain-of-thought block if present
        if "<think>" in raw_content and "</think>" in raw_content:
            parts = raw_content.split("</think>", 1)
            reasoning = parts[0].replace("<think>", "").strip()
            report_text = parts[1].strip()
            logger.info("DeepSeek-R1 diagnostic reasoning captured (%d characters)", len(reasoning))
        elif "</think>" in raw_content:
            report_text = raw_content.split("</think>", 1)[1].strip()
        else:
            report_text = raw_content

        return report_text

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        reraise=True,
    )
    async def ask_question(
        self,
        question: str,
        person_name: str = "Genel",
    ) -> str:
        """Answer a natural language health question based on patient's records."""
        context = await self.build_patient_context()

        system_prompt = (
            "Sen e-Nabız AI klinik asistanısın. Sana sunulan hastanın tıbbi geçmişi, laboratuvar tahlilleri, "
            "reçeteleri ve doktor teşhislerine dayanarak kullanıcının sorusunu doğrudan, tıbbi açıdan doğru, "
            "anlaşılır ve şık bir Türkçe ile yanıtla. Tahlil değerlerini tarihleriyle birlikte karşılaştır. "
            "Önemli Kural: Tıbbi teşhis yerine geçmediğini, bunun bir AI destekli bilgilendirme olduğunu ve "
            "kesin kararların takip eden hekime ait olduğunu nazikçe belirt."
        )

        user_prompt = f"{context}\n\n## KULLANICININ SORUSU ({person_name}):\n{question}\n\nLütfen hastanın verilerine dayanarak soruyu detaylı ve anlaşılır şekilde yanıtla:"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_ctx": 16384,
            },
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.ollama_base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            raw_content = data.get("message", {}).get("content", "").strip()

        # Handle DeepSeek-R1 <think> chain-of-thought block if present
        if "<think>" in raw_content and "</think>" in raw_content:
            parts = raw_content.split("</think>", 1)
            reasoning = parts[0].replace("<think>", "").strip()
            answer_text = parts[1].strip()
            logger.info("DeepSeek-R1 Q&A reasoning captured (%d characters)", len(reasoning))
        elif "</think>" in raw_content:
            answer_text = raw_content.split("</think>", 1)[1].strip()
        else:
            answer_text = raw_content

        return answer_text

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        reraise=True,
    )
    async def send_to_telegram(self, report_text: str, bot_token: str, chat_id: str, person_name: str = "Genel") -> bool:
        """Send formatted report chunks to user's Telegram."""
        if not bot_token or not chat_id:
            logger.warning("Telegram bot credentials not configured")
            return False

        telegram_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        # Sanitize LLM-generated text to prevent HTML injection
        safe_text = html.escape(report_text)
        safe_person = html.escape(person_name)

        chunks: list[str] = []
        curr = ""
        for line in safe_text.split("\n"):
            if len(curr) + len(line) + 1 > 3800:
                chunks.append(curr)
                curr = line + "\n"
            else:
                curr += line + "\n"
        if curr:
            chunks.append(curr)

        async with httpx.AsyncClient(timeout=30.0) as client:
            for idx, chunk in enumerate(chunks):
                header = f"🏥 <b>e-Nabız AI — Haftalık Klinik Değerlendirme Raporu ({safe_person})</b>\n\n" if idx == 0 else ""
                await client.post(telegram_url, json={
                    "chat_id": chat_id,
                    "text": header + chunk,
                    "parse_mode": "HTML",
                })

        logger.info("Clinical report dispatched to Telegram chat %s for %s", chat_id, person_name)
        return True
