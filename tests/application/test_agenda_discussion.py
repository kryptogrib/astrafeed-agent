from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from astrafeed.adapters.repository.sqlite.agenda import dumps, loads
from astrafeed.application.agenda_discussion import DiscussionEnricher
from astrafeed.domain.agenda import (
    CoverageInfo,
    DiscussionDigest,
    PublicationRef,
    Snapshot,
    StoryCard,
    StoryDetail,
)
from astrafeed.domain.models import DiscussionComment

T = datetime(2026, 9, 25, 12, tzinfo=UTC)


def _card(story_id: str) -> StoryCard:
    return StoryCard(
        story_id=story_id,
        title=f"Сюжет {story_id}",
        entities=(),
        current_channels=2,
        previous_channels=0,
        growth=2,
        growth_null_reason=None,
        first_seen=T,
        freshness=T,
        explanation="",
        claims=(),
    )


def _snapshot(*story_ids: str) -> Snapshot:
    cards = tuple(_card(sid) for sid in story_ids)
    return Snapshot(
        snapshot_id="snap",
        t=T,
        collected_at=T,
        analyzed_at=T,
        published_at=T,
        coverage=CoverageInfo(2, 0, 0, 2, 2, 0, 0, 2),
        queue_depth=0,
        limitations=(),
        agenda=cards,
        agenda_mode="full",
        stories={
            card.story_id: StoryDetail(
                card=card,
                publications=(
                    PublicationRef(
                        f"1:{card.story_id}1", "@a", f"https://t.me/a/{card.story_id}1", T
                    ),
                    PublicationRef(
                        f"2:{card.story_id}2", "@b", f"https://t.me/b/{card.story_id}2", T
                    ),
                ),
            )
            for card in cards
        },
    )


class Reader:
    def __init__(self, counts: dict[str, dict[str, int]], comments: list[str]) -> None:
        self.counts = counts
        self.comments = comments
        self.fetched: list[str] = []

    async def reply_counts(self, channel_ref, post_ids):
        return {pid: n for pid, n in self.counts.get(channel_ref, {}).items() if pid in post_ids}

    async def fetch_comments(self, item, *, limit):
        self.fetched.append(f"{item.channel_ref}/{item.external_id}")
        return [
            DiscussionComment(external_id=str(i), text=text, timestamp=T, link=f"{item.link}?c={i}")
            for i, text in enumerate(self.comments[:limit])
        ]


class Summarizer:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def summarize(self, title, posts, comments):
        self.calls.append(list(comments))
        self.posts = list(posts)
        # Facts pair with comment indices; blank or out-of-range ones are dropped.
        return DiscussionDigest(
            points=(),
            quote_indices=(0, 1, 99, 3, 4, 5),
            highlights=(" ", "A reader reports withdrawals stuck", "x", "c", "d", "e"),
        )


COMMENTS = [f"комментарий номер {i} про биржу" for i in range(6)] + [
    "ok",
    "комментарий НОМЕР 0 про биржу",
]


@pytest.mark.asyncio
async def test_discussion_is_attached_to_cards_and_details_without_touching_counts():
    reader = Reader({"@a": {"s1": 12}, "@b": {"s2": 30}}, COMMENTS)
    summarizer = Summarizer()

    snapshot = await DiscussionEnricher(reader, summarizer).enrich(_snapshot("s"), T)

    card = snapshot.agenda[0]
    assert card.current_channels == 2 and card.growth == 2
    discussion = card.discussion
    assert discussion is not None
    assert discussion.comment_count == 42
    # Short and case-duplicate comments are dropped before the model sees them.
    assert summarizer.calls[0] == COMMENTS[:6]
    assert discussion.read_count == 6
    assert discussion.points == ()
    # At most three facts, each with the comment that states it.
    assert discussion.highlights == ("A reader reports withdrawals stuck", "c", "d")
    assert [q.text for q in discussion.quotes] == [COMMENTS[1], COMMENTS[3], COMMENTS[4]]
    assert discussion.quotes[0].link == "https://t.me/b/s2?c=1"
    # Busiest thread is read first.
    assert reader.fetched[0] == "@b/s2"
    assert snapshot.stories["s"].card.discussion == discussion
    assert loads(dumps(snapshot)) == snapshot


@pytest.mark.asyncio
async def test_only_top_stories_are_summarized_and_quiet_threads_are_skipped():
    reader = Reader({"@a": {"s11": 5, "t1": 7}}, COMMENTS)
    summarizer = Summarizer()

    snapshot = await DiscussionEnricher(reader, summarizer, summarize_top=1).enrich(
        _snapshot("s1", "t", "q"), T
    )

    top, second, quiet = snapshot.agenda
    assert top.discussion is not None and top.discussion.highlights
    assert second.discussion is not None
    assert second.discussion.comment_count == 7 and second.discussion.points == ()
    assert quiet.discussion is None
    assert len(summarizer.calls) == 1


@pytest.mark.asyncio
async def test_cached_until_ttl_or_count_change():
    reader = Reader({"@a": {"s1": 12}}, COMMENTS)
    summarizer = Summarizer()
    enricher = DiscussionEnricher(reader, summarizer, ttl=timedelta(minutes=30))

    await enricher.enrich(_snapshot("s"), T)
    await enricher.enrich(_snapshot("s"), T + timedelta(minutes=5))
    assert len(summarizer.calls) == 1

    reader.counts["@a"]["s1"] = 20
    again = await enricher.enrich(_snapshot("s"), T + timedelta(minutes=6))
    assert len(summarizer.calls) == 2
    assert again.agenda[0].discussion.comment_count == 20


@pytest.mark.asyncio
async def test_failures_degrade_to_counts_or_plain_snapshot():
    class BrokenSummarizer:
        async def summarize(self, title, posts, comments):
            raise RuntimeError("model down")

    reader = Reader({"@a": {"s1": 12}}, COMMENTS)
    snapshot = await DiscussionEnricher(reader, BrokenSummarizer()).enrich(_snapshot("s"), T)
    assert snapshot.agenda[0].discussion.comment_count == 12
    assert snapshot.agenda[0].discussion.points == ()

    class BrokenReader(Reader):
        async def reply_counts(self, channel_ref, post_ids):
            raise ConnectionError

    plain = _snapshot("s")
    enriched = await DiscussionEnricher(BrokenReader({}, []), Summarizer()).enrich(plain, T)
    assert enriched == plain


@pytest.mark.asyncio
async def test_even_few_comments_are_checked_for_facts_and_opinions_are_not_shown():
    reader = Reader({"@a": {"s1": 3}}, COMMENTS[:3])

    class NoFacts:
        async def summarize(self, title, posts, comments):
            return DiscussionDigest(points=())

    snapshot = await DiscussionEnricher(reader, NoFacts()).enrich(_snapshot("s"), T)

    discussion = snapshot.agenda[0].discussion
    assert discussion.read_count == 3
    # No facts means no quotes either: comments are not shown just for being there.
    assert discussion.highlights == () and discussion.quotes == ()
    assert replace(snapshot.agenda[0], discussion=None) == _snapshot("s").agenda[0]
