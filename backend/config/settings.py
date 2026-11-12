from __future__ import annotations

from typing import List, Optional
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven SmartNet configuration.

    Development defaults are intentionally local-only. Production startup fails
    closed until strong secrets and real integrations are explicitly configured.
    """

    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    SECRET_KEY: str = "dev-only-change-me-before-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    PAYMENT_WEBHOOK_SECRET: str = "dev-only-change-me-before-production"
    PAYMENT_PROVIDER_MODE: str = "manual"  # "manual" or "gateway"
    PAYMENT_CHECKOUT_URL: Optional[str] = None
    PAYMENT_DEMO_MODE: bool = True
    APP_PUBLIC_URL: str = "http://127.0.0.1:5173"

    DASHBOARD_USERNAME: str = "admin"
    DASHBOARD_PASSWORD: str = "dev-only-SmartNet-Admin-Change-This-2026!"

    MIKROTIK_HOST: str = "192.168.88.1"
    MIKROTIK_USERNAME: str = "admin"
    MIKROTIK_PASSWORD: str = ""
    MIKROTIK_PORT: int = 8728
    MIKROTIK_DEMO_MODE: bool = True
    SSID: str = "SmartNet-WiFi"

    DATABASE_URL: str = "sqlite+aiosqlite:///./smartnet.db"
    POSTGRES_DB: Optional[str] = None
    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: Optional[str] = None

    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_ADMIN_IDS: List[int] = Field(default_factory=list)
    BOT_API_BASE_URL: str = "http://127.0.0.1:8000"

    SUBSCRIPTION_AGENT_DELAY_SECONDS: int = 60
    SUBSCRIPTION_AGENT_INTERVAL_SECONDS: int = 30

    CORS_ORIGINS: List[str] = Field(default_factory=lambda: [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ])

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    @model_validator(mode="after")
    def validate_production_configuration(self) -> "Settings":
        if self.ENVIRONMENT.lower() == "production":
            insecure = {
                "SECRET_KEY": self.SECRET_KEY,
                "PAYMENT_WEBHOOK_SECRET": self.PAYMENT_WEBHOOK_SECRET,
                "DASHBOARD_PASSWORD": self.DASHBOARD_PASSWORD,
            }
            weak = [
                key for key, value in insecure.items()
                if not value or value.startswith("dev-only-") or value in {"admin123", "password", "changeme"}
            ]
            if weak:
                raise ValueError("Production configuration contains missing/default secrets: " + ", ".join(weak))
            if len(self.SECRET_KEY) < 32 or len(self.PAYMENT_WEBHOOK_SECRET) < 32:
                raise ValueError("Production secrets must each contain at least 32 characters.")
            if self.PAYMENT_DEMO_MODE:
                raise ValueError("PAYMENT_DEMO_MODE must be false in production.")
            if self.MIKROTIK_DEMO_MODE:
                raise ValueError("MIKROTIK_DEMO_MODE must be false in production.")
            if not self.MIKROTIK_PASSWORD:
                raise ValueError("MIKROTIK_PASSWORD is required in production.")
            if not self.DATABASE_URL.startswith("postgresql+asyncpg://"):
                raise ValueError("Production must use PostgreSQL.")
            if self.PAYMENT_PROVIDER_MODE not in {"manual", "gateway"}:
                raise ValueError("PAYMENT_PROVIDER_MODE must be 'manual' or 'gateway'.")
            if self.PAYMENT_PROVIDER_MODE == "gateway" and not self.PAYMENT_CHECKOUT_URL:
                raise ValueError("PAYMENT_CHECKOUT_URL is required when PAYMENT_PROVIDER_MODE=gateway.")
            if len(self.DASHBOARD_PASSWORD) < 12:
                raise ValueError("DASHBOARD_PASSWORD must contain at least 12 characters in production.")
            if self.DASHBOARD_USERNAME.strip().lower() in {"admin", "administrator"}:
                raise ValueError("Set a unique non-default DASHBOARD_USERNAME in production.")
            if not self.POSTGRES_PASSWORD or len(self.POSTGRES_PASSWORD) < 16 or self.POSTGRES_PASSWORD.startswith("dev-only-"):
                raise ValueError("Set a unique POSTGRES_PASSWORD with at least 16 characters in production.")
            if not self.CORS_ORIGINS:
                raise ValueError("At least one exact HTTPS CORS origin is required in production.")
            if any(not origin.startswith("https://") for origin in self.CORS_ORIGINS):
                raise ValueError("Production CORS_ORIGINS must contain only HTTPS origins.")
        return self


settings = Settings()
