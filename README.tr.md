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
│  CLI ─▶ Orkestratör ─▶ Tarayıcı (Playwright)                    │
│              │            ├──▶ e-Devlet Girişi (2FA İletimi)    │
│              │            └──▶ Doğrudan e-Nabız (2FA'lı/2FA'sız)│
│              │                       │           │              │
│              │                       ▼           ▼              │
│              │       e-Nabız Gezinme (LLM)   2FA ─▶ Telegram    │
│              │              │                                   │
│              ▼              ▼                                   │
│         Docling (PDF) ─▶ SQLite DB ◀── LLM Çıkarıcı (Ollama)    │
└─────────────────────────────────────────────────────────────────┘
```

## Özellikler

- **Tamamen asenkron** Python 3.11+ mimarisi (`asyncio` ve `aiosqlite`)
- **Çift Giriş Yöntemi ve Otomatik Yedekleme** — e-Devlet veya doğrudan e-Nabız şifresi ile giriş; birincil yöntem başarısız olursa ikincisine otomatik geçiş
- **Esnek 2FA Desteği** — Telegram Bot ile SMS onay iletimi veya konsol yedeği; 2FA'lı ve 2FA'sız hesaplar desteklenir
- **Çoklu Profil Yalıtımı** — Her aile bireyi için izole şifreli kimlikler, sağlık kayıtları ve dosya dizinleri
- **Yerel görsel modeller** (Arayüz analizi için Ollama üzerinden `qwen2.5-vl:14b`)
- **Hibrit tarayıcı otomasyonu** — Giriş işlemleri için kararlı Playwright, portal içi gezinme için LLM destekli gezgin
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

### Çoklu Profil Yönetimi ve Çift Giriş

Sistem birden fazla aile bireyinin profilini birbirinden izole şekilde destekler. Her profil **e-Devlet**, doğrudan **e-Nabız şifresi** veya **her ikisi** ile (otomatik yedekleme/fallback) kimlik doğrulayabilir:

```bash
# Yeni profil eklemek için etkileşimli sihirbaz
enabiz-ai profile add anne --name "Annem" --relation "Anne"

# Sihirbaz giriş yöntemini seçmenizi ister:
# 1. e-Devlet şifresi + 2FA (varsayılan)
# 2. Doğrudan e-Nabız şifresi (2FA SMS'li veya 2FA'sız)
# 3. Her iki yöntem (önce e-Devlet denenir, başarısız olursa e-Nabız'a geçilir)

# Kayıtlı profilleri ve giriş yöntemlerini listeleme
enabiz-ai profile list

# Bir profil için oturum açıp çerezleri önbelleğe alma
enabiz-ai profile login anne
```

### Veri Senkronizasyonu ve Sorgular

```bash
# e-Nabız verilerini senkronize etme
enabiz-ai sync labs          # Tahlil sonuçlarını indir ve ayrıştır
enabiz-ai sync rx            # Reçeteleri indir
enabiz-ai sync all           # Tam senkronizasyon
enabiz-ai weekly --profile all # Tüm profiller için haftalık senkronizasyon ve yapay zeka raporu

# Yerel PDF dosyalarını ayrıştırma
enabiz-ai parse rapor.pdf    # Tahlil sonucu PDF dosyasını ayrıştır

# Depolanan verileri sorgulama
enabiz-ai query labs                    # Tüm tahlil raporlarını listele
enabiz-ai query labs --since 2024-01-01 # Tarihe göre filtrele
enabiz-ai query labs -s "hemoglobin"    # Test adına göre ara

# Verileri dışa aktarma
enabiz-ai export csv --table lab_tests -o sonuclar.csv

# Sistem durumu ve sürüm bilgisi
enabiz-ai status
enabiz-ai version
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
│   ├── authenticator.py   # Strateji seçici ve etkileşimli kimlik doğrulama
│   ├── edevlet_login.py   # Kararlı e-Devlet kimlik doğrulama işleyicisi
│   ├── enabiz_login.py    # Doğrudan e-Nabız T.C.+şifre kimlik doğrulama işleyicisi
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

## Yol Haritası ve Gelecek Planları

- 🗺️ **[Ürün Yol Haritası ve İş Listesi (ROADMAP.md)](ROADMAP.md)**: Yakın dönem geliştirmeleri ve aşama takibi.
- 🏥 **[Barındırılan Abonelik Hizmeti Mimarisi (Maksimum 50 Kullanıcı)](docs/HOSTED_SUBSCRIPTION_PLAN.md)**: Kod çalıştırmak veya terminal kullanmak istemeyen kullanıcılar için Telegram tabanlı yönetilen konsiyerj hizmetinin teknik mimarisi ve güvenlik planı.

## Lisans

MIT Lisansı — Kişisel ve eğitim amaçlı kullanım. Ayrıntılar için [LISANS.md](LISANS.md) dosyasına bakınız.
