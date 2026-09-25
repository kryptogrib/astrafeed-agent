from datetime import UTC, datetime, timedelta

import httpx
import pytest

from astrafeed.adapters.http.app import create_app
from astrafeed.adapters.repository.memory_agenda import InMemoryAgendaStore
from astrafeed.application.agenda_query import (
    agenda_payload,
    search_payload,
    story_payload,
)
from astrafeed.application.agenda_snapshot import publish_snapshot
from astrafeed.application.agenda_text import growth_text
from astrafeed.domain.agenda import (
    ClaimCard,
    CoverageInfo,
    PublicationRef,
    SearchDoc,
    Snapshot,
    StoryCard,
    StoryDetail,
)


def _snapshot(t: datetime) -> Snapshot:
    claim = ClaimCard(
        kind="event",
        speaker="author",
        quote="Отток ETH ETF составил 120 млн.",
        paraphrase_ru="Пишут об оттоке ETH ETF на 120 млн.",
        link="https://t.me/alpha/10",
        channel_ref="@alpha",
        published_at=t - timedelta(hours=2),
    )
    card = StoryCard(
        story_id="st-eth",
        title="Потоки ETH ETF",
        entities=("Ethereum",),
        current_channels=2,
        previous_channels=0,
        growth=2,
        growth_null_reason=None,
        first_seen=t - timedelta(hours=20),
        freshness=t - timedelta(hours=2),
        explanation="Пишут об оттоке ETH ETF на 120 млн.",
        claims=(claim,),
    )
    return Snapshot(
        snapshot_id="snap-demo",
        t=t,
        collected_at=t,
        analyzed_at=t,
        published_at=t,
        coverage=CoverageInfo(2, 0, 0, 3, 3, 0, 0, 2),
        queue_depth=0,
        limitations=(),
        agenda=(card,),
        agenda_mode="full",
        stories={
            "st-eth": StoryDetail(
                card=card,
                publications=(
                    PublicationRef(
                        "1:10",
                        "@alpha",
                        "https://t.me/alpha/10",
                        t - timedelta(hours=2),
                        "Отток ETH ETF составил 120 млн.",
                    ),
                ),
            )
        },
        search_docs=(
            SearchDoc("st-eth", "title", "Потоки ETH ETF"),
            SearchDoc("st-eth", "entity", "Ethereum"),
            SearchDoc("st-eth", "alias", "ETH"),
            SearchDoc("st-eth", "claim", "Отток ETH ETF составил 120 млн."),
        ),
    )


async def _get(app, url: str):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(url)


@pytest.mark.asyncio
async def test_agenda_search_story_share_one_snapshot():
    store = InMemoryAgendaStore()
    t = datetime(2026, 9, 24, 12, tzinfo=UTC)
    await publish_snapshot(store, _snapshot(t))

    async def agenda(snapshot_id=None, format="json"):
        return await agenda_payload(store, snapshot_id=snapshot_id, now=t)

    async def search(q, snapshot_id=None, limit=10, offset=0):
        return await search_payload(
            store, q, snapshot_id=snapshot_id, now=t, limit=limit, offset=offset
        )

    async def story(story_id, snapshot_id=None):
        return await story_payload(store, story_id, snapshot_id=snapshot_id, now=t)

    app = create_app(agenda=agenda, stories_search=search, story=story)
    r = await _get(app, "/agenda")
    assert r.status_code == 200
    body = r.json()
    assert body["snapshot_id"] == "snap-demo"
    assert body["stories"][0]["title"] == "Потоки ETH ETF"
    assert body["stories"][0]["claims"][0]["link"] == "https://t.me/alpha/10"

    md = await _get(app, "/agenda?format=md")
    assert md.headers["content-type"].startswith("text/markdown")
    assert "Потоки ETH ETF" in md.text
    assert "**2 sources** · ↑ +2 in 24h" in md.text
    assert "Covered by: [@alpha](https://t.me/alpha/10)" in md.text
    # Without a translation the original quote is shown as is.
    assert "> “Отток ETH ETF составил 120 млн.” — [@alpha](https://t.me/alpha/10)" in md.text

    page = await _get(app, "/agenda?format=html")
    assert page.headers["content-type"].startswith("text/html")
    assert "AstraFeed" in page.text
    assert 'rel="icon" href="/favicon.ico"' in page.text
    assert "POST /a2mcp/astrafeed" in page.text
    assert '<a href="/stories/st-eth?format=html&amp;snapshot_id=snap-demo">' in page.text
    assert '<a href="https://t.me/alpha/10">@alpha</a>' in page.text

    story_page = await _get(app, "/stories/st-eth?format=html")
    assert "<h1>Потоки ETH ETF</h1>" in story_page.text
    assert "Posts" in story_page.text
    story_md = await _get(app, "/stories/st-eth?format=md")
    assert "## Posts" in story_md.text

    found = await _get(app, "/stories/search?q=Потоки%20ETH%20ETF")
    assert found.json()["hits"][0]["story_id"] == "st-eth"
    eth = await _get(app, "/stories/search?q=ETH")
    assert eth.json()["hits"][0]["story_id"] == "st-eth"

    card = await _get(app, "/stories/st-eth")
    assert card.json()["story"]["publications"][0]["link"] == "https://t.me/alpha/10"
    assert card.json()["snapshot_id"] == "snap-demo"

    assert (await _get(app, "/stories/missing")).status_code == 404
    assert (await _get(app, "/agenda?snapshot_id=nope")).status_code == 404


