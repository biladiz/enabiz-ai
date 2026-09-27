# 🗺️ e-Nabız AI — Product Roadmap & Backlog

This document outlines the development roadmap, ongoing milestones, and future plans for the **e-Nabız AI Automation System**.

---

## 🎯 Current Milestone: v0.1.x (Foundation & Multi-Profile) — ✅ COMPLETED

- [x] **v0.0.1 Baseline Architecture:**
  - Playwright browser automation with deterministic e-Devlet login.
  - Interactive Telegram Bot 2FA OTP relay.
  - IBM Docling PDF medical report parsing (TableFormer).
  - Asynchronous SQLite database (`aiosqlite`) with deduplication.
  - Local Ollama RAG clinical report synthesis (`qwen2.5`).
- [x] **v0.1.0 Multi-Profile & Direct Login:**
  - Family multi-profile management with isolated directories (`ProfileManager`).
  - Direct e-Nabız password login alongside e-Devlet (`EnabizLogin`).
  - Dual-credential storage with automated fallback.
  - Interactive CLI wizard for profile configuration (`enabiz-ai profile add`).
  - Dual-language documentation synchronization (`README.md` & `README.tr.md`).
  - Git pre-commit enforcement hooks & Keep a Changelog (`RELEASE_NOTES.md`).
  - Hardening: SQLite WAL mode, foreign keys, Telegram HTML auto-detection, batch error isolation.

---

## 🚀 Near-Term Milestone: v0.2.0 (Core Hardening & Polish)

- [ ] **Architecture Refactoring:**
  - Extract common `BaseLoginHandler` to eliminate duplication between `edevlet_login.py` and `enabiz_login.py`.
  - Deprecate/refactor legacy single-user `orchestrator.py` to unify around `SyncService`.
  - Consolidate exception hierarchy under `EnabizError`.
- [ ] **RAG Engine Enhancements:**
  - Implement time-window filtering and token budget budgeting for large medical histories.
  - Support natural language chat / Q&A queries against local health database.
- [ ] **Testing & Coverage:**
  - Add mock unit test suite for `authenticator.py` strategy selection and fallback.
  - Add unit test suite for `llm_extractor.py` JSON extraction.

---

## 🔬 Hardware Milestone: MSI EdgeXpert 13SUS (NVIDIA GB10 128GB) & Multi-Model Architecture

Architecture and multi-model deployment strategy engineered for the production **MSI EdgeXpert 13SUS** (NVIDIA DGX Spark platform powered by the **NVIDIA GB10 Grace Blackwell Superchip**, 20-core ARM CPU, **128 GB LPDDR5x unified memory**, and 4TB PCIe Gen5 NVMe SSD).

### 1. Hardware Architecture & 128 GB Unified Memory Allocation
- [x] **Hardware Profile Confirmed:**
  - **SoC:** NVIDIA GB10 Grace Blackwell (20 ARM cores: 10x Cortex-X925 + 10x Cortex-A725, 1,000 TOPS FP4 compute).
  - **Unified RAM:** 128 GB LPDDR5x coherent memory (~500+ GB/s bandwidth) shared dynamically between CPU and GPU.
  - **Storage:** 4 TB PCIe Gen5 NVMe SSD (up to 14,000 MB/s sequential read/write) for sub-5s model weight loading.
  - **OS:** NVIDIA DGX OS / Ubuntu 24.04 LTS ARM64.
- [x] **Zero-Swapping Dual-Resident Strategy:**
  - With 128 GB unified memory, model swapping is eliminated. Both specialized models remain permanently resident in memory:
    - **Vision & Document OCR:** `qwen2.5-vl:14b` (~10 GB VRAM).
    - **Clinical Diagnostic Reasoning:** `deepseek-r1:70b` (Q4_K_M ~43 GB VRAM).
    - **KV-Cache & Context Expansion:** ~10 GB buffer for up to 128k context windows.
    - **Playwright Chromium Pool:** ~4 GB (2 concurrent workers).
    - **OS / Kernel / Buffer:** ~6 GB.
    - **Available Free Headroom:** ~55 GB buffer.
- [x] **Ollama Daemon Systemd Override Configuration:**
  - `Environment="OLLAMA_MAX_LOADED_MODELS=2"`
  - `Environment="OLLAMA_NUM_PARALLEL=2"`
  - `Environment="OLLAMA_KEEP_ALIVE=-1"` (keeps both models permanently active in memory).

