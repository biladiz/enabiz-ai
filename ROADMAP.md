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

## 🔬 Investigation Milestone: MSI DGX Spark Hardware Audit & Specialized Multi-Model Routing

Plan to benchmark the production **MSI DGX Spark** (Ubuntu ARM64) and architect specialized multi-model routing for distinct pipeline tasks rather than relying on a single general-purpose model.

### 1. Hardware & VRAM Audit (MSI DGX Spark)
- [ ] Profile available GPU/NPU architecture, total VRAM, CUDA runtime, and memory bandwidth on the DGX Spark.
- [ ] Measure Ollama inference latency, token generation speeds (tok/s), and thermal throttling under sustained load.
- [ ] Determine optimal quantization levels (`Q4_K_M` vs `Q8_0` vs `fp16`) for 7B, 14B, and 32B model sizes within available VRAM.

### 2. Task Specialization & Candidate Model Benchmarking
Distinct tasks have fundamentally different performance, context, and intelligence requirements:

- **Job A: Web Navigation, OCR & Structured Document Extraction:**
  - *Requirements:* High visual element grounding, rapid JSON formatting, low latency, robust OCR for lab tables.
  - *Candidate Models to Evaluate:*
    - `qwen2.5-vl:7b` / `qwen2.5-vl:14b`: Primary candidates for Playwright UI understanding and PDF document OCR.
    - `llama-3.2-vision:11b`: High precision for complex medical PDF tables.
    - `qwen2.5:7b-instruct`: Ultra-fast structured JSON extraction for pre-parsed plain text.
- **Job B: Clinical Health Reasoning, Longitudinal Trend Analysis & Medical Suggestions:**
  - *Requirements:* Deep biomedical understanding, nuanced Turkish fluency, empathetic and clear communication, chain-of-thought reasoning across multi-year biomarker trends.
  - *Candidate Models to Evaluate:*
    - `qwen2.5:14b` / `qwen2.5:32b` (4-bit): High Turkish fluency, strong medical synthesis, and reliable doctor visit talking points.
    - `deepseek-r1:14b` / `deepseek-r1:8b`: Deep chain-of-thought reasoning for correlating multiple simultaneous abnormal markers.
    - `meditron:7b` / `biomistral:7b`: Medical-domain specialized LLMs (evaluating Turkish translation and clinical terminology accuracy).

### 3. Routing Architecture Decision: In-App vs. MSI DGX Spark Gateway
Evaluate the architectural design for routing requests to specialized models:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        MODEL ROUTING STRATEGIES                        │
│                                                                        │
│  Option 1: In-App Role Slots (Direct)                                  │
│  enabiz-ai config ──▶ extraction_model ──▶ Ollama (/api/chat)          │
│                   ──▶ clinical_model   ──▶ Ollama (/api/chat)          │
│                                                                        │
│  Option 2: MSI DGX Spark Gateway Proxy (LiteLLM / vLLM)                │
│  enabiz-ai ──▶ LiteLLM Proxy on DGX Spark ──▶ Ollama / vLLM backends   │
│                (model aliases: 'extractor', 'clinical-expert')         │
│                                                                        │
│  ⭐ Recommendation: In-App Role Abstraction with OpenAI-compatible API  │
│     Direct connection to Ollama by default, with seamless support for   │
│     a LiteLLM / Open-WebUI proxy on the DGX Spark if needed.           │
└────────────────────────────────────────────────────────────────────────┘
```

- [ ] **Phase A (In-App Roles):** Separate single `ollama_model` in `config.py` into distinct functional roles:
  - `model_vision_nav`: For browser automation (`qwen2.5-vl`).
  - `model_extraction`: For document OCR and JSON parsing (`qwen2.5-vl` / `llama3.2-vision`).
  - `model_clinical_rag`: For longitudinal health evaluation and doctor talking points (`qwen2.5:14b` / `deepseek-r1`).
  - `model_chat`: For interactive Telegram Q&A (`qwen2.5:7b`).
- [ ] **Phase B (MSI Gateway Proxy Investigation):** Evaluate deploying **LiteLLM Proxy** on the DGX Spark:
  - Decouples client applications from backend model providers.
  - Enables centralized fallback (e.g. fall back from 14B to 7B if VRAM is constrained).
  - Provides model load balancing, request queuing, and latency tracking.
- [ ] **VRAM Thrashing Prevention:** Implement sequential batch scheduling (execute all Job A extractions first, then switch to Job B clinical reasoning) so Ollama does not constantly swap large models in and out of GPU memory.

---

## 🌟 Future Backlog: Managed Hosted Subscription Service (Max 50 Users)

> Detailed Technical Blueprint: [docs/HOSTED_SUBSCRIPTION_PLAN.md](docs/HOSTED_SUBSCRIPTION_PLAN.md)

Designed for users who want e-Nabız AI weekly intelligence without touching code, running Docker/Python, or managing local LLMs.

### Constraints & Principles
- **Strict 50-Subscriber Limit:** Keeps operations manageable, ensures zero performance degradation on dedicated hardware (DGX Spark), and controls regulatory exposure.
- **Zero-Code Delivery:** Operated 100% via a private Telegram Bot concierge.
- **Credential Minimization:** Uses direct e-Nabız passwords (isolated from e-Devlet identity records) with in-memory session token exchange.
- **KVKK & Sensitive Data Compliance:** Explicit consent flow, strictly local AI inference in Turkey, and `/delete_my_data` right-to-erasure.

### Planned Epics
1. **Epic 1 — Multi-Tenant Architecture:** Per-tenant SQLite database isolation (`tenants/<uuid>/health.db`).
2. **Epic 2 — DGX Spark Distributed Worker Queue:** Redis + Celery/RQ job worker with rate-limited Playwright browser pool (max 2 concurrency) and staggered weekly runs (~7 users/day).
3. **Epic 3 — Multi-Tenant Telegram Concierge Gateway:** Standalone bot gateway with multi-user session state machine and 2FA OTP routing.
4. **Epic 4 — Credential Enclave & Security:** In-memory credential consumption with zero plain-text disk storage.
5. **Epic 5 — Subscription & Billing Integration:** 50-seat inventory lock and domestic Turkish payment processor integration (Iyzico / Shopier).
6. **Epic 6 — Legal & KVKK Compliance Kit:** Mandatory Turkish consent contracts (Açık Rıza & Aydınlatma Metni) and automated deletion routines.
