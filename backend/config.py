"""Environment based ResolveIQ configuration."""
from __future__ import annotations

import json
from pathlib import Path
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App & Environment
    environment: str = "production"
    log_level: str = "INFO"

    # PayPal Integration
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    paypal_timeout_seconds: float = 15.0

    # Gemini AI Intelligence
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # Zapier Webhook Automation
    zapier_webhook_url: str = ""
    zapier_webhook_timeout_seconds: float = 8.0

    # Storage & Persistence
    upload_dir: str = "storage/uploads"
    db_path: str = "storage/resolveiq.db"
    database_url: str = ""
    max_upload_size_mb: int = 15

    # Security & CORS settings
    allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    allowed_origin_regex: str = r"^https:\/\/.*\.vercel\.app$"
    max_request_body_size_mb: int = 20
    rate_limit_enabled: bool = True
    merchant_api_key: str = ""

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v):
        if isinstance(v, str):
            v_clean = v.strip()
            if v_clean.startswith("[") and v_clean.endswith("]"):
                try:
                    return json.loads(v_clean)
                except Exception:
                    pass
            return [origin.strip() for origin in v_clean.split(",") if origin.strip()]
        return v

    @model_validator(mode="after")
    def resolve_database_url(self) -> Settings:
        if self.database_url:
            clean_url = self.database_url.strip()
            if clean_url.startswith("sqlite:///"):
                # Extract path from sqlite:///path/to/db
                self.db_path = clean_url[len("sqlite:///"):]
            elif clean_url.startswith("sqlite://"):
                self.db_path = clean_url[len("sqlite://"):]
        return self

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def ensure_directories(self) -> None:
        Path(self.upload_dir).mkdir(parents=True, exist_ok=True)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
