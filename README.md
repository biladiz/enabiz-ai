# 🏥 e-Nabız AI Automation System

A privacy-first, locally-hosted automation system that logs into Turkey's e-Devlet/e-Nabız health portal, navigates it via AI-driven browser automation, extracts medical data (lab results, prescriptions, radiology reports), and stores everything in a local SQLite database.

**All data stays on your machine.** Credentials are encrypted with Fernet/PBKDF2. LLM inference runs locally via Ollama.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Your Machine (Windows dev) ──Tailscale──▶ MSI DGX Spark (prod)│
│                                                                 │
│  CLI ─▶ Orchestrator ─▶ Browser (Playwright) ─▶ e-Devlet Login  │
│              │              │                       │           │
│              │              ▼                       ▼           │
│              │         e-Nabız Nav (LLM)    2FA ─▶ Telegram     │
│              │              │                                   │
│              ▼              ▼                                   │
│         Docling (PDF) ─▶ SQLite DB ◀── LLM Extractor (Ollama)  │
└─────────────────────────────────────────────────────────────────┘
```

## Features

- **Fully async** Python 3.11+ implementation
- **Local vision models** (qwen2.5-vl:14b via Ollama) for UI understanding
- **Hybrid browser automation** — deterministic Playwright for login, LLM-driven for portal navigation
- **2FA relay** via Telegram Bot (or console fallback) — no open ports needed
- **Encrypted credentials** (Fernet + PBKDF2) — password never exposed to LLM
- **PDF parsing** using IBM Docling with TableFormer for medical lab tables
- **SQLite storage** with dedup, full-text search, and CSV export
- **Cross-platform** — develop on Windows, deploy on DGX Spark (ARM64 Ubuntu)

## Quick Start

### 1. Install Dependencies

```bash
# Clone and install
pip install -e .

# Install Playwright browser
playwright install chromium
```

### 2. Setup Ollama

Install [Ollama](https://ollama.com/) and pull the vision model:

```bash
ollama pull qwen2.5-vl:14b
```

> **DGX Spark via Tailscale:** If Ollama runs on your DGX Spark, set
> `OLLAMA_BASE_URL=http://<dgx-spark-tailscale-ip>:11434` in your `.env`.

### 3. Setup Telegram Bot (Recommended)

1. Message [@BotFather](https://t.me/BotFather) on Telegram → `/newbot`
2. Copy the bot token
3. Message your new bot → `/start` → it will show your Chat ID

### 4. Configure Environment

```bash
copy .env.example .env
# Edit .env with your values
```

### 5. First-Time Setup

```bash
enabiz-ai setup
```

This wizard will:
- Set your master encryption passphrase
- Store your TC Kimlik No & e-Devlet password (encrypted)
- Configure Telegram bot (optional)

## Usage

```bash
# Sync health data from e-Nabız
enabiz-ai sync labs          # Download & parse lab results
enabiz-ai sync rx            # Download prescriptions
enabiz-ai sync all           # Full sync

# Parse local PDF files
enabiz-ai parse report.pdf   # Parse a lab result PDF

# Query stored data
enabiz-ai query labs                    # List all lab reports
enabiz-ai query labs --since 2024-01-01 # Filter by date
enabiz-ai query labs -s "hemoglobin"    # Search

# Export data
enabiz-ai export csv --table lab_tests -o results.csv

# System status
enabiz-ai status
```

## DGX Spark Deployment via Tailscale

For production use on your MSI DGX Spark:

1. **Install Tailscale** on both machines:
   ```bash
   # On DGX Spark (Ubuntu ARM64)
   curl -fsSL https://tailscale.com/install.sh | sh
   tailscale up

   # On Windows dev machine
   # Install from https://tailscale.com/download/windows
   ```

2. **Point Ollama to DGX Spark** (in `.env`):
   ```env
   OLLAMA_BASE_URL=http://<dgx-spark-tailscale-ip>:11434
   ```

3. **Or run everything on DGX Spark**:
   ```bash
   # SSH into DGX Spark via Tailscale
   ssh user@<dgx-spark-tailscale-ip>

   # Clone repo, install, and run
   git clone <repo> && cd enabiz-ai
   pip install -e .
   playwright install chromium
   enabiz-ai setup
   enabiz-ai sync all
   ```

## Automated Testing

The project includes a comprehensive automated test suite with unit, security, and integration tests:

```powershell
# Run using PowerShell launcher
.\run_unit_tests.ps1

# Or run with pytest directly
.venv\Scripts\python.exe -m pytest tests -v
```

The test suite covers:
- **Profile Validation & Path Traversal Defense** (`test_profiles.py`)
- **PBKDF2/Fernet Credential & Session Encryption** (`test_credentials.py`, `test_session_manager.py`)
- **Database Idempotent Upserts & Dedup** (`test_database.py`)
- **Turkish Date Parsing & Lab Abnormality Evaluator** (`test_extraction.py`)
- **PowerShell Injection Sanitization & HTML Output Escaping** (`test_security.py`)
- **Clinical RAG Engine & Multi-Profile Batching** (`test_services.py`)
- **Typer CLI Runner Operations** (`test_cli.py`)

## Project Structure

```
src/enabiz_ai/
├── cli.py                 # Thin Typer CLI interface
├── config.py              # Pydantic Settings configuration & cached paths
├── exceptions.py          # Central exception hierarchy
├── orchestrator.py        # Programmatic orchestration wrapper
├── services/              # Core business services
│   ├── pipeline.py        # SyncService (harvesting & clinical analysis)
│   └── scheduler.py       # SchedulerService (Windows Task Scheduler)
├── profiles/              # Multi-person family profile management
│   ├── manager.py         # ProfileManager with isolated directories
│   └── models.py          # ProfileInfo models
├── credentials/           # Encrypted credential storage
│   ├── manager.py         # Fernet/PBKDF2 encryption
│   └── models.py          # Credential Pydantic models
├── browser/               # Browser automation
│   ├── authenticator.py   # Visible Chrome browser interactive login
│   ├── edevlet_login.py   # Deterministic e-Devlet authentication
│   └── session_manager.py # Cookie persistence with Fernet encryption at rest
├── extraction/            # Document and portal parsing
│   ├── harvester.py       # Direct portal harvesting with SHA-256 IDs
│   ├── lab_parser.py      # Docling PDF table extraction & abnormality checks
│   ├── llm_extractor.py   # Ollama-based text extraction with tenacity retries
│   └── models.py          # Health data Pydantic models
├── analysis/              # Clinical AI synthesis
│   └── rag_engine.py      # Longitudinal RAG synthesis with HTML sanitization
└── storage/               # Data persistence
    ├── repository.py      # HealthRepository Protocol interface
    ├── database.py        # Async SQLite database (aiosqlite)
    └── file_store.py      # Categorized local health file storage
```

## License

Private — personal use only. Do not distribute scraped health data.
