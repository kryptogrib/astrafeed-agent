"""Attach reader comments to published agenda cards.

Comments are context for an analyst, not evidence: they never change channel
counts, growth or ranking. Every failure degrades to a card without discussion.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from astrafeed.domain.agenda import (
    CommentQuote,
    Discussion,
    PublicationRef,
    Snapshot,
    StoryCard,
)
from astrafeed.domain.models import Item
from astrafeed.ports.agenda import CommentReader, DiscussionSummarizer

_log = logging.getLogger(__name__)

MIN_COMMENT_CHARS = 15
MAX_FACTS = 3


@dataclass(frozen=True)
class _Cached:
    at: datetime
    comment_count: int
    discussion: Discussion | None


class DiscussionEnricher:
    def __init__(
        self,
        reader: CommentReader,
        summarizer: DiscussionSummarizer,
        *,
        summarize_top: int = 5,
        threads_per_story: int = 3,
        comments_per_thread: int = 40,
        max_comments: int = 80,
        ttl: timedelta = timedelta(minutes=30),
        timeout_seconds: float = 180,
    ) -> None:
        self._reader = reader
        self._summarizer = summarizer
        self._summarize_top = summarize_top
        self._threads_per_story = threads_per_story
        self._comments_per_thread = comments_per_thread
        self._max_comments = max_comments
        self._ttl = ttl
        self._timeout = timeout_seconds
        self._cache: dict[str, _Cached] = {}

    async def enrich(self, snapshot: Snapshot, now: datetime) -> Snapshot:
        try:
            async with asyncio.timeout(self._timeout):
                discussions = await self._discussions(snapshot, now)
        except Exception as exc:
            _log.warning("agenda discussion skipped: %s", type(exc).__name__)
            return snapshot
        return _with_discussions(snapshot, discussions)

    async def _discussions(self, snapshot: Snapshot, now: datetime) -> dict[str, Discussion]:
        pubs = {
            card.story_id: snapshot.stories[card.story_id].publications
            for card in snapshot.agenda
            if card.story_id in snapshot.stories
        }
        counts = await self._reply_counts([pub for refs in pubs.values() for pub in refs])
        result: dict[str, Discussion] = {}
        for rank, card in enumerate(snapshot.agenda):
            refs = pubs.get(card.story_id, ())
            total = sum(counts.get(pub.publication_id, 0) for pub in refs)
            if total == 0:
                continue
            cached = self._cache.get(card.story_id)
            if cached and now - cached.at < self._ttl and cached.comment_count == total:
                if cached.discussion is not None:
                    result[card.story_id] = cached.discussion
                continue
            discussion = Discussion(comment_count=total, read_count=0)
            if rank < self._summarize_top:
                try:
                    discussion = await self._summarize(card, refs, counts, total)
                except Exception as exc:
                    _log.warning(
                        "agenda discussion story=%s failed: %s", card.story_id, type(exc).__name__
                    )
            self._cache[card.story_id] = _Cached(now, total, discussion)
            result[card.story_id] = discussion
        return result

    async def _reply_counts(self, refs: list[PublicationRef]) -> dict[str, int]:
        by_channel: dict[str, dict[str, str]] = defaultdict(dict)
        for pub in refs:
            by_channel[pub.channel_ref][_external_id(pub)] = pub.publication_id
        counts: dict[str, int] = {}
        for channel, ids in by_channel.items():
            try:
                replies = await self._reader.reply_counts(channel, list(ids))
            except Exception as exc:
                _log.info("agenda reply counts %s failed: %s", channel, type(exc).__name__)
                continue
            for external_id, count in replies.items():
                if external_id in ids:
                    counts[ids[external_id]] = count
        return counts

    async def _summarize(
        self,
        card: StoryCard,
        refs: tuple[PublicationRef, ...],
        counts: dict[str, int],
        total: int,
    ) -> Discussion:
        threads = sorted(
            (pub for pub in refs if counts.get(pub.publication_id, 0) > 0),
            key=lambda pub: counts[pub.publication_id],
            reverse=True,
        )[: self._threads_per_story]
        comments: list[CommentQuote] = []
        seen: set[str] = set()
        for pub in threads:
            item = Item(
                channel_ref=pub.channel_ref,
                external_id=_external_id(pub),
                text="",
                link=pub.link,
                timestamp=pub.published_at,
            )
            for comment in await self._reader.fetch_comments(item, limit=self._comments_per_thread):
                text = " ".join(comment.text.split())
                if len(text) < MIN_COMMENT_CHARS or text.casefold() in seen:
                    continue
                seen.add(text.casefold())
                comments.append(CommentQuote(text[:500], comment.link or pub.link, pub.channel_ref))
        comments = comments[: self._max_comments]
        if not comments:
            return Discussion(comment_count=total, read_count=0)
        # The model sees what the posts say, so it keeps only what comments add.
        posts = [claim.quote for claim in card.claims]
        digest = await self._summarizer.summarize(card.title, posts, [c.text for c in comments])
        # Each fact keeps the comment that states it; a fact without a valid
        # source comment is dropped rather than shown unsourced.
        facts: list[tuple[str, CommentQuote]] = []
        for text, index in zip(digest.highlights, digest.quote_indices, strict=False):
            if text.strip() and 0 <= index < len(comments):
                facts.append((text.strip(), comments[index]))
        facts = facts[:MAX_FACTS]
        return Discussion(
            comment_count=total,
            read_count=len(comments),
            quotes=tuple(quote for _, quote in facts),
            highlights=tuple(text for text, _ in facts),
        )


def _external_id(pub: PublicationRef) -> str:
    return pub.publication_id.rpartition(":")[2]


def _with_discussions(snapshot: Snapshot, discussions: dict[str, Discussion]) -> Snapshot:
    if not discussions:
        return snapshot

    def attach(card: StoryCard) -> StoryCard:
        discussion = discussions.get(card.story_id)
        return card if discussion is None else replace(card, discussion=discussion)

    return replace(
        snapshot,
        agenda=tuple(attach(card) for card in snapshot.agenda),
        stories={
            story_id: replace(detail, card=attach(detail.card))
            for story_id, detail in snapshot.stories.items()
        },
    )
