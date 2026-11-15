import httpx
import pytest

from app.config import Settings

MESSAGE = "Check out our latest business platform and grow your online visibility. https://example.com"
LINK = "https://example.com"


@pytest.fixture
def settings() -> Settings:
    # _env_file=None keeps a developer's real .env out of the tests.
    return Settings(
        _env_file=None,
        telegram_bot_token="123:abc",
        telegram_chat_id="@dxora_test",
        discord_webhook_url="https://discord.com/api/webhooks/111/secret",
        mastodon_base_url="https://mastodon.example",
        mastodon_access_token="mastodon-token",
        bluesky_service_url="https://bsky.example",
        bluesky_handle="dxora.bsky.social",
        bluesky_app_password="app-pass",
        github_token="gh-token",
        telegraph_access_token="telegraph-token",
        telegraph_author_name="Dxora",
    )


@pytest.fixture
async def client():
    async with httpx.AsyncClient() as http_client:
        yield http_client
