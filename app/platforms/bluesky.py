from datetime import datetime, timezone

from app.platforms.base import Platform, PublishedPost


class BlueskyPlatform(Platform):
    """Creates a post over the AT Protocol: https://docs.bsky.app/docs/advanced-guides/posts"""

    name = "Bluesky"
    required_settings = ("bluesky_handle", "bluesky_app_password")

    async def publish(self, message: str, link: str) -> PublishedPost:
        base_url = self.settings.bluesky_service_url.rstrip("/")

        session = self.ensure_ok(
            await self.client.post(
                f"{base_url}/xrpc/com.atproto.server.createSession",
                json={
                    "identifier": self.settings.bluesky_handle,
                    "password": self.settings.bluesky_app_password.get_secret_value(),
                },
            )
        )

        record = {
            "$type": "app.bsky.feed.post",
            "text": message,
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "facets": [link_facet(message, link)],
        }
        created = self.ensure_ok(
            await self.client.post(
                f"{base_url}/xrpc/com.atproto.repo.createRecord",
                headers={"Authorization": f"Bearer {session['accessJwt']}"},
                json={"repo": session["did"], "collection": "app.bsky.feed.post", "record": record},
            )
        )

        # uri looks like at://did:plc:xyz/app.bsky.feed.post/<rkey>
        record_key = created["uri"].rsplit("/", 1)[-1]
        handle = session.get("handle", self.settings.bluesky_handle)
        return PublishedPost(url=f"https://bsky.app/profile/{handle}/post/{record_key}", public=True)


def link_facet(message: str, link: str) -> dict:
    """Bluesky doesn't auto-link URLs; links need a facet with UTF-8 byte offsets."""
    start = len(message[: message.index(link)].encode("utf-8"))
    end = start + len(link.encode("utf-8"))
    return {
        "index": {"byteStart": start, "byteEnd": end},
        "features": [{"$type": "app.bsky.richtext.facet#link", "uri": link}],
    }
