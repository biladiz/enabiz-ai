# 🏥 e-Nabız Yapay Zeka Otomasyon Sistemi

[🇹🇷 Türkçe](README.tr.md) | [🇬🇧 English](README.md)

> [!CAUTION]
> ### ⚠️ Temel Tıbbi ve Hukuki Uyarı (Yasal Sorumluluk Reddi)
>
> **Tıbbi Sorumluluk Reddi:** Bu yazılım deneysel, kişisel veri arşivleme ve eğitim amaçlı bir araçtır. Tıbbi tavsiye, teşhis veya klinik tedavi planı sunmaz. Bu yazılım tarafından üretilen yapay zeka değerlendirmeleri, hiçbir koşulda yetkili bir sağlık uzmanının (hekimin) konsültasyonunun veya teşhisinin yerine geçemez. Yazar(lar), bu yazılımın çıktılarına dayanılarak alınan tıbbi kararlar veya uygulanan eylemler konusunda hiçbir sorumluluk kabul etmez.
>
> **Kullanım Şartları Bildirimi:** Kullanıcılar, otomasyon kullanımlarının ilgili e-Devlet ve e-Nabız kullanım şartlarına ve yürürlükteki yerel yasalara uygun olmasını sağlamaktan bizzat sorumludur. Kimlik bilgilerinizi ve şifrelerinizi her zaman koruyunuz; şifrelenmemiş tıbbi verileri asla üçüncü taraflarla paylaşmayınız veya yayınlamayınız.

Türkiye'nin e-Devlet/e-Nabız sağlık portalına giriş yapan, yapay zeka destekli tarayıcı otomasyonu ile portali tarayan, tıbbi verileri (laboratuvar tahlil sonuçları, reçeteler, radyoloji raporları) çıkaran ve her şeyi yerel bir SQLite veritabanında depolayan, **gizlilik odaklı ve tamamen yerel barındırılan** bir otomasyon sistemi.

**Tüm verileriniz yalnızca kendi cihazınızda kalır.** Kimlik ve giriş bilgileri Fernet/PBKDF2 ile şifrelenir. Büyük dil modelleri (LLM) Ollama aracılığıyla yerel olarak çalıştırılır.

## Mimari

```
┌─────────────────────────────────────────────────────────────────┐
│  Kendi Cihazınız (Windows dev) ──Tailscale──▶ MSI DGX Spark     │
│                                                                 │
│  CLI ─▶ Orkestratör ─▶ Tarayıcı (Playwright) ─▶ e-Devlet Girişi │
│              │              │                       │           │
│              │              ▼                       ▼           │
│              │       e-Nabız Gezinme (LLM)   2FA ─▶ Telegram    │
│              │              │                                   │
│              ▼              ▼                                   │
│         Docling (PDF) ─▶ SQLite DB ◀── LLM Çıkarıcı (Ollama)    │
└─────────────────────────────────────────────────────────────────┘
```

## Özellikler

- **Tamamen asenkron** Python 3.11+ mimarisi (`asyncio` ve `aiosqlite`)
- **Yerel görsel modeller** (Arayüz analizi için Ollama üzerinden `qwen2.5-vl:14b`)
- **Hibrit tarayıcı otomasyonu** — Giriş işlemleri için kararlı Playwright, portal içi gezinme için LLM destekli gezgin
- **Telegram Bot ile 2FA iletimi** (veya konsol yedeği) — Dışarıya port açmaya gerek yoktur
- **Şifreli kimlik saklama** (Fernet + PBKDF2) — Parola asla LLM'e veya açık metin olarak diske aktarılmaz
- **PDF ayrıştırma** — Tıbbi laboratuvar tabloları için TableFormer destekli IBM Docling entegrasyonu
- **SQLite veri depolama** — Mükerrer kayıt engelleme (deduplication), tam metin arama ve CSV dışa aktarımı
- **Platform bağımsız** — Windows üzerinde geliştirme, DGX Spark (ARM64 Ubuntu) üzerinde üretim dağıtımı

## Hızlı Başlangıç

### 1. Bağımlılıkları Yükleyin

```bash
# Projeyi kurun
pip install -e .

# Playwright tarayıcısını yükleyin
playwright install chromium
```

### 2. Ollama Kurulumu

