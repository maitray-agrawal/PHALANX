"""Configuration and environment settings with strict security boundaries.

Rule: No secret defaults in code. Secrets must be injected via environment.
"""

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
    allowed_hosts: str = Field(default="*")
    database_url: str = Field(
        default="postgresql+psycopg://phalanx_app:phalanx_app_password@localhost:5432/phalanx_db"
    )

    # Security: No secret defaults! Must be supplied via environment/.env
    secret_key: str = Field(default="")
    paypal_client_id: str = Field(default="")
    paypal_client_secret: str = Field(default="")
    paypal_webhook_id: str = Field(default="")
    paypal_environment: str = Field(default="sandbox")

    # Mandate Ed25519 Signing Key (never logged or defaulted to static secret)
    mandate_signing_key_hex: str = Field(default="")
    mandate_signing_key_file: str = Field(default="")


settings = Settings()
