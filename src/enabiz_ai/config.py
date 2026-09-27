from functools import cached_property
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class AppConfig(BaseSettings):
    """Application configuration for e-Nabiz AI."""

    # Telegram
    telegram_bot_token: str = Field(default="", description="Telegram Bot Token")
    telegram_chat_id: str = Field(default="", description="Telegram Chat ID")

    # Ollama / Local AI on MSI EdgeXpert 13SUS (NVIDIA GB10 128GB)
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="deepseek-r1:70b", description="Default/primary model")
    model_clinical: str = Field(
        default="deepseek-r1:70b",
        description="Clinical reasoning engine: 'deepseek-r1:70b' (deep diagnostic reasoning) or 'medgemma:27b' (Google domain-native clinical EHR synthesis)",
    )
    model_vision: str = Field(
        default="qwen2.5-vl:14b",
        description="Visual web navigation and medical document OCR model",
    )
    model_radiology: str = Field(
        default="medgemma:27b",
        description="Multimodal medical imaging and radiology report interpretation model (Google MedGemma 27B / MedSigLIP)",
    )
    model_extraction: str = Field(
        default="qwen2.5:7b",
        description="Fast structured JSON extractor for plain text lab tables",
    )

    # Data
    enabiz_data_dir: str = Field(default="~/.enabiz-ai")

    # Browser
    chrome_cdp_url: str = Field(default="http://127.0.0.1:9222")
    chrome_path: str | None = Field(default=None)
    headless: bool = Field(default=False)

    # Logging
    log_level: str = Field(default="INFO")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @cached_property
    def data_dir(self) -> Path:
        """Get the base data directory and ensure it exists."""
        path = Path(os.path.expanduser(self.enabiz_data_dir))
        path.mkdir(parents=True, exist_ok=True)
        return path

    @cached_property
    def downloads_dir(self) -> Path:
        """Directory for general downloads."""
        path = self.data_dir / "downloads"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @cached_property
    def lab_results_dir(self) -> Path:
        """Directory for laboratory results."""
        path = self.data_dir / "lab_results"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @cached_property
    def prescriptions_dir(self) -> Path:
        """Directory for prescriptions."""
        path = self.data_dir / "prescriptions"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @cached_property
    def radiology_dir(self) -> Path:
        """Directory for radiology reports."""
        path = self.data_dir / "radiology"
        path.mkdir(parents=True, exist_ok=True)
        return path

