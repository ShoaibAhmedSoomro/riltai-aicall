"""The live-calls list and the monitor socket."""

import asyncio
import base64
import json
import struct
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.routes import live_monitor as routes
from api.services import live_monitor as svc
from api.services.pipecat.run_event_bus import audio_key, events_key, listen_key, meta_key
from api.tests._fake_monitor_redis import FakeRedis


def _event(kind, **payload):
    return {"type": kind, "payload": payload}


async def _add(r, run_id, event):
    await r.xadd(events_key(run_id), {"d": json.dumps(event)})


def _fresh_id():
    return f"{int(time.time() * 1000)}-0"


# -- /live-calls ---------------------------------------------------------------------


def _run(run_id, **over):
    base = dict(
        id=run_id, workflow_id=1, workflow_name="Sales", mode="twilio", call_type="outbound",
        created_at=datetime.now(UTC), initial_context={"called_number": "+971501234567"},
    )
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_lists_calls_with_their_current_step_and_hides_crashed_ones():
    r = FakeRedis()
    await _add(r, 1, _event("rtf-node-transition", node_name="Greeting"))
    await _add(r, 1, _event("rtf-node-transition", node_name="Qualify"))
    await _add(r, 1, _event("rtf-bot-text", text="hello"))

    async def slot(run_id):
        return (9, "slot", None) if run_id == 1 else None

    with (
        patch.object(svc, "db_client") as db,
        patch.object(svc.rate_limiter, "get_workflow_slot_mapping", new=slot),
    ):
        db.get_live_workflow_runs = AsyncMock(return_value=[_run(1), _run(2)])  # 2: pipeline died
        out = await svc.live_calls(9, redis=r)

    assert [c["run_id"] for c in out] == [1]
    assert out[0]["current_node"] == "Qualify"  # the newest transition, not the newest event
    assert out[0]["number"] == "+971501234567"


@pytest.mark.asyncio
async def test_a_call_without_a_slot_record_counts_if_its_stream_is_moving():
    r = FakeRedis()
    r.streams[events_key(3)] = [(_fresh_id(), {"d": json.dumps(_event("rtf-bot-text"))})]
    r.streams[events_key(4)] = [("1-0", {"d": json.dumps(_event("rtf-bot-text"))})]  # written in 1970

    with (
        patch.object(svc, "db_client") as db,
        patch.object(svc.rate_limiter, "get_workflow_slot_mapping", new=AsyncMock(return_value=None)),
    ):
        db.get_live_workflow_runs = AsyncMock(return_value=[_run(3), _run(4)])
        out = await svc.live_calls(9, redis=r)

    assert [c["run_id"] for c in out] == [3]


def test_inbound_shows_the_caller_and_outbound_shows_who_was_dialled():
    both = {"caller_number": "A", "called_number": "B"}
    assert svc._number(_run(1, call_type="inbound", initial_context=both)) == "A"
    assert svc._number(_run(1, call_type="outbound", initial_context=both)) == "B"
    assert svc._number(_run(1, initial_context={})) is None


# -- the socket ------------------------------------------------------------------------


class _WS:
    def __init__(self, client_msgs=()):
        self.sent: list = []
        self.closed_with = None
        self.accepted = False
        self._inbox: asyncio.Queue = asyncio.Queue()
        for m in client_msgs:
            self._inbox.put_nowait(m)

    async def send_json(self, data):
        self.sent.append(data)

    async def send_bytes(self, data):
        self.sent.append(data)

    async def receive_json(self):
        return await self._inbox.get()

    async def close(self, code=1000, reason=None):
        self.closed_with = code

    async def accept(self):
        self.accepted = True


def _types(ws):
    return [m["type"] if isinstance(m, dict) else "audio" for m in ws.sent]


def _audio(ws):
    return [m for m in ws.sent if not isinstance(m, dict)]