[Ollama](https://ollama.com/) yazılımını yükleyin ve görsel modeli indirin:

```bash
ollama pull qwen2.5-vl:14b
```

> **Tailscale ile DGX Spark Kullanımı:** Ollama DGX Spark üzerinde çalışıyorsa `.env` dosyanızda şu şekilde tanımlayın:
> `OLLAMA_BASE_URL=http://<dgx-spark-tailscale-ip>:11434`

### 3. Telegram Bot Kurulumu (Önerilen)

1. Telegram'da [@BotFather](https://t.me/BotFather) ile konuşun → `/newbot`
2. Bot belirtecini (token) kopyalayın
3. Yeni botunuza mesaj atın → `/start` → Chat ID bilginizi görüntüler

### 4. Çevre Değişkenlerini Yapılandırın

```bash
copy .env.example .env
# .env dosyasını kendi bilgilerinize göre düzenleyin
```

### 5. İlk Kurulum Sihirbazı

```bash
enabiz-ai setup
```

Bu sihirbaz şunları gerçekleştirir:
- Ana şifreleme parolanızı (Master Passphrase) belirler
- T.C. Kimlik Numaranızı ve e-Devlet şifrenizi şifreleyerek kaydeder
- İsteğe bağlı olarak Telegram bot yapılandırmanızı tamamlar

## Kullanım

```bash
# e-Nabız verilerini senkronize etme
enabiz-ai sync labs          # Tahlil sonuçlarını indir ve ayrıştır
enabiz-ai sync rx            # Reçeteleri indir
enabiz-ai sync all           # Tam senkronizasyon

# Yerel PDF dosyalarını ayrıştırma
enabiz-ai parse rapor.pdf    # Tahlil sonucu PDF dosyasını ayrıştır

# Depolanan verileri sorgulama
enabiz-ai query labs                    # Tüm tahlil raporlarını listele
enabiz-ai query labs --since 2024-01-01 # Tarihe göre filtrele
enabiz-ai query labs -s "hemoglobin"    # Test adına göre ara

# Verileri dışa aktarma
enabiz-ai export csv --table lab_tests -o sonuclar.csv

# Sistem durumunu görüntüleme
enabiz-ai status
```

## Tailscale Üzerinden DGX Spark Dağıtımı

Üretim ortamında MSI DGX Spark üzerinde çalıştırmak için:

1. **Her iki makineye de Tailscale kurun**:
   ```bash
   # DGX Spark üzerinde (Ubuntu ARM64)
   curl -fsSL https://tailscale.com/install.sh | sh
   tailscale up

   # Windows geliştirici makinesinde
   # https://tailscale.com/download/windows adresinden kurun
   ```

2. **Ollama'yı DGX Spark'a yönlendirin** (`.env` içinde):
   ```env
   OLLAMA_BASE_URL=http://<dgx-spark-tailscale-ip>:11434
   ```

3. **Veya tüm sistemi doğrudan DGX Spark üzerinde çalıştırın**:
   ```bash
   # Tailscale ile DGX Spark'a bağlanın
   ssh user@<dgx-spark-tailscale-ip>

   # Depoyu klonlayıp kurun
   git clone <repo> && cd enabiz-ai
   pip install -e .
   playwright install chromium
   enabiz-ai setup
   enabiz-ai sync all
   ```

## Otomatik Testler

Proje; birim, güvenlik ve entegrasyon senaryolarını kapsayan kapsamlı bir otomatik test paketine sahiptir:

```powershell
# PowerShell başlatıcısı ile çalıştırma
.\run_unit_tests.ps1

# veya doğrudan pytest ile
.venv\Scripts\python.exe -m pytest tests -v
```

Test kapsamı:
- **Profil Doğrulama ve Dizin Atlama (Path Traversal) Koruması** (`test_profiles.py`)
- **PBKDF2/Fernet Kimlik ve Oturum Şifreleme** (`test_credentials.py`, `test_session_manager.py`)
- **Veritabanı İdempotent Ekleme ve Mükerrer Kayıt Önleme** (`test_database.py`)
- **Türkçe Tarih Ayrıştırma ve Tahlil Referans Aralığı Değerlendirici** (`test_extraction.py`)
- **PowerShell Enjeksiyon Temizleme ve HTML Çıktı Güvenliği** (`test_security.py`)
- **Klinik RAG Motoru ve Çoklu Profil Toplu İşleme** (`test_services.py`)
- **Typer CLI Komut Satırı İşlemleri** (`test_cli.py`)

## Proje Yapısı

```
src/enabiz_ai/
├── cli.py                 # İnce Typer CLI arayüzü
├── config.py              # Pydantic Settings yapılandırması ve önbellekli yollar
├── exceptions.py          # Merkezi istisna (exception) hiyerarşisi
├── orchestrator.py        # Programatik orkestrasyon sarmalayıcısı
├── services/              # Çekirdek iş servisleri
│   ├── pipeline.py        # SyncService (veri toplama ve klinik analiz)
│   └── scheduler.py       # SchedulerService (Windows Görev Zamanlayıcısı)
├── profiles/              # Aile bireyleri için çoklu profil yönetimi
│   ├── manager.py         # Yalıtılmış dizinlerle ProfileManager
│   └── models.py          # ProfileInfo modelleri
├── credentials/           # Şifreli kimlik bilgisi depolama
│   ├── manager.py         # Fernet/PBKDF2 şifreleme
│   └── models.py          # Pydantic kimlik modelleri
├── browser/               # Tarayıcı otomasyonu
│   ├── authenticator.py   # Görünür Chrome ile etkileşimli oturum açma
│   ├── edevlet_login.py   # Kararlı e-Devlet kimlik doğrulama
│   └── session_manager.py # Dinlenim halinde Fernet şifreli çerez saklama
├── extraction/            # Belge ve portal ayrıştırma
│   ├── harvester.py       # SHA-256 kimlikleri ile doğrudan portal hasadı
│   ├── lab_parser.py      # Docling PDF tablo çıkarma ve anormallik denetimi
│   ├── llm_extractor.py   # Tenacity yeniden denemeli Ollama tabanlı metin çıkarma
│   └── models.py          # Sağlık verisi Pydantic modelleri
├── analysis/              # Klinik yapay zeka sentezi
│   └── rag_engine.py      # HTML temizlemeli boylamsal RAG sentezi
└── storage/               # Veri kalıcılığı
    ├── repository.py      # HealthRepository Protocol arayüzü
    ├── database.py        # Asenkron SQLite veritabanı (aiosqlite)
    └── file_store.py      # Kategorize edilmiş yerel sağlık dosyası depolama
```

## Lisans

MIT Lisansı — Kişisel ve eğitim amaçlı kullanım. Ayrıntılar için [LISANS.md](LISANS.md) dosyasına bakınız.
