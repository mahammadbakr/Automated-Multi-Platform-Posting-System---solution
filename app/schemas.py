import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.links import find_links, is_valid_url

MAX_MESSAGE_LENGTH = 200


class PostRequest(BaseModel):
    message: str = Field(
        ...,
        description="Text to publish. Max 200 characters and exactly one http(s) CTA link.",
        examples=[
            "Check out our latest business platform and grow your online visibility. https://example.com"
        ],
    )

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        message = value.strip()
        if not message:
            raise ValueError("Message must not be empty")

        if len(message) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Message must not exceed {MAX_MESSAGE_LENGTH} characters (got {len(message)})")

        links = find_links(message)
        if len(links) != 1:
            raise ValueError(f"Message must contain exactly one CTA link (found {len(links)})")

        if not is_valid_url(links[0]):
            raise ValueError(
                f"CTA link '{links[0]}' is not a valid URL. Use a full http:// or https:// address"
            )

        return message


class PlatformResult(BaseModel):
    platform: str
    status: Literal["success", "failed"]
    posted_url: str | None = None
    public_access: bool = False
    date: dt.date | None = None
    time: dt.time | None = None
    error: str | None = None


class PostingResponse(BaseModel):
    success: bool
    results: list[PlatformResult]


class PlatformInfo(BaseModel):
    platform: str
    configured: bool
    missing_settings: list[str]
