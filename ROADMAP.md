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
