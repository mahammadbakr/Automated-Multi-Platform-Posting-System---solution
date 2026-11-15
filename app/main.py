import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.middleware import BodySizeLimitMiddleware
from app.platforms import build_platforms
from app.schemas import PlatformInfo, PostingResponse, PostRequest
from app.security import RateLimiter, enforce_rate_limit, require_api_key
from app.services.posting_service import PostingService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# httpx logs every request URL at INFO, and Telegram/Discord URLs contain the secret token.
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.api_key is None:
        logger.warning("API_KEY is not set: /posting is open to anyone who can reach this server")

    app.state.rate_limiter = RateLimiter(limit=settings.rate_limit_per_minute)
    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        app.state.posting_service = PostingService(build_platforms(settings, client))
        yield


app = FastAPI(
    title="Automated Multi-Platform Posting System",
    description="Publishes one short message with a CTA link to several platforms at once.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(BodySizeLimitMiddleware)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = []
    for error in exc.errors():
        field = ".".join(str(part) for part in error["loc"] if part != "body") or "body"
        errors.append({"field": field, "message": error["msg"].removeprefix("Value error, ")})

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"success": False, "errors": errors},
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "errors": [{"field": None, "message": exc.detail}]},
        headers=exc.headers,
    )


def get_posting_service(request: Request) -> PostingService:
    return request.app.state.posting_service


PostingServiceDep = Annotated[PostingService, Depends(get_posting_service)]


@app.post(
    "/posting",
    response_model=PostingResponse,
    # Rate limit first, so failed API key guesses are throttled too.
    dependencies=[Depends(enforce_rate_limit), Depends(require_api_key)],
)
async def create_posting(payload: PostRequest, service: PostingServiceDep) -> PostingResponse:
    return await service.publish(payload.message)


@app.get("/platforms", response_model=list[PlatformInfo], dependencies=[Depends(require_api_key)])
async def list_platforms(service: PostingServiceDep) -> list[PlatformInfo]:
    return service.describe_platforms()
