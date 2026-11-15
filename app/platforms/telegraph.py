from app.platforms.base import Platform, PlatformError, PublishedPost

API_URL = "https://api.telegra.ph/createPage"
MAX_TITLE_LENGTH = 256


class TelegraphPlatform(Platform):
    """Publishes a page on telegra.ph: https://telegra.ph/api#createPage"""

    name = "Telegraph"
    required_settings = ("telegraph_access_token",)

    async def publish(self, message: str, link: str) -> PublishedPost:
        payload = {
            "access_token": self.settings.telegraph_access_token.get_secret_value(),
            "title": page_title(message, link),
            "content": page_content(message, link),
            "return_content": False,
        }
        if self.settings.telegraph_author_name:
            payload["author_name"] = self.settings.telegraph_author_name

        body = self.ensure_ok(await self.client.post(API_URL, json=payload))

        # Telegraph reports failures with HTTP 200 and ok=false.
        if not body.get("ok"):
            raise PlatformError(body.get("error") or "Telegraph rejected the page")

        return PublishedPost(url=body["result"]["url"], public=True)


def page_title(message: str, link: str) -> str:
    title = message.replace(link, "").strip(" -:|") or "Announcement"
    return title[:MAX_TITLE_LENGTH]


def page_content(message: str, link: str) -> list[dict]:
    before, _, after = message.partition(link)
    children: list = [before, {"tag": "a", "attrs": {"href": link}, "children": [link]}, after]
    return [{"tag": "p", "children": [child for child in children if child]}]
