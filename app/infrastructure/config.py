"""Configuration and environment settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable overrides."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")
    secret_key: str = Field(default="insecure-dev-key-must-be-changed-in-production")
    allowed_hosts: str = Field(default="*")
    database_url: str = Field(
        default="postgresql+psycopg://phalanx_app:phalanx_app_password@localhost:5432/phalanx_db"
    )

    # PayPal Sandbox Configuration
    paypal_client_id: str = Field(default="")
    paypal_client_secret: str = Field(default="")
    paypal_webhook_id: str = Field(default="")
    paypal_environment: str = Field(default="sandbox")


settings = Settings()
