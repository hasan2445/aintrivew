import os
import secrets as _secrets
from typing import List, Optional

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from environment variables.

    All critical secrets and configurable parameters are defined here. Using
    Pydantic's validation ensures the app fails fast if required values are
    missing or malformed. In development a random JWT secret is generated so the
    app still boots; in production a real ``JWT_SECRET_KEY`` is mandatory.
    """

    app_name: str = Field(default="InterviewAI", description="Application name")
    environment: str = Field(default="development", description="Running environment (development / production)")
    debug: bool = Field(default=False, description="Enable FastAPI debug mode")

    database_url: str = Field(..., description="SQLAlchemy connection URL")

    # Default is a per-process random value so a forgotten secret never silently
    # becomes a well-known one. Tokens simply do not survive a restart in dev.
    jwt_secret_key: SecretStr = Field(
        default_factory=lambda: SecretStr(_secrets.token_urlsafe(48)),
        description="Secret key for signing JWTs",
    )
    jwt_algorithm: str = Field(default="HS256", description="Algorithm for JWT encoding")
    # Was 60, which is inside the plausible length of a 12-question interview
    # with up to three follow-ups each. Hitting the cliff mid-interview logged
    # the candidate out and discarded the session id, so the still-live Redis
    # session became unreachable. 480 sits comfortably past the 6-hour session
    # TTL, and /api/auth/refresh renews it during long sessions.
    access_token_expire_minutes: int = Field(default=480, ge=1, description="JWT expiry in minutes")

    groq_api_key: SecretStr = Field(..., description="Groq API key for LLM calls")
    # Configurable on purpose. This was hardcoded to llama-3.3-70b-versatile,
    # which Groq later decommissioned — the failure surfaced only as a 502 from
    # /api/upload-resume with "model_not_found" buried in the server log. A
    # provider retiring a model is routine; needing a code change and a rebuild
    # to survive it is not.
    groq_model: str = Field(default="openai/gpt-oss-120b", description="Groq chat model id")
    # Reserved output budget. Groq counts max_tokens against the per-minute
    # token limit *before* the call runs, so an oversized value fails with a 413
    # rather than merely wasting headroom. 8000 was sized for a different model
    # and exceeded the free tier's 8k TPM on its own. Question generation is the
    # only call that needs real room: 8-12 question objects plus a profile.
    groq_max_tokens: int = Field(default=4000, ge=256, le=32000, description="Max output tokens per LLM call")

    # Optional: text-to-speech returns 503 when this is unset rather than
    # falling back to a baked-in key.
    elevenlabs_api_key: Optional[SecretStr] = Field(default=None, description="ElevenLabs API key for TTS")

    redis_url: Optional[str] = Field(default=None, description="Redis connection URL, e.g., redis://localhost:6379/0")
    session_ttl_seconds: int = Field(default=60 * 60 * 6, ge=60, description="Expiry for stored interview sessions")

    # Comma-separated list, or "*" (only honoured outside production).
    cors_allow_origins: str = Field(default="http://localhost:8000,http://127.0.0.1:8000")

    max_upload_size_mb: int = Field(default=10, ge=1, le=100, description="Maximum resume upload size")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "case_sensitive": False,
    }

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_env_aliases(cls, values):
        """Accept historical env var spellings so existing .env files keep working."""
        if not isinstance(values, dict):
            return values
        aliases = {
            "elevenlabs_api_key": ("ELEVEN_LABS_API_KEY", "ELEVENLABS_API_KEY"),
        }
        lowered = {str(k).lower() for k in values}
        for target, env_names in aliases.items():
            if target in lowered:
                continue
            for env_name in env_names:
                found = os.getenv(env_name)
                if found:
                    values[target] = found
                    break
        return values

    @field_validator("environment")
    @classmethod
    def _normalise_environment(cls, v: str) -> str:
        v = (v or "development").strip().lower()
        if v in {"prod", "production"}:
            return "production"
        if v in {"test", "testing"}:
            return "testing"
        return "development"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def allowed_origins(self) -> List[str]:
        raw = (self.cors_allow_origins or "").strip()
        if not raw:
            return []
        origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
        if "*" in origins:
            # A wildcard origin cannot be combined with credentialed requests, and
            # is never appropriate in production.
            if self.is_production:
                raise ValueError(
                    "CORS_ALLOW_ORIGINS='*' is not permitted when ENVIRONMENT=production. "
                    "List the explicit frontend origins instead."
                )
            return ["*"]
        return origins

    @model_validator(mode="after")
    def _require_real_secrets_in_production(self):
        if self.is_production:
            secret = self.jwt_secret_key.get_secret_value()
            if not secret or secret in {"dev-secret", "changeme", "secret"} or len(secret) < 32:
                raise ValueError(
                    "JWT_SECRET_KEY must be set to a strong value (>=32 chars) when ENVIRONMENT=production."
                )
            if self.debug:
                raise ValueError("DEBUG must be false when ENVIRONMENT=production.")
        return self


settings = Settings()
