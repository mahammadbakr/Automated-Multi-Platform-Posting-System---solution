from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

import httpx

from app.config import Settings


class PlatformError(Exception):
    """Raised when a platform rejects a post or returns something we can't use."""


@dataclass(frozen=True)
class PublishedPost:
    url: str | None
    public: bool


class Platform(ABC):
    name: ClassVar[str]
    required_settings: ClassVar[tuple[str, ...]] = ()

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.client = client

    def missing_settings(self) -> list[str]:
        return [key.upper() for key in self.required_settings if not getattr(self.settings, key)]

    @abstractmethod
    async def publish(self, message: str, link: str) -> PublishedPost:
        """Publish the message and return where it ended up."""

    @staticmethod
    def ensure_ok(response: httpx.Response) -> dict:
        """Return the JSON body or raise a PlatformError with the API's own error text.

        We deliberately don't use response.raise_for_status(): its message contains the
        request URL, which for Telegram and Discord embeds the secret token.
        """
        try:
            body = response.json()
        except ValueError:
            body = None

        if response.is_success and isinstance(body, dict):
            return body

        detail = _extract_error(body) or response.reason_phrase or "Unexpected response"
        raise PlatformError(f"HTTP {response.status_code}: {detail}")


def _extract_error(body: object) -> str | None:
    if not isinstance(body, dict):
        return None
    for key in ("description", "error_description", "message", "error"):
        value = body.get(key)
        if isinstance(value, str) and value:
            return value
    return None