### 2. Task Specialization & Role-Based Routing
Distinct pipeline tasks are routed to specialized models configured in `src/enabiz_ai/config.py`:

- **Job A: Web Navigation, OCR & Document Extraction:**
  - **Assigned Model:** `qwen2.5-vl:14b` (`model_vision`)
  - **Role:** High-fidelity visual grounding of e-Devlet/e-Nabız UI elements, PDF lab report OCR, and complex TableFormer extraction.
- **Job B: Clinical Diagnostic Reasoning & Longitudinal EHR Analysis:**
  - **Assigned Models:**
    - `deepseek-r1:70b` (`model_clinical` / `ollama_model`): Deep biomedical chain-of-thought reasoning across multi-year biomarker trends, detecting subtle shifts in liver/kidney/lipid markers, and generating doctor consultation talking points. `<think>` tokens stripped for patient Telegram summaries.
    - `medgemma:27b` (Google Health AI / Gemma 3, 87.7% MedQA): Fast, domain-native clinical EHR evaluation with minimal hallucination risk and 1/10th the inference compute cost of larger models.
- **Job C: Multimodal Medical Imaging & Radiology Interpretation (Planned):**
  - **Assigned Model:** `medgemma:27b` / `medsiglip` (`model_radiology`)
  - **Role:** Direct interpretation of e-Nabız radiology reports (Röntgen, MR, BT) and medical imaging studies alongside blood biomarkers.
- **Job D: Lightweight Structured JSON Extraction (Fallback):**
  - **Assigned Model:** `qwen2.5:7b` (`model_extraction`) for rapid low-overhead JSON formatting from pre-parsed text.

### 3. Implementation Status & Next Steps
- [x] Add specialized model role slots to `AppConfig` (`model_clinical`, `model_vision`, `model_radiology`, `model_extraction`).
- [x] Update `RAGEngine` to support `deepseek-r1:70b` (with `<think>` filtering) and `medgemma:27b`.
- [x] Add automated unit tests for DeepSeek-R1 `<think>` token filtering and MedGemma 27B report generation (`tests/test_services.py`).
- [ ] Measure token generation speeds (tok/s) and thermal headroom on the physical MSI EdgeXpert 13SUS hardware.
- [ ] Benchmark `deepseek-r1:70b` vs `medgemma:27b` for speed, accuracy, and Turkish clinical nuance.
- [ ] Prototype e-Nabız radiology image/report ingestion using MedGemma 27B Multimodal and MedSigLIP.
- [ ] Evaluate LiteLLM proxy deployment on the EdgeXpert for external API client access and health monitoring.

---

## 🌟 Future Backlog: Managed Hosted Subscription Service (Max 50 Users)

> Detailed Technical Blueprint: [docs/HOSTED_SUBSCRIPTION_PLAN.md](docs/HOSTED_SUBSCRIPTION_PLAN.md)

Designed for users who want e-Nabız AI weekly intelligence without touching code, running Docker/Python, or managing local LLMs.

### Constraints & Principles
- **Strict 50-Subscriber Limit:** Keeps operations manageable, ensures zero performance degradation on dedicated hardware (MSI EdgeXpert 13SUS), and controls regulatory exposure.
- **Zero-Code Delivery:** Operated 100% via a private Telegram Bot concierge.
- **Credential Minimization:** Uses direct e-Nabız passwords (isolated from e-Devlet identity records) with in-memory session token exchange.
- **KVKK & Sensitive Data Compliance:** Explicit consent flow, strictly local AI inference in Turkey, and `/delete_my_data` right-to-erasure.

### Planned Epics
1. **Epic 1 — Multi-Tenant Architecture:** Per-tenant SQLite database isolation (`tenants/<uuid>/health.db`).
2. **Epic 2 — MSI EdgeXpert Distributed Worker Queue:** Redis + Celery/RQ job worker with rate-limited Playwright browser pool (max 2 concurrency) and staggered weekly runs (~7 users/day).
3. **Epic 3 — Multi-Tenant Telegram Concierge Gateway:** Standalone bot gateway with multi-user session state machine and 2FA OTP routing.
4. **Epic 4 — Credential Enclave & Security:** In-memory credential consumption with zero plain-text disk storage.
5. **Epic 5 — Subscription & Billing Integration:** 50-seat inventory lock and domestic Turkish payment processor integration (Iyzico / Shopier).
6. **Epic 6 — Legal & KVKK Compliance Kit:** Mandatory Turkish consent contracts (Açık Rıza & Aydınlatma Metni) and automated deletion routines.