@pytest.mark.asyncio
async def test_preparing_is_503_and_old_apis_remain():
    async def missing_agenda(snapshot_id=None):
        from astrafeed.application.agenda_query import AgendaPreparing

        raise AgendaPreparing("preparing")

    app = create_app(
        agenda=missing_agenda,
        pulse=lambda topic, window=None: {"brief_markdown": "old", "topic": topic},
    )
    r = await _get(app, "/agenda")
    assert r.status_code == 503
    assert r.json()["status"] == "preparing"
    assert (await _get(app, "/pulse?topic=zec")).status_code == 200


def test_agenda_page_escapes_text_and_drops_unsafe_links():
    from astrafeed.application.agenda_html import render_agenda_html

    payload = {
        "snapshot_id": "snap",
        "t": "2026-09-25T12:00:00+00:00",
        "stale": True,
        "limitations": ["processing_in_progress"],
        "coverage": {
            "channels_ok": 3,
            "channels_failed": 0,
            "publications_total": 10,
            "publications_processed": 8,
        },
        "stories": [
            {
                "story_id": "s1",
                "title": "<script>x</script>",
                "entities": ["HYPE"],
                "current_channels": 1,
                "growth": None,
                "first_seen": "2026-09-25T09:14:00+00:00",
                "explanation": "a & b",
                "claims": [{"quote": "</blockquote>", "channel": "@c", "link": "javascript:1"}],
            }
        ],
    }

    page = render_agenda_html(payload)

    assert "<script>x" not in page and "&lt;script&gt;x" in page
    assert "a &amp; b" in page and "&lt;/blockquote&gt;" in page
    assert "javascript:" not in page
    assert "snapshot is stale; processing is still running" in page
    assert "growth n/a" in page and "story tracked since Sep 25, 09:14 UTC" in page


def test_story_history_and_first_linked_source_have_distinct_labels():
    from astrafeed.application.agenda_markdown import render_agenda_md

    card = {
        "story_id": "bitget",
        "title": "Bitget report",
        "entities": ["Bitget"],
        "current_channels": 2,
        "growth": 2,
        "first_seen": "2026-09-24T20:04:00+00:00",
        "explanation": "Reported in two channels",
        "claims": [],
        "signals": {
            "confirmation": "rumor",
            "attributed_to": [],
            "spread_minutes": 10,
            "sources": [
                {
                    "channel": "@a",
                    "link": "https://t.me/a/1",
                    "published_at": "2026-09-24T20:14:00+00:00",
                    "minutes_after_first": 0,
                    "echo_of": None,
                },
                {
                    "channel": "@b",
                    "link": "https://t.me/b/2",
                    "published_at": "2026-09-24T20:24:00+00:00",
                    "minutes_after_first": 10,
                    "echo_of": None,
                },
            ],
            "independent_channels": 2,
            "echo_channels": 0,
            "figures_conflict": False,
            "figures": [],
            "price": None,
        },
    }
    payload = {
        "snapshot_id": "snap",
        "t": "2026-09-24T20:30:00+00:00",
        "stale": False,
        "limitations": [],
        "coverage": {
            "channels_ok": 2,
            "channels_failed": 0,
            "publications_total": 2,
            "publications_processed": 2,
        },
        "stories": [card],
    }

    md = render_agenda_md(payload)

    assert "story tracked since Sep 24, 20:04 UTC" in md
    assert "First linked source: @a at 20:14 UTC" in md


