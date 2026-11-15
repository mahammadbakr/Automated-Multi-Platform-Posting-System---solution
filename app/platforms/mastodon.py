import hashlib

from app.platforms.base import Platform, PublishedPost


class MastodonPlatform(Platform):
    """Publishes a status: https://docs.joinmastodon.org/methods/statuses/#create"""

    name = "Mastodon"
    required_settings = ("mastodon_access_token",)

    async def publish(self, message: str, link: str) -> PublishedPost:
        token = self.settings.mastodon_access_token.get_secret_value()
        base_url = self.settings.mastodon_base_url.rstrip("/")

        response = await self.client.post(
            f"{base_url}/api/v1/statuses",
            headers={
                "Authorization": f"Bearer {token}",
                # Mastodon dedupes requests with the same key for an hour, so a retry
                # of the same message never produces a duplicate toot.
                "Idempotency-Key": hashlib.sha256(message.encode()).hexdigest(),
            },
            data={"status": message, "visibility": "public"},
        )
        status = self.ensure_ok(response)
        return PublishedPost(url=status.get("url"), public=status.get("visibility") == "public")
