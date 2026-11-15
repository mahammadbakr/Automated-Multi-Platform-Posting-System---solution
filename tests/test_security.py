import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.main import app, get_posting_service
from app.middleware import BodySizeLimitMiddleware
from app.security import RateLimiter
from tests.conftest import MESSAGE
from tests.test_posting import StubService

SECRET_WEBHOOK = "https://discord.com/api/webhooks/123/super-secret-token"


class TestSettingsValidation:
    @pytest.mark.parametrize("field", ["mastodon_base_url", "bluesky_service_url"])
    def test_token_hosts_must_use_https(self, field):
        with pytest.raises(ValidationError, match="must start with https://"):
            Settings(_env_file=None, **{field: "http://insecure.example"})

    def test_trailing_slash_is_removed(self):
        assert Settings(_env_file=None, mastodon_base_url="https://m.example/").mastodon_base_url == (
            "https://m.example"
        )

    @pytest.mark.parametrize(
        "url",
        [
            SECRET_WEBHOOK,
            "https://discordapp.com/api/webhooks/1/abc_DEF-123",
            "https://canary.discord.com/api/webhooks/1/abc",
        ],
    )
    def test_accepts_discord_webhooks(self, url):
        assert Settings(_env_file=None, discord_webhook_url=url).discord_webhook_url.get_secret_value() == url

    @pytest.mark.parametrize(
        "url",
        [
            "http://discord.com/api/webhooks/1/abc",
            "https://evil.example/api/webhooks/1/abc",
            "https://discord.com.evil.example/api/webhooks/1/abc",
            "https://discord.com/api/webhooks/1/abc?x=1",
            "not a url",
        ],
    )
    def test_rejects_other_webhook_urls(self, url):
        with pytest.raises(ValidationError, match="must look like"):
            Settings(_env_file=None, discord_webhook_url=url)

    def test_validation_error_does_not_print_the_secret(self):
        with pytest.raises(ValidationError) as exc_info:
            Settings(_env_file=None, discord_webhook_url="https://evil.example/api/webhooks/1/super-secret")
        assert "super-secret" not in str(exc_info.value)

    def test_secrets_are_masked_in_repr(self):
        settings = Settings(_env_file=None, discord_webhook_url=SECRET_WEBHOOK, github_token="ghp_secret")
        assert "super-secret-token" not in repr(settings)
        assert "ghp_secret" not in repr(settings)


class TestRateLimiter:
    def test_blocks_after_limit(self):
        limiter = RateLimiter(limit=2)
        limiter.check("1.1.1.1")
        limiter.check("1.1.1.1")

        with pytest.raises(HTTPException) as exc_info:
            limiter.check("1.1.1.1")

        assert exc_info.value.status_code == 429
        assert int(exc_info.value.headers["Retry-After"]) > 0

    def test_clients_are_counted_separately(self):
        limiter = RateLimiter(limit=1)
        limiter.check("1.1.1.1")
        limiter.check("2.2.2.2")

    def test_window_slides(self, monkeypatch):
        clock = [1000.0]
        monkeypatch.setattr("app.security.time.monotonic", lambda: clock[0])
        limiter = RateLimiter(limit=1, window_seconds=60)
        limiter.check("1.1.1.1")

        clock[0] += 60
        limiter.check("1.1.1.1")


@pytest.fixture
def make_client():
    clients = []

    def _make(**settings_values):
        stub = StubService()
        app.dependency_overrides[get_posting_service] = lambda: stub
        app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, **settings_values)
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client, stub

    yield _make
    for client in clients:
        client.__exit__(None, None, None)
    app.dependency_overrides.clear()


class TestApiKey:
    def test_open_when_no_key_configured(self, make_client):
        client, _ = make_client()
        assert client.post("/posting", json={"message": MESSAGE}).status_code == 200

    @pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}, {"X-API-Key": ""}])
    def test_rejects_missing_or_wrong_key(self, make_client, headers):
        client, stub = make_client(api_key="s3cret")

        response = client.post("/posting", json={"message": MESSAGE}, headers=headers)

        assert response.status_code == 401
        assert response.json() == {
            "success": False,
            "errors": [{"field": None, "message": "Invalid or missing API key"}],
        }
        assert stub.messages == []

    def test_accepts_correct_key(self, make_client):
        client, stub = make_client(api_key="s3cret")

        response = client.post("/posting", json={"message": MESSAGE}, headers={"X-API-Key": "s3cret"})

        assert response.status_code == 200
        assert stub.messages == [MESSAGE]

    def test_platforms_endpoint_is_protected_too(self, make_client):
        client, _ = make_client(api_key="s3cret")
        assert client.get("/platforms").status_code == 401
        assert client.get("/platforms", headers={"X-API-Key": "s3cret"}).status_code == 200


class TestApiRateLimit:
    def test_too_many_requests(self, make_client):
        client, stub = make_client()
        app.state.rate_limiter = RateLimiter(limit=2)

        codes = [client.post("/posting", json={"message": MESSAGE}).status_code for _ in range(3)]

        assert codes == [200, 200, 429]
        assert len(stub.messages) == 2

    def test_invalid_requests_count_too(self, make_client):
        client, _ = make_client()
        app.state.rate_limiter = RateLimiter(limit=1)

        client.post("/posting", json={"message": "no link"})

        assert client.post("/posting", json={"message": MESSAGE}).status_code == 429


class TestBodySizeLimit:
    def test_large_body_is_rejected(self, make_client):
        client, stub = make_client()

        response = client.post("/posting", json={"message": "x" * 20_000})

        assert response.status_code == 413
        assert response.json()["errors"][0]["message"] == "Request body is too large"
        assert stub.messages == []

    def test_chunked_body_without_content_length_is_rejected(self, make_client):
        client, stub = make_client()

        def chunks():
            yield b'{"message": "'
            for _ in range(20):
                yield b"x" * 1024
            yield b'"}'

        response = client.post("/posting", content=chunks(), headers={"Content-Type": "application/json"})

        assert response.status_code == 413
        assert stub.messages == []

    async def test_invalid_content_length_is_rejected(self):
        sent = []

        async def downstream(scope, receive, send):
            raise AssertionError("request should not reach the app")

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        middleware = BodySizeLimitMiddleware(downstream)
        scope = {"type": "http", "headers": [(b"content-length", b"abc")]}

        await middleware(scope, receive, send)

        assert sent[0]["status"] == 413

    async def test_non_http_scopes_pass_through(self):
        called = []

        async def downstream(scope, receive, send):
            called.append(scope["type"])

        await BodySizeLimitMiddleware(downstream)({"type": "lifespan"}, None, None)

        assert called == ["lifespan"]


def test_wrong_api_key_attempts_are_rate_limited(make_client):
    client, _ = make_client(api_key="s3cret")
    app.state.rate_limiter = RateLimiter(limit=2)
    bad_key = {"X-API-Key": "guess"}

    codes = [
        client.post("/posting", json={"message": MESSAGE}, headers=bad_key).status_code for _ in range(3)
    ]

    assert codes == [401, 401, 429]
