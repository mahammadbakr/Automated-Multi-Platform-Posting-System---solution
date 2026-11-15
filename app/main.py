import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.platforms import build_platforms
from app.schemas import PlatformInfo, PostingResponse, PostRequest
from app.services.posting_service import PostingService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        app.state.posting_service = PostingService(build_platforms(settings, client))
        yield


app = FastAPI(
    title="Automated Multi-Platform Posting System",
    description="Publishes one short message with a CTA link to several platforms at once.",
    version="1.0.0",
    lifespan=lifespan,
)


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


def get_posting_service(request: Request) -> PostingService:
    return request.app.state.posting_service


PostingServiceDep = Annotated[PostingService, Depends(get_posting_service)]


@app.post("/posting", response_model=PostingResponse)
async def create_posting(payload: PostRequest, service: PostingServiceDep) -> PostingResponse:
    return await service.publish(payload.message)


@app.get("/platforms", response_model=list[PlatformInfo])
async def list_platforms(service: PostingServiceDep) -> list[PlatformInfo]:
    return service.describe_platforms()
