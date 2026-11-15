from app.platforms.base import Platform, PublishedPost

API_URL = "https://api.github.com/gists"


class GitHubGistPlatform(Platform):
    """Creates a public gist: https://docs.github.com/en/rest/gists/gists#create-a-gist"""

    name = "GitHub Gist"
    required_settings = ("github_token",)

    async def publish(self, message: str, link: str) -> PublishedPost:
        response = await self.client.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {self.settings.github_token.get_secret_value()}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={
                "description": message,
                "public": True,
                "files": {"post.md": {"content": message}},
            },
        )
        gist = self.ensure_ok(response)
        return PublishedPost(url=gist.get("html_url"), public=bool(gist.get("public")))
