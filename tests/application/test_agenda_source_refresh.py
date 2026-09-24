from types import SimpleNamespace

import pytest

from astrafeed.cli import _refresh_displayed_posts


@pytest.mark.asyncio
async def test_refresh_displayed_posts_rereads_only_visible_publications():
    visible = SimpleNamespace(
        story_id="visible",
    )
    snapshot = SimpleNamespace(
        agenda=(visible,),
        stories={
            "visible": SimpleNamespace(
                publications=(
                    SimpleNamespace(publication_id="2:10"),
                    SimpleNamespace(publication_id="2:11"),
                    SimpleNamespace(publication_id="3:20"),
                )
            ),
            "hidden": SimpleNamespace(
                publications=(SimpleNamespace(publication_id="4:30"),)
            ),
        },
    )

    class Store:
        def __init__(self):
            self.saved = []

        async def get_source(self, source_id):
            return SimpleNamespace(telegram_id=source_id + 100)

        async def store_items(self, source_id, items):
            self.saved.append((source_id, items))

    class Reader:
        def __init__(self):
            self.calls = []

        async def read_posts(self, telegram_id, ids):
            self.calls.append((telegram_id, tuple(ids)))
            return [SimpleNamespace(external_id=value) for value in ids]

    store, reader = Store(), Reader()
    count = await _refresh_displayed_posts(snapshot, store, reader)
    assert count == 3
    assert sorted(reader.calls) == [(102, (10, 11)), (103, (20,))]
    assert {source_id for source_id, _ in store.saved} == {2, 3}
