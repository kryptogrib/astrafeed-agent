from telethon.errors import FloodWaitError

from astrafeed.adapters.source.telegram import _Access, _classify_fetch
from astrafeed.domain import CommentStatus


def test_flood_wait_is_reported_as_retryable_incomplete_fetch():
    error = FloodWaitError(None, capture=15)
    status = _classify_fetch(access=_Access.READABLE, raw_count=0, error=error)
    assert status is CommentStatus.FLOOD_WAIT
