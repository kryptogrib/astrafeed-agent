import asyncio
import logging
from types import SimpleNamespace

import pytest
from telethon.errors import AuthKeyDuplicatedError

import astrafeed.cli as cli
from astrafeed.cli import _ensure_connected, _finalize_poll_task, _source_failure_status


@pytest.mark.asyncio
async def test_finalize_poll_task_logs_prior_crash(caplog):
    async def boom():
        raise RuntimeError("boom")

    poll_task = asyncio.create_task(boom(), name="agenda-cycle")
    await asyncio.sleep(0)
    caplog.set_level(logging.ERROR)
    await _finalize_poll_task(poll_task)
    assert "boom" in caplog.text
    assert "agenda poll task exited unexpectedly" in caplog.text


@pytest.mark.asyncio
async def test_finalize_poll_task_does_not_log_cancel(caplog):
    async def hang():
        await asyncio.Event().wait()

    poll_task = asyncio.create_task(hang(), name="agenda-cycle")
    await asyncio.sleep(0)
    caplog.set_level(logging.ERROR)
    await _finalize_poll_task(poll_task)
    assert "exited unexpectedly" not in caplog.text


@pytest.mark.asyncio
async def test_telegram_auth_key_revocation_is_not_retried_forever():
    class Client:
        def __init__(self):
            self.calls = 0

        def is_connected(self):
            return False

        async def connect(self):
            self.calls += 1
            raise AuthKeyDuplicatedError(None)

    client = Client()
    with pytest.raises(AuthKeyDuplicatedError):
        await _ensure_connected(client)
    assert client.calls == 1
    assert _source_failure_status(AuthKeyDuplicatedError(None)) == "auth_key_revoked"


@pytest.mark.asyncio
async def test_supervisor_logs_poll_iteration_failure_and_starts_again(monkeypatch, caplog):
    calls = 0

    async def broken_poll(*args):
        nonlocal calls
        calls += 1
        raise RuntimeError("poll state failed")

    async def stop_after_failure(_delay):
        raise asyncio.CancelledError

    monkeypatch.setattr(cli, "_agenda_poll", broken_poll)
    monkeypatch.setattr(cli.asyncio, "sleep", stop_after_failure)
    caplog.set_level(logging.ERROR)
    with pytest.raises(asyncio.CancelledError):
        await cli._supervised_agenda_poll(SimpleNamespace(poll_seconds=5), *([None] * 9))
    assert calls == 1
    assert "agenda poll iteration failed" in caplog.text
    assert "poll state failed" in caplog.text
