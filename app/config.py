import re
from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DISCORD_WEBHOOK = re.compile(r"^https://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+$")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Validation errors would otherwise echo the raw value, secrets included.
        hide_input_in_errors=True,
    )

    request_timeout: float = Field(default=15.0, gt=0, le=120)

    # When set, every request must send it in the X-API-Key header.
    api_key: SecretStr | None = None
    rate_limit_per_minute: int = Field(default=10, ge=1)

    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None

    discord_webhook_url: SecretStr | None = None

    mastodon_base_url: str = "https://mastodon.social"
    mastodon_access_token: SecretStr | None = None

    bluesky_service_url: str = "https://bsky.social"
    bluesky_handle: str | None = None
    bluesky_app_password: SecretStr | None = None

    github_token: SecretStr | None = None

    telegraph_access_token: SecretStr | None = None
    telegraph_author_name: str | None = None

    @field_validator("mastodon_base_url", "bluesky_service_url")
    @classmethod
    def require_https(cls, value: str) -> str:
        # These hosts receive bearer tokens, so plain http would leak them.
        if not value.startswith("https://"):
            raise ValueError("must start with https://")
        return value.rstrip("/")

    @field_validator("discord_webhook_url")
    @classmethod
    def validate_discord_webhook(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not _DISCORD_WEBHOOK.match(value.get_secret_value()):
            raise ValueError("must look like https://discord.com/api/webhooks/<id>/<token>")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
