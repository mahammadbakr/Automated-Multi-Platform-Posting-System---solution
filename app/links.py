import re

from pydantic import HttpUrl, TypeAdapter, ValidationError

# Anything that looks like a link: an explicit http(s) scheme or a bare "www." prefix.
_LINK_PATTERN = re.compile(r"(?:https?://|www\.)[^\s<>\"']+", re.IGNORECASE)

# Punctuation that usually ends a sentence rather than belonging to the URL.
_TRAILING_PUNCTUATION = ".,;:!?)]}'\""

_http_url = TypeAdapter(HttpUrl)


def find_links(text: str) -> list[str]:
    return [match.group().rstrip(_TRAILING_PUNCTUATION) for match in _LINK_PATTERN.finditer(text)]


def is_valid_url(url: str) -> bool:
    if not url.lower().startswith(("http://", "https://")):
        return False

    try:
        parsed = _http_url.validate_python(url)
    except ValidationError:
        return False

    host = parsed.host or ""
    labels = host.split(".")
    # Require a public-looking domain such as example.com, not "localhost" or "foo".
    return len(labels) >= 2 and all(labels) and labels[-1].isalpha() and len(labels[-1]) >= 2
