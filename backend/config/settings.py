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
    MIKROTIK_MONITOR_USERNAME: str = "smartnet-monitor"
    MIKROTIK_MONITOR_PASSWORD: str = ""
    MIKROTIK_OPERATOR_USERNAME: str = ""
    MIKROTIK_OPERATOR_PASSWORD: str = ""
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
    MARIADB_ROOT_PASSWORD: str = ""

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
    NETWORK_SNAPSHOT_RETENTION_DAYS: int = Field(default=30, ge=7, le=365)

    METRICS_ENABLED: bool = True
    METRICS_TOKEN: str = ""
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
            if not all([self.MIKROTIK_MONITOR_USERNAME, self.MIKROTIK_MONITOR_PASSWORD, self.MIKROTIK_OPERATOR_USERNAME, self.MIKROTIK_OPERATOR_PASSWORD]):
                raise ValueError("Separate read-only MIKROTIK_MONITOR_* and write-capable MIKROTIK_OPERATOR_* credentials are required.")
            if self.MIKROTIK_MONITOR_USERNAME == self.MIKROTIK_OPERATOR_USERNAME:
                raise ValueError("MikroTik monitor and operator accounts must be distinct.")
            if len(self.MIKROTIK_MONITOR_PASSWORD) < 16 or len(self.MIKROTIK_OPERATOR_PASSWORD) < 16:
                raise ValueError("MikroTik monitor and operator passwords must each contain at least 16 characters.")
            if not self.MIKROTIK_USE_SSL or not self.MIKROTIK_SSL_VERIFY or not self.MIKROTIK_SSL_VERIFY_HOSTNAME:
                raise ValueError("Production MikroTik connections must use verified TLS.")
            if self.DATABASE_BACKEND != "mariadb":
                raise ValueError("Production must use MariaDB via DATABASE_BACKEND=mariadb.")
            if self.DATABASE_URL and not self.DATABASE_URL.startswith("mysql+asyncmy://"):
                raise ValueError("When set, DATABASE_URL must use the mysql+asyncmy dialect.")
            if not all([
                self.MARIADB_HOST, self.MARIADB_DATABASE, self.MARIADB_USER, self.MARIADB_PASSWORD
            ]):
                raise ValueError("MARIADB_HOST, MARIADB_DATABASE, MARIADB_USER and MARIADB_PASSWORD are required.")
            if (
                len(self.MARIADB_PASSWORD) < 16
                or self.MARIADB_PASSWORD.startswith("dev-only-")
                or self.MARIADB_PASSWORD.lower() in {"password", "changeme", "smartnet"}
            ):
                raise ValueError("MARIADB_PASSWORD must be a strong unique secret with at least 16 characters.")
            # The application connects with the restricted database user and must
            # never receive the MariaDB root secret. Compose supplies the root
            # secret only to the database service; validate it here only when an
            # operator explicitly provides it to a standalone environment.
            if self.MARIADB_ROOT_PASSWORD:
                if (
                    len(self.MARIADB_ROOT_PASSWORD) < 20
                    or self.MARIADB_ROOT_PASSWORD.startswith("dev-only-")
                    or self.MARIADB_ROOT_PASSWORD.lower() in {"password", "changeme", "smartnet"}
                ):
                    raise ValueError("MARIADB_ROOT_PASSWORD must contain at least 20 characters.")
                if self.MARIADB_PASSWORD == self.MARIADB_ROOT_PASSWORD:
                    raise ValueError("MariaDB application and root passwords must be different.")
            if self.METRICS_ENABLED and len(self.METRICS_TOKEN) < 32:
                raise ValueError("METRICS_TOKEN must contain at least 32 characters when metrics are enabled.")
            if self.PAYMENT_PROVIDER_MODE != "manual":
                raise ValueError("Production currently supports operational manual payment only; gateway mode requires a provider-specific verified adapter.")
            if len(self.DASHBOARD_PASSWORD) < 12:
                raise ValueError("DASHBOARD_PASSWORD must contain at least 12 characters.")
            if self.DASHBOARD_USERNAME.strip().lower() in {"admin", "administrator"}:
                raise ValueError("Set a unique non-default DASHBOARD_USERNAME in production.")
            if not self.CORS_ORIGINS or any(not origin.startswith("https://") for origin in self.CORS_ORIGINS):
                raise ValueError("Production CORS_ORIGINS must contain only exact HTTPS origins.")
        return self


settings = Settings()
