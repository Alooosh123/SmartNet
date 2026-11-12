from __future__ import annotations

import re
from typing import List, Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """SmartNet configuration. SQLite is development/test only; production uses MariaDB."""

    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    SECRET_KEY: str = "dev-only-change-me-before-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    PAYMENT_WEBHOOK_SECRET: str = "dev-only-change-me-before-production"
    PAYMENT_PROVIDER_MODE: str = "manual"
    PAYMENT_CHECKOUT_URL: Optional[str] = None
    PAYMENT_DEMO_MODE: bool = True
    APP_PUBLIC_URL: str = "http://127.0.0.1:5173"

    DASHBOARD_USERNAME: str = "admin"
    DASHBOARD_PASSWORD: str = "dev-only-SmartNet-Admin-Change-This-2026!"

    MIKROTIK_HOST: str = "192.168.88.1"
    MIKROTIK_USERNAME: str = "admin"
    MIKROTIK_PASSWORD: str = ""
    MIKROTIK_READ_USERNAME: Optional[str] = None
    MIKROTIK_READ_PASSWORD: Optional[str] = None
    MIKROTIK_PORT: int = 8728
    MIKROTIK_DEMO_MODE: bool = True
    MIKROTIK_USE_SSL: bool = False
    SSID: str = "SmartNet-WiFi"

    DATABASE_URL: str = "sqlite+aiosqlite:///./smartnet.db"
    MARIADB_DATABASE: str = "smartnet"
    MARIADB_USER: str = "smartnet"
    MARIADB_PASSWORD: Optional[str] = None
    MARIADB_ROOT_PASSWORD: Optional[str] = None

    NETWORK_MONITOR_ENABLED: bool = False
    NETWORK_MONITOR_INTERVAL_SECONDS: int = 60
    NETWORK_CPU_ALERT_THRESHOLD: int = 85
    NETWORK_FREE_MEMORY_ALERT_PERCENT: int = 10

    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_ADMIN_IDS: List[int] = Field(default_factory=list)
    BOT_API_BASE_URL: str = "http://127.0.0.1:8000"

    SUBSCRIPTION_AGENT_DELAY_SECONDS: int = 60
    SUBSCRIPTION_AGENT_INTERVAL_SECONDS: int = 30

    CORS_ORIGINS: List[str] = Field(default_factory=lambda: [
        "http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173",
    ])

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=True)

    @model_validator(mode="after")
    def validate_configuration(self) -> "Settings":
        if self.NETWORK_MONITOR_INTERVAL_SECONDS < 15:
            raise ValueError("NETWORK_MONITOR_INTERVAL_SECONDS must be at least 15 seconds.")
        if not 1 <= self.NETWORK_CPU_ALERT_THRESHOLD <= 100:
            raise ValueError("NETWORK_CPU_ALERT_THRESHOLD must be between 1 and 100.")
        if not 1 <= self.NETWORK_FREE_MEMORY_ALERT_PERCENT <= 100:
            raise ValueError("NETWORK_FREE_MEMORY_ALERT_PERCENT must be between 1 and 100.")
        if self.ENVIRONMENT.lower() == "production":
            secrets = {
                "SECRET_KEY": self.SECRET_KEY,
                "PAYMENT_WEBHOOK_SECRET": self.PAYMENT_WEBHOOK_SECRET,
                "DASHBOARD_PASSWORD": self.DASHBOARD_PASSWORD,
            }
            weak = [
                key for key, value in secrets.items()
                if not value or value.startswith("dev-only-") or value in {"admin123", "password", "changeme"}
            ]
            if weak:
                raise ValueError("Production contains missing/default secrets: " + ", ".join(weak))
            if len(self.SECRET_KEY) < 32 or len(self.PAYMENT_WEBHOOK_SECRET) < 32:
                raise ValueError("Production secrets must each contain at least 32 characters.")
            if self.PAYMENT_DEMO_MODE:
                raise ValueError("PAYMENT_DEMO_MODE must be false in production.")
            if self.PAYMENT_PROVIDER_MODE != "manual":
                raise ValueError("Only manual payment mode is enabled until a real provider adapter passes contract tests.")
            if self.MIKROTIK_DEMO_MODE:
                raise ValueError("MIKROTIK_DEMO_MODE must be false in production.")
            if not self.MIKROTIK_PASSWORD:
                raise ValueError("MIKROTIK_PASSWORD is required in production.")
            if not self.MIKROTIK_READ_USERNAME or not self.MIKROTIK_READ_PASSWORD:
                raise ValueError("Dedicated read-only RouterOS credentials are required in production.")
            if self.MIKROTIK_READ_USERNAME == self.MIKROTIK_USERNAME:
                raise ValueError("The RouterOS observer account must be separate from the control account.")
            if not self.MIKROTIK_USE_SSL or self.MIKROTIK_PORT != 8729:
                raise ValueError("Production MikroTik must use API-SSL on port 8729.")
            if not self.DATABASE_URL.startswith("mysql+asyncmy://"):
                raise ValueError("Production DATABASE_URL must use MariaDB via mysql+asyncmy.")
            if not self.MARIADB_PASSWORD or len(self.MARIADB_PASSWORD) < 24 or not re.fullmatch(r"[A-Za-z0-9]{24,}", self.MARIADB_PASSWORD):
                raise ValueError("MARIADB_PASSWORD must be URL-safe alphanumeric and at least 24 characters.")
            if not self.MARIADB_ROOT_PASSWORD or len(self.MARIADB_ROOT_PASSWORD) < 24:
                raise ValueError("MARIADB_ROOT_PASSWORD must be at least 24 characters.")
            if self.DASHBOARD_USERNAME.strip().lower() in {"admin", "administrator"}:
                raise ValueError("Set a unique non-default DASHBOARD_USERNAME.")
            if len(self.DASHBOARD_PASSWORD) < 12:
                raise ValueError("DASHBOARD_PASSWORD must contain at least 12 characters.")
            if not self.CORS_ORIGINS or any(not x.startswith("https://") for x in self.CORS_ORIGINS):
                raise ValueError("Production CORS_ORIGINS must contain exact HTTPS origins only.")
            if not self.APP_PUBLIC_URL.startswith("https://"):
                raise ValueError("APP_PUBLIC_URL must use HTTPS in production.")
        return self


settings = Settings()
