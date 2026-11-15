import asyncio
import logging
from collections.abc import Sequence
from datetime import datetime, timezone

import httpx

from app.links import find_links
from app.platforms import Platform, PlatformError
from app.schemas import PlatformInfo, PlatformResult, PostingResponse

logger = logging.getLogger(__name__)


class PostingService:
    def __init__(self, platforms: Sequence[Platform]) -> None:
        self._platforms = tuple(platforms)

    def describe_platforms(self) -> list[PlatformInfo]:
        return [
            PlatformInfo(
                platform=platform.name,
                configured=not platform.missing_settings(),
                missing_settings=platform.missing_settings(),
            )
            for platform in self._platforms
        ]

    async def publish(self, message: str) -> PostingResponse:
        link = find_links(message)[0]
        # Every platform runs concurrently and _publish_to never raises,
        # so one broken integration can't stop the others.
        results = await asyncio.gather(
            *(self._publish_to(platform, message, link) for platform in self._platforms)
        )
        succeeded = sum(result.status == "success" for result in results)
        logger.info("Posted to %d of %d platforms", succeeded, len(results))
        return PostingResponse(success=succeeded > 0, results=list(results))

    async def _publish_to(self, platform: Platform, message: str, link: str) -> PlatformResult:
        missing = platform.missing_settings()
        if missing:
            return _failed(platform.name, f"Not configured: missing {', '.join(missing)}")

        try:
            post = await platform.publish(message, link)
        except PlatformError as exc:
            error = str(exc)
        except httpx.TimeoutException:
            error = "Request timed out"
        except httpx.RequestError as exc:
            # str(exc) may include the request URL (and tokens with it), so only expose the type.
            error = f"Network error ({type(exc).__name__})"
        except Exception:
            logger.exception("Unexpected error while posting to %s", platform.name)
            error = "Unexpected error, check server logs"
        else:
            posted_at = datetime.now(timezone.utc).replace(microsecond=0)
            logger.info("%s: posted %s", platform.name, post.url)
            return PlatformResult(
                platform=platform.name,
                status="success",
                posted_url=post.url,
                public_access=post.public,
                date=posted_at.date(),
                time=posted_at.time(),
            )

        logger.warning("%s: %s", platform.name, error)
        return _failed(platform.name, error)


def _failed(platform_name: str, error: str) -> PlatformResult:
    return PlatformResult(platform=platform_name, status="failed", error=error)