def test_discussion_is_rendered_in_markdown_and_html_and_escaped():
    from astrafeed.application.agenda_html import render_agenda_html, render_story_html
    from astrafeed.application.agenda_markdown import render_agenda_md, render_story_md

    card = {
        "story_id": "s1",
        "title": "Bitget",
        "entities": [],
        "current_channels": 3,
        "growth": 1,
        "first_seen": "2026-09-25T09:14:00+00:00",
        "explanation": "e",
        "claims": [],
        "discussion": {
            "comment_count": 214,
            "read_count": 80,
            "points": [],
            "highlights": ["A reader says <b>withdrawals</b> are stuck", "Second fact"],
            "quotes": [
                {
                    "text": "вывел всё вчера",
                    "translation": "withdrew everything yesterday",
                    "link": "https://t.me/a/1?comment=5",
                    "channel": "@a",
                },
                {"text": "второй", "link": "javascript:alert(1)", "channel": "@b"},
            ],
        },
    }
    payload = {
        "snapshot_id": "snap",
        "t": "2026-09-25T12:00:00+00:00",
        "stale": False,
        "limitations": [],
        "coverage": {
            "channels_ok": 3,
            "channels_failed": 0,
            "publications_total": 1,
            "publications_processed": 1,
        },
        "stories": [card],
    }

    md = render_agenda_md(payload)
    assert "💬 **From reader comments** (214 comments, unverified):" in md
    assert (
        "- A reader says <b>withdrawals</b> are stuck — [comments under @a post](https://t.me/a/1?comment=5)"
    ) in md
    # The agenda keeps facts short; the comment text is on the story page.
    assert "withdrew everything yesterday" not in md and "вывел" not in md

    page = render_agenda_html(payload)
    assert "A reader says &lt;b&gt;withdrawals&lt;/b&gt; are stuck" in page
    assert "javascript:" not in page and "(214 comments, unverified)" in page

    story = render_story_md({**payload, "story": card})
    assert "  > “withdrew everything yesterday”" in story and "вывел" not in story
    story_page = render_story_html({**payload, "story": card})
    assert "<summary>original</summary>вывел всё вчера" in story_page

    silent = {**card, "discussion": {**card["discussion"], "highlights": [], "quotes": []}}
    assert "reader comments" not in render_agenda_md({**payload, "stories": [silent]})


def test_agenda_markdown_ends_with_a_measured_trust_line():
    from astrafeed.application.agenda_markdown import render_agenda_md

    payload = {
        "snapshot_id": "snap",
        "t": "2026-09-25T12:00:00+00:00",
        "collected_at": "2026-09-25T11:57:18+00:00",
        "published_at": "2026-09-25T12:00:00+00:00",
        "stale": False,
        "limitations": [],
        "coverage": {
            "channels_ok": 37,
            "channels_failed": 0,
            "publications_total": 2518,
            "publications_processed": 2481,
        },
        "stories": [
            {
                "story_id": "s1",
                "title": "Payy",
                "entities": [],
                "current_channels": 2,
                "growth": 2,
                "first_seen": "2026-09-25T09:14:00+00:00",
                "explanation": "e",
                "claims": [
                    {"quote": "$1.83m", "channel": "@c", "link": "https://t.me/c/1"},
                ],
            }
        ],
    }
    md = render_agenda_md(payload)
    assert "1 displayed quote passed the span check" in md
    assert "162s collect→publish" in md
    assert "37 sources, 2481/2518 posts" in md


def test_growth_text_explains_incomplete_channel():
    assert (
        growth_text({"growth": 5, "current_channels": 6, "previous_channels": 0})
        == "↑ +5 in 24h on comparable sources (6 observed)"
    )
    assert growth_text({"growth": 2, "current_channels": 2, "previous_channels": 0}) == (
        "↑ +2 in 24h"
    )


def test_html_groups_source_links_and_labels_snapshot_coverage():
    from astrafeed.application.agenda_html import render_agenda_html

    card = {
        "story_id": "mixed",
        "title": "Mixed-source story",
        "entities": [],
        "current_channels": 3,
        "previous_channels": 0,
        "growth": 3,
        "first_seen": "2026-09-25T10:00:00+00:00",
        "explanation": "Covered by several sources",
        "claims": [],
        "signals": {
            "sources": [
                {
                    "channel": "@alpha",
                    "link": "https://t.me/alpha/1",
                    "minutes_after_first": 0,
                    "echo_of": None,
                },
                {
                    "channel": "r/Bitcoin",
                    "link": "https://www.reddit.com/r/Bitcoin/comments/abc",
                    "minutes_after_first": 4,
                    "echo_of": None,
                },
                {
                    "channel": "protos.com",
                    "link": "https://protos.com/news/abc",
                    "minutes_after_first": 8,
                    "echo_of": None,
                },
            ],
            "spread_minutes": None,
            "confirmation": "rumor",
            "attributed_to": [],
            "figures_conflict": False,
            "figures": [],
            "echo_channels": 0,
            "price": None,
        },
    }
    payload = {
        "snapshot_id": "snap-old",
        "t": "2026-09-25T12:00:00+00:00",
        "published_at": "2026-09-25T12:02:00+00:00",
        "stale": True,
        "limitations": [],
        "coverage": {
            "channels_ok": 37,
            "channels_failed": 0,
            "publications_total": 2530,
            "publications_processed": 2493,
        },
        "stories": [card],
    }

    page = render_agenda_html(payload)

    assert "Coverage in this snapshot: 37 sources, 2493 of 2530 posts analyzed" in page
    assert "Last published snapshot: Sep 25, 12:02 UTC" in page
    assert "Newer collection is not included in these counts" in page
    assert "<span>Telegram</span>" in page
    assert "<span>Reddit</span>" in page
    assert "<span>News sites</span>" in page
    assert '<a href="https://t.me/alpha/1">@alpha</a>' in page
    assert '<a href="https://www.reddit.com/r/Bitcoin/comments/abc">r/Bitcoin</a>' in page
    assert '<a href="https://protos.com/news/abc">protos.com</a>' in page
