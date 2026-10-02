"""The per-run event bus: fan-out to the caller's browser and supervisors, and the
Redis stream that makes a call visible from any replica."""

import json

import pytest

from api.services.governance.monitor import allows_listen_in, monitor_view_for
from api.services.governance.policy import GovernancePolicy
from api.services.pipecat import run_event_bus as bus_mod
from api.services.pipecat.run_event_bus import (
    RunEventBus,
    events_key,
    get_or_create_bus,
    release_bus,
    unsubscribe,
)
from api.schemas.workflow_configurations import GuardrailConfigurationDefaults
from api.tests._fake_monitor_redis import FakeRedis


def _policy(**over):
    base = dict(
        storage_mode="everything",
        retention_days=None,
        record_audio=True,
        store_transcript=True,
        redaction_categories=(),
        redact_gathered_context=False,
        guardrails=GuardrailConfigurationDefaults(),
    )
    base.update(over)
    return GovernancePolicy(**base)


def _recorder():
    got = []

    async def send(event):
        got.append(event)

    return send, got


@pytest.mark.asyncio
async def test_two_subscribers_each_receive_one_publish():
    bus = RunEventBus(1, redis=FakeRedis())
    a, got_a = _recorder()
    b, got_b = _recorder()
    bus.subscribe(a)
    bus.subscribe(b)

    await bus.publish({"type": "rtf-bot-text", "payload": {"text": "hi"}})

    assert len(got_a) == len(got_b) == 1


@pytest.mark.asyncio
async def test_unsubscribing_one_leaves_the_other_live():
    bus = RunEventBus(1, redis=FakeRedis())
    a, got_a = _recorder()
    b, got_b = _recorder()
    token_a = bus.subscribe(a)
    bus.subscribe(b)

    bus.unsubscribe(token_a)
    await bus.publish({"type": "x"})

    assert got_a == [] and len(got_b) == 1


@pytest.mark.asyncio
async def test_a_subscriber_added_after_the_handle_was_taken_is_seen():
    """The reason the bus is a stable handle: the pipeline captured it earlier."""
    bus_mod._buses.clear()
    captured = get_or_create_bus(7)  # what run_pipeline holds
    captured._redis = FakeRedis()
    late, got = _recorder()
    get_or_create_bus(7).subscribe(late)  # a participant attaching mid-call

    await captured.publish({"type": "x"})

    assert len(got) == 1
    release_bus(7)


@pytest.mark.asyncio
async def test_a_failing_subscriber_does_not_starve_the_rest_or_the_stream():
    r = FakeRedis()
    bus = RunEventBus(1, redis=r)

    async def boom(event):
        raise RuntimeError("socket closed")

    ok, got = _recorder()
    bus.subscribe(boom)
    bus.subscribe(ok)

    await bus.publish({"type": "x"})

    assert len(got) == 1
    assert len(r.xadd_calls) == 1


@pytest.mark.asyncio
async def test_every_event_is_appended_once_to_the_capped_stream():
    r = FakeRedis()
    bus = RunEventBus(5, redis=r)

    await bus.publish({"type": "rtf-bot-text", "payload": {"text": "a"}})
    await bus.publish({"type": "rtf-bot-text", "payload": {"text": "b"}})

    assert [c[0] for c in r.xadd_calls] == [events_key(5)] * 2
    assert r.xadd_calls[0][2]["maxlen"] == bus_mod.EVENTS_MAXLEN
    assert r.ttls[events_key(5)] == bus_mod.EVENTS_TTL_SECONDS
    assert json.loads(r.xadd_calls[0][1]["d"])["payload"]["text"] == "a"


@pytest.mark.asyncio
async def test_a_redis_outage_never_breaks_the_call():
    class Down:
        def pipeline(self, transaction=False):
            raise ConnectionError("redis down")

    bus = RunEventBus(1, redis=Down())
    send, got = _recorder()
    bus.subscribe(send)

    await bus.publish({"type": "x"})  # must not raise

    assert len(got) == 1


def test_unsubscribe_on_a_released_run_is_a_no_op():
    bus_mod._buses.clear()
    unsubscribe(999, 1)  # no bus for this run; must not create or raise
    assert 999 not in bus_mod._buses


# -- the governed copy that leaves the call ----------------------------------------


def _speech(text, final=True):
    return {"type": "rtf-user-transcription", "payload": {"text": text, "final": final}}


@pytest.mark.asyncio
async def test_interim_transcripts_stay_off_the_stream_but_reach_the_caller():
    r = FakeRedis()
    bus = RunEventBus(1, redis=r)
    bus.set_monitor_filter(monitor_view_for(_policy()))
    send, got = _recorder()
    bus.subscribe(send)

    await bus.publish(_speech("hel", final=False))
    await bus.publish(_speech("hello", final=True))

    assert len(got) == 2  # the caller's own browser sees both
    assert len(r.xadd_calls) == 1  # the monitor stream only the final


@pytest.mark.asyncio
async def test_a_basic_only_call_publishes_no_words_to_the_monitor():
    r = FakeRedis()
    bus = RunEventBus(1, redis=r)
    bus.set_monitor_filter(monitor_view_for(_policy(storage_mode="basic_only", store_transcript=False, record_audio=False)))

    await bus.publish(_speech("my card is 4111 1111 1111 1111"))
    await bus.publish({"type": "rtf-node-transition", "payload": {"node_name": "Greeting"}})

    kept = [json.loads(c[1]["d"])["type"] for c in r.xadd_calls]
    assert kept == ["rtf-node-transition"]  # what happened, not what was said


@pytest.mark.asyncio
async def test_redaction_applies_to_the_monitor_copy():
    r = FakeRedis()
    bus = RunEventBus(1, redis=r)
    bus.set_monitor_filter(monitor_view_for(_policy(redaction_categories=("email",))))

    await bus.publish(_speech("write to jo@example.com"))

    text = json.loads(r.xadd_calls[0][1]["d"])["payload"]["text"]
    assert "jo@example.com" not in text


def test_listen_in_is_off_when_the_policy_withholds_or_redacts():
    assert allows_listen_in(_policy()) is True
    assert allows_listen_in(_policy(record_audio=False)) is False
    assert allows_listen_in(_policy(redaction_categories=("phone",))) is False
    assert allows_listen_in(None) is True
