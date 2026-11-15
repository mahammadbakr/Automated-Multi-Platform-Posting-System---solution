import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_posting_service
from app.schemas import PlatformInfo, PlatformResult, PostingResponse
from tests.conftest import MESSAGE


class StubService:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def publish(self, message: str) -> PostingResponse:
        self.messages.append(message)
        return PostingResponse(
            success=True,
            results=[
                PlatformResult(
                    platform="Mastodon",
                    status="success",
                    posted_url="https://mastodon.social/@dxora/1",
                    public_access=True,
                    date=dt.date(2026, 11, 15),
                    time=dt.time(10, 30),
                ),
                PlatformResult(platform="Discord", status="failed", error="HTTP 401: Unauthorized"),
            ],
        )

    def describe_platforms(self) -> list[PlatformInfo]:
        return [PlatformInfo(platform="Mastodon", configured=True, missing_settings=[])]


@pytest.fixture
def service():
    stub = StubService()
    app.dependency_overrides[get_posting_service] = lambda: stub
    yield stub
    app.dependency_overrides.clear()


@pytest.fixture
def api(service):
    with TestClient(app) as test_client:
        yield test_client


def test_posting_returns_results_per_platform(api, service):
    response = api.post("/posting", json={"message": MESSAGE})

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "results": [
            {
                "platform": "Mastodon",
                "status": "success",
                "posted_url": "https://mastodon.social/@dxora/1",
                "public_access": True,
                "date": "2026-11-15",
                "time": "10:30:00",
                "error": None,
            },
            {
                "platform": "Discord",
                "status": "failed",
                "posted_url": None,
                "public_access": False,
                "date": None,
                "time": None,
                "error": "HTTP 401: Unauthorized",
            },
        ],
    }
    assert service.messages == [MESSAGE]


def test_posting_passes_trimmed_message(api, service):
    api.post("/posting", json={"message": f"   {MESSAGE}   "})

    assert service.messages == [MESSAGE]


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        ({"message": "x" * 190 + " https://example.com"}, "must not exceed 200 characters"),
        ({"message": "No link at all"}, "exactly one CTA link (found 0)"),
        ({"message": "https://a.com or https://b.com"}, "exactly one CTA link (found 2)"),
        ({"message": "Visit www.example.com"}, "not a valid URL"),
        ({"message": "Visit https://nota-domain"}, "not a valid URL"),
        ({"message": ""}, "must not be empty"),
    ],
)
def test_posting_rejects_invalid_messages(api, service, payload, expected_error):
    response = api.post("/posting", json=payload)

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["errors"][0]["field"] == "message"
    assert expected_error in body["errors"][0]["message"]
    assert service.messages == []


def test_posting_requires_message_field(api):
    response = api.post("/posting", json={})

    assert response.status_code == 422
    assert response.json()["errors"] == [{"field": "message", "message": "Field required"}]


def test_posting_rejects_malformed_json(api):
    response = api.post("/posting", content="{not json", headers={"Content-Type": "application/json"})

    assert response.status_code == 422
    assert response.json()["success"] is False


def test_list_platforms(api):
    response = api.get("/platforms")

    assert response.status_code == 200
    assert response.json() == [{"platform": "Mastodon", "configured": True, "missing_settings": []}]


def test_app_wires_real_service_on_startup():
    with TestClient(app) as test_client:
        names = [p["platform"] for p in test_client.get("/platforms").json()]

    assert names == ["Telegram", "Discord", "Mastodon", "Bluesky", "GitHub Gist", "Telegraph"]


def test_openapi_docs_available():
    with TestClient(app) as test_client:
        assert test_client.get("/docs").status_code == 200
        assert "/posting" in test_client.get("/openapi.json").json()["paths"]


def test_httpx_request_logs_are_silenced():
    # Request URLs for Telegram and Discord contain secrets, so httpx must not log them.
    import logging

    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
