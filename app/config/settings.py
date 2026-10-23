from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Bot & Telegram
    TELEGRAM_BOT_TOKEN: str = Field(default="1234567890:ABCdefGHIjklMNOpqrsTUVwxyz", description="Telegram Bot Token from @BotFather")
    SUPER_ADMIN_TELEGRAM_ID: int = Field(default=0, description="Telegram ID of the primary Super Admin")
    SUPPORT_TELEGRAM_USERNAME: str = Field(default="sharkklee", description="Admin Telegram username for customer support")

    # App
    ENVIRONMENT: str = Field(default="development", description="Environment: development or production")
    DEBUG: bool = Field(default=True)
    APP_SECRET_KEY: str = Field(default="mtk-super-secret-key-change-in-production-min-32-chars")
    PORT: int = Field(default=8000)
    HOST: str = Field(default="0.0.0.0")
    WEB_BASE_URL: str = Field(default="http://localhost:8000")

    # Database
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./mtk_bot.db",
        description="SQLAlchemy async connection URL (sqlite+aiosqlite or postgresql+asyncpg)"
    )

    # SePay Payment Gateway
    SEPAY_API_KEY: str = Field(default="sepay_api_key_demo", description="SePay API Key")
    SEPAY_BANK_ACCOUNT: str = Field(default="0123456789", description="Bank account number for QR")
    SEPAY_BANK_NAME: str = Field(default="MBBank", description="Bank code / name (MBBank, VCB, TCB,...)")
    SEPAY_ACCOUNT_NAME: str = Field(default="MTK STORE", description="Bank account owner name")
    ALLOW_TEST_PAYMENTS: bool = Field(default=False, description="Allow test payments - strictly false in production")

    # Admin Dashboard
    ADMIN_DEFAULT_USERNAME: str = Field(default="admin")
    ADMIN_DEFAULT_PASSWORD: str = Field(default="Admin@MTK2026!")
    JWT_EXPIRE_MINUTES: int = Field(default=1440)
    JWT_ALGORITHM: str = Field(default="HS256")

    # Business Rules
    ORDER_EXPIRE_MINUTES: int = Field(default=15)
    DEFAULT_AFFILIATE_COMMISSION_PERCENT: float = Field(default=10.0)

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


settings = Settings()
