from app.platforms.base import Platform, PlatformError, PublishedPost

API_URL = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramPlatform(Platform):
    """Posts to a channel through the Bot API: https://core.telegram.org/bots/api#sendmessage"""

    name = "Telegram"
    required_settings = ("telegram_bot_token", "telegram_chat_id")

    async def publish(self, message: str, link: str) -> PublishedPost:
        token = self.settings.telegram_bot_token.get_secret_value()
        response = await self.client.post(
            API_URL.format(token=token),
            json={"chat_id": self.settings.telegram_chat_id, "text": message},
        )
        body = self.ensure_ok(response)
        if not body.get("ok"):
            raise PlatformError(body.get("description") or "Telegram rejected the message")

        result = body["result"]
        message_id = result["message_id"]
        chat = result.get("chat", {})

        # Public channels have a username and a t.me link anyone can open.
        if username := chat.get("username"):
            return PublishedPost(url=f"https://t.me/{username}/{message_id}", public=True)

        # Private channels/groups: only members can open the t.me/c/ link.
        chat_id = str(chat.get("id", ""))
        if chat_id.startswith("-100"):
            return PublishedPost(url=f"https://t.me/c/{chat_id[4:]}/{message_id}", public=False)

        return PublishedPost(url=None, public=False)
