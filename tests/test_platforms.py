import json

import httpx
import pytest
import respx

from app.config import Settings
from app.platforms import PLATFORM_CLASSES, PlatformError, build_platforms
from app.platforms.bluesky import BlueskyPlatform, link_facet
from app.platforms.discord import DiscordPlatform
from app.platforms.github_gist import GitHubGistPlatform
from app.platforms.mastodon import MastodonPlatform
from app.platforms.telegram import TelegramPlatform
from app.platforms.telegraph import TelegraphPlatform, page_content, page_title
from tests.conftest import LINK, MESSAGE

TELEGRAM_URL = "https://api.telegram.org/bot123:abc/sendMessage"
WEBHOOK_URL = "https://discord.com/api/webhooks/111/secret"


def test_build_platforms_creates_every_integration(settings, client):
    platforms = build_platforms(settings, client)
    assert [type(p) for p in platforms] == list(PLATFORM_CLASSES)
    assert len(platforms) >= 5


def test_missing_settings_are_reported_in_env_format(client):
    platform = TelegramPlatform(Settings(_env_file=None), client)
    assert platform.missing_settings() == ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]


class TestTelegram:
    @respx.mock
    async def test_public_channel(self, settings, client):
        route = respx.post(TELEGRAM_URL).respond(
            json={"ok": True, "result": {"message_id": 42, "chat": {"id": -1001, "username": "dxora_test"}}}
        )

        post = await TelegramPlatform(settings, client).publish(MESSAGE, LINK)

        assert post.url == "https://t.me/dxora_test/42"
        assert post.public is True
        assert json.loads(route.calls.last.request.content) == {"chat_id": "@dxora_test", "text": MESSAGE}

    @respx.mock
    async def test_private_channel(self, settings, client):
        respx.post(TELEGRAM_URL).respond(
            json={"ok": True, "result": {"message_id": 7, "chat": {"id": -1009876543210}}}
        )

        post = await TelegramPlatform(settings, client).publish(MESSAGE, LINK)

        assert post.url == "https://t.me/c/9876543210/7"
        assert post.public is False

    @respx.mock
    async def test_private_chat_has_no_url(self, settings, client):
        respx.post(TELEGRAM_URL).respond(json={"ok": True, "result": {"message_id": 7, "chat": {"id": 555}}})

        post = await TelegramPlatform(settings, client).publish(MESSAGE, LINK)

        assert post.url is None
        assert post.public is False

    @respx.mock
    async def test_api_error_does_not_leak_token(self, settings, client):
        respx.post(TELEGRAM_URL).respond(
            401, json={"ok": False, "error_code": 401, "description": "Unauthorized"}
        )

        with pytest.raises(PlatformError) as exc_info:
            await TelegramPlatform(settings, client).publish(MESSAGE, LINK)

        assert str(exc_info.value) == "HTTP 401: Unauthorized"
        assert "123:abc" not in str(exc_info.value)

    @respx.mock
    async def test_ok_false_with_200(self, settings, client):
        respx.post(TELEGRAM_URL).respond(json={"ok": False, "description": "Bad Request: chat not found"})

        with pytest.raises(PlatformError, match="chat not found"):
            await TelegramPlatform(settings, client).publish(MESSAGE, LINK)


class TestDiscord:
    @respx.mock
    async def test_posts_and_builds_message_link(self, settings, client):
        post_route = respx.post(WEBHOOK_URL, params={"wait": "true"}).respond(
            json={"id": "300", "channel_id": "200", "content": MESSAGE}
        )
        respx.get(WEBHOOK_URL).respond(json={"id": "111", "guild_id": "100", "channel_id": "200"})

        post = await DiscordPlatform(settings, client).publish(MESSAGE, LINK)

        assert post.url == "https://discord.com/channels/100/200/300"
        assert post.public is False
        assert json.loads(post_route.calls.last.request.content) == {
            "content": MESSAGE,
            "allowed_mentions": {"parse": []},
        }

    @respx.mock
    async def test_invalid_webhook(self, settings, client):
        respx.post(WEBHOOK_URL).respond(404, json={"message": "Unknown Webhook", "code": 10015})

        with pytest.raises(PlatformError, match="HTTP 404: Unknown Webhook"):
            await DiscordPlatform(settings, client).publish(MESSAGE, LINK)


class TestMastodon:
    @respx.mock
    async def test_creates_public_status(self, settings, client):
        route = respx.post("https://mastodon.example/api/v1/statuses").respond(
            json={"id": "1", "url": "https://mastodon.example/@dxora/1", "visibility": "public"}
        )

        post = await MastodonPlatform(settings, client).publish(MESSAGE, LINK)

        assert post.url == "https://mastodon.example/@dxora/1"
        assert post.public is True
        request = route.calls.last.request
        assert request.headers["Authorization"] == "Bearer mastodon-token"
        assert request.headers["Idempotency-Key"]
        assert b"visibility=public" in request.content

    @respx.mock
    async def test_unlisted_status_is_not_public(self, settings, client):
        respx.post("https://mastodon.example/api/v1/statuses").respond(
            json={"url": "https://mastodon.example/@dxora/1", "visibility": "unlisted"}
        )

        post = await MastodonPlatform(settings, client).publish(MESSAGE, LINK)

        assert post.public is False

    @respx.mock
    async def test_invalid_token(self, settings, client):
        respx.post("https://mastodon.example/api/v1/statuses").respond(
            401, json={"error": "The access token is invalid"}
        )

        with pytest.raises(PlatformError, match="HTTP 401: The access token is invalid"):
            await MastodonPlatform(settings, client).publish(MESSAGE, LINK)


