from __future__ import annotations

from typing import List, Optional
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven SmartNet configuration.

    SQLite is reserved for local/test use. Production runs on MariaDB and
    refuses demo payment, demo MikroTik and non-TLS router connections.
    """

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
    MIKROTIK_USERNAME: str = "smartnet-monitor"
    MIKROTIK_PASSWORD: str = ""
    MIKROTIK_PORT: int = 8729
    MIKROTIK_DEMO_MODE: bool = True
    MIKROTIK_USE_SSL: bool = True
    MIKROTIK_SSL_VERIFY: bool = True
    MIKROTIK_SSL_VERIFY_HOSTNAME: bool = True
    SSID: str = "SmartNet-WiFi"

    DATABASE_BACKEND: str = "sqlite"
    DATABASE_URL: Optional[str] = None
    MARIADB_HOST: str = "127.0.0.1"
    MARIADB_PORT: int = 3306
    MARIADB_DATABASE: str = "smartnet"
    MARIADB_USER: str = "smartnet"
    MARIADB_PASSWORD: str = ""

    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_ADMIN_IDS: List[int] = Field(default_factory=list)
    BOT_API_BASE_URL: str = "http://127.0.0.1:8000"

    SUBSCRIPTION_AGENT_DELAY_SECONDS: int = 60
    SUBSCRIPTION_AGENT_INTERVAL_SECONDS: int = 30

    NETWORK_MONITOR_ENABLED: bool = False
    NETWORK_MONITOR_INTERVAL_SECONDS: int = 60
    NETWORK_CPU_ALERT_THRESHOLD: int = 85
    NETWORK_ACTIVE_USERS_ALERT_THRESHOLD: int = 500
    NETWORK_ALERT_COOLDOWN_SECONDS: int = 900

    METRICS_ENABLED: bool = True
    SENTRY_DSN: Optional[str] = None
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = None

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
    def validate_configuration(self) -> "Settings":
        if self.DATABASE_BACKEND not in {"sqlite", "mariadb"}:
            raise ValueError("DATABASE_BACKEND must be sqlite or mariadb.")
        if self.MIKROTIK_PORT < 1 or self.MIKROTIK_PORT > 65535:
            raise ValueError("MIKROTIK_PORT must be a valid TCP port.")
        if self.NETWORK_MONITOR_INTERVAL_SECONDS < 15:
            raise ValueError("NETWORK_MONITOR_INTERVAL_SECONDS must be at least 15 seconds.")
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
                raise ValueError("Production configuration contains missing/default secrets: " + ", ".join(weak))
            if len(self.SECRET_KEY) < 32 or len(self.PAYMENT_WEBHOOK_SECRET) < 32:
                raise ValueError("Production secrets must each contain at least 32 characters.")
            if self.PAYMENT_DEMO_MODE:
                raise ValueError("PAYMENT_DEMO_MODE must be false in production.")
            if self.MIKROTIK_DEMO_MODE:
                raise ValueError("MIKROTIK_DEMO_MODE must be false in production.")
            if not self.MIKROTIK_PASSWORD:
                raise ValueError("MIKROTIK_PASSWORD is required in production.")
            if not self.MIKROTIK_USE_SSL or not self.MIKROTIK_SSL_VERIFY or not self.MIKROTIK_SSL_VERIFY_HOSTNAME:
                raise ValueError("Production MikroTik connections must use verified TLS.")
            if self.DATABASE_BACKEND != "mariadb" and not (
                self.DATABASE_URL and self.DATABASE_URL.startswith("mysql+asyncmy://")
            ):
                raise ValueError("Production must use MariaDB via mysql+asyncmy.")
            if self.DATABASE_BACKEND == "mariadb" and not all([
                self.MARIADB_HOST, self.MARIADB_DATABASE, self.MARIADB_USER, self.MARIADB_PASSWORD
            ]):
                raise ValueError("MARIADB_HOST, MARIADB_DATABASE, MARIADB_USER and MARIADB_PASSWORD are required.")
            if self.PAYMENT_PROVIDER_MODE not in {"manual", "gateway"}:
                raise ValueError("PAYMENT_PROVIDER_MODE must be manual or gateway.")
            if self.PAYMENT_PROVIDER_MODE == "gateway" and not self.PAYMENT_CHECKOUT_URL:
                raise ValueError("PAYMENT_CHECKOUT_URL is required when PAYMENT_PROVIDER_MODE=gateway.")
            if len(self.DASHBOARD_PASSWORD) < 12:
                raise ValueError("DASHBOARD_PASSWORD must contain at least 12 characters.")
            if self.DASHBOARD_USERNAME.strip().lower() in {"admin", "administrator"}:
                raise ValueError("Set a unique non-default DASHBOARD_USERNAME in production.")
            if not self.CORS_ORIGINS or any(not origin.startswith("https://") for origin in self.CORS_ORIGINS):
                raise ValueError("Production CORS_ORIGINS must contain only exact HTTPS origins.")
        return self


settings = Settings()