async def _drive(ws, r, *, can_listen=False, running=None, until=None, timeout=2.0):
    """Run monitor_run until `until()` holds (or the timeout), then let the run end."""
    state = {"running": True}

    async def still_running():
        return state["running"] if running is None else running()

    task = asyncio.create_task(
        svc.monitor_run(ws, 5, can_listen=can_listen, still_running=still_running, redis=r)
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not (until and until()):
        await asyncio.sleep(0.01)
    state["running"] = False
    try:
        await asyncio.wait_for(task, 1.5)
    except asyncio.TimeoutError:
        task.cancel()


@pytest.fixture(autouse=True)
def _fast_polls(monkeypatch):
    monkeypatch.setattr(svc, "STATE_POLL_SECONDS", 0.05)
    monkeypatch.setattr(svc, "LISTEN_REFRESH_SECONDS", 0.05)


@pytest.mark.asyncio
async def test_a_client_that_connects_late_gets_everything_said_so_far():
    r = FakeRedis()
    for i in range(3):
        await _add(r, 5, _event("rtf-bot-text", text=f"line {i}"))
    ws = _WS()

    await _drive(ws, r, until=lambda: len(ws.sent) >= 1)

    first = ws.sent[0]
    assert first["type"] == "monitor-backfill"
    assert [e["payload"]["text"] for e in first["events"]] == ["line 0", "line 1", "line 2"]


@pytest.mark.asyncio
async def test_later_events_arrive_in_order_without_repeating_the_backfill():
    r = FakeRedis()
    await _add(r, 5, _event("rtf-bot-text", text="before"))
    ws = _WS()
    driver = asyncio.create_task(_drive(ws, r, until=lambda: len(ws.sent) >= 4))
    await asyncio.sleep(0.05)
    for t in ("a", "b", "c"):
        await _add(r, 5, _event("rtf-bot-text", text=t))
    await driver

    live = [m["payload"]["text"] for m in ws.sent[1:] if isinstance(m, dict) and m["type"] == "rtf-bot-text"]
    assert live == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_the_socket_closes_normally_when_the_run_leaves_running():
    ws = _WS()

    await _drive(ws, FakeRedis(), running=lambda: False, until=lambda: ws.closed_with is not None)

    assert "monitor-ended" in _types(ws)
    assert ws.closed_with == 1000


@pytest.mark.asyncio
async def test_meta_tells_the_monitor_whether_listening_is_possible():
    r = FakeRedis()
    await r.set(meta_key(5), json.dumps({"listen_in": False}))
    ws = _WS()

    await _drive(ws, r, can_listen=True, until=lambda: len(ws.sent) >= 1)

    assert ws.sent[0]["meta"] == {"listen_in": False}
    assert ws.sent[0]["can_listen"] is True


def _chunk(direction, pcm=b"\x01\x02\x03\x04", sr=16000):
    return {"dir": direction, "sr": str(sr), "pcm": base64.b64encode(pcm).decode()}


@pytest.mark.asyncio
async def test_an_admin_who_turns_listening_on_gets_audio_and_keeps_the_flag_alive():
    r = FakeRedis()
    ws = _WS(client_msgs=[{"type": "listen", "on": True}])
    driver = asyncio.create_task(_drive(ws, r, can_listen=True, until=lambda: bool(_audio(ws))))
    await asyncio.sleep(0.15)  # listening is on and the tail position is fixed
    await r.xadd(audio_key(5), _chunk("bot"))
    await driver

    assert r.ttls[listen_key(5)] == svc.LISTEN_FLAG_TTL_SECONDS
    audio = _audio(ws)[0]
    assert struct.unpack("!BI", audio[:5]) == (1, 16000)
    assert audio[5:] == b"\x01\x02\x03\x04"


@pytest.mark.asyncio
async def test_listening_does_not_replay_old_chunks():
    r = FakeRedis()
    await r.xadd(audio_key(5), _chunk("bot", b"OLD!"))
    ws = _WS(client_msgs=[{"type": "listen", "on": True}])

    await _drive(ws, r, can_listen=True, timeout=0.4)

    assert _audio(ws) == []


@pytest.mark.asyncio
async def test_a_member_cannot_switch_listening_on():
    r = FakeRedis()
    ws = _WS(client_msgs=[{"type": "listen", "on": True}])

    await _drive(ws, r, can_listen=False, timeout=0.4)

    assert listen_key(5) not in r.values


# -- the route itself --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_run_from_another_organization_is_refused():
    ws = _WS()
    user = SimpleNamespace(id=1, selected_organization_id=2, is_superuser=False)
    with patch.object(routes, "db_client") as db:
        db.get_workflow_run = AsyncMock(return_value=None)  # not found *for this org*
        await routes.monitor_websocket(ws, 99, user)

    assert ws.closed_with == 1008 and not ws.accepted
    db.get_workflow_run.assert_awaited_once_with(99, organization_id=2)