class TestBluesky:
    @respx.mock
    async def test_creates_session_then_post(self, settings, client):
        respx.post("https://bsky.example/xrpc/com.atproto.server.createSession").respond(
            json={"accessJwt": "jwt", "did": "did:plc:abc", "handle": "dxora.bsky.social"}
        )
        create = respx.post("https://bsky.example/xrpc/com.atproto.repo.createRecord").respond(
            json={"uri": "at://did:plc:abc/app.bsky.feed.post/3kxyz", "cid": "bafy"}
        )

        post = await BlueskyPlatform(settings, client).publish(MESSAGE, LINK)

        assert post.url == "https://bsky.app/profile/dxora.bsky.social/post/3kxyz"
        assert post.public is True

        request = create.calls.last.request
        body = json.loads(request.content)
        assert request.headers["Authorization"] == "Bearer jwt"
        assert body["repo"] == "did:plc:abc"
        assert body["record"]["text"] == MESSAGE
        assert body["record"]["createdAt"].endswith("Z")
        assert body["record"]["facets"] == [link_facet(MESSAGE, LINK)]

    @respx.mock
    async def test_bad_credentials(self, settings, client):
        respx.post("https://bsky.example/xrpc/com.atproto.server.createSession").respond(
            401, json={"error": "AuthenticationRequired", "message": "Invalid identifier or password"}
        )

        with pytest.raises(PlatformError, match="Invalid identifier or password"):
            await BlueskyPlatform(settings, client).publish(MESSAGE, LINK)

    def test_link_facet_uses_utf8_byte_offsets(self):
        message = "Café ☕ https://example.com"
        facet = link_facet(message, LINK)

        start, end = facet["index"]["byteStart"], facet["index"]["byteEnd"]
        assert message.encode()[start:end].decode() == LINK
        assert start == len("Café ☕ ".encode())


class TestGitHubGist:
    @respx.mock
    async def test_creates_public_gist(self, settings, client):
        route = respx.post("https://api.github.com/gists").respond(
            201, json={"html_url": "https://gist.github.com/dxora/abc", "public": True}
        )

        post = await GitHubGistPlatform(settings, client).publish(MESSAGE, LINK)

        assert post.url == "https://gist.github.com/dxora/abc"
        assert post.public is True
        body = json.loads(route.calls.last.request.content)
        assert body["public"] is True
        assert body["files"]["post.md"]["content"] == MESSAGE

    @respx.mock
    async def test_bad_token(self, settings, client):
        respx.post("https://api.github.com/gists").respond(401, json={"message": "Bad credentials"})

        with pytest.raises(PlatformError, match="HTTP 401: Bad credentials"):
            await GitHubGistPlatform(settings, client).publish(MESSAGE, LINK)


class TestTelegraph:
    @respx.mock
    async def test_creates_page(self, settings, client):
        route = respx.post("https://api.telegra.ph/createPage").respond(
            json={
                "ok": True,
                "result": {"url": "https://telegra.ph/Check-out-11-15", "path": "Check-out-11-15"},
            }
        )

        post = await TelegraphPlatform(settings, client).publish(MESSAGE, LINK)

        assert post.url == "https://telegra.ph/Check-out-11-15"
        assert post.public is True
        body = json.loads(route.calls.last.request.content)
        assert body["author_name"] == "Dxora"
        assert body["content"] == page_content(MESSAGE, LINK)

    @respx.mock
    async def test_ok_false_is_an_error(self, settings, client):
        respx.post("https://api.telegra.ph/createPage").respond(
            json={"ok": False, "error": "ACCESS_TOKEN_INVALID"}
        )

        with pytest.raises(PlatformError, match="ACCESS_TOKEN_INVALID"):
            await TelegraphPlatform(settings, client).publish(MESSAGE, LINK)

    def test_page_title_drops_the_link(self):
        assert (
            page_title(MESSAGE, LINK)
            == "Check out our latest business platform and grow your online visibility."
        )
        assert page_title(LINK, LINK) == "Announcement"

    def test_page_content_wraps_link_in_anchor(self):
        assert page_content("Go https://example.com now", LINK) == [
            {
                "tag": "p",
                "children": ["Go ", {"tag": "a", "attrs": {"href": LINK}, "children": [LINK]}, " now"],
            }
        ]


class TestEnsureOk:
    @respx.mock
    async def test_non_json_error_uses_reason_phrase(self, settings, client):
        respx.post("https://api.github.com/gists").respond(502, text="<html>Bad gateway</html>")

        with pytest.raises(PlatformError, match="HTTP 502: Bad Gateway"):
            await GitHubGistPlatform(settings, client).publish(MESSAGE, LINK)

    @respx.mock
    async def test_success_with_non_object_body_is_an_error(self, settings, client):
        respx.post("https://api.github.com/gists").respond(200, json=["unexpected"])

        with pytest.raises(PlatformError, match="HTTP 200"):
            await GitHubGistPlatform(settings, client).publish(MESSAGE, LINK)

    @respx.mock
    async def test_network_errors_propagate_to_caller(self, settings, client):
        respx.post("https://api.github.com/gists").mock(side_effect=httpx.ConnectError("boom"))

        with pytest.raises(httpx.ConnectError):
            await GitHubGistPlatform(settings, client).publish(MESSAGE, LINK)
