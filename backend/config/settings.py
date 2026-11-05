from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List

class Settings(BaseSettings):
    # API Security
    SECRET_KEY: str = "smartnet-super-secret-key-change-in-production-2024"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440 # 1 day
    PAYMENT_WEBHOOK_SECRET: str = "smartnet-webhook-secret-key"
    PAYMENT_CHECKOUT_URL: Optional[str] = None
    PAYMENT_DEMO_MODE: bool = True
    APP_PUBLIC_URL: str = "http://127.0.0.1:5173"
    SUBSCRIPTION_AGENT_DELAY_SECONDS: int = 60
    SUBSCRIPTION_AGENT_INTERVAL_SECONDS: int = 10
    AUTO_APPROVAL_DAYS: int = 30

    # Default Dashboard Credentials
    DASHBOARD_USERNAME: str = "admin"
    DASHBOARD_PASSWORD: str = "admin123"

    # MikroTik
    MIKROTIK_HOST: str = "192.168.88.1"
    MIKROTIK_USERNAME: str = "admin"
    MIKROTIK_PASSWORD: str = ""
    MIKROTIK_PORT: int = 8728
    MIKROTIK_DEMO_MODE: bool = True
    SSID: str = "SmartNet-WiFi"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./smartnet.db"

    # AI & Integrations
    OPENAI_API_KEY: Optional[str] = None

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()

