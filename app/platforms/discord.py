from app.platforms.base import Platform, PublishedPost


class DiscordPlatform(Platform):
    """Posts through a channel webhook: https://discord.com/developers/docs/resources/webhook#execute-webhook"""

    name = "Discord"
    required_settings = ("discord_webhook_url",)

    async def publish(self, message: str, link: str) -> PublishedPost:
        webhook_url = self.settings.discord_webhook_url.get_secret_value()

        # wait=true makes Discord return the created message instead of 204 No Content.
        response = await self.client.post(webhook_url, params={"wait": "true"}, json={"content": message})
        posted = self.ensure_ok(response)

        # The message payload has no guild_id, but the webhook object does.
        webhook = self.ensure_ok(await self.client.get(webhook_url))
        url = f"https://discord.com/channels/{webhook['guild_id']}/{posted['channel_id']}/{posted['id']}"

        # Discord messages are only visible to members of the server.
        return PublishedPost(url=url, public=False)
