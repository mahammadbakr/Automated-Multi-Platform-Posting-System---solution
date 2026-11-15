import asyncio
import datetime as dt

import httpx

from app.config import Settings
from app.platforms import Platform, PlatformError, PublishedPost
from app.services.posting_service import PostingService
from tests.conftest import LINK, MESSAGE


class FakePlatform(Platform):
    name = "Fake"

    def __init__(self, name: str, outcome: object = None, missing: list[str] | None = None) -> None:
        super().__init__(Settings(_env_file=None), client=None)
        self.name = name
        self.outcome = outcome or PublishedPost(url=f"https://{name.lower()}.example/1", public=True)
        self.missing = missing or []
        self.calls: list[tuple[str, str]] = []

    def missing_settings(self) -> list[str]:
        return self.missing

    async def publish(self, message: str, link: str) -> PublishedPost:
        self.calls.append((message, link))
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


async def test_all_platforms_succeed():
    platforms = [FakePlatform("A"), FakePlatform("B", PublishedPost(url="https://b.example/2", public=False))]

    response = await PostingService(platforms).publish(MESSAGE)

    assert response.success is True
    first, second = response.results
    assert first.platform == "A"
    assert first.status == "success"
    assert first.posted_url == "https://a.example/1"
    assert first.public_access is True
    assert first.error is None
    assert first.date == dt.datetime.now(dt.timezone.utc).date()
    assert first.time is not None and first.time.microsecond == 0
    assert second.public_access is False
    assert platforms[0].calls == [(MESSAGE, LINK)]


async def test_one_failure_does_not_stop_the_others():
    platforms = [
        FakePlatform("A"),
        FakePlatform("Broken", PlatformError("HTTP 401: Unauthorized")),
        FakePlatform("C"),
    ]

    response = await PostingService(platforms).publish(MESSAGE)

    assert response.success is True
    assert [r.status for r in response.results] == ["success", "failed", "success"]
    failed = response.results[1]
    assert failed.error == "HTTP 401: Unauthorized"
    assert failed.posted_url is None
    assert failed.public_access is False
    assert failed.date is None and failed.time is None


async def test_success_is_false_when_everything_fails():
    platforms = [FakePlatform("A", PlatformError("nope")), FakePlatform("B", PlatformError("nope"))]

    response = await PostingService(platforms).publish(MESSAGE)

    assert response.success is False


async def test_unconfigured_platform_is_skipped():
    platform = FakePlatform("A", missing=["A_TOKEN", "A_CHAT_ID"])

    response = await PostingService([platform]).publish(MESSAGE)

    assert response.results[0].error == "Not configured: missing A_TOKEN, A_CHAT_ID"
    assert platform.calls == []


async def test_network_errors_are_reported_without_details():
    request = httpx.Request("POST", "https://api.telegram.org/botSECRET/sendMessage")
    platforms = [
        FakePlatform("Slow", httpx.ReadTimeout("timed out", request=request)),
        FakePlatform("Down", httpx.ConnectError("https://api.telegram.org/botSECRET", request=request)),
    ]

    response = await PostingService(platforms).publish(MESSAGE)

    assert response.results[0].error == "Request timed out"
    assert response.results[1].error == "Network error (ConnectError)"
    assert all("SECRET" not in r.error for r in response.results)


async def test_unexpected_exception_is_contained(caplog):
    platforms = [FakePlatform("Buggy", KeyError("result")), FakePlatform("B")]

    response = await PostingService(platforms).publish(MESSAGE)

    assert response.results[0].error == "Unexpected error, check server logs"
    assert response.results[1].status == "success"
    assert "Unexpected error while posting to Buggy" in caplog.text


async def test_platforms_are_called_concurrently():
    started = asyncio.Event()

    class Waiting(FakePlatform):
        async def publish(self, message, link):
            await asyncio.wait_for(started.wait(), timeout=1)
            return await super().publish(message, link)

    class Signalling(FakePlatform):
        async def publish(self, message, link):
            started.set()
            return await super().publish(message, link)

    # If the service ran platforms one by one, Waiting would time out.
    response = await PostingService([Waiting("A"), Signalling("B")]).publish(MESSAGE)

    assert [r.status for r in response.results] == ["success", "success"]


def test_describe_platforms():
    service = PostingService([FakePlatform("A"), FakePlatform("B", missing=["B_TOKEN"])])

    info = service.describe_platforms()

    assert [(i.platform, i.configured, i.missing_settings) for i in info] == [
        ("A", True, []),
        ("B", False, ["B_TOKEN"]),
    ]
