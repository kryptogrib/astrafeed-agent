from dataclasses import replace
from datetime import UTC, datetime

import pytest

from astrafeed.adapters.repository.sqlite.agenda import dumps, loads
from astrafeed.application.agenda_localize import EnglishLocalizer
from astrafeed.domain.agenda import (
    ClaimCard,
    CommentQuote,
    CoverageInfo,
    Discussion,
    PositionCard,
    Snapshot,
    StoryCard,
    StoryDetail,
)

T = datetime(2026, 9, 25, 12, tzinfo=UTC)
QUOTE = "Отток ETH ETF составил 120 млн."


def _snapshot() -> Snapshot:
    claim = ClaimCard("event", "author", QUOTE, "", "https://t.me/a/1", "@a", T)
    english = ClaimCard("event", "author", "ETH ETF outflow", "", "https://t.me/b/1", "@b", T)
    card = StoryCard(
        story_id="s",
        title="Потоки ETH ETF",
        entities=("Ethereum",),
        current_channels=2,
        previous_channels=0,
        growth=2,
        growth_null_reason=None,
        first_seen=T,
        freshness=T,
        explanation=QUOTE,
        claims=(claim, english),
        discussion=Discussion(
            5,
            5,
            ("Readers doubt it",),
            (CommentQuote("вывел всё вчера", "https://t.me/a/1", "@a"),),
        ),
    )
    hidden = replace(card, story_id="h", title="Скрытый сюжет")
    return Snapshot(
        snapshot_id="snap",
        t=T,
        collected_at=T,
        analyzed_at=T,
        published_at=T,
        coverage=CoverageInfo(2, 0, 0, 2, 2, 0, 0, 2),
        queue_depth=0,
        limitations=(),
        agenda=(card,),
        agenda_mode="full",
        stories={
            "s": StoryDetail(
                card=card,
                positions=(
                    PositionCard("author", "@a", "Я думаю, это дно", "", "https://t.me/a/2"),
                ),
            ),
            "h": StoryDetail(card=hidden),
        },
    )


class Translator:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[list[str]] = []
        self.fail = fail

    async def to_english(self, texts):
        self.calls.append(list(texts))
        if self.fail:
            raise RuntimeError("model down")
        table = {
            "Потоки ETH ETF": "ETH ETF flows",
            QUOTE: "ETH ETF outflow was 120M.",
            "вывел всё вчера": "withdrew everything yesterday",
            "Я думаю, это дно": "Я думаю",  # still Russian: rejected
        }
        return [table.get(text, "") for text in texts]


@pytest.mark.asyncio
async def test_shown_stories_are_translated_and_originals_kept():
    translator = Translator()
    snapshot = await EnglishLocalizer(translator).localize(_snapshot())

    card = snapshot.agenda[0]
    assert card.title == "ETH ETF flows"
    assert card.explanation == "ETH ETF outflow was 120M."
    assert card.claims[0].quote == QUOTE
    assert card.claims[0].translation == "ETH ETF outflow was 120M."
    # English text is neither sent nor given a translation.
    assert card.claims[1].translation == ""
    assert card.discussion.quotes[0].translation == "withdrew everything yesterday"
    assert snapshot.stories["s"].card == card
    # A reply that is still Russian is not accepted as a translation.
    assert snapshot.stories["s"].positions[0].translation == ""
    # Stories off the agenda are not translated.
    assert snapshot.stories["h"].card.title == "Скрытый сюжет"
    sent = [text for call in translator.calls for text in call]
    assert "ETH ETF outflow" not in sent and "Скрытый сюжет" not in sent
    assert sent.count(QUOTE) == 1
    assert loads(dumps(snapshot)) == snapshot


@pytest.mark.asyncio
async def test_translations_are_cached_and_failures_keep_originals():
    translator = Translator()
    localizer = EnglishLocalizer(translator)
    await localizer.localize(_snapshot())
    await localizer.localize(_snapshot())
    # Only the rejected Russian reply is asked again.
    assert translator.calls[1] == ["Я думаю, это дно"]

    broken = await EnglishLocalizer(Translator(fail=True)).localize(_snapshot())
    assert broken.agenda[0].title == "Потоки ETH ETF"
    assert broken.agenda[0].claims[0].translation == ""
