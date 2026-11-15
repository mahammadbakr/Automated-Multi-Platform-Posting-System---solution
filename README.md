# Automated Multi-Platform Posting System

A FastAPI service that takes one short message with a call-to-action link and publishes it to six platforms at once through their official APIs:

| Platform | API used | Posted URL | Public access |
|---|---|---|---|
| **Telegram** | [Bot API `sendMessage`](https://core.telegram.org/bots/api#sendmessage) | `https://t.me/<channel>/<id>` | Yes for public channels, no for private ones |
| **Discord** | [Execute Webhook](https://discord.com/developers/docs/resources/webhook#execute-webhook) | `https://discord.com/channels/<guild>/<channel>/<id>` | No, only server members can see it |
| **Mastodon** | [`POST /api/v1/statuses`](https://docs.joinmastodon.org/methods/statuses/#create) | URL returned by the instance | Yes when visibility is `public` |
| **Bluesky** | [AT Protocol `createSession` + `createRecord`](https://docs.bsky.app/docs/advanced-guides/posts) | `https://bsky.app/profile/<handle>/post/<rkey>` | Yes |
| **GitHub Gist** | [`POST /gists`](https://docs.github.com/en/rest/gists/gists#create-a-gist) | `html_url` of the gist | Yes, the gist is created as public |
| **Telegraph** | [`createPage`](https://telegra.ph/api#createPage) | `https://telegra.ph/<path>` | Yes |

The endpoint picks the platforms itself. Each one runs on its own: if one fails because of bad credentials, a timeout or an API error, the rest still get posted, and the response says what happened on each platform.

---

## Contents

- [Quick start](#quick-start)
- [Configuration](#configuration)
- [API](#api)
- [Input validation](#input-validation)
- [How it works](#how-it-works)
- [Project structure](#project-structure)
- [Testing](#testing)
- [Logs from a real run](#logs-from-a-real-run)
- [Security](#security)
- [Design decisions](#design-decisions)
- [Adding a new platform](#adding-a-new-platform)

---

## Quick start

Requires **Python 3.10+**.

```bash
git clone https://github.com/mahammadbakr/Automated-Multi-Platform-Posting-System---solution.git
cd Automated-Multi-Platform-Posting-System---solution

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # then fill in the credentials you have
uvicorn app.main:app --host 0.0.0.0 --port 4000
```

- API: `POST http://localhost:4000/posting`
- Swagger UI: http://localhost:4000/docs
- Which platforms are configured: `GET http://localhost:4000/platforms`

You don't need all six platforms. Any platform without credentials is skipped and shows up as `failed` with a `Not configured: missing ...` error that names the exact variable to set.

---

## Configuration

All credentials come from environment variables, either a `.env` file in the project root or the real environment. `.env` is in `.gitignore`, so it never gets committed. See [`.env.example`](.env.example) for the full template.

| Variable | Required for | How to get it |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Telegram | Create a bot with [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | Telegram | `@yourchannel` for a public channel, or the numeric `-100…` id. Add the bot as a channel admin. |
| `DISCORD_WEBHOOK_URL` | Discord | Channel settings → Integrations → Webhooks → New Webhook → Copy URL |
| `MASTODON_BASE_URL` | Mastodon | Your instance, default `https://mastodon.social` |
| `MASTODON_ACCESS_TOKEN` | Mastodon | Preferences → Development → New application, scope `write:statuses` |
| `BLUESKY_HANDLE` | Bluesky | e.g. `yourname.bsky.social` |
| `BLUESKY_APP_PASSWORD` | Bluesky | Settings → Privacy and security → App passwords. Don't use your main password. |
| `BLUESKY_SERVICE_URL` | Bluesky | Default `https://bsky.social` |
| `GITHUB_TOKEN` | GitHub Gist | Personal access token with the `gist` scope |
| `TELEGRAPH_ACCESS_TOKEN` | Telegraph | See below |
| `TELEGRAPH_AUTHOR_NAME` | Telegraph | Optional byline shown on the page |
| `REQUEST_TIMEOUT` | All | HTTP timeout in seconds, default `15` |
| `API_KEY` | Endpoint security | **Recommended.** When set, clients must send it in the `X-API-Key` header. Generate one with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `RATE_LIMIT_PER_MINUTE` | Endpoint security | Max `POST /posting` requests per client IP per minute, default `10` |

The settings are checked at startup. `MASTODON_BASE_URL` and `BLUESKY_SERVICE_URL` must use `https://`, since tokens are sent to them. `DISCORD_WEBHOOK_URL` must be a real `discord.com/api/webhooks/...` URL. If a value is wrong, the app refuses to start and says which setting is wrong, without printing the secret.

**Telegraph token.** Telegraph has no sign-up form. An account is created with a single API call that returns an `access_token`:

```bash
curl "https://api.telegra.ph/createAccount?short_name=MyPoster&author_name=My%20Company"
```

---

## API

### `POST /posting`

**Request**

```bash
curl -X POST http://localhost:4000/posting \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your API_KEY>" \
  -d '{"message": "Check out our latest business platform and grow your online visibility. https://example.com"}'
```

Leave out the `X-API-Key` header if `API_KEY` isn't set. In Swagger UI, use the **Authorize** button.

**Response `200 OK`** (example with four platforms configured and two broken)

```json
{
  "success": true,
  "results": [
    {
      "platform": "Telegram",
      "status": "success",
      "posted_url": "https://t.me/my_channel/42",
      "public_access": true,
      "date": "2026-11-15",
      "time": "10:30:00",
      "error": null
    },
    {
      "platform": "Discord",
      "status": "failed",
      "posted_url": null,
      "public_access": false,
      "date": null,
      "time": null,
      "error": "HTTP 404: Unknown Webhook"
    },
    {
      "platform": "Mastodon",
      "status": "success",
      "posted_url": "https://mastodon.social/@my_account/113000000000000000",
      "public_access": true,
      "date": "2026-11-15",
      "time": "10:30:00",
      "error": null
    },
    {
      "platform": "Bluesky",
      "status": "success",
      "posted_url": "https://bsky.app/profile/my.bsky.social/post/3lb2xyzabc",
      "public_access": true,
      "date": "2026-11-15",
      "time": "10:30:01",
      "error": null
    },
    {
      "platform": "GitHub Gist",
      "status": "success",
      "posted_url": "https://gist.github.com/my-user/0123456789abcdef",
      "public_access": true,
      "date": "2026-11-15",
      "time": "10:30:00",
      "error": null
    },
    {
      "platform": "Telegraph",
      "status": "failed",
      "posted_url": null,
      "public_access": false,
      "date": null,
      "time": null,
      "error": "Not configured: missing TELEGRAPH_ACCESS_TOKEN"
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `success` | `true` if **at least one** platform got the post |
| `platform` | Platform name |
| `status` | `success` or `failed` |
| `posted_url` | Link to the published content, `null` on failure |
| `public_access` | Whether someone without an account or membership can open the post. This comes from what the platform reports, e.g. Mastodon `visibility` or Gist `public`. |
| `date` / `time` | When the platform confirmed the post, in **UTC** |
| `error` | The platform's own error message, or a short description such as `Request timed out` |

A valid request always gets `200`, even if every platform failed. The request itself was fine; the per-platform results show what went wrong.

**Validation error `422`**

```json
{
  "success": false,
  "errors": [
    { "field": "message", "message": "Message must contain exactly one CTA link (found 2)" }
  ]
}
```

**Other errors** use the same format:

| Status | When |
|---|---|
| `401` | `API_KEY` is set and the `X-API-Key` header is missing or wrong |
| `413` | Request body is over 16 KB |
| `429` | Rate limit hit. The `Retry-After` header says how many seconds to wait. |

```json
{ "success": false, "errors": [{ "field": null, "message": "Invalid or missing API key" }] }
```

### `GET /platforms`

Shows which integrations are ready, which helps when setting up `.env`:

```json
[
  { "platform": "Telegram", "configured": true,  "missing_settings": [] },
  { "platform": "Discord",  "configured": false, "missing_settings": ["DISCORD_WEBHOOK_URL"] }
]
```

---

## Input validation

The rules live in [`app/schemas.py`](app/schemas.py) and [`app/links.py`](app/links.py):

| Rule | Example input | Error |
|---|---|---|
| Not empty (whitespace is trimmed first) | `"   "` | `Message must not be empty` |
| At most 200 characters | 201-char message | `Message must not exceed 200 characters (got 201)` |
| Exactly one link | `"No link here"` | `Message must contain exactly one CTA link (found 0)` |
| Exactly one link | `"https://a.com or https://b.com"` | `Message must contain exactly one CTA link (found 2)` |
| Link must be a full http(s) URL | `"Visit www.example.com"` | `CTA link 'www.example.com' is not a valid URL. Use a full http:// or https:// address` |
| Link must have a real public domain | `"https://localhost:8000"` | `... is not a valid URL ...` |
| `message` must be present and a string | `{}` | `Field required` |

How links are detected:
- Anything starting with `http://`, `https://` or `www.` counts as a link. A `www.` link is counted, so it can't be used to sneak in a second link, but it's rejected because it has no scheme.
- Trailing sentence punctuation is dropped, so `"...at https://example.com."` gives `https://example.com`.
- The URL is parsed with Pydantic's `HttpUrl`, and the host must look like a public domain (`name.tld`). `localhost`, bare hostnames and raw IPs are rejected.

---

## How it works

```
POST /posting
     │
     ▼
PostRequest (Pydantic) ── invalid ──► 422 {"success": false, "errors": [...]}
     │ valid
     ▼
PostingService.publish(message)
     │  asyncio.gather — all platforms at the same time
     ├──► TelegramPlatform.publish()   ─┐
     ├──► DiscordPlatform.publish()     │  each one wrapped in its own
     ├──► MastodonPlatform.publish()    │  try/except, so a failure becomes
     ├──► BlueskyPlatform.publish()     │  a "failed" result and doesn't
     ├──► GitHubGistPlatform.publish()  │  stop the others
     └──► TelegraphPlatform.publish()  ─┘
     │
     ▼
PostingResponse {"success": ..., "results": [...]}
```

1. **Startup.** The app creates one shared `httpx.AsyncClient`, so connections are pooled and there's a single timeout setting, and builds every platform from the settings.
2. **Validation.** FastAPI and Pydantic reject bad input before any platform is called.
3. **Fan-out.** `PostingService` runs every platform at the same time. Total latency is roughly the slowest platform, not the sum of all of them.
4. **Isolation.** Each platform call is wrapped so that:
   - a missing credential gives `Not configured: missing X`, and no request is sent;
   - an API rejection gives the platform's own error text, e.g. `HTTP 401: Bad credentials`;
   - a timeout gives `Request timed out`;
   - a network failure gives `Network error (ConnectError)`;
   - any other bug gives `Unexpected error, check server logs`, and the full traceback is logged.
5. **Response.** Results come back in a fixed order, with the timestamp taken when each platform confirmed the post.

### Platform notes

- **Telegram** returns the chat's `username` for public channels, which gives a `t.me/<username>/<id>` link. Private channels get a `t.me/c/<id>/<msg>` link that only members can open, so `public_access` is `false`.
- **Discord** webhook messages don't include the `guild_id` needed to build a message link. After posting, the service makes one `GET` request on the webhook to read it. Discord content is never public, so `public_access` is always `false`.
- **Mastodon** requests send an `Idempotency-Key` header based on the message, so a retried request won't create a duplicate toot.
- **Bluesky** doesn't turn URLs into links on its own. The service adds a [link facet](https://docs.bsky.app/docs/advanced-guides/post-richtext) with **UTF-8 byte offsets**, so the link stays clickable even when the message has emoji or accented characters.
- **Telegraph** returns HTTP 200 with `{"ok": false}` when it fails, so the service checks the body and not only the status code. The link is shown as a real `<a>` tag, and the text without the link becomes the page title.

---

## Project structure

```
.
├── app/
│   ├── main.py                  # FastAPI app, lifespan, routes, validation error handler
│   ├── config.py                # Settings loaded from env / .env (pydantic-settings)
│   ├── schemas.py               # Request/response models + message validation
│   ├── links.py                 # Link detection and URL validation
│   ├── security.py              # API key check + per-IP rate limiter
│   ├── middleware.py            # Request body size limit
│   ├── platforms/
│   │   ├── __init__.py          # Platform registry (build_platforms)
│   │   ├── base.py              # Platform ABC, PublishedPost, PlatformError, ensure_ok()
│   │   ├── telegram.py
│   │   ├── discord.py
│   │   ├── mastodon.py
│   │   ├── bluesky.py
│   │   ├── github_gist.py
│   │   └── telegraph.py
│   └── services/
│       └── posting_service.py   # Concurrent fan-out + per-platform error isolation
├── tests/
│   ├── conftest.py              # Shared fixtures (settings with fake creds, http client)
│   ├── test_validation.py       # Link detection, URL rules, PostRequest validation
│   ├── test_platforms.py        # Each integration against mocked HTTP (respx)
│   ├── test_posting_service.py  # Failure isolation, concurrency, error mapping
│   ├── test_posting.py          # API endpoints via FastAPI TestClient
│   └── test_security.py         # API key, rate limit, body limit, config hardening
├── .env.example
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
├── ruff.toml
└── python-post-message.md       # Original assignment brief
```

---

## Testing

```bash
pip install -r requirements-dev.txt
pytest
pytest --cov=app --cov-report=term-missing   # with coverage
```

The tests **never touch the network.** Each platform is tested against mocked HTTP responses with [respx](https://lundberg.github.io/respx/). The mocked responses follow each API's documented format. The tests also load settings with `_env_file=None`, so a real `.env` on your machine is never read.

What's covered:

- **Validation:** length limits (200 passes, 201 fails), empty input, 0 or 2 links, `www.` links, localhost and IP hosts, trailing punctuation, wrong types.
- **Each integration:** the exact request sent (headers, body, auth), how the posted URL and public flag are worked out, and how errors are read (including Telegram/Telegraph `ok: false` and non-JSON error pages).
- **Security:** the Telegram bot token, which is part of the request URL, never shows up in error messages.
- **Service:** one failure doesn't stop the others; unconfigured platforms send no request; timeouts and network errors become clean messages; unexpected exceptions are contained and logged; platforms really do run concurrently.
- **API:** response shape, the 422 error format, malformed JSON, a missing field, `/platforms`, `/docs`.
- **Hardening:** API key (missing, wrong, correct), rate limiting (including wrong-key guesses), 413 for big and chunked bodies, HTTPS-only base URLs, the webhook URL format, and that secrets never appear in validation errors or reprs.

Latest run:

```
$ pytest --cov=app --cov-report=term-missing
Name                              Stmts   Miss  Cover
-----------------------------------------------------
app/config.py                        36      0   100%
app/links.py                         17      0   100%
app/main.py                          48      0   100%
app/middleware.py                    45      2    96%
app/platforms/base.py                35      1    97%
app/platforms/bluesky.py             17      0   100%
app/platforms/discord.py             11      0   100%
app/platforms/github_gist.py          9      0   100%
app/platforms/mastodon.py            11      0   100%
app/platforms/telegram.py            20      0   100%
app/platforms/telegraph.py           21      0   100%
app/schemas.py                       29      0   100%
app/security.py                      31      0   100%
app/services/posting_service.py      42      0   100%
-----------------------------------------------------
TOTAL                               385      3    99%
103 passed in 1.95s
```

Lint: `ruff check app tests`

---

## Logs from a real run

**Live run against the real APIs.** Discord used a real webhook. The other five used deliberately invalid credentials, to show that each integration reaches the real endpoint, sends a request the API understands, and turns the rejection into a clean error. Even with five platforms failing, Discord still posted:

```
success: True
  Telegram     failed   HTTP 401: Unauthorized: invalid token specified
  Discord      success  https://discord.com/channels/1571486850248605729/1571486850756120659/1571488681884385420
  Mastodon     failed   HTTP 401: The access token is invalid
  Bluesky      failed   HTTP 401: Invalid identifier or password
  GitHub Gist  failed   HTTP 401: Bad credentials
  Telegraph    failed   ACCESS_TOKEN_INVALID
```

**Server log for the same run.** No tokens or webhook URLs appear in it:

```
INFO:     Uvicorn running on http://0.0.0.0:4000 (Press CTRL+C to quit)
WARNING app.services.posting_service: Telegram: HTTP 401: Unauthorized: invalid token specified
WARNING app.services.posting_service: Mastodon: HTTP 401: The access token is invalid
WARNING app.services.posting_service: GitHub Gist: HTTP 401: Bad credentials
WARNING app.services.posting_service: Telegraph: ACCESS_TOKEN_INVALID
WARNING app.services.posting_service: Bluesky: HTTP 401: Invalid identifier or password
INFO app.services.posting_service: Discord: posted https://discord.com/channels/1571486850248605729/1571486850756120659/1571488681884385420
INFO app.services.posting_service: Posted to 1 of 6 platforms
```

**Protections checked on the running server:**

```
no API key          -> 401 {"success":false,"errors":[{"field":null,"message":"Invalid or missing API key"}]}
wrong API key       -> 401
20 KB body          -> 413 {"success": false, "errors": [{"field": "body", "message": "Request body is too large"}]}
two links           -> 422 {"success":false,"errors":[{"field":"message","message":"Message must contain exactly one CTA link (found 2)"}]}
4th wrong-key guess -> 429 (RATE_LIMIT_PER_MINUTE=3)
```

---

## Security

| Risk | What the app does |
|---|---|
| Anyone on the network posting to your accounts (the server binds to `0.0.0.0`) | Optional `API_KEY`, checked with `secrets.compare_digest` so the comparison time gives nothing away. A warning is logged at startup if it isn't set. |
| Spam, or someone guessing the API key | Per-IP rate limit. It runs **before** the key check, so wrong guesses are throttled too. |
| Memory exhaustion from huge bodies | ASGI middleware rejects bodies over 16 KB with `413`. It checks `Content-Length` and also counts streamed bytes, so chunked uploads can't get around it. |
| Tokens leaking into logs | httpx request logging is turned down, because Telegram and Discord URLs contain the token. `raise_for_status()` isn't used. Network errors only show the exception type. |
| Tokens leaking into config errors | All tokens are `SecretStr`, and settings use `hide_input_in_errors`, so a bad value is never echoed back. |
| Tokens sent over plain HTTP | Mastodon and Bluesky base URLs must be `https://`. |
| Misconfigured or look-alike webhook URL | `DISCORD_WEBHOOK_URL` must match the official `discord.com/api/webhooks/<id>/<token>` format. |
| `@everyone` / `@here` mass pings on Discord | Every webhook call sends `allowed_mentions: {"parse": []}`, so no mention in a message can ping anyone. |
| Server-side request forgery | The service never requests the user's CTA link. It only calls fixed platform hosts that come from your config. |
| Secrets in the repo | `.env` is in `.gitignore`, and only `.env.example` with empty values is committed. |

Checked with `bandit -r app` (no issues) and `pip-audit -r requirements.txt` (no known vulnerabilities).

---

## Design decisions

- **Strategy pattern for platforms.** Every integration subclasses `Platform` and implements one method, `publish(message, link) -> PublishedPost`. The service doesn't know anything about specific platforms, and adding one doesn't change the service.
- **Concurrent but isolated.** `asyncio.gather` runs everything in parallel. Errors are caught *inside* each task, so a failure becomes a result and is never raised up to the caller.
- **Credentials are optional per platform.** Each platform lists its `required_settings`. Missing ones are reported with the exact env var name, so the app is usable with any subset of platforms.
- **Secrets stay secret.** Tokens are stored as `SecretStr`, so they never appear in logs or reprs. `httpx`'s `raise_for_status()` is deliberately not used because its message includes the request URL, which contains the token for Telegram and Discord. Network errors only expose the exception type.
- **`public_access` is what the platform reports**, not a guess. For example, an unlisted Mastodon toot or a private Telegram channel shows `false`.
- **UTC timestamps.** The server's local timezone has no effect on the output.
- **Shared HTTP client.** One `httpx.AsyncClient` for the whole app lifetime, opened and closed in FastAPI's `lifespan`.

### Limitations and possible next steps

- No retry or backoff yet. Mastodon's idempotency key makes retries safe there, and a small retry wrapper in `PostingService` would be the natural next step.
- The rate limiter lives in memory, so each process counts on its own. With several workers or instances it would need a shared store such as Redis. Behind a reverse proxy it would also need to read the real client IP from the proxy headers.
- X/Twitter, LinkedIn, Facebook and Reddit were left out on purpose: they need paid API tiers or app review before you can post, which doesn't fit a project that has to run locally. They would plug into the same `Platform` interface.

---

## Adding a new platform

1. Create `app/platforms/my_platform.py`:

   ```python
   from app.platforms.base import Platform, PublishedPost

   class MyPlatform(Platform):
       name = "My Platform"
       required_settings = ("my_platform_token",)

       async def publish(self, message: str, link: str) -> PublishedPost:
           response = await self.client.post(
               "https://api.example.com/posts",
               headers={"Authorization": f"Bearer {self.settings.my_platform_token.get_secret_value()}"},
               json={"text": message},
           )
           body = self.ensure_ok(response)
           return PublishedPost(url=body["url"], public=True)
   ```

2. Add `my_platform_token: SecretStr | None = None` to `Settings` in `app/config.py`.
3. Add the class to `PLATFORM_CLASSES` in `app/platforms/__init__.py`.
4. Add a respx-backed test in `tests/test_platforms.py`.
