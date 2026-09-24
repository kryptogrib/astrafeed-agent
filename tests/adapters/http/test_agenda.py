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
    assert "**2 канала** · ↑ +2 за сутки" in md.text
    assert "Пишут: [@alpha](https://t.me/alpha/10)" in md.text
    assert "> «Отток ETH ETF составил 120 млн.» — [@alpha](https://t.me/alpha/10)" in md.text

    page = await _get(app, "/agenda?format=html")
    assert page.headers["content-type"].startswith("text/html")
    assert '<a href="/stories/st-eth?format=html&amp;snapshot_id=snap-demo">' in page.text
    assert '<a href="https://t.me/alpha/10">@alpha</a>' in page.text

    story_page = await _get(app, "/stories/st-eth?format=html")
    assert "<h1>Потоки ETH ETF</h1>" in story_page.text
    assert "Посты" in story_page.text
    story_md = await _get(app, "/stories/st-eth?format=md")
    assert "## Посты" in story_md.text

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
    from astrafeed.application.agenda_query import render_agenda_html

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
    assert "снимок устарел; обработка ещё идёт" in page
    assert "рост н/д" in page and "впервые 25.09 09:14 UTC" in page


def test_discussion_is_rendered_in_markdown_and_html_and_escaped():
    from astrafeed.application.agenda_query import render_agenda_html, render_agenda_md

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
            "points": ["Многие <b>не верят</b> во взлом"],
            "quotes": [
                {"text": "вывел всё вчера", "link": "https://t.me/a/1?comment=5", "channel": "@a"},
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
    assert "💬 **В комментариях** (214):" in md
    assert "- Многие <b>не верят</b> во взлом" in md
    assert "> «вывел всё вчера» — [комментарий в @a](https://t.me/a/1?comment=5)" in md
    # The agenda card shows one comment; the story page shows them all.
    assert "второй" not in md

    page = render_agenda_html(payload)
    assert "Многие &lt;b&gt;не верят&lt;/b&gt; во взлом" in page
    assert "(214)" in page and "вывел всё вчера" in page
