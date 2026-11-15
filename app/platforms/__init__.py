import httpx

from app.config import Settings
from app.platforms.base import Platform, PlatformError, PublishedPost
from app.platforms.bluesky import BlueskyPlatform
from app.platforms.discord import DiscordPlatform
from app.platforms.github_gist import GitHubGistPlatform
from app.platforms.mastodon import MastodonPlatform
from app.platforms.telegram import TelegramPlatform
from app.platforms.telegraph import TelegraphPlatform

PLATFORM_CLASSES: tuple[type[Platform], ...] = (
    TelegramPlatform,
    DiscordPlatform,
    MastodonPlatform,
    BlueskyPlatform,
    GitHubGistPlatform,
    TelegraphPlatform,
)


def build_platforms(settings: Settings, client: httpx.AsyncClient) -> list[Platform]:
    return [platform_cls(settings, client) for platform_cls in PLATFORM_CLASSES]


__all__ = ["Platform", "PlatformError", "PublishedPost", "PLATFORM_CLASSES", "build_platforms"]
