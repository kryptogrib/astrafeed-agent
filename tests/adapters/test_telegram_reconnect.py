import asyncio

import pytest

from astrafeed.adapters.source.telegram import TelegramSource


class Client:
    def __init__(self):
        self.connected = True
        self.connect_calls = 0

    def is_connected(self):
        return self.connected

    async def connect(self):
        self.connect_calls += 1
        self.connected = True


@pytest.mark.asyncio
async def test_single_disconnect_reconnects_and_retries_once():
    client = Client()
    source = TelegramSource(client)
    calls = 0

    async def operation():
        nonlocal calls
        calls += 1
        if calls == 1:
            client.connected = False
            raise ConnectionError("dropped")
        return "ok"

    assert await source._with_reconnect(operation) == "ok"
    assert calls == 2
    assert client.connect_calls == 1


@pytest.mark.asyncio
async def test_second_disconnect_propagates_after_one_retry():
    client = Client()
    source = TelegramSource(client)
    calls = 0

    async def operation():
        nonlocal calls
        calls += 1
        client.connected = False
        raise ConnectionError("still disconnected")

    with pytest.raises(ConnectionError, match="still disconnected"):
        await source._with_reconnect(operation)
    assert calls == 2
    assert client.connect_calls == 1


@pytest.mark.asyncio
async def test_concurrent_callers_share_single_reconnect():
    client = Client()
    client.connected = False
    source = TelegramSource(client)
    gate = asyncio.Event()
    original_connect = client.connect

    async def slow_connect():
        await gate.wait()
        await original_connect()

    client.connect = slow_connect
    one = asyncio.create_task(source._ensure_connected())
    two = asyncio.create_task(source._ensure_connected())
    await asyncio.sleep(0)
    gate.set()
    await asyncio.gather(one, two)
    assert client.connect_calls == 1
