import pytest
from pydantic import ValidationError

from app.links import find_links, is_valid_url
from app.schemas import PostRequest
from tests.conftest import MESSAGE


class TestFindLinks:
    def test_finds_single_link(self):
        assert find_links(MESSAGE) == ["https://example.com"]

    def test_strips_trailing_punctuation(self):
        assert find_links("Visit https://example.com/page.") == ["https://example.com/page"]
        assert find_links("(see https://example.com)") == ["https://example.com"]

    def test_keeps_path_and_query(self):
        assert find_links("Go https://example.com/a/b?x=1&y=2#top now") == [
            "https://example.com/a/b?x=1&y=2#top"
        ]

    def test_detects_www_links_without_scheme(self):
        assert find_links("Visit www.example.com today") == ["www.example.com"]

    def test_finds_multiple_links(self):
        assert len(find_links("https://a.com and http://b.org")) == 2

    def test_no_links(self):
        assert find_links("Just a plain message") == []


class TestIsValidUrl:
    @pytest.mark.parametrize(
        "url",
        ["https://example.com", "http://example.com/path?q=1", "https://sub.domain.co.uk/x"],
    )
    def test_valid(self, url):
        assert is_valid_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "www.example.com",
            "ftp://example.com",
            "https://localhost",
            "https://example",
            "https://example.c",
            "https://exa_mple..com",
            "https://192.168.0.1",
            "https://",
        ],
    )
    def test_invalid(self, url):
        assert not is_valid_url(url)


class TestPostRequest:
    def test_accepts_valid_message(self):
        assert PostRequest(message=MESSAGE).message == MESSAGE

    def test_strips_surrounding_whitespace(self):
        assert PostRequest(message=f"  {MESSAGE}\n").message == MESSAGE

    def test_accepts_exactly_200_characters(self):
        link = " https://example.com"
        message = "a" * (200 - len(link)) + link
        assert len(PostRequest(message=message).message) == 200

    def test_rejects_201_characters(self):
        link = " https://example.com"
        message = "a" * (201 - len(link)) + link
        with pytest.raises(ValidationError, match="must not exceed 200 characters"):
            PostRequest(message=message)

    @pytest.mark.parametrize("message", ["", "   "])
    def test_rejects_empty(self, message):
        with pytest.raises(ValidationError, match="must not be empty"):
            PostRequest(message=message)

    def test_rejects_message_without_link(self):
        with pytest.raises(ValidationError, match=r"exactly one CTA link \(found 0\)"):
            PostRequest(message="No link here")

    def test_rejects_message_with_two_links(self):
        with pytest.raises(ValidationError, match=r"exactly one CTA link \(found 2\)"):
            PostRequest(message="Try https://a.com or https://b.com")

    def test_rejects_link_without_scheme(self):
        with pytest.raises(ValidationError, match="not a valid URL"):
            PostRequest(message="Visit www.example.com today")

    def test_rejects_invalid_host(self):
        with pytest.raises(ValidationError, match="not a valid URL"):
            PostRequest(message="Visit https://localhost:8000 today")

    def test_rejects_non_string(self):
        with pytest.raises(ValidationError):
            PostRequest(message=123)
