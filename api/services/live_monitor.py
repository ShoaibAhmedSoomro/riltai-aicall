"""Reading live calls: which are running, and a socket to watch one.

Everything here reads Redis and never the local event bus. The call's pipeline may be
on another replica, so there is exactly one code path whether or not it happens to be
on this one. See services/pipecat/run_event_bus.py for what is written.
"""

from __future__ import annotations

import asyncio
import base64
import json
import struct
import time
from typing import Awaitable, Callable, Optional

from loguru import logger

from api.db import db_client
from api.services.call_concurrency.rate_limiter import rate_limiter
from api.services.pipecat.run_event_bus import (
    audio_key,
    events_key,
    get_redis,
    listen_key,
    meta_key,
)

BACKFILL_COUNT = 200
READ_BLOCK_MS = 1000
LISTEN_REFRESH_SECONDS = 5.0
LISTEN_FLAG_TTL_SECONDS = 15
STATE_POLL_SECONDS = 5.0
# A call with no slot record still counts as live if its stream moved this recently.
STREAM_FRESH_SECONDS = 300

NODE_TRANSITION = "rtf-node-transition"


def _stream_age_seconds(entry_id: str) -> float:
    """Redis stream ids start with the millisecond time they were written."""
    return max(0.0, time.time() - int(entry_id.split("-")[0]) / 1000.0)


def _parse(entries) -> list[dict]:
    out = []
    for _id, fields in entries:
        try:
            out.append(json.loads(fields["d"]))
        except (KeyError, ValueError, TypeError):
            continue
    return out


async def _last_entry(r, run_id: int):
    rows = await r.xrevrange(events_key(run_id), count=1)
    return rows[0] if rows else None


async def current_node(run_id: int, redis=None) -> Optional[str]:
    """The agent step the call is in, from the newest node transition on its stream."""
    r = redis or get_redis()
    for _id, fields in await r.xrevrange(events_key(run_id), count=100):
        try:
            event = json.loads(fields["d"])
        except (KeyError, ValueError, TypeError):
            continue
        if event.get("type") == NODE_TRANSITION:
            payload = event.get("payload") or {}
            return payload.get("node_name") or event.get("node_name")
    return None


async def _is_really_live(run_id: int, redis) -> bool:
    """A row says 'running' even after its pipeline died without saying otherwise."""
    if await rate_limiter.get_workflow_slot_mapping(run_id) is not None:
        return True
    last = await _last_entry(redis, run_id)
    return bool(last) and _stream_age_seconds(last[0]) < STREAM_FRESH_SECONDS


def _number(run: dict) -> Optional[str]:
    ctx = run.get("initial_context") or {}
    inbound = run.get("call_type") == "inbound"
    keys = ("caller_number", "phone_number") if inbound else ("called_number", "phone_number")
    return next((ctx[k] for k in keys if ctx.get(k)), None)


async def live_calls(organization_id: int, redis=None) -> list[dict]:
    r = redis or get_redis()
    calls = []
    for run in await db_client.get_live_workflow_runs(organization_id):
        try:
            if not await _is_really_live(run["id"], r):
                continue
            node = await current_node(run["id"], r)
        except Exception as e:
            # Redis trouble should show fewer details, not an empty page.
            logger.warning(f"live monitor: could not inspect run {run['id']}: {e}")
            node = None
        calls.append(
            {
                "run_id": run["id"],
                "workflow_id": run["workflow_id"],
                "workflow_name": run["workflow_name"],
                "mode": run["mode"],
                "call_type": run["call_type"],
                "number": _number(run),
                "started_at": run["created_at"],
                "current_node": node,
            }
        )
    return calls


def audio_header(direction: str, sample_rate: int) -> bytes:
    """1 byte direction (0 caller, 1 agent) + 4 bytes sample rate, then raw PCM16."""
    return struct.pack("!BI", 0 if direction == "user" else 1, sample_rate)


class _ClientState:
    def __init__(self):
        self.listening = False
        self.closed = False


async def _read_client(ws, state: _ClientState, can_listen: bool) -> None:
    """The only thing a monitor says to us is whether it wants to listen."""
    try:
        while True:
            msg = await ws.receive_json()
            if isinstance(msg, dict) and msg.get("type") == "listen":
                state.listening = bool(msg.get("on")) and can_listen
    except Exception:
        state.closed = True


async def monitor_run(
    ws,
    run_id: int,
    *,
    can_listen: bool,
    still_running: Callable[[], Awaitable[bool]],
    redis=None,
) -> None:
    """Backfill what was already said, then follow the call until it ends."""
    r = redis or get_redis()
    key = events_key(run_id)

    meta = None
    try:
        raw = await r.get(meta_key(run_id))
        meta = json.loads(raw) if raw else None
    except Exception:
        pass

    backfill_rows = list(reversed(await r.xrevrange(key, count=BACKFILL_COUNT)))
    await ws.send_json(
        {
            "type": "monitor-backfill",
            "events": _parse(backfill_rows),
            "meta": meta,
            "can_listen": can_listen,
        }
    )
    last_id = backfill_rows[-1][0] if backfill_rows else "0-0"
    audio_last: Optional[str] = None

    state = _ClientState()
    reader = asyncio.create_task(_read_client(ws, state, can_listen))
    last_refresh = 0.0
    last_state_check = time.monotonic()
    try:
        while not state.closed:
            now = time.monotonic()
            streams = {key: last_id}
            if state.listening:
                if audio_last is None:
                    # Tail only. Replaying the stream's old chunks would play a burst
                    # of stale audio the moment listening starts.
                    tail = await r.xrevrange(audio_key(run_id), count=1)
                    audio_last = tail[0][0] if tail else "0-0"
                streams[audio_key(run_id)] = audio_last
                if now - last_refresh >= LISTEN_REFRESH_SECONDS:
                    await r.set(listen_key(run_id), "1", ex=LISTEN_FLAG_TTL_SECONDS)
                    last_refresh = now
            else:
                audio_last = None

            for stream, entries in await r.xread(streams, block=READ_BLOCK_MS, count=100):
                if stream == key:
                    for event in _parse(entries):
                        await ws.send_json(event)
                    last_id = entries[-1][0]
                else:
                    for _id, f in entries:
                        pcm = f.get("pcm")
                        if pcm:
                            await ws.send_bytes(
                                audio_header(f.get("dir", "bot"), int(f.get("sr", 16000)))
                                + base64.b64decode(pcm)
                            )
                    audio_last = entries[-1][0]

            if time.monotonic() - last_state_check >= STATE_POLL_SECONDS:
                last_state_check = time.monotonic()
                if not await still_running():
                    await ws.send_json({"type": "monitor-ended"})
                    await ws.close(code=1000)
                    return
    except Exception as e:
        # The monitor leaving (or its socket breaking) is not an error.
        logger.debug(f"monitor of run {run_id} ended: {e}")
    finally:
        reader.cancel()
