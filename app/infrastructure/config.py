"""Configuration and environment settings with strict security boundaries.

Rule: No secret defaults in code. Secrets must be injected via environment.
"""

from pydantic import Field, field_validator
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
    database_url: str = Field(default="postgresql+psycopg://phalanx_app@localhost:5433/phalanx_db")
    postgres_password: str = Field(
        default="", description="PostgreSQL password required for application database access"
    )
    phalanx_app_db_password: str = Field(
        default="", description="PostgreSQL application password for phalanx_app"
    )
    postgres_port: int = Field(default=5433, description="PostgreSQL port (default host 5433)")
    app_port: int = Field(default=8000, description="Application HTTP server port")
    payment_rail: str = Field(
        default="paypal",
        description="Active payment rail provider: 'paypal' or 'fake'",
    )
    demo_mode: bool = Field(
        default=False,
        description="Demo mode: allows visitor role switching and simulated tampering",
    )
    demo_seed: bool = Field(
        default=False,
        description="Explicitly enable demo seed data injection",
    )
    forwarded_allow_ips: str = Field(
        default="127.0.0.1,::1",
        description="Comma-separated IPs or subnets trusted for X-Forwarded-For headers",
    )
    trusted_proxy_count: int = Field(
        default=0,
        description="Number of reverse proxies; 0 disables X-Forwarded-For chaining",
    )
    demo_token_rate_limit: int = Field(
        default=15,
        description="Default rate limit per client IP for demo token dispensing (req/min)",
    )
    reconciler_enabled: bool = Field(
        default=False,
        description="Enable periodic background reconciliation loop (off in tests)",
    )
    reconcile_max_age_seconds: int = Field(
        default=86400,
        description="Max age in seconds before ambiguous requests mark NEEDS_REVIEW",
    )
    reconcile_interval_seconds: int = Field(
        default=60,
        description="Interval in seconds for periodic background reconciliation loop",
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        if isinstance(v, str):
            if v.startswith("postgres://"):
                return "postgresql+psycopg://" + v[len("postgres://") :]
            if v.startswith("postgresql://") and not v.startswith("postgresql+psycopg://"):
                return "postgresql+psycopg://" + v[len("postgresql://") :]
        return v

    # Security: No secret defaults! Must be supplied via environment/.env
    secret_key: str = Field(default="")
    admin_token: str = Field(default="", description="Token for administrative endpoints")
    paypal_client_id: str = Field(default="")
    paypal_client_secret: str = Field(default="")
    paypal_webhook_id: str = Field(default="")
    paypal_environment: str = Field(default="sandbox")

    # Mandate Ed25519 Signing Key (never logged or defaulted to static secret)
    mandate_signing_key_hex: str = Field(default="")
    mandate_signing_key_file: str = Field(default="")

    # LLM & AI Guardrails (Manual 41-44)
    llm_model_name: str = Field(default="gpt-4o-mini")
    llm_timeout_seconds: float = Field(default=5.0)
    llm_max_retries: int = Field(default=2)
    llm_token_cap_per_identity: int = Field(default=50_000)
    llm_cost_cap_dollars_per_identity: float = Field(default=2.0)


settings = Settings()
