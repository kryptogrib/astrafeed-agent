import asyncio
import logging

import pytest

from astrafeed.cli import _finalize_poll_task


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
