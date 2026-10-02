"""Asterisk keypresses reach the call's pipeline from the other process."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from pipecat.audio.dtmf.types import KeypadEntry
from pipecat.frames.frames import InputDTMFFrame

from api.services.telephony.providers.ari.dtmf_bridge import (
    digit_to_frame,
    dtmf_channel,
    publish_digit,
    run_dtmf_bridge,
)


def test_each_key_becomes_a_keypad_frame():
    for key in ("0", "5", "9", "*", "#"):
        frame = digit_to_frame(key)
        assert isinstance(frame, InputDTMFFrame) and frame.button == KeypadEntry(key)
    assert digit_to_frame(b"7").button == KeypadEntry("7")


def test_anything_that_is_not_a_key_is_dropped():
    for junk in ("", "x", "12", None, b"\xff"):
        assert digit_to_frame(junk) is None


def test_each_run_has_its_own_channel():
    assert dtmf_channel(5) != dtmf_channel(6)


@pytest.mark.asyncio
async def test_publishing_goes_to_the_runs_channel_and_never_raises():
    redis = AsyncMock()
    await publish_digit(redis, 7, "3")
    redis.publish.assert_awaited_once_with(dtmf_channel(7), "3")

    redis.publish.side_effect = ConnectionError("redis down")
    await publish_digit(redis, 7, "3")  # must not raise


class _PubSub:
    def __init__(self, messages):
        self._messages = messages
        self.subscribed = []
        self.unsubscribed = []
        self.closed = False

    async def subscribe(self, channel):
        self.subscribed.append(channel)

    async def listen(self):
        for m in self._messages:
            yield m
        await asyncio.sleep(3600)  # then wait, like a real subscription

    async def unsubscribe(self, channel):
        self.unsubscribed.append(channel)

    async def aclose(self):
        self.closed = True


class _Redis:
    def __init__(self, pubsub):
        self._pubsub = pubsub

    def pubsub(self):
        return self._pubsub


async def _run(messages, queue):
    pubsub = _PubSub(messages)
    task = asyncio.create_task(run_dtmf_bridge(_Redis(pubsub), 9, queue))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    return pubsub


@pytest.mark.asyncio
async def test_digits_for_this_run_are_queued_in_order():
    queued = []

    async def queue(frame):
        queued.append(frame.button.value)

    msgs = [
        {"type": "subscribe", "data": 1},
        {"type": "message", "data": "1"},
        {"type": "message", "data": "#"},
    ]
    pubsub = await _run(msgs, queue)

    assert queued == ["1", "#"]
    assert pubsub.subscribed == [dtmf_channel(9)]


@pytest.mark.asyncio
async def test_junk_and_a_failing_queue_do_not_stop_the_bridge():
    calls = []

    async def queue(frame):
        calls.append(frame.button.value)
        if len(calls) == 1:
            raise RuntimeError("pipeline busy")

    msgs = [{"type": "message", "data": "zz"}, {"type": "message", "data": "1"}, {"type": "message", "data": "2"}]
    await _run(msgs, queue)

    assert calls == ["1", "2"]  # the first failed, the second still arrived


@pytest.mark.asyncio
async def test_the_subscription_is_released_when_the_call_ends():
    pubsub = await _run([], AsyncMock())
    assert pubsub.unsubscribed == [dtmf_channel(9)] and pubsub.closed
