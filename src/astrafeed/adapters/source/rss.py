"""Read RSS/Atom article metadata as source-backed publications."""

from __future__ import annotations

import hashlib
import html
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import httpx
from defusedxml import ElementTree as ET

from astrafeed.domain.models import Item

MAX_FEED_BYTES = 2_000_000
REDDIT_USER_AGENT = (
    "Mozilla/5.0 (compatible; AstraFeed/0.1; +https://github.com/kryptogrib/astrafeed-agent)"
)
_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")


def _plain(value: str) -> str:
    return _SPACES.sub(" ", html.unescape(_TAGS.sub(" ", value))).strip()


def _date(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _child(element: ET.Element, *names: str) -> str:
    for name in names:
        child = element.find(name)
        if child is not None:
            return "".join(child.itertext()).strip()
    return ""


def parse_feed(body: bytes, url: str) -> list[Item]:
    root = ET.fromstring(body)
    atom = root.tag == "{http://www.w3.org/2005/Atom}feed"
    if atom:
        entries = root.findall("{http://www.w3.org/2005/Atom}entry")
        name = _child(root, "{http://www.w3.org/2005/Atom}title")
    elif root.tag.lower() == "rss" or root.tag.lower().endswith("}rss"):
        channel = root.find("channel")
        if channel is None:
            raise ValueError("RSS channel missing")
        entries = channel.findall("item")
        name = _child(channel, "title")
    else:
        raise ValueError("Unsupported feed format")
    hostname = (urlparse(url).hostname or url).removeprefix("www.")
    source_name = name or hostname
    items: list[Item] = []
    for entry in entries:
        if atom:
            ns = "{http://www.w3.org/2005/Atom}"
            link = next(
                (
                    node.get("href", "")
                    for node in entry.findall(ns + "link")
                    if node.get("rel", "alternate") == "alternate"
                ),
                "",
            )
            guid = _child(entry, ns + "id")
            summary = _child(entry, ns + "summary", ns + "content")
            published = _child(entry, ns + "published", ns + "updated")
            title = _child(entry, ns + "title")
        else:
            link = _child(entry, "link")
            guid = _child(entry, "guid")
            summary = _child(
                entry, "description", "{http://purl.org/rss/1.0/modules/content/}encoded"
            )
            published = _child(entry, "pubDate", "{http://purl.org/dc/elements/1.1/}date")
            title = _child(entry, "title")
        timestamp = _date(published) if published else None
        if timestamp is None or urlparse(link).scheme not in {"http", "https"}:
            continue
        text = _plain(title + ". " + summary)[:4000]
        if not text:
            continue
        identity = guid or link
        items.append(
            Item(
                channel_ref=hostname,
                external_id=hashlib.sha256(identity.encode()).hexdigest()[:32],
                text=text,
                link=link,
                timestamp=timestamp,
                channel_name=source_name,
            )
        )
    return sorted(items, key=lambda item: item.timestamp)


class RssReader:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def read(self, url: str) -> list[Item]:
        if urlparse(url).scheme != "https":
            raise ValueError("RSS feed URL must use HTTPS")
        headers = (
            {"User-Agent": REDDIT_USER_AGENT}
            if urlparse(url).hostname in {"reddit.com", "www.reddit.com"}
            else None
        )
        async with self._client.stream("GET", url, headers=headers) as response:
            response.raise_for_status()
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_FEED_BYTES:
                    raise ValueError("RSS feed exceeds size limit")
                chunks.append(chunk)
        return parse_feed(b"".join(chunks), url)
