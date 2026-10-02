"""Listen-in audio is copied to Redis only while a supervisor is listening."""

import pytest

from api.services.pipecat import run_event_bus as bus_mod
from api.services.pipecat.realtime_feedback_observer import RealtimeFeedbackObserver
from api.services.pipecat.run_event_bus import RunEventBus, audio_key, listen_key
from api.tests._fake_monitor_redis import FakeRedis
from pipecat.frames.frames import InputAudioRawFrame, OutputAudioRawFrame
from pipecat.processors.frame_processor import FrameDirection


class _Data:
    def __init__(self, frame, direction=FrameDirection.DOWNSTREAM):
        self.frame = frame
        self.direction = direction
        self.source = None


def _observer(bus):
    async def noop(event):
        pass

    return RealtimeFeedbackObserver(ws_sender=noop, bus=bus)


def _in(n=0):
    return InputAudioRawFrame(audio=b"\x01\x02" * 160, sample_rate=16000, num_channels=1)


def _out(n=0):
    return OutputAudioRawFrame(audio=b"\x03\x04" * 160, sample_rate=16000, num_channels=1)


def _audio_adds(r):
    return [c for c in r.xadd_calls if c[0].startswith("monitor:audio:")]


@pytest.mark.asyncio
async def test_nothing_is_written_when_nobody_is_listening():
    r = FakeRedis()
    obs = _observer(RunEventBus(1, redis=r))

    for _ in range(20):
        await obs.on_push_frame(_Data(_in()))
        await obs.on_push_frame(_Data(_out()))

    assert _audio_adds(r) == []


@pytest.mark.asyncio
async def test_one_write_per_frame_while_a_supervisor_listens():
    r = FakeRedis()
    await r.set(listen_key(1), "1", ex=15)
    obs = _observer(RunEventBus(1, redis=r))

    await obs.on_push_frame(_Data(_in()))
    await obs.on_push_frame(_Data(_out()))

    adds = _audio_adds(r)
    assert len(adds) == 2
    assert {a[1]["dir"] for a in adds} == {"user", "bot"}
    assert all(a[0] == audio_key(1) and a[1]["sr"] == "16000" for a in adds)
    assert r.ttls[audio_key(1)] == bus_mod.AUDIO_TTL_SECONDS


@pytest.mark.asyncio
async def test_a_frame_seen_at_several_hops_is_sent_once():
    r = FakeRedis()
    await r.set(listen_key(1), "1", ex=15)
    obs = _observer(RunEventBus(1, redis=r))
    frame = _out()

    for _ in range(5):  # the same frame observed at five processors
        await obs.on_push_frame(_Data(frame))

    assert len(_audio_adds(r)) == 1


@pytest.mark.asyncio
async def test_a_policy_that_forbids_listening_wins_over_the_flag():
    r = FakeRedis()
    await r.set(listen_key(1), "1", ex=15)
    bus = RunEventBus(1, redis=r)
    bus.forbid_listening()
    obs = _observer(bus)

    await obs.on_push_frame(_Data(_in()))

    assert _audio_adds(r) == []


@pytest.mark.asyncio
async def test_audio_never_enters_the_frames_seen_set():
    obs = _observer(RunEventBus(1, redis=FakeRedis()))

    for _ in range(100):
        await obs.on_push_frame(_Data(_in()))

    assert obs._frames_seen == set()
