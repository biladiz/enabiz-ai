# Release Notes

All notable changes to the **e-Nabız AI Automation System** (`enabiz-ai`) will be documented in this file.

The project adheres to Semantic Versioning and minor versions are incremented for each major feature set or change.

---

## [Unreleased]

### Added
- **MSI EdgeXpert 13SUS (NVIDIA GB10 128GB) Multi-Model Architecture:**
  - Added multi-model role slots in `AppConfig`: `model_clinical` (`deepseek-r1:70b` / `medgemma:27b`), `model_vision` (`qwen2.5-vl:14b`), `model_radiology` (`medgemma:27b`), and `model_extraction` (`qwen2.5:7b`).
  - Added first-class support for **Google MedGemma 27B** (HAI-DEF / Gemma 3, 87.7% MedQA) for fast, domain-native clinical EHR synthesis and planned medical imaging interpretation via MedSigLIP.
  - Updated `RAGEngine` to support both `deepseek-r1:70b` (with defensive `<think>...</think>` token stripping) and `medgemma:27b`.
  - Documented multi-model deployment architecture for 128 GB unified memory on the NVIDIA GB10 Grace Blackwell Superchip (`OLLAMA_MAX_LOADED_MODELS=2`, `OLLAMA_KEEP_ALIVE=-1`).
  - Added unit test `test_rag_engine_medgemma_model_support` in `tests/test_services.py` (58 tests passing).

---

## [0.1.0] - 2026-09-27

### Added
- **Direct ENabız Login Support (`EnabizLogin`):**
  - Added direct TC Kimlik No and e-Nabız password authentication at `https://enabiz.gov.tr/Account/Login`.
  - Added support for 2FA SMS verification (`#ikiAsamaliOnay` / `#IkiAsamaSmsKod`) as well as 2FA-disabled accounts.
  - Added detection of frozen accounts, CAPTCHAs, and toast error messages.
- **Dual-Credential Storage & Fallback Strategy:**
  - Extended `Credentials` model to store both e-Devlet (`password`) and e-Nabız direct (`enabiz_password`) credentials.
  - Authenticator automatically prioritizes e-Devlet and seamlessly falls back to direct e-Nabız login if primary auth fails.
  - Transparent backward compatibility for previously saved credentials.
- **Interactive CLI Profile Wizard:**
  - `enabiz-ai profile add` now guides users through choosing a login method:
    1. e-Devlet password + 2FA (default)
    2. e-Nabız password (with optional 2FA)
    3. Both methods (e-Devlet primary with e-Nabız fallback)
  - `enabiz-ai profile list` shows a dedicated "Giriş Yöntemi" column indicating method per profile.
- **Documentation & Versioning Enforcement Hooks:**
  - Added Git pre-commit verification hook (`scripts/check_docs_sync.py`).
  - Added Antigravity workspace rules (`.agents/rules/docs_and_versioning.md`) and lifecycle hooks (`.agents/hooks.json`).
  - Added version bump automation utility (`scripts/bump_version.py`).

### Fixed & Improved
- **Telegram Notification Parse Mode:** Added auto-detection of HTML tags and automatic fallback to plain text if formatting fails.
- **SQLite Concurrency & Integrity:** Enabled `PRAGMA foreign_keys = ON;`, `PRAGMA journal_mode = WAL;`, and `PRAGMA busy_timeout = 5000;`.
- **CLI Batch Resilience:** Isolated per-profile errors in `weekly --profile all` and `analyze` loops so single-profile issues do not abort the batch.
- **LLM Extraction Timeline:** Added explicit report and prescription date parameters to `LLMExtractor` to preserve historical clinical dates.

### Tests
- Added 12 new automated test cases across `tests/test_credentials.py` and `tests/test_profiles.py` (total test suite at 56 passing tests).

---

## [0.0.1] - 2026-09-27

### Added
- **Initial Baseline Release:**
  - **Browser Automation:** Deterministic Playwright login flow for e-Devlet and AI-guided e-Nabız portal navigation.
  - **2FA Relay:** Interactive OTP relay via Telegram Bot (`python-telegram-bot`) with console fallback.
  - **Secure Storage:** Encrypted credential and session cookie storage using Fernet + PBKDF2 key derivation.
  - **Medical Data Extraction:** IBM Docling PDF parser with TableFormer for tabular lab reports, plus Ollama LLM extraction.
  - **Storage & Database:** Asynchronous SQLite database (`aiosqlite`) with SHA256 record deduplication and CSV export.
  - **Health Analysis:** Local RAG analysis engine using Ollama (`qwen2.5-vl`) for personal medical summaries.
  - **Multi-Profile Management:** Profile isolation, directory sandbox validation, and Windows Task Scheduler integration.
