import asyncio
import json
import os
import sys
from datetime import datetime
import httpx

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MONTH_MAP = {
    "ocak": "01", "şubat": "02", "subat": "02", "mart": "03", "nisan": "04",
    "mayıs": "05", "mayis": "05", "haziran": "06", "temmuz": "07", "ağustos": "08",
    "agustos": "08", "eylül": "09", "eylul": "09", "ekim": "10", "kasım": "11",
    "kasim": "11", "aralık": "12", "aralik": "12"
}

def parse_tr_date(date_str: str) -> str:
    parts = date_str.lower().split()
    if len(parts) >= 3 and parts[1] in MONTH_MAP:
        day = parts[0].zfill(2)
        month = MONTH_MAP[parts[1]]
        year = parts[2]
        return f"{year}-{month}-{day}"
    return date_str

async def run_rag_analysis():
    # 1. Load harvested health data
    json_path = os.path.expanduser('~/.enabiz-ai/harvested_health_data.json')
    if not os.path.exists(json_path):
        print("Harvested data file not found:", json_path)
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print("=== Loaded Harvested Health Data ===")
    print(f"Lab reports: {len(data['labs'])}")
    print(f"Diagnoses: {len(data['diagnoses'])}")
    print(f"Prescriptions: {len(data['prescriptions'])}")
    print(f"Visits: {len(data['visits'])}")

    # 2. Build structured RAG medical context
    # Clean up test names and abnormal items
    clean_labs = []
    abnormal_items = []
    marker_history = {}

    for report in data["labs"]:
        clean_date = parse_tr_date(report["date"])
        hosp = report.get("hospital", "Bilinmeyen Hastane")
        report_tests = []
        for t in report["tests"]:
            name = t["test_name"].split("\n")[0].strip()
            # remove "Bu İşlem Bana Ait Değil" if attached
            name = name.replace("Bu İşlem Bana Ait Değil", "").strip()
            val = t["value"].strip()
            unit = t.get("unit", "").strip()
            ref = t.get("reference_range", "").strip()
            is_abn = t.get("is_abnormal", False)

            test_obj = {
                "name": name,
                "value": val,
                "unit": unit,
                "reference": ref,
                "is_abnormal": is_abn,
                "date": clean_date,
                "hospital": hosp
            }
            report_tests.append(test_obj)

            if is_abn:
                abnormal_items.append(test_obj)

            # Track marker trends over time
            if name not in marker_history:
                marker_history[name] = []
            marker_history[name].append({"date": clean_date, "value": val, "unit": unit})

        clean_labs.append({
            "date": clean_date,
            "hospital": hosp,
            "tests": report_tests
        })

    # Prepare Context Prompt for Ollama
    context_lines = []
    context_lines.append("## HASTANIN TIBBİ GEÇMİŞİ VE E-NABIZ KAYITLARI\n")

    context_lines.append("### 1. ANORMAL / REFERANS DIŞI TAHLİL DEĞERLERİ:")
    if abnormal_items:
        for a in abnormal_items:
            context_lines.append(f"- Tarih: {a['date']} | Test: {a['name']} | Sonuç: {a['value']} {a['unit']} (Referans: {a['reference']}) [🔴 REFERANS DIŞI]")
    else:
        context_lines.append("Referans dışı değer saptanmadı.")

    context_lines.append("\n### 2. TÜM TAHLİL RAPORLARI VE TESTLER:")
    for rep in clean_labs:
        context_lines.append(f"• Tahlil Tarihi: {rep['date']} ({rep['hospital']})")
        for t in rep["tests"]:
            flag = "[🔴 ABNORMAL]" if t["is_abnormal"] else "[Normal]"
            context_lines.append(f"   - {t['name']}: {t['value']} {t['unit']} (Ref: {t['reference']}) {flag}")

    context_lines.append("\n### 3. TANI VE HASTALIK KAYITLARI (Tanı Kodları):")
    seen_diag = set()
    for d in data["diagnoses"]:
        d_str = f"- {d['date']}: {d['diagnosis']} | Klinik: {d['clinic']} | Hekim: {d['doctor']}"
        if d_str not in seen_diag:
            seen_diag.add(d_str)
            context_lines.append(d_str)

    context_lines.append("\n### 4. REÇETE VE İLAÇ GEÇMİŞİ:")
    for rx in data["prescriptions"]:
        context_lines.append(f"- {rx['date']}: Reçete No: {rx['rx_number']} ({rx['rx_type']}) | Hekim: {rx['doctor']}")

    context_text = "\n".join(context_lines)

    system_prompt = """Sen uzman bir Klinik Biyokimya ve Dahiliye hekimi gibi davranan, hastaya şefkatli, net, anlaşılır ve güven verici dille bilgi aktaran bir Yapay Zeka Medikal Asistanısın.

Görevin:
Sana sunulan e-Nabız sağlık geçmişi kayıtlarını (tahliller, tanılar, reçeteler, trendler) analiz ederek hastaya yönelik kapsamlı, net ve eyleme dönüştürülebilir bir "Haftalık Sağlık ve Klinik Değerlendirme Raporu" oluşturmak.

Rapor Formatı:
1. 🩺 **Genel Sağlık Durumu Özeti**: Hastanın genel tablosunu 2-3 cümleyle özetle.
2. 🚨 **Dikkat Çeken Değerler ve Klinik Korelasyon**:
   - Normal dışı çıkan tahlil sonuçlarını (örn: Karaciğer enzimi ALT yüksekliği 53 IU/L, Açlık Glukoz 101 mg/dL) ve bunların ilişkili olduğu tanıları (örn: Gastroenteroloji'deki K76.0 Yağlı Karaciğer tanısı) klinik olarak birbiriyle ilişkilendirip anlaşılır dilde açıkla.
3. 📈 **Zaman İçindeki Trendler**:
   - Geçmiş yıllardaki testlerle (örn: 2018 vs 2022) son durum arasındaki değişimi karşılaştır (örn: karaciğer enzimleri normalden yüksek seviyeye çıkmış mı?).
4. 💊 **Tedavi ve İlaç Notları**: Reçeteler ve klinik takiplere dair gözlemler.
5. 🍏 **Önleyici Yaşam Tarzı ve Hekim Önerileri**:
   - Karaciğer yağlanması ve kan şekeri dengesi için beslenme, egzersiz tavsiyeleri.
   - Bir sonraki hekim kontrolünde doktora sorulabilecek kritik sorular ve yaptırılması faydalı testler (örn: Kontrol Karaciğer Paneli ALT/AST/GGT, Lipid profili, HbA1c takibi).

Önemli Kural: Tıbbi teşhis yerine geçmediğini, bunun bir AI destekli bilgilendirme olduğunu ve kesin kararların takip eden hekime ait olduğunu nazikçe belirt. Yanıtını şık Telegram formatında (emojiler, kalın başlıklar, madde işaretleri) Türkçe olarak üret."""

    print("\n--- Sending Context to DGX Spark Ollama (qwen2.5:7b) ---")
    ollama_url = "http://100.73.171.33:11434/api/chat"
    payload = {
        "model": "qwen2.5:7b",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Aşağıdaki e-Nabız sağlık verilerimi analiz ederek haftalık klinik değerlendirme raporumu hazırla:\n\n{context_text}"}
        ],
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_ctx": 16384
        }
    }

    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(ollama_url, json=payload)
        resp.raise_for_status()
        res_data = resp.json()
        analysis_report = res_data.get("message", {}).get("content", "")

    print("\n================ CLINICAL AI ANALYSIS REPORT ================\n")
    print(analysis_report)
    print("\n============================================================\n")

    # Save analysis report locally
    report_file = os.path.expanduser('~/.enabiz-ai/latest_clinical_report.md')
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(analysis_report)
    print(f"Saved clinical report to: {report_file}")

    # 3. Send report to Telegram
    from enabiz_ai.config import config
    bot_token = config.telegram_bot_token
    chat_id = config.telegram_chat_id

    if bot_token and chat_id:
        print(f"\nDispatching report to Telegram (@onur_enabiz_bot, Chat: {chat_id})...")
        telegram_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        # Telegram max message length is 4096 chars, split if needed
        chunks = []
        curr = ""
        for line in analysis_report.split("\n"):
            if len(curr) + len(line) + 1 > 3800:
                chunks.append(curr)
                curr = line + "\n"
            else:
                curr += line + "\n"
        if curr:
            chunks.append(curr)

        async with httpx.AsyncClient(timeout=30.0) as client:
            for idx, chunk in enumerate(chunks):
                header = "🏥 <b>e-Nabız AI — Haftalık Klinik Değerlendirme Raporu</b>\n\n" if idx == 0 else ""
                # Replace markdown bold with HTML bold or send markdown
                await client.post(telegram_url, json={
                    "chat_id": chat_id,
                    "text": header + chunk,
                })
        print("✅ Report successfully delivered to Telegram!")

if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(run_rag_analysis())
